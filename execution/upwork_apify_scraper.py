#!/usr/bin/env python3
"""
Upwork Job Scraper using Apify Actor

Uses the upwork-vibe~upwork-job-scraper actor (free tier).
Supports post-scrape filtering for budget, experience, verified payment, etc.

Usage:
    python execution/upwork_apify_scraper.py --limit 50 --days 1 --verified-payment -o .tmp/upwork_jobs.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Ensure execution directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reviewer_agent import review_on_failure
import requests
from dotenv import load_dotenv

# Load environment variables
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(WORKSPACE_ROOT / ".env")

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
ACTOR_ID = "upwork-vibe~upwork-job-scraper"
APIFY_BASE_URL = "https://api.apify.com/v2"

# Default AI/automation keywords
DEFAULT_KEYWORDS = [
    "AI automation",
    "Claude API",
    "n8n workflow",
    "Zapier automation",
    "Make automation",
    "workflow automation",
    "AI agent",
    "LLM integration",
    "GPT automation",
    "AI chatbot"
]


def run_actor(keywords: list[str], limit: int, from_date: str, to_date: str) -> str:
    """Start the Apify actor run and return the run ID."""
    url = f"{APIFY_BASE_URL}/acts/{ACTOR_ID}/runs"
    
    headers = {
        "Authorization": f"Bearer {APIFY_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # The current free actor schema only accepts broad scrape controls. Keyword
    # matching is applied locally after results are fetched.
    payload = {
        "limit": limit,
        "fromDate": from_date,
        "toDate": to_date
    }
    
    print(f"Starting Apify actor with broad scrape limit={limit}")
    print(f"Local keywords: {', '.join(keywords)}")
    print(f"Date range: {from_date} to {to_date}")
    
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    if response.status_code != 201:
        print(f"API Response ({response.status_code}): {response.text[:500]}")
    
    response.raise_for_status()
    
    run_data = response.json()["data"]
    run_id = run_data["id"]
    print(f"Actor run started: {run_id}")
    
    return run_id


def poll_run_status(run_id: str, timeout: int = 300, poll_interval: int = 3) -> bool:
    """Poll the actor run status until completion or timeout."""
    url = f"{APIFY_BASE_URL}/actor-runs/{run_id}"
    headers = {"Authorization": f"Bearer {APIFY_API_TOKEN}"}
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        status = response.json()["data"]["status"]
        print(f"Run status: {status}")
        
        if status == "SUCCEEDED":
            return True
        elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
            print(f"Actor run failed with status: {status}")
            return False
        
        time.sleep(poll_interval)
    
    print(f"Timeout waiting for actor run after {timeout}s")
    return False


def fetch_results(run_id: str) -> list[dict]:
    """Fetch the results from the completed actor run."""
    url = f"{APIFY_BASE_URL}/actor-runs/{run_id}/dataset/items"
    headers = {"Authorization": f"Bearer {APIFY_API_TOKEN}"}
    
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    
    return response.json()


def parse_money(val: int | float | str | None) -> float:
    """Parse money string (e.g. '$10k+', '$500') to float."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    s = str(val).lower().replace("$", "").replace(",", "").replace("+", "").strip()
    multiplier = 1.0
    
    if s.endswith("k"):
        multiplier = 1000.0
        s = s[:-1]
    elif s.endswith("m"):
        multiplier = 1000000.0
        s = s[:-1]
        
    try:
        return float(s) * multiplier
    except ValueError:
        return 0.0


def filter_jobs(
    jobs: list[dict],
    keywords: list[str] | None = None,
    verified_payment: bool = False,
    min_spent: int | None = None,
    experience_levels: list[str] | None = None,
    min_budget: int | None = None
) -> list[dict]:
    """Apply post-scrape filters to job results."""
    filtered = []
    
    if jobs:
        print(f"\nDEBUG: First Raw Job Keys: {list(jobs[0].keys())}")
        print(f"DEBUG: First Raw Job Client: {jobs[0].get('client', {})}")
        print(f"DEBUG: First Raw Job Budget: {jobs[0].get('budget', {})}\n")
    
    for job in jobs:
        # Keyword filter applied locally because the actor does not support
        # keyword input on the free schema.
        if keywords:
            skills = job.get("skills", [])
            if isinstance(skills, list):
                skills_text = " ".join(str(skill) for skill in skills)
            else:
                skills_text = str(skills)
            haystack = " ".join([
                str(job.get("title", "")),
                str(job.get("description", "")),
                skills_text,
                str(job.get("category", "")),
                str(job.get("subcategory", "")),
            ]).lower()
            if not any(keyword.lower() in haystack for keyword in keywords):
                continue

        # Verified payment filter
        if verified_payment:
            payment_verified = job.get("client", {}).get("paymentMethodVerified", False)
            if not payment_verified:
                continue
        
        # Minimum client spend filter
        if min_spent is not None:
            total_spent_raw = job.get("client", {}).get("stats", {}).get("totalSpent", 0)
            total_spent = parse_money(total_spent_raw)
            # print(f"DEBUG: id={job.get('uid')} raw_spent='{total_spent_raw}' parsed={total_spent} min_spent={min_spent}")
            
            if total_spent < min_spent:
                continue
        
        # Experience level filter
        if experience_levels:
            # Try top-level first, then vendor
            job_exp = job.get("experienceLevel") or job.get("vendor", {}).get("experienceLevel") or ""
            job_exp = job_exp.lower()
            if not any(exp.lower() in job_exp for exp in experience_levels):
                continue
        
        # Minimum budget filter
        if min_budget is not None:
            budget = job.get("budget", {})
            if isinstance(budget, dict):
                # Fixed price
                amount = budget.get("amount", 0)
            elif isinstance(budget, (int, float)):
                amount = budget
            else:
                # Try to parse string
                try:
                    amount = float(str(budget).replace("$", "").replace(",", ""))
                except (ValueError, TypeError):
                    amount = 0
            
            if amount < min_budget:
                continue
        
        filtered.append(job)
    
    return filtered


