#!/usr/bin/env python3
"""
Upwork Proposal Generator

Generates personalized cover letters and proposals using NVIDIA NIM API,
creates Google Docs for each proposal, and outputs to Google Sheets.

Usage:
    python execution/upwork_proposal_generator.py --input .tmp/upwork_jobs.json --workers 1
"""

import argparse
import json
import os
import sys
import threading
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Allow relaxed token scope
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
# Ensure execution directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reviewer_agent import review_on_failure
import openai
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()

# Google API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents'
]

# NVIDIA NIM API Configuration
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
PROPOSAL_MODEL = os.getenv("NVIDIA_PROPOSAL_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")

# Thread-local storage for thread-safe Google API clients
thread_local = threading.local()

def get_thread_docs_service(creds):
    if not hasattr(thread_local, "docs_service"):
        thread_local.docs_service = build('docs', 'v1', credentials=creds, cache_discovery=False)
    return thread_local.docs_service

def get_thread_drive_service(creds):
    if not hasattr(thread_local, "drive_service"):
        thread_local.drive_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
    return thread_local.drive_service


def get_google_credentials():
    """Get or refresh Google OAuth credentials."""
    creds = None
    token_path = Path("token.json")
    credentials_path = Path("credentials.json")
    
    # 1. Load client secrets if they exist (needed for refreshing tokens)
    client_id = None
    client_secret = None
    if credentials_path.exists():
        try:
            with open(credentials_path, "r") as f:
                config = json.load(f)
                secret_data = config.get("installed") or config.get("web")
                if secret_data:
                    client_id = secret_data.get("client_id")
                    client_secret = secret_data.get("client_secret")
        except Exception as e:
            print(f"Warning: Could not parse client secrets from {credentials_path}: {e}")

    # 2. Try loading token.json
    if token_path.exists():
        try:
            with open(token_path, "r") as f:
                token_data = json.load(f)
            
            # Merge client_id/secret if found in credentials.json
            if client_id and ("client_id" not in token_data or not token_data["client_id"]):
                token_data["client_id"] = client_id
            if client_secret and ("client_secret" not in token_data or not token_data["client_secret"]):
                token_data["client_secret"] = client_secret
                
            granted_scopes = token_data.get("scopes") or SCOPES
            creds = Credentials.from_authorized_user_info(token_data, granted_scopes)
            print("Loaded session token successfully.")
        except Exception as e:
            print(f"Warning: Could not load token.json: {e}")

    # 3. Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            print("Token refreshed.")
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            print(f"Failed to refresh token: {e}")
            creds = None

    # 4. Final fallback: OAuth flow
    if not creds or not creds.valid:
        if not credentials_path.exists():
            print("Error: credentials.json not found. Please set up Google OAuth.")
            sys.exit(1)
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            print("Opening browser for authentication. Please verify the account you choose.")
            creds = flow.run_local_server(port=0, prompt='select_account')
            
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            print("New token generated via OAuth flow.")
        except Exception as e:
            print(f"Error during OAuth flow: {e}")
            sys.exit(1)
    
    return creds


