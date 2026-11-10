# Harish DOE Workspace (Deterministic Orchestrated Execution)

An agentic automation framework separating concerns across a **3-Layer Architecture** (Directives, Orchestration, and Deterministic Python Execution) to deliver robust, reproducible business pipelines.

---

## 🏛️ The 3-Layer Architecture

1. **Layer 1: Directives (`directives/`)**
   Standard Operating Procedures (SOPs) written in Markdown defining workflow goals, inputs, tools, outputs, and edge cases.
2. **Layer 2: Orchestration (AI Agent / Developer)**
   Intelligent decision-making, routing, argument formulation, and failure handling.
3. **Layer 3: Execution (`execution/`)**
   Deterministic, testable Python scripts handling API requests, data transformations, web scraping, and cloud deliverables.

---

## 🚀 Workflows & Execution Tools

* **Upwork Job Scraper & Proposal Engine:**
  * [`execution/upwork_full_workflow.py`](execution/upwork_full_workflow.py): Scrapes jobs via Apify, generates tailored proposals via NVIDIA NIM LLM, creates viewable Google Docs, and appends rows to a live Google Sheet.
  * [`execution/upwork_proposal_generator.py`](execution/upwork_proposal_generator.py): Standalone proposal generator and Google Docs/Sheets publisher with deterministic fallback synthesis.
  * [`execution/upwork_apify_scraper.py`](execution/upwork_apify_scraper.py): Apify actor integration for job queries and local filtering.
* **Client Onboarding & Communication:**
  * [`execution/send_onboarding_email.py`](execution/send_onboarding_email.py): Direct, fast Gmail SMTP integration using standard library and app passwords.
  * [`execution/send_whatsapp_selenium.py`](execution/send_whatsapp_selenium.py): Selenium-driven WhatsApp Web automation with persistent browser session caching.
* **Quality Assurance & Verification:**
  * [`execution/reviewer_agent.py`](execution/reviewer_agent.py): Code review sub-agent for automated failure diagnosis and script critiques.
  * [`execution/google_auth_helper.py`](execution/google_auth_helper.py): OAuth session manager for Google Drive, Docs, and Sheets scopes.

---

## ⚙️ Setup & Installation

### 1. Clone & Install Dependencies

```bash
git clone <your-repo-url>
cd <repo-folder>
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example environment template:
```bash
cp .env.example .env
```
Fill in your credentials in `.env`:
* `GMAIL_ADDRESS` & `GMAIL_APP_PASSWORD`
* `APIFY_API_TOKEN`
* `NVIDIA_NIM` (API key)

### 3. Google OAuth Setup (for Docs & Sheets)

1. Place your Google Cloud `credentials.json` in the root directory.
2. Run the authentication helper to generate `token.json`:
   ```bash
   python execution/google_auth_helper.py
   ```

---

## 🔒 Security Notice

All secrets, environment files (`.env`), Google OAuth credentials (`credentials.json`, `token.json`), and temporary caches (`.tmp/`) are strictly excluded via `.gitignore` to prevent credential exposure.
