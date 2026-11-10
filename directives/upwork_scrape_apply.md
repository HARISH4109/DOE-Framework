# Upwork Job Scraping & Proposal Generation

> Scrape Upwork jobs matching AI/automation keywords, generate personalized proposals with Qwen 3 Coder (via OpenRouter), create Google Docs, and output to Google Sheet with one-click apply links.

> [!IMPORTANT]
> **CRITICAL RULE: Always Run Proposal Generator on Job Scrape Requests**
> Whenever the user asks to "scrape a job", "scrape jobs", or requests jobs on any topic, **NEVER stop after only scraping**. You MUST run the proposal generator automatically as part of the workflow. The full pipeline (`execution/upwork_full_workflow.py` or `upwork_apify_scraper.py` followed immediately by `upwork_proposal_generator.py`) must execute end-to-end so proposals and the Google Sheet are delivered. Scraping without proposal generation is strictly reserved for when the user explicitly says "only scrape without generating proposals".


## Goal
Automate the Upwork proposal process: discover relevant jobs, generate high-quality personalized proposals, and present them in a Google Sheet ready for one-click applications.

## Inputs
- **Keywords**: AI, automation, n8n, Claude, Zapier, Make, workflow automation
- **Date Range**: Typically last 1-7 days
- **Limit**: Number of jobs to scrape (default 50)
- **Filters**:
  - `--verified-payment`: Only verified payment clients
  - `--min-spent N`: Minimum client total spend
  - `--experience`: Entry, intermediate, expert
  - `--min-budget N`: Minimum job budget

## Tools/Scripts

### Preferred: `execution/upwork_full_workflow.py`
Runs scraping, combines outputs, generates proposals, creates Google Docs, and outputs the Google Sheet in one command.
The script creates the Google Sheet before scraping starts, prints the live URL immediately, and saves it to `.tmp/upwork_sheet_[run-name].txt`. It then scrapes each search group and immediately generates proposals for that group into the same sheet before moving to the next group.

```bash
python execution/upwork_full_workflow.py \
  --search "content creation,content creator,social media content:4" \
  --search "video editing,video editor,short form video editing:3"
```

Use this for normal user requests so the workflow does not stop after scraping.

### Lower-level: `execution/upwork_apify_scraper.py`
Scrapes Upwork using `upwork-vibe~upwork-job-scraper` Apify actor.

```bash
python execution/upwork_apify_scraper.py \
  --limit 50 --days 1 --verified-payment \
  --min-spent 1000 --experience intermediate,expert \
  -o .tmp/upwork_jobs.json
```

### Lower-level: `execution/upwork_proposal_generator.py`
Generates proposals with Google Gemini (via Direct API, model: `gemini-flash-latest`) and outputs to Google Sheets.

```bash
python execution/upwork_proposal_generator.py \
  --input .tmp/upwork_jobs.json \
  --workers 5 \
  -o .tmp/upwork_proposals.json
```

## Steps

1. **Run Full Workflow**
   ```bash
   python execution/upwork_full_workflow.py --search "keyword one,keyword two:COUNT"
   ```
   Repeat `--search` for multiple job categories. This is the default path for user-facing requests.

2. **If Debugging Only: Scrape Jobs**
   ```bash
   python execution/upwork_apify_scraper.py --limit 50 --days 1 -o .tmp/upwork_jobs.json
   ```

3. **If Debugging Only: Generate Proposals** (auto-creates Google Sheet)
   ```bash
   python execution/upwork_proposal_generator.py --input .tmp/upwork_jobs.json --workers 1
   ```
   *Note: Use `--workers 1` to prevent rate limit errors on OpenRouter free tier.*

4. **Review & Apply**
   - Open the Google Sheet URL from terminal output
   - Review proposals in linked Google Docs
   - Click "Apply Link" to apply in one click

## Outputs

**Google Sheet Columns:**
| Column | Description |
|--------|-------------|
| Title | Job title |
| URL | Job posting link |
| Budget | Fixed price or hourly range |
| Experience | Required experience level |
| Skills | Required skills list |
| Category | Job category |
| Client Country | Client location |
| Client Spent | Total client spend on Upwork |
| Client Hires | Number of past hires |
| Connects | Cost to apply |
| Apply Link | One-click apply URL |
| Cover Letter | ~35 word intro for application |
| Proposal Doc | Link to full proposal Google Doc |

## Edge Cases

### Apify Failures
- **Timeout**: Poll every 3s, timeout after 5 min, retry once
- **No results**: Lower `limit` or extend `days` range
- **Rate limit**: Wait 60s and retry

### AI Model (Google Gemini 2.0 Flash)
- **Rate limit**: Free tier on OpenRouter has strict limits.
- **Mitigation**: Use `--workers 1` for sequential processing and explicit sleeps in script.
- **Headers**: Requires `HTTP-Referer` and `X-Title` headers (handled in script).

### Google APIs
- **SSL errors on parallel Doc creation**: Already serialized with semaphore
- **Token expired**: Re-run OAuth flow with `credentials.json`
- **Doc creation fails**: Fallback to embedding proposal in sheet cell

## Learnings

### Apify Actor Constraints
- Free tier only supports `limit`, `fromDate`, `toDate`
- All other filters must be post-scrape. Do not send `includeKeywords`; the actor rejects it with `Property input.includeKeywords is not allowed`.
- For keyword requests, use `--scrape-limit` to fetch a broader raw set, then filter locally with `--keywords` and cap final output with `--limit`.
- For "app tester" requests, phrase matching can be too narrow. Prefer a broader query such as `app testing,mobile testing,mobile app testing,QA testing,software testing,user testing,manual testing`, with `--days 14 --min-scrape-limit 300` if the first pass finds no jobs.
- Job URL: `https://www.upwork.com/jobs/~{id}`
- Apply URL: `https://www.upwork.com/nx/proposals/job/~{id}/apply/`

### Performance Benchmarks
- 10 jobs with 5 workers: ~2 min (vs ~20 min sequential)
- Opus 4.5 with 8000 thinking tokens: 30-60s per call
- Google Doc creation: 2-5s each (serialized)

### Cost
- **Apify**: Free tier (limited runs per month)
- **Google AI Studio (Gemini)**: Free tier (15 RPM, 1500 req/day) - **Recommended**
- **OpenRouter (Free)**: Very limited (daily caps often hit).
- **Total**: $0.00

### Setup
1. Get a free API Key from [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Add to `.env`: `GEMINI_API_KEY=your_key_here`

### Cover Letter Format
Must stay above the fold, ~35 words:
```
Hi. I work with [2-4 word paraphrase] daily & just built a [2-5 word thing]. Free walkthrough: [DOC_LINK]
```

### Proposal Format
~300 words, first-person conversational:
```
Hey [name if available].

I spent ~15 minutes putting this together for you. In short, it's how I would create your [2-4 word paraphrase] end to end.

I've worked with $MM companies like Anthropic (yes—that Anthropic) and I have a lot of experience designing/building similar workflows.

Here's a step-by-step, along with my reasoning at every point:

My proposed approach

[4-6 numbered steps with WHY for each, mention specific tools: n8n, Claude API, Zapier, Make, etc.]

What you'll get

[2-3 concrete deliverables]

Timeline

[Realistic estimate, conversational]
```