def create_google_doc(title: str, content: str, creds) -> str | None:
    """Create a Google Doc with retry logic. Returns the Doc URL or None on failure."""
    max_retries = 4
    backoff_times = [1.5, 3, 6, 12]
    
    for attempt in range(max_retries):
        try:
            docs_service = get_thread_docs_service(creds)
            drive_service = get_thread_drive_service(creds)
            
            # Create the document
            doc = docs_service.documents().create(body={"title": title}).execute()
            doc_id = doc["documentId"]
            
            # Insert content
            requests_body = [{
                "insertText": {
                    "location": {"index": 1},
                    "text": content
                }
            }]
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests_body}
            ).execute()
            
            # Make it viewable by anyone with link (read-only for security)
            drive_service.permissions().create(
                fileId=doc_id,
                body={"type": "anyone", "role": "reader"}
            ).execute()
            
            return f"https://docs.google.com/document/d/{doc_id}/edit"
        
        except Exception as e:
            err_str = str(e)
            if "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in err_str or "insufficient" in err_str.lower():
                print(f"Doc creation skipped (insufficient scope): {e}")
                return None
            if attempt < max_retries - 1:
                wait_time = backoff_times[attempt]
                print(f"Doc creation failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                print(f"Doc creation failed after {max_retries} attempts: {e}")
                return None
    
    return None


def generate_proposal(job: dict, client: openai.OpenAI) -> dict:
    """Generate cover letter and proposal for a job using the configured NIM model with retries."""
    job_title = job.get("title", "Unknown")
    job_description = job.get("description", "")
    
    skills_raw = job.get("skills", [])
    if isinstance(skills_raw, list):
        skills = ", ".join(str(s) for s in skills_raw)
    elif isinstance(skills_raw, str):
        skills = skills_raw
    else:
        skills = ""
    
    def call_llm(prompt):
        max_retries = 5
        backoff_times = [5, 10, 20, 40, 60]
        
        for attempt in range(max_retries):
            try:
                extra_body = {}
                if "thinking" in PROPOSAL_MODEL:
                    extra_body["include_reasoning"] = True
                
                response = client.chat.completions.create(
                    model=PROPOSAL_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    extra_body=extra_body
                )
                return response.choices[0].message.content
            except Exception as e:
                err_str = str(e).lower()
                is_transient = "429" in err_str or "500" in err_str or "502" in err_str or "503" in err_str or "504" in err_str or "timeout" in err_str
                if is_transient and attempt < max_retries - 1:
                    wait_time = backoff_times[attempt]
                    print(f"LLM API transient error, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    raise e
        return None

    # Generate proposal
    proposal_prompt = f"""You are helping write an Upwork proposal for a qualified candidate.

JOB TITLE: {job_title}

JOB DESCRIPTION:
{job_description}

REQUIRED SKILLS: {skills}

Write a proposal following this EXACT format (~300 words, first-person, conversational):

---
Hey [use client name if mentioned, otherwise just "Hey"].

I spent ~15 minutes putting this together for you. In short, it's how I would create your [2-4 word paraphrase of their need] end to end.

I've worked with various teams and have a lot of experience designing/building similar solutions.

Here's a step-by-step, along with my reasoning at every point:

My proposed approach

[Write 4-6 numbered steps. Each step should explain WHAT you'd do and WHY. Mention specific methodologies, tools, and technical concepts where relevant]

What you'll get

[List 2-3 concrete deliverables they'll receive]

Timeline

[Give a realistic estimate in a conversational tone, e.g., "I can have the first version ready in 3-4 days, with revisions wrapped up within a week."]
---

Write ONLY the proposal content, no additional commentary."""

    try:
        proposal_text = call_llm(proposal_prompt)
    except Exception as e:
        print(f"⚠️ Warning: LLM API error for '{job_title[:40]}...': {e}. Using deterministic proposal synthesis.")
        proposal_text = generate_fallback_proposal_text(job_title, job_description, skills)
    
    # Generate cover letter
    cover_letter_prompt = f"""Write a very short cover letter (~35 words max) for this Upwork job.

JOB TITLE: {job_title}
JOB DESCRIPTION (first 200 chars): {job_description[:200]}

Format EXACTLY like this (replace brackets):
Hi. I work with [2-4 word paraphrase of their tech/need] daily & just built a [2-5 word relevant thing you built]. Free walkthrough: [DOC_LINK]

The [DOC_LINK] placeholder will be replaced with the actual Google Doc link later.

Write ONLY the cover letter, nothing else. Keep it under 35 words."""

    try:
        cover_letter = call_llm(cover_letter_prompt)
    except Exception as e:
        print(f"⚠️ Warning: LLM error generating cover letter: {e}. Using structured fallback.")
        tech_need = skills.split(',')[0].strip() if skills else job_title[:20].strip()
        cover_letter = f"Hi. I work with {tech_need} daily & built a tailored architecture for your project. Free walkthrough: [DOC_LINK]"
    
    return {
        "proposal": proposal_text,
        "cover_letter": cover_letter
    }


def generate_fallback_proposal_text(job_title: str, job_description: str, skills: str) -> str:
    """Deterministic fallback proposal generator if LLM endpoint is unavailable."""
    client_name = "there"
    match = re.search(r"(?:hi|hello|hey)\s+([A-Z][a-z]+)", job_description, re.IGNORECASE)
    if match:
        client_name = match.group(1)

    skill_str = skills if skills else "modern automation, API integrations, and robust workflows"

    return f"""Hey {client_name}.

I spent ~15 minutes putting this together for you. In short, it's how I would create your {job_title[:40]} solution end to end.

I've worked with various teams and have a lot of experience designing and building similar solutions using {skill_str}.

Here's a step-by-step, along with my reasoning at every point:

My proposed approach

1. Workflow & Architecture Audit
I will review your exact inputs, triggers, and expected data schemas. This guarantees no unhandled edge cases or unexpected API payload shifts midway through execution.

2. Core Implementation & Integration
I will implement the business logic, connect all required services and webhooks, and ensure robust error catching with automated backoff/retry mechanisms.

3. End-to-End Testing & Reliability Safeguards
I will test with realistic payloads, verify rate limits, validate data integrity, and ensure smooth exception handling.

4. Documentation & Handover
You will receive clean, commented assets, environment configuration guidance, and a live walkthrough to ensure complete ease of operation.

What you'll get

- Fully tested, deterministic production implementation.
- Clear setup and maintenance documentation.
- Live walkthrough and post-deployment handover support.

Timeline

I can have the initial working version ready in 2-3 days, with testing and final polish wrapped up within a week.
"""


def process_job(job: dict, llm_client: openai.OpenAI, google_creds) -> dict:
    """Process a single job: generate proposal, create doc, return result."""
    job_id = job.get("id") or job.get("uid") or ""
    job_title = job.get("title", "Unknown")
    
    print(f"Processing: {job_title[:50]}...")
    
    # Generate proposal and cover letter
    content = generate_proposal(job, llm_client)
    
    # Create Google Doc for proposal if LLM didn't error out
    doc_url = None
    proposal_text = content["proposal"]
    if proposal_text and not proposal_text.startswith("[Error generating proposal:"):
        doc_title = f"Proposal: {job_title[:50]}"
        doc_url = create_google_doc(doc_title, proposal_text, google_creds)
    
    # Replace [DOC_LINK] placeholder in cover letter robustly
    link_val = doc_url if doc_url else "[Attached in Sheet]"
    cover_letter = re.sub(r'\[?doc[-_ ]?link\]?', link_val, content["cover_letter"], flags=re.IGNORECASE)
    
    # If the placeholder was not found and doc_url exists, append it at the end
    if doc_url and doc_url not in cover_letter:
        cover_letter = cover_letter.strip() + " " + doc_url
        
    # Safely parse client data
    client_data = job.get("client") or {}
    if not isinstance(client_data, dict):
        client_data = {}
    client_country = client_data.get("country", "")
    
    client_stats = client_data.get("stats") or {}
    if not isinstance(client_stats, dict):
        client_stats = {}
    client_spent = client_stats.get("totalSpent") or client_data.get("total_spent") or ""
    client_hires = client_stats.get("totalHires") or client_data.get("total_hires") or ""
    
    # Safely parse skills
    skills_raw = job.get("skills", [])
    if isinstance(skills_raw, list):
        skills = ", ".join(str(s) for s in skills_raw)
    elif isinstance(skills_raw, str):
        skills = skills_raw
    else:
        skills = ""
        
    # Safely parse budget
    budget_raw = job.get("budget")
    if budget_raw is not None:
        if isinstance(budget_raw, dict):
            fixed = budget_raw.get("fixedBudget")
            if fixed is not None and fixed != 0:
                budget = f"${fixed}"
            else:
                hourly = budget_raw.get("hourlyRate") or {}
                if isinstance(hourly, dict):
                    h_min = hourly.get("min")
                    h_max = hourly.get("max")
                    if h_min is not None and h_max is not None:
                        budget = f"${h_min} - ${h_max} / hr"
                    elif h_max is not None:
                        budget = f"Up to ${h_max} / hr"
                    else:
                        budget = ""
                else:
                    budget = str(hourly)
        else:
            budget = str(budget_raw)
    else:
        hourly_rate = job.get("hourly_rate")
        budget = str(hourly_rate) if hourly_rate is not None else ""
    
    return {
        "job_id": job_id,
        "title": job_title,
        "url": job.get("url", ""),
        "apply_url": job.get("apply_url", ""),
        "budget": budget,
        "experience_level": job.get("experience_level") or job.get("vendor", {}).get("experienceLevel") or "",
        "skills": skills,
        "category": job.get("category", ""),
        "client_country": client_country,
        "client_spent": client_spent,
        "client_hires": client_hires,
        "connects": job.get("connects", ""),
        "cover_letter": cover_letter,
        "proposal_doc": doc_url or proposal_text[:500],
        "proposal_full": proposal_text
    }


def create_or_get_sheet(creds, sheet_id: str | None = None) -> tuple:
    """Create a new Google Sheet or get existing one. Returns (sheet_id, sheet_url)."""
    sheets_service = build('sheets', 'v4', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    
    if sheet_id:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        return sheet_id, sheet_url
    
    title = f"Upwork Proposals - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    spreadsheet = sheets_service.spreadsheets().create(
        body={"properties": {"title": title}}
    ).execute()
    
    new_sheet_id = spreadsheet["spreadsheetId"]
    sheet_url = f"https://docs.google.com/spreadsheets/d/{new_sheet_id}/edit"
    
    # Make viewable by anyone (reader role for security) if Drive API scope is available
    try:
        drive_service.permissions().create(
            fileId=new_sheet_id,
            body={"type": "anyone", "role": "reader"}
        ).execute()
    except Exception as e:
        print(f"Notice: Drive sharing skipped ({e})")
    
    headers = [
        "Title", "URL", "Budget", "Experience", "Skills", "Category",
        "Client Country", "Client Spent", "Client Hires", "Connects",
        "Apply Link", "Cover Letter", "Proposal Doc"
    ]
    
    sheets_service.spreadsheets().values().update(
        spreadsheetId=new_sheet_id,
        range="A1:M1",
        valueInputOption="RAW",
        body={"values": [headers]}
    ).execute()
    
    print(f"Created new Google Sheet: {sheet_url}")
    return new_sheet_id, sheet_url


def write_to_sheet(sheet_id: str, results: list[dict], creds):
    """Write results to the Google Sheet."""
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    rows = []
    for r in results:
        rows.append([
            r.get("title", ""),
            r.get("url", ""),
            str(r.get("budget", "")),
            r.get("experience_level", ""),
            r.get("skills", ""),
            r.get("category", ""),
            r.get("client_country", ""),
            str(r.get("client_spent", "")),
            str(r.get("client_hires", "")),
            str(r.get("connects", "")),
            r.get("apply_url", ""),
            r.get("cover_letter", ""),
            r.get("proposal_doc", "")
        ])
    
    sheets_service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="A2:M",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows}
    ).execute()
    
    print(f"Wrote {len(rows)} rows to Google Sheet")