def normalize_job(job: dict) -> dict:
    """Normalize job data to a consistent format."""
    job_id = job.get("id") or job.get("jobId") or job.get("uid") or ""
    
    # Extract job ID from URL if not directly available
    if not job_id and job.get("url"):
        url = job.get("url", "")
        if "~" in url:
            job_id = url.split("~")[-1].split("/")[0].split("?")[0]
    
    client = job.get("client", {})
    
    # Parse budget
    budget_raw = job.get("budget", {})
    budget_str = "Negotiable" # Default
    if isinstance(budget_raw, dict):
        fixed = budget_raw.get("fixedBudget")
        hourly = budget_raw.get("hourlyRate", {})
        
        # Handle fixed budget (check explicit None, allow 0 if valid but usually implies negotiable)
        if fixed is not None and fixed > 0:
             budget_str = f"${fixed}"
        elif hourly and (hourly.get("min") or hourly.get("max")):
            mn = hourly.get("min") or 0
            mx = hourly.get("max") or ""
            budget_str = f"${mn}-${mx}/hr" if mx else f"${mn}+/hr"
        elif fixed == 0:
            budget_str = "Negotiable" # Explicit 0 often means not set

    else:
        budget_str = str(budget_raw)

    return {
        "id": job_id,
        "title": job.get("title", ""),
        "description": job.get("description", ""),
        "url": job.get("url") or f"https://www.upwork.com/jobs/~{job_id}",
        "apply_url": f"https://www.upwork.com/nx/proposals/job/~{job_id}/apply/",
        "budget": budget_str,
        "hourly_rate": job.get("hourlyRate"),
        "experience_level": job.get("experienceLevel") or job.get("vendor", {}).get("experienceLevel") or "",
        "skills": job.get("skills", []),
        "category": job.get("category", ""),
        "subcategory": job.get("subcategory", ""),
        "connects": job.get("connects", ""),
        "posted_on": job.get("createdAt", ""),
        "client": {
            "country": client.get("countryCode", ""),
            "total_spent": client.get("stats", {}).get("totalSpent", 0),
            "total_hires": client.get("stats", {}).get("totalHires", 0),
            "payment_verified": client.get("paymentMethodVerified", False),
            "rating": client.get("stats", {}).get("feedbackRate"),
            "reviews": client.get("stats", {}).get("feedbackCount", 0)
        }
    }


@review_on_failure
def main():
    parser = argparse.ArgumentParser(description="Scrape Upwork jobs using Apify")
    parser.add_argument("--limit", type=int, default=50, help="Maximum jobs to scrape")
    parser.add_argument("--scrape-limit", type=int, help="Raw actor scrape limit before local filtering")
    parser.add_argument("--days", type=int, default=1, help="Days back to search")
    parser.add_argument("--keywords", type=str, help="Comma-separated keywords (default: AI/automation)")
    parser.add_argument("--verified-payment", action="store_true", help="Only verified payment clients")
    parser.add_argument("--min-spent", type=int, help="Minimum client total spend")
    parser.add_argument("--experience", type=str, help="Experience levels: entry,intermediate,expert")
    parser.add_argument("--min-budget", type=int, help="Minimum job budget")
    parser.add_argument("-o", "--output", type=str, default=".tmp/upwork_jobs.json", help="Output file")
    
    args = parser.parse_args()
    
    if not APIFY_API_TOKEN:
        print("Error: APIFY_API_TOKEN not found in environment")
        sys.exit(1)
    
    # Prepare keywords
    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",")]
    else:
        keywords = DEFAULT_KEYWORDS
    
    # Prepare date range
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    
    # Run the actor
    try:
        actor_limit = args.scrape_limit or max(args.limit * 20, args.limit, 50)
        run_id = run_actor(keywords, actor_limit, from_date, to_date)
    except requests.RequestException as e:
        print(f"Error starting actor: {e}")
        sys.exit(1)
    
    # Poll for completion
    if not poll_run_status(run_id):
        print("Actor run did not complete successfully")
        sys.exit(1)
    
    # Fetch results
    try:
        jobs = fetch_results(run_id)
        print(f"Fetched {len(jobs)} jobs from Apify")
    except requests.RequestException as e:
        print(f"Error fetching results: {e}")
        sys.exit(1)
    
    # Apply filters
    experience_levels = None
    if args.experience:
        experience_levels = [e.strip() for e in args.experience.split(",")]
    
    filtered_jobs = filter_jobs(
        jobs,
        keywords=keywords,
        verified_payment=args.verified_payment,
        min_spent=args.min_spent,
        experience_levels=experience_levels,
        min_budget=args.min_budget
    )
    print(f"After filtering: {len(filtered_jobs)} jobs")
    
    # Normalize job data
    normalized_jobs = [normalize_job(job) for job in filtered_jobs[:args.limit]]
    
    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(normalized_jobs, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(normalized_jobs)} jobs to {output_path}")
    
    # Print summary
    if normalized_jobs:
        print("\nSample job titles:")
        for job in normalized_jobs[:5]:
            print(f"  - {job['title'][:60]}...")


if __name__ == "__main__":
    main()
