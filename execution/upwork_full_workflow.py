#!/usr/bin/env python3
"""
Run the full Upwork workflow end to end.

This script creates a live Google Sheet first, then scrapes each keyword group
and immediately generates proposals for that group before moving on.

Example:
    python execution/upwork_full_workflow.py \
      --search "content creation,content creator,social media content:4" \
      --search "video editing,video editor,short form video editing:3"
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Allow relaxed token scope for Google OAuth
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
# Ensure execution directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from upwork_proposal_generator import create_or_get_sheet, get_google_credentials
from reviewer_agent import review_on_failure


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = WORKSPACE_ROOT / ".tmp"
SCRAPER = WORKSPACE_ROOT / "execution" / "upwork_apify_scraper.py"
PROPOSAL_GENERATOR = WORKSPACE_ROOT / "execution" / "upwork_proposal_generator.py"


def run_command(cmd: list[str], timeout: int | None = None) -> str:
    """Run a command, stream output, and return captured stdout."""
    print("\nRunning:")
    print(" ".join(cmd))
    print("-" * 80)

    process = subprocess.Popen(
        cmd,
        cwd=WORKSPACE_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    output_lines = []
    try:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            output_lines.append(line)
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(cmd)}")

    output = "".join(output_lines)
    if return_code != 0:
        raise RuntimeError(f"Command failed with exit code {return_code}: {' '.join(cmd)}")

    return output


def run_proposal_command(cmd: list[str], timeout: int | None = None) -> tuple[str, str | None]:
    """Run proposal generation and surface the Google Sheet URL immediately."""
    print("\nRunning:")
    print(" ".join(cmd))
    print("-" * 80)

    process = subprocess.Popen(
        cmd,
        cwd=WORKSPACE_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    output_lines = []
    sheet_url = None
    try:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            output_lines.append(line)
            discovered_url = extract_sheet_url(line)
            if discovered_url and discovered_url != sheet_url:
                sheet_url = discovered_url
                print("\nLive Google Sheet:")
                print(sheet_url)
                print("Rows will appear here as proposals finish.\n")
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(cmd)}")

    output = "".join(output_lines)
    if return_code != 0:
        raise RuntimeError(f"Command failed with exit code {return_code}: {' '.join(cmd)}")

    return output, sheet_url


def parse_search(raw: str) -> tuple[list[str], int]:
    """Parse 'keyword one,keyword two:limit'."""
    if ":" not in raw:
        raise ValueError(
            f"Invalid --search value '{raw}'. Use 'keyword one,keyword two:limit'."
        )

    keyword_text, limit_text = raw.rsplit(":", 1)
    keywords = [item.strip() for item in keyword_text.split(",") if item.strip()]
    if not keywords:
        raise ValueError(f"Invalid --search value '{raw}': no keywords found.")

    try:
        limit = int(limit_text.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid --search value '{raw}': limit must be a number.") from exc

    if limit < 1:
        raise ValueError(f"Invalid --search value '{raw}': limit must be at least 1.")

    return keywords, limit


def load_jobs(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of jobs in {path}")
    return data


def dedupe_jobs(jobs: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for job in jobs:
        key = job.get("id") or job.get("url") or job.get("title")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def job_key(job: dict) -> str:
    return str(job.get("id") or job.get("url") or job.get("title") or "")


def extract_sheet_url(output: str) -> str | None:
    for line in output.splitlines():
        if "https://docs.google.com/spreadsheets/d/" in line:
            return line[line.find("https://docs.google.com/spreadsheets/d/") :].strip()
    return None


@review_on_failure
def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Upwork jobs and generate proposal Google Sheet")
    parser.add_argument(
        "--search",
        action="append",
        required=True,
        help="Keyword group and final count, e.g. 'content creation,content creator:4'. Repeat for multiple groups.",
    )
    parser.add_argument("--days", type=int, default=7, help="Days back to search")
    parser.add_argument(
        "--scrape-multiplier",
        type=int,
        default=25,
        help="Raw scrape size multiplier per requested job count",
    )
    parser.add_argument("--min-scrape-limit", type=int, default=100, help="Minimum raw scrape size per group")
    parser.add_argument("--workers", type=int, default=1, help="Proposal generator workers")
    parser.add_argument("--sheet-id", help="Existing Google Sheet ID to append to")
    parser.add_argument("--verified-payment", action="store_true", help="Only verified payment clients")
    parser.add_argument("--min-spent", type=int, help="Minimum client total spend")
    parser.add_argument("--experience", help="Experience levels: entry,intermediate,expert")
    parser.add_argument("--min-budget", type=int, help="Minimum job budget")
    parser.add_argument("--run-name", default=datetime.now().strftime("%Y%m%d_%H%M%S"))

    args = parser.parse_args()
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    print("Creating Google Sheet before scraping so the live link is available immediately.")
    google_creds = get_google_credentials()
    sheet_id, sheet_url = create_or_get_sheet(google_creds, args.sheet_id)
    sheet_url_path = TMP_DIR / f"upwork_sheet_{args.run_name}.txt"
    sheet_url_path.write_text(sheet_url, encoding="utf-8")

    print("\nLive Google Sheet:")
    print(sheet_url)
    print(f"Saved live sheet URL to {sheet_url_path}")
    print("Proposals will be added here after each search group is scraped.\n")

    searches = [parse_search(value) for value in args.search]
    all_jobs = []
    all_proposals = []
    seen_job_keys = set()

    for index, (keywords, limit) in enumerate(searches, start=1):
        output_path = TMP_DIR / f"upwork_scrape_{args.run_name}_{index}.json"
        unique_group_path = TMP_DIR / f"upwork_jobs_{args.run_name}_{index}_unique.json"
        group_proposals_path = TMP_DIR / f"upwork_proposals_{args.run_name}_{index}.json"
        scrape_limit = max(args.min_scrape_limit, limit * args.scrape_multiplier)

        cmd = [
            sys.executable,
            str(SCRAPER),
            "--limit",
            str(limit),
            "--scrape-limit",
            str(scrape_limit),
            "--days",
            str(args.days),
            "--keywords",
            ",".join(keywords),
            "-o",
            str(output_path),
        ]

        if args.verified_payment:
            cmd.append("--verified-payment")
        if args.min_spent is not None:
            cmd.extend(["--min-spent", str(args.min_spent)])
        if args.experience:
            cmd.extend(["--experience", args.experience])
        if args.min_budget is not None:
            cmd.extend(["--min-budget", str(args.min_budget)])

        run_command(cmd, timeout=420)
        jobs = load_jobs(output_path)
        print(f"Loaded {len(jobs)} filtered jobs from {output_path}")

        if len(jobs) < limit:
            print(
                f"Warning: requested {limit} jobs for '{', '.join(keywords)}' "
                f"but only found {len(jobs)}."
            )

        unique_group_jobs = []
        for job in jobs:
            key = job_key(job)
            if key in seen_job_keys:
                continue
            seen_job_keys.add(key)
            unique_group_jobs.append(job)

        all_jobs.extend(unique_group_jobs)

        if not unique_group_jobs:
            print("No new unique jobs in this search group; skipping proposal generation for it.")
            continue

        with open(unique_group_path, "w", encoding="utf-8") as f:
            json.dump(unique_group_jobs, f, indent=2, ensure_ascii=False)

        print(
            f"\nStarting proposal generation for {len(unique_group_jobs)} "
            f"new jobs from search group {index}/{len(searches)}."
        )
        proposal_cmd = [
            sys.executable,
            str(PROPOSAL_GENERATOR),
            "--input",
            str(unique_group_path),
            "--workers",
            str(args.workers),
            "-o",
            str(group_proposals_path),
            "--sheet-id",
            sheet_id,
        ]

        proposal_output, detected_sheet_url = run_proposal_command(proposal_cmd)
        sheet_url = detected_sheet_url or extract_sheet_url(proposal_output) or sheet_url
        all_proposals.extend(load_jobs(group_proposals_path))

    combined_jobs = dedupe_jobs(all_jobs)
    combined_path = TMP_DIR / f"upwork_jobs_{args.run_name}_combined.json"
    proposals_path = TMP_DIR / f"upwork_proposals_{args.run_name}.json"

    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(combined_jobs, f, indent=2, ensure_ascii=False)

    with open(proposals_path, "w", encoding="utf-8") as f:
        json.dump(all_proposals, f, indent=2, ensure_ascii=False)

    if not combined_jobs:
        raise RuntimeError("No jobs found after scraping; proposal generation was not run.")

    print("\nWorkflow complete.")
    print(f"Jobs JSON: {combined_path}")
    print(f"Proposals JSON: {proposals_path}")
    if sheet_url:
        print(f"Google Sheet: {sheet_url}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