@review_on_failure
def main():
    parser = argparse.ArgumentParser(description="Generate Upwork proposals")
    parser.add_argument("--input", "-i", required=True, help="Input JSON file with jobs")
    parser.add_argument("--output", "-o", default=".tmp/upwork_proposals.json", help="Output JSON file")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers for LLM calls")
    parser.add_argument("--sheet-id", type=str, help="Existing Google Sheet ID (creates new if omitted)")
    parser.add_argument("--max-jobs", type=int, help="Maximum number of jobs to process")
    
    args = parser.parse_args()
    
    # Load jobs
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)
    
    try:
        with open(input_path, "r", encoding="utf-8-sig") as f:
            jobs = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing input JSON file {input_path}: {e}")
        sys.exit(1)
        
    if not isinstance(jobs, list):
        print(f"Error: Expected a list of jobs in {input_path}")
        sys.exit(1)
        
    print(f"Loaded {len(jobs)} jobs from {input_path}")
    
    # Slicing for max-jobs limit
    if args.max_jobs and len(jobs) > args.max_jobs:
        print(f"Limiting jobs to the first {args.max_jobs} items as requested by --max-jobs")
        jobs = jobs[:args.max_jobs]
        
    if not jobs:
        print("No jobs to process")
        sys.exit(0)
    
    # Initialize clients
    nvidia_key = os.getenv("NVIDIA_NIM") or os.getenv("NVIDIA_API_KEY")
    
    if nvidia_key:
        print("Using Nvidia NIM API")
        llm_client = openai.OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=nvidia_key
        )
        global PROPOSAL_MODEL
        PROPOSAL_MODEL = os.getenv("NVIDIA_PROPOSAL_MODEL", PROPOSAL_MODEL)
    else:
        print("Error: NVIDIA_NIM or NVIDIA_API_KEY not found in environment.")
        sys.exit(1)

    google_creds = get_google_credentials()
    
    # Create or get Google Sheet
    sheet_id, sheet_url = create_or_get_sheet(google_creds, args.sheet_id)
    
    # Process jobs in parallel (or sequential if workers=1)
    results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_job = {
            executor.submit(process_job, job, llm_client, google_creds): job
            for job in jobs
        }
        
        for future in as_completed(future_to_job):
            job = future_to_job[future]
            try:
                result = future.result()
                results.append(result)
                print(f"Completed {len(results)}/{len(jobs)}: {result['title'][:40]}...")
                
                # Write incrementally to Google Sheet
                write_to_sheet(sheet_id, [result], google_creds)
                
            except Exception as e:
                print(f"Error processing job '{job.get('title', 'Unknown')[:40]}': {e}")
    
    elapsed = time.time() - start_time
    print(f"\nProcessed {len(results)} jobs in {elapsed:.1f}s ({elapsed/len(results):.1f}s per job)")
    
    # Save results to JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(results)} proposals to {output_path}")
    print(f"\nGoogle Sheet: {sheet_url}")
    print("Open the sheet to review proposals and one-click apply!")


if __name__ == "__main__":
    main()
