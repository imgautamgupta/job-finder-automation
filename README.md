# Job Finder Automation (Part 1)

A modular, personal automation tool designed to aggregate relevant job opportunities from LinkedIn and Naukri, filter them against custom criteria, eliminate duplicates, persist history in SQLite, and generate formatted Excel reports daily.

> **Important**: This is a personal-use automation system, not a SaaS product. Part 1 focuses on modular source architecture, standardized data modeling, persistence, filtering, and reporting. Job application automation will be implemented in Part 2.

---

## Project Structure

```text
job-finder-automation/
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # Core pipeline orchestrator
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── job.py               # Standardized Job Pydantic model & ApplicationPriority
│   │   ├── profile.py           # User profile & matching rules models
│   │   ├── recommendation.py    # ApplicationRecommendation Pydantic model (Phase 9)
│   │   ├── interview.py         # Interview & Daily Action models (Phase 11)
│   │   ├── analytics.py         # Application Analytics & Funnel models (Phase 12)
│   │   └── search_intelligence.py # Job Search Intelligence & Source Optimization models (Phase 13)
│   │
│   ├── sources/                 # Modular source connectors
│   │   ├── __init__.py
│   │   ├── base.py              # BaseJobSource abstract class
│   │   ├── greenhouse.py        # Greenhouse public Job Board API connector
│   │   ├── lever.py             # Lever public Postings API connector
│   │   ├── linkedin.py          # LinkedIn connector (Placeholder)
│   │   └── naukri.py            # Naukri connector (Live collection / safe handling)
│   │
│   ├── services/                # Pipeline processing services
│   │   ├── __init__.py
│   │   ├── collector.py         # Multi-source coordinator
│   │   ├── filter.py            # Profile criteria & keyword matching
│   │   ├── matcher.py           # 100-point deterministic scoring engine
│   │   ├── recommender.py       # Deterministic application recommendation engine (Phase 9)
│   │   ├── deduplicator.py      # URL normalization & duplicate detection
│   │   ├── excel_exporter.py    # Formatted .xlsx workbook generation (with Analytics & Search Intelligence sheets)
│   │   ├── job_tracker.py       # Job status, follow-up & interview tracking service
│   │   ├── resume_intelligence.py # Resume intelligence & alignment engine (Phase 10)
│   │   ├── interview_preparation.py # Deterministic interview prep engine (Phase 11)
│   │   ├── analytics.py         # Deterministic analytics & optimization service (Phase 12)
│   │   └── search_intelligence.py # Deterministic search intelligence & source optimization engine (Phase 13)
│   │
│   ├── dashboard/               # Local Job Review Dashboard (Phases 8–13)
│   │   ├── __init__.py
│   │   ├── __main__.py          # CLI runner (python -m app.dashboard)
│   │   ├── app.py               # FastAPI application factory & filters
│   │   ├── routes.py            # Dashboard routes (/search-intelligence, /analytics, /applications, /today)
│   │   ├── templates/           # Server-rendered Jinja2 templates
│   │   │   ├── base.html
│   │   │   ├── dashboard.html
│   │   │   ├── search_intelligence.html # Job Search Intelligence Dashboard (Phase 13)
│   │   │   ├── analytics.html   # Application Analytics Dashboard (Phase 12)
│   │   │   ├── applications.html# Application Command Center (Phase 11)
│   │   │   ├── today.html       # Daily Action Plan UI (Phase 11)
│   │   │   ├── interview_prep.html # Interview Preparation Workspace (Phase 11)
│   │   │   ├── apply_today.html # Actionable Apply Today queue UI (Phase 9)
│   │   │   ├── resume_prep.html # Resume preparation queue UI (Phase 10)
│   │   │   ├── jobs.html
│   │   │   ├── job_detail.html  # Enhanced detail with timeline, interview & prep
│   │   │   ├── pipeline_runs.html
│   │   │   └── source_health.html
│   │   └── static/              # Vanilla CSS & client interactions
│   │       ├── style.css
│   │       └── dashboard.js
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   └── database.py          # SQLite persistence & historical lookups
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   └── lock.py              # Process lock & log retention cleanup
│   │
│   └── config/
│       ├── __init__.py
│       └── settings.py          # Environment settings & profile loader
│
├── data/
│   ├── jobs.db                  # SQLite database (auto-created)
│   ├── exports/                 # Generated Excel spreadsheets (.xlsx)
│   ├── logs/                    # Timestamped automated execution logs (.log)
│   └── profile.json             # Search criteria & preference rules
│
├── docs/
│   └── windows-task-scheduler.md # Windows Task Scheduler step-by-step setup guide
│
├── scripts/
│   ├── run_daily_job_finder.bat # Windows daily automated batch runner
│   ├── run_dashboard.bat        # Windows local dashboard launcher
│   └── DailyJobFinderTask.xml   # Portable Task Scheduler XML template
│
├── tests/
│   ├── __init__.py
│   ├── test_models.py           # Model tests
│   ├── test_database.py         # Database integration tests
│   ├── test_services.py         # Service unit tests
│   ├── test_phase_6e_sources.py # Source integration tests
│   ├── test_phase_6f_matcher.py # Matcher refinement tests
│   ├── test_phase_7a_pipeline.py# Tracking & pipeline tests
│   ├── test_phase_7b_runner.py  # Lock, cleanup, & runner tests
│   └── test_phase_8_dashboard.py# Dashboard & tracking UI tests
│
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment configuration template
├── .gitignore                   # Version control ignore rules
└── README.md
```

---

## Component Overview

| Component | File | Description |
| :--- | :--- | :--- |
| **Data Model** | `app/models/job.py` | Standardized `Job` schema with fields (`title`, `company`, `location`, `source`, `url`, `description`, `easy_apply`, `date_posted`, `date_found`, `job_id`, `employment_type`, `experience_required`, `salary`), validation, and export formatting. |
| **Source Interface** | `app/sources/base.py` | Abstract `BaseJobSource` providing a uniform contract (`setup()`, `collect_jobs()`, `teardown()`). Adding new job boards (e.g. Indeed, Glassdoor) requires only subclassing `BaseJobSource` without touching core pipeline logic. |
| **Source Connectors** | `app/sources/linkedin.py`, `app/sources/naukri.py`, `app/sources/lever.py`, `app/sources/greenhouse.py` | Platform-specific connectors implementing `BaseJobSource`. Strictly adhere to safety, access control, and rate-limit guidelines. |
| **Collector Service** | `app/services/collector.py` | Manages source lifecycle and aggregates jobs across all registered connectors. |
| **Filter Service** | `app/services/filter.py` | Matches listings against target roles, locations, keywords, experience ranges, and excludes negative keywords defined in `data/profile.json`. |
| **Deduplicator Service**| `app/services/deduplicator.py` | Strips tracking query parameters (e.g., `ref`, `utm_*`, `trackingId`) and verifies against in-batch items and previously seen jobs stored in SQLite. |
| **Database Manager** | `app/database/database.py` | Manages SQLite storage (`data/jobs.db`), ensuring historical jobs are recorded and never re-notified. |
| **Excel Exporter** | `app/services/excel_exporter.py` | Creates professional Excel workbooks (`data/exports/jobs_YYYYMMDD_HHMMSS.xlsx`) with colored headers, auto-fit columns, zebra striping, and clickable hyperlinks. |
| **Configuration** | `app/config/settings.py` | Loads `.env` variables and deserializes `data/profile.json` into type-safe Pydantic models. |
| **Main Orchestrator** | `app/main.py` | Coordinates the full sequential pipeline from collection to export. |

---

## Installation

### 1. Prerequisites
* Python 3.11 or higher
* PowerShell or Windows Terminal

### 2. Setup Virtual Environment

Open PowerShell in the project directory:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

*(If script execution is disabled in PowerShell, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)*

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Install Playwright Browsers (For Future Collection Steps)

```powershell
playwright install chromium
```

---

## Configuration

### 1. Environment Variables

Copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

Adjust settings in `.env` if desired:
```ini
APP_ENV=development
LOG_LEVEL=INFO
MAX_RESULTS_PER_SOURCE=25
HEADLESS_BROWSER=true
BROWSER_TIMEOUT_MS=30000
```

### 2. Job Search Profile (`data/profile.json`)

Your search preferences are stored in [`data/profile.json`](file:///c:/Users/gauta/job-finder-automation/data/profile.json). This file acts as the **single source of truth** for your job search criteria—no preferences are hardcoded in the Python source files.

#### Profile File Location
```text
job-finder-automation/data/profile.json
```

#### How the Application Loads the Profile
At runtime, `settings.load_profile()` dynamically reads and validates `data/profile.json` into strongly-typed Pydantic models:
* `JobProfile` validates lists of roles, locations, skills, positive keywords, negative keywords, and experience levels.
* `SearchPreferences` validates boolean switches (`remote_allowed`, `internship_allowed`, `fresher_allowed`, `entry_level_allowed`).
* The collector and filter services consume these validated preferences directly.

#### Current Profile Structure & Default Values
```json
{
  "target_roles": [
    "Python Developer",
    "Backend Developer",
    "Software Engineer",
    "Full Stack Developer",
    "Web Developer",
    "ML Engineer",
    "AI Engineer",
    "SDE Intern",
    "Python Developer Intern",
    "Machine Learning Intern",
    "Web Developer Intern"
  ],
  "preferred_locations": [
    "Delhi",
    "Noida",
    "Bangalore",
    "Bengaluru",
    "Ahmedabad",
    "India",
    "Remote"
  ],
  "experience_levels": [
    "Fresher",
    "Entry Level",
    "Internship",
    "0-1 years"
  ],
  "skills": [
    "Python",
    "JavaScript",
    "TypeScript",
    "React",
    "Next.js",
    "FastAPI",
    "REST API",
    "MongoDB",
    "SQL",
    "PostgreSQL",
    "Machine Learning",
    "Scikit-learn",
    "OpenCV",
    "NLP",
    "Pandas",
    "NumPy",
    "Git",
    "GitHub"
  ],
  "positive_keywords": [
    "AI",
    "Artificial Intelligence",
    "Backend",
    "Full Stack",
    "Software Development",
    "Web Development"
  ],
  "negative_keywords": [
    "Senior",
    "Lead",
    "Principal",
    "Staff",
    "Manager",
    "Director",
    "Architect",
    "5+ years",
    "7+ years",
    "10+ years"
  ],
  "preferences": {
    "remote_allowed": true,
    "internship_allowed": true,
    "fresher_allowed": true,
    "entry_level_allowed": true
  }
}
```

#### Example: How to Edit Job Preferences

To customize your target roles or add new locations, simply edit `data/profile.json`:

```json
{
  "target_roles": [
    "Python Developer",
    "Django Developer",
    "Data Engineer"
  ],
  "preferred_locations": [
    "Hyderabad",
    "Pune",
    "Remote"
  ],
  "preferences": {
    "remote_allowed": true,
    "internship_allowed": false,
    "fresher_allowed": true,
    "entry_level_allowed": true
  }
}
```

Next time `python -m app.main` runs, it will immediately adopt the updated search criteria without any code changes or recompilation.

---

## SQLite Storage & Historical Deduplication (Phase 3)

The persistent layer is built with SQLite to retain historical discoveries, track newly posted jobs, and prevent duplicate notifications.

### Database Location
```text
job-finder-automation/data/jobs.db
```
The database is auto-created on initial run. Schema migrations and required indices are automatically maintained by [`DatabaseManager`](file:///c:/Users/gauta/job-finder-automation/app/database/database.py).

### Multi-Level Deduplication Strategy

Job candidates pass through a three-tier deduplication check:

1. **Level 1 — Source Job ID**:
   - Matches `(source, source_job_id)` (e.g. `linkedin::123456789`).
   - Strongest identifier; detects identical postings even if URLs or parameters change.
2. **Level 2 — Canonical URL**:
   - Cleans and canonicalizes URLs by stripping tracking, referral, and analytics parameters (`utm_*`, `trackingId`, `ref`, `fbclid`, `gclid`, etc.).
   - Sorts remaining legitimate query parameters and normalizes path structure.
3. **Level 3 — Deterministic Fingerprint**:
   - Computes a deterministic SHA-256 hash across stable job attributes: `source|title|company|location|canonical_url`.
   - Protects against duplicate postings when source job IDs are absent.

### Historical Jobs & Update Behavior

When an existing job is encountered again on subsequent daily runs:
* **No duplicate rows are created** in the database.
* **Discovery metadata is preserved**: Original `date_found` and `created_at` timestamps are never overwritten.
* **Mutable details are refreshed**: Updated descriptions, compensation changes, or application statuses are synchronized, and `updated_at` is refreshed to the current timestamp.

### Running Database & Deduplication Tests

To run the dedicated database and deduplication tests:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_database.py -v
```

---

## Deterministic Job Matching & Scoring Engine (Phase 4)

A deterministic, fully explainable scoring system calculates alignment between each discovered job and your active `data/profile.json` preferences on a `0-100` scale.

### Scoring Breakdown (100 Points Total)

| Evaluation Component | Weight | Matching Logic |
| :--- | :---: | :--- |
| **Role / Title** | **40 pts** | Case-insensitive token and phrase matching against `target_roles`. Direct match awards 40 pts; partial domain match awards 20 pts; unrelated titles award 0 pts. |
| **Skills / Keywords** | **30 pts** | Word-boundary scan across title, description, and requirements against `profile.skills` (6 pts each) and `profile.positive_keywords` (3 pts each), capped at 30 pts. Deduplicated so skills aren't counted twice. |
| **Location & Remote** | **20 pts** | Deterministic priority hierarchy: **Delhi / Noida** = 20 pts (Highest), **Bangalore / Bengaluru** = 18 pts (High, equivalent), **Remote** = 18 pts (when remote allowed), **Ahmedabad** = 15 pts (Medium), **India / Pan India** = 12 pts (broad country fallback; ignores unrelated cities), **Unknown / Missing** = 0 pts, **Unrelated** = 0 pts. |
| **Experience Level** | **10 pts** | Explicit fresher, intern, or entry-level (0-1 yrs, 0-2 yrs) postings award 10 pts. Overqualified/senior roles award 0 pts. Missing experience receives neutral 5 pts. |

**Mathematical Guarantee**:
$$\text{role\_score} + \text{skills\_score} + \text{location\_score} + \text{experience\_score} = \text{total\_score}$$

### Qualitative Match Categories

```text
90 - 100  →  Excellent
80 - 89   →  Strong
70 - 79   →  Good
60 - 69   →  Possible
0  - 59   →  Not Relevant
```

### Negative Keywords & Diagnostics

If any negative keyword (`Senior`, `Lead`, `Principal`, `5+ years`, `10+ years`, etc.) is detected:
* Diagnostic entries are logged in `excluded_reasons`.
* Titles containing negative keywords forfeit role score and are capped at `Possible` or `Not Relevant`.

### Example Match Result (`MatchResult`)

```json
{
  "score": 87,
  "category": "Strong",
  "role_score": 40,
  "skills_score": 27,
  "location_score": 20,
  "experience_score": 0,
  "matched_roles": [
    "Python Developer"
  ],
  "matched_skills": [
    "Python",
    "FastAPI",
    "MongoDB",
    "SQL"
  ],
  "matched_locations": [
    "Bangalore"
  ],
  "experience_match": false,
  "excluded_reasons": []
}
```

### Running Matcher Tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_matcher.py -v
```

---

## Production-Ready Excel Job Report (Phase 5)

Every morning when the automation runs, a new, timestamped Excel workbook is saved to:

```text
job-finder-automation/data/exports/jobs_YYYYMMDD_HHMMSS.xlsx
```

### Multi-Sheet Architecture

The workbook is structured into two dedicated worksheets and automatically opens on **Top Matches**:

1. **`Top Matches` (Primary Sheet)**
   - Includes only high-relevance jobs with a **Match Score $\ge 80$**.
   - Opens as the active default sheet for rapid daily review.
2. **`All Relevant Jobs` (Comprehensive Sheet)**
   - Includes all qualified jobs with a **Match Score $\ge 60$**.

### Sorting Hierarchy

Both worksheets are sorted by:
1. **Match Score** (Descending — highest scoring opportunities first).
2. **Easy Apply** (Secondary preference — 1-click applications appear first for identical scores).
3. **Date Posted / Found** (Newest listings first).

### Priority Thresholds

* `HIGH` $\rightarrow$ Match Score $90 - 100$ (highlighted in soft green)
* `MEDIUM` $\rightarrow$ Match Score $80 - 89$ (highlighted in soft blue)
* `NORMAL` $\rightarrow$ Match Score $60 - 79$ (neutral subtle shading)

### Column Structure (17 Columns in Order)

| # | Column Header | Description |
| :-: | :--- | :--- |
| **1** | `Priority` | `HIGH`, `MEDIUM`, or `NORMAL` based on score. |
| **2** | `Match Score` | Integer score between 0 and 100. |
| **3** | `Match Category` | `Excellent`, `Strong`, `Good`, or `Possible`. |
| **4** | `Company` | Hiring organization name. |
| **5** | `Job Title` | Job title from posting. |
| **6** | `Location` | City, State, or Remote. |
| **7** | `Source` | Platform name (`Linkedin`, `Naukri`). |
| **8** | `Easy Apply` | `Yes` or `No`. |
| **9** | `Date Posted` | Relative or absolute posting date. |
| **10** | `Date Found` | Discovery timestamp. |
| **11** | `Job URL` | Full, clickable hyperlink directly opening the job in your browser. |
| **12** | `Matched Roles` | Which profile target roles matched the title. |
| **13** | `Matched Skills` | Comma-separated list of identified profile skills. |
| **14** | `Matched Locations`| Which preferred locations matched. |
| **15** | `Experience Match` | `Yes` or `No` indicating experience level fit. |
| **16** | `Excluded Reasons` | Penalties or negative keywords detected (blank if clean). |
| **17** | `Notes` | Editable column reserved for your personal notes / status tracking. |

### Excel Usability & Styling
* **Top Row Frozen**: Headers remain visible when scrolling down large sheets.
* **AutoFilter Enabled**: Dropdown filters on all columns for custom filtering.
* **Auto-Fit Widths & Text Wrapping**: Ensures clean readability without text truncation.
* **Safe Empty Results**: If no matching jobs are found on a particular day, valid workbooks with headers are still created without errors.

### Running Excel Exporter Tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_excel.py -v
```

---

## Naukri Job Collection Connector (Phase 6A)

The Naukri connector (`app/sources/naukri.py`) implements automated job collection and normalization into the standardized `Job` schema.

### Configuration (`.env`)

```ini
NAUKRI_ENABLED=true
NAUKRI_MAX_PAGES=1
NAUKRI_MAX_JOBS=10
NAUKRI_REQUEST_DELAY_SEC=2.0
```

### Safety & Access Control Principles

* **No Anti-Bot Bypass**: Adheres strictly to platform terms and access controls. Does not use stealth plugins, proxy rotation, CAPTCHA bypass, or fingerprint spoofing.
* **Graceful Degradation**: If automated access is blocked by the platform (e.g., HTTP 403 / Access Denied), the connector halts collection gracefully, logs an informative warning, and allows the remaining pipeline to proceed.
* **Zero Fake Data**: The connector will never fabricate mock jobs to make a blocked run appear successful.
* **Never Guess Easy Apply**: Easy Apply is set to `True` only when explicitly indicated by the listing; otherwise `False`.

### Running Naukri Connector Tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_naukri.py -v
```

---

## Lever Public Job Source (Phase 6B.1)

The Lever source connector (`app/sources/lever.py`) collects public job postings directly from Lever's public Postings API without requiring private accounts, API keys, or browser rendering.

### Public Postings API Mechanism

* Lever exposes a public endpoint intended for company career pages and custom integrations:
  `https://api.lever.co/v0/postings/<company>?mode=json`
* The connector requests publicly published job listings directly via standard HTTP (`urllib.request`).
* Lever posting data is mapped into the project's standardized `Job` model using stable posting IDs (`id` -> `source_job_id`) for historical SQLite deduplication.

### Configuration (`.env`)

```ini
# Lever Public Job Source Configuration
LEVER_ENABLED=false
LEVER_COMPANIES=
LEVER_MAX_JOBS_PER_COMPANY=100
LEVER_REQUEST_DELAY_SEC=1.0
```

Example configuration for testing or active use:
```ini
LEVER_ENABLED=true
LEVER_COMPANIES=example-company
LEVER_MAX_JOBS_PER_COMPANY=100
LEVER_REQUEST_DELAY_SEC=1.0
```
> **Note**: `example-company` above is strictly an illustrative placeholder example and is not claimed to be a real company. You can configure multiple comma-separated company identifiers: `LEVER_COMPANIES=company-one,company-two`. Whitespace is automatically stripped.

### Key Behaviors & Safety Controls

* **Company Identifier Configuration**: The connector targets specifically configured company sites rather than attempting internet-wide crawling. If `LEVER_COMPANIES` is empty, it logs an informational message and returns 0 jobs without error.
* **Enable / Disable Switch**: Setting `LEVER_ENABLED=false` prevents network requests entirely and returns 0 jobs cleanly.
* **Strict Safety & Compliance**: Does **not** bypass authentication, CAPTCHA, or rate limits. Does not use stealth browser plugins, proxy rotation, or fingerprint spoofing.
* **HTTP 401 / 403 / 429 Safety**:
  - `HTTP 401 / 403`: Access restriction is logged, and the connector stops querying that company safely.
  - `HTTP 429`: Rate limit is logged, and collection stops safely without aggressive retries.
  - `HTTP 404`: Logs that the company was not found and continues with remaining companies.
* **Location Integrity (Phase 6A.1 Compatibility)**: Missing locations are preserved as `None` (0 location points in matcher) and **never** defaulted to `"India"`. Multi-location postings (e.g. `Bangalore, India; Remote`) are preserved in a unified normalized string.
* **Rate Limiting & Delays**: Configured `LEVER_REQUEST_DELAY_SEC` is observed between company requests, and `LEVER_MAX_JOBS_PER_COMPANY` prevents any single company from overwhelming the pipeline.
* **Easy Apply**: Lever postings do not expose LinkedIn Easy Apply semantics; `easy_apply` is always explicitly set to `False`.

### Running Lever Connector Tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_lever.py -v
```

---

## Greenhouse Public Job Board Source (Phase 6C)

The Greenhouse source connector (`app/sources/greenhouse.py`) collects public job postings directly from Greenhouse's public Job Board API without requiring private accounts, API keys, or browser rendering.

### Public Job Board API Mechanism

* Greenhouse exposes an official, unauthenticated REST API intended for company career sites:
  `https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs?content=true`
* The connector requests publicly published job listings directly via standard HTTP (`urllib.request`).
* The parameter `content=true` includes complete HTML descriptions, department associations, office locations, and custom metadata fields.
* HTML descriptions are safely unescaped, block elements are converted into layout-preserving newlines, and markup is stripped.
* Posting IDs (`id`) are mapped directly to `source_job_id` as stable identifiers for SQLite deduplication.

### Configuration (`.env`)

```ini
# Greenhouse Public Job Board Configuration
GREENHOUSE_ENABLED=false
GREENHOUSE_COMPANIES=
GREENHOUSE_MAX_JOBS_PER_COMPANY=25
GREENHOUSE_REQUEST_DELAY_SEC=1.0
```

Example configuration for testing or active use:
```ini
GREENHOUSE_ENABLED=true
GREENHOUSE_COMPANIES=cloudflare
GREENHOUSE_MAX_JOBS_PER_COMPANY=25
GREENHOUSE_REQUEST_DELAY_SEC=1.0
```
> **Board Identifier Format**: `GREENHOUSE_COMPANIES` expects the company's unique Greenhouse board token (slug). This is the identifier that appears in the company's public Greenhouse URL (e.g., `https://boards.greenhouse.io/<board_token>`). Multiple comma-separated company identifiers are supported: `GREENHOUSE_COMPANIES=cloudflare,elastic`. Whitespace is automatically stripped.

### Key Behaviors & Safety Controls

* **Public-Access Only**: Operates strictly against Greenhouse's keyless public Job Board API. Does **not** require private API keys, Harvest API credentials, or authentication tokens.
* **Enable / Disable Switch**: Setting `GREENHOUSE_ENABLED=false` prevents network requests entirely and returns 0 jobs cleanly.
* **Strict Safety & Compliance**: Does **not** bypass authentication, CAPTCHA, or rate limits. Does not use stealth browser plugins, proxy rotation, or fingerprint spoofing.
* **HTTP 401 / 403 / 404 / 429 Safety**:
  - `HTTP 401 / 403`: Access restriction is logged, and collection stops safely for that company.
  - `HTTP 404`: Logs that the company board was not found and continues with remaining companies.
  - `HTTP 429`: Rate limit is logged, and collection stops safely without aggressive retries.
* **Location Integrity**: Missing locations are preserved as `None` (0 location points in matcher) and **never** defaulted to `"India"`. Multi-location postings across primary location and office entries (e.g. `Bangalore, India; Remote`) are preserved in a unified semicolon-separated string.
* **Easy Apply**: Greenhouse jobs do not expose LinkedIn Easy Apply semantics; `easy_apply` is always explicitly set to `False`.

### Running Greenhouse Connector Tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_greenhouse.py -v
```

---

## Running the Project Locally

Run the pipeline directly:

```powershell
.\venv\Scripts\python.exe -m app.main
```

### Running Tests

Execute the full test suite (covering profile validation, schema parsing, filtering, deduplication, SQLite persistence, and Excel exports):

```powershell
.\venv\Scripts\python.exe -m pytest -v
```

---

---

## Daily Pipeline & Reliability (Phase 7A)

The daily pipeline executes an end-to-end, deterministic batch process designed for unattended, repeatable daily operation:

```text
Run Job Finder
   ↓
Collect Listings across Sources (Lever, Greenhouse, Naukri, LinkedIn)
   ↓
Filter Listings against Profile Preferences & Seniority Rules
   ↓
Deterministic 100-Point Scoring & Category Grading
   ↓
In-Batch Deduplication (Canonical URL, Job ID, SHA-256 Fingerprint)
   ↓
SQLite Historical Upsert & Seen-Date Tracking (Run ID tagging)
   ↓
Excel Export (New Matches, Top Matches, All Relevant Jobs)
   ↓
Structured Run Summary & Pipeline Execution Record
```

### Unique Pipeline Run ID

Every pipeline execution generates a single, deterministic run identifier formatted as:
`YYYYMMDD-HHMMSS-<hex6>` (e.g. `20261007-095938-1aee1b`).
* Generated once per pipeline execution and logged immediately (`[RUN] Started: <run_id>`).
* Associated with all jobs encountered or refreshed during that execution (`last_seen_run_id`).
* Stored in the lightweight SQLite `pipeline_runs` table alongside start time, completion time, counts (raw collected, filtered, relevant, strong, excellent, new jobs, duplicates), and status (`COMPLETED`, `COMPLETED_WITH_SOURCE_WARNINGS`, `PARTIAL`, `FAILED`).

### Source Failure Distinction

The pipeline strictly distinguishes between **a source returning 0 jobs** versus **a source that could not be accessed**:
* If Naukri or another provider encounters an access denial (e.g., `HTTP 403`), anti-bot challenge, or network timeout, the connector safely halts without evasion or crashing.
* The source status is explicitly recorded as `BLOCKED (HTTP 403)` or `UNAVAILABLE` rather than disguised as "0 jobs collected, completed successfully".
* The overall pipeline status is marked as `COMPLETED_WITH_SOURCE_WARNINGS` so automated health checks can immediately detect degraded sources.

### Job Application Status Tracking

Each persistent job in SQLite tracks an explicit lifecycle status:

| Status | Meaning |
| :--- | :--- |
| `NEW` | Discovered by the pipeline, not yet reviewed or modified by the user. |
| `VIEWED` | Examined by the user. |
| `SHORTLISTED` | Flagged as a high-potential job to apply for. |
| `APPLIED` | Application submitted by user. |
| `REJECTED` | Candidate rejected or position filled. |
| `NOT_INTERESTED` | Dismissed by the user. |
| `INTERVIEW` | Interview stages underway. |
| `OFFER` | Job offer received. |

#### Status Preservation Guarantee
* When the pipeline rediscovers an existing job (e.g., in a subsequent daily run), mutable job details (description, salary, date posted) refresh, but **the tracking status is NEVER reset** (`APPLIED` remains `APPLIED`, `SHORTLISTED` remains `SHORTLISTED`).
* `first_seen_at` preserves the exact original timestamp of the job's initial discovery.
* `last_seen_at` and `last_seen_run_id` update to the timestamp and ID of the latest run.
* User notes (`notes`) and `status_updated_at` are strictly preserved across pipeline executions.

#### Programmatic Status Management (`app/services/job_tracker.py`)

Job status and notes can be updated programmatically using the `JobTracker` service:

```python
from app.database.database import DatabaseManager
from app.services.job_tracker import JobTracker
from app.models.job import JobStatus

db = DatabaseManager("data/jobs.db")
tracker = JobTracker(db)

# Update application status with optional notes
tracker.update_status(job_id=7, status=JobStatus.APPLIED, notes="Applied via company portal")

# Check status
current_status = tracker.get_status(job_id=7)  # Returns JobStatus.APPLIED
```

### Multi-Sheet Excel Reports & "New Matches" Rule

Each exported workbook (`data/exports/jobs_YYYYMMDD_HHMMSS.xlsx`) includes three dedicated worksheets:

1. **New Matches**: Contains **only** jobs that were discovered for the very first time during the current pipeline run (`first_seen_at == current run`) and satisfy the relevance threshold (`Match Score >= 60`). Previously seen jobs rediscovered today do **not** appear in this sheet.
2. **Top Matches**: Contains all jobs scoring `>= 80` ("Strong" and "Excellent"), regardless of whether they were first discovered today or in previous runs.
3. **All Relevant Jobs**: Contains all active candidate jobs scoring `>= 60`, preserving the entire catalog of qualified opportunities.

All 17 original columns are preserved in exact order, with additional tracking columns appended:
* Column 17: `Notes`
* Column 18: `Status` (e.g. `NEW`, `APPLIED`, `SHORTLISTED`)
* Column 19: `First Seen` (YYYY-MM-DD HH:MM:SS)
* Column 20: `Last Seen` (YYYY-MM-DD HH:MM:SS)

---

## Daily Automation on Windows

The project includes production-ready automated daily execution on Windows via a dedicated batch runner and Windows Task Scheduler.

> [!IMPORTANT]
> **Personal-Use Discovery Tool Only**: This project automatically discovers, scores, persists, and exports job opportunities to Excel. It **does NOT** submit automatic job applications, fill out browser forms, bypass CAPTCHAs, or send unsolicited emails. Application submission remains entirely manual under your control.

### 1. Manual Execution

You can test and run the daily pipeline manually from any terminal or directory:

```cmd
scripts\run_daily_job_finder.bat
```

Or from PowerShell / Command Prompt at any path:

```cmd
C:\path\to\job-finder-automation\scripts\run_daily_job_finder.bat
```

The runner automatically:
* Resolves the project root directory regardless of current working directory (`%~dp0..`).
* Locates and utilizes the project's existing virtual environment (`venv\Scripts\python.exe` or `.venv\Scripts\python.exe`).
* Acquires a file-based process lock (`data/job_finder.lock`) to prevent simultaneous runs.
* Executes the complete multi-source discovery, filtering, matching, and database pipeline.
* Captures all standard output and standard error into a timestamped log file.
* Rotates and purges log files older than 30 days (leaving database and Excel reports untouched).
* Returns a standardized, meaningful exit code.

### 2. Log Location & Rotation

Every automated or manual run creates a timestamped log file under:

```text
data/logs/job_finder_YYYYMMDD_HHMMSS.log
```

**Log Contents**:
* Run start timestamp, project root, and Python executable path.
* Pipeline initiation, profile preferences, and registered sources.
* Individual source collection outcomes and warnings (e.g. Naukri HTTP 403 status).
* In-batch deduplication, match score distributions, and SQLite upsert counts.
* Generated Excel report file path.
* Overall pipeline completion status and final exit code.
* **Security & Privacy**: API keys, passwords, cookies, and secrets are strictly excluded from logs.

**Log Retention**: The pipeline automatically retains the latest **30 days** of log files. Older `.log` files are automatically removed upon run completion. SQLite database files and exported Excel sheets are never deleted.

### 3. Exit Codes

The batch runner returns standardized exit codes:

| Exit Code | Meaning | Details |
|:---:|:---|:---|
| `0` | **Success** | Pipeline completed successfully. Includes runs with handled source warnings (e.g., Naukri HTTP 403 while Lever and Greenhouse succeed). |
| `1` | **Pipeline Failure** | Unhandled internal exception occurred. Detailed traceback is captured in the log. |
| `2` | **Runner / Environment Error** | Missing project root, Python executable, or `app/main.py`. |
| `3` | **Run in Progress** | Another instance is currently active (`data/job_finder.lock` active). Second pipeline execution was prevented. |

### 4. Overlap Prevention & Process Lock

To protect SQLite database integrity and prevent resource exhaustion, the pipeline uses a lightweight, Windows-safe file lock:

* **Lock File**: `data/job_finder.lock`
* **Lock Lifecycle**: Acquired upon pipeline start; released automatically upon completion or error.
* **Active Protection**: If another process attempts to start while a run is active, the second runner logs an explanatory message and immediately terminates with **exit code 3**.
* **Stale Lock Recovery**: If Windows crashes or shuts down abruptly during a run, future runs inspect the recorded PID via Windows kernel APIs. If the PID is dead or exceeds 4 hours, the stale lock is safely cleared and execution proceeds normally.

### 5. Windows Task Scheduler Setup

To schedule the job finder to run automatically every day:

1. Press `Win + R`, type `taskschd.msc`, and press **Enter**.
2. In the right-hand **Actions** panel, click **Create Task...** (do not use *Create Basic Task*).
3. **General Tab**:
   * **Name**: `Daily Job Finder Automation`
   * **Security options**: Select **Run only when user is logged on** (or *Run whether user is logged on or not* if you wish it to run while locked).
   * Uncheck *Run with highest privileges* (admin privileges are not needed).
4. **Triggers Tab**:
   * Click **New...** -> Select **Daily**.
   * Set your preferred daily time (e.g., `09:00:00 AM`).
   * Set *Stop task if it runs longer than* to `1 hour`.
5. **Actions Tab**:
   * Click **New...** -> Select **Start a program**.
   * **Program/script**: Browse and select `scripts\run_daily_job_finder.bat`.
   * **Start in (optional)**: Enter your full project root path (e.g., `C:\Users\<username>\job-finder-automation`).
6. **Conditions Tab**:
   * Under **Network**, check **Start only if the following network connection is available: Any connection**.
   * Under **Power**, uncheck *Start the task only if the computer is on AC power* if you use a laptop.
7. **Settings Tab**:
   * Check **Run task as soon as possible after a scheduled start is missed**.
   * Check **If the task fails, restart every: 10 minutes** (up to 3 times).
   * Select **Do not start a new instance** if the task is already running.

For detailed step-by-step instructions and XML import options, see [docs/windows-task-scheduler.md](file:///c:/Users/gauta/job-finder-automation/docs/windows-task-scheduler.md).

### 6. Verifying a Scheduled Run

1. In Task Scheduler, find **Daily Job Finder Automation** in the **Task Scheduler Library**.
2. Right-click the task and select **Run**.
3. Check the **Last Run Result** column: `The operation completed successfully. (0x0)`.
4. Open `data\logs\` and confirm that a new timestamped log was generated.
5. Open `data\exports\` and inspect the newly created Excel workbook.

### 7. Troubleshooting Failures

* **Exit Code 1**: Check the latest file in `data\logs\` for the Python stack trace.
* **Exit Code 2**: Ensure the virtual environment at `venv\Scripts\python.exe` exists and has required packages installed.
* **Exit Code 3**: A run is already in progress, or an abandoned run left a lock. If no Python process is running, delete `data\job_finder.lock`.
* **Missed Execution**: Ensure the condition *Run task as soon as possible after a scheduled start is missed* is checked in Task Scheduler.

### 8. Disabling or Removing the Scheduled Task

* **To Pause**: Open `taskschd.msc`, right-click **Daily Job Finder Automation**, and select **Disable**.
* **To Delete**: Right-click **Daily Job Finder Automation** and select **Delete**.

---

## Job Review Dashboard

Phase 8 introduces a simple, lightweight local web dashboard for reviewing collected jobs and tracking application lifecycles.

### 1. Purpose

The dashboard provides a personal desktop interface to:
* Review jobs collected from Lever, Greenhouse, Naukri, and other sources.
* Inspect 100-point deterministic match score breakdowns (roles, skills, locations, experience).
* Manage application status (`NEW`, `VIEWED`, `SHORTLISTED`, `APPLIED`, `INTERVIEW`, `OFFER`, `REJECTED`, `NOT_INTERESTED`).
* Add and update application notes (e.g., recruiter contacts, follow-up dates).
* Inspect historical pipeline execution runs and diagnose connector health (e.g., HTTP 403 blocks).
* Strictly preserve existing `APPLIED`, `INTERVIEW`, and `OFFER` statuses when the daily pipeline discovers the same job on future runs.

> **Note**: This is a personal desktop application designed solely for local use. It does **not** automate application submissions, fill employer forms, solve CAPTCHAs, or log into external job portals.

### 2. Quick Start

Ensure the virtual environment is activated, then launch using either method:

**Method A: Dedicated Windows Batch Script**
```cmd
scripts\run_dashboard.bat
```

**Method B: Python Module CLI**
```cmd
python -m app.dashboard
```

**Method C: Uvicorn Direct**
```cmd
uvicorn app.dashboard.app:app --host 127.0.0.1 --port 8000
```

### 3. Server URL & Access

Once started, open your web browser at:
```text
http://127.0.0.1:8000
```

### 4. Available Pages & Views

| Route | View Name | Description |
|:---|:---|:---|
| `/dashboard` | **Overview** | Summary KPI cards (Total, New, High Priority, Applied, Interview, Offer), top matches preview, recent pipeline runs, and connector health. |
| `/jobs` | **All Jobs** | Master job table with multi-parameter filtering, sorting, pagination, and quick status actions. |
| `/new-matches` | **New Matches** | Filtered view for newly discovered listings based on `first_seen_at` (today, last 3 days, last 7 days). |
| `/shortlisted` | **Shortlisted** | Dedicated queue for jobs bookmarked for application preparation. |
| `/applied` | **Applied** | Active applications tracker with notes and dates. |
| `/interviews` | **Interviews** | Jobs in active screening or technical interview rounds. |
| `/offers` | **Offers** | Received job offers and decision tracking. |
| `/jobs/{job_id}` | **Job Detail** | Full view of job metadata, original external URL, match scoring criteria, description, status updater, and notes editor. |
| `/pipeline-runs` | **Pipeline Runs** | Audit log of previous pipeline executions, collection counts, deduplication, and warnings. |
| `/source-health` | **Source Health** | Status indicators and diagnostic details for each job board collector. |

### 5. Filtering, Sorting & Search

* **Match Score**: Filter by threshold (`90+ Highest`, `80+ Strong`, `70+ Good`, `60+ Relevant`).
* **Status**: Filter by any valid `JobStatus` enum value.
* **Source**: Dynamically populated from distinct sources present in the database (e.g., `lever`, `greenhouse`, `naukri`).
* **Location & Company**: Filter listings by exact or partial company name and location.
* **Keyword Search**: Safe parameterized search matching across title, company, location, and description.
* **Sorting**: Sort by Match Score (desc/asc), Date Posted (newest/oldest), First Seen (newest/oldest), or Last Seen (newest/oldest).
* **Pagination**: Configurable page sizes (25, 50, 100 jobs per page) utilizing database-level SQL `LIMIT` / `OFFSET`.

### 6. Status & Notes Management

* **Application Status Updates**: Change statuses via the job detail page or quick actions on the job list. Status transitions update `status_updated_at` while preserving `first_seen_at`, `last_seen_at`, and user notes.
* **Persistent Notes**: Save freeform text notes (e.g., "Referral submitted via Jane Doe") directly to SQLite. Notes are strictly preserved and never overwritten by daily automated pipeline runs.
* **Applied Safety Rule**: Re-running the daily collector will never revert an `APPLIED`, `INTERVIEW`, or `OFFER` job back to `NEW`.

### 7. How to Stop the Dashboard

In the terminal or command window running the dashboard, press:
```text
Ctrl + C
```

### 8. Security & Local Architecture

* **Local Loopback Only**: The dashboard listens on `127.0.0.1` by default and is never exposed publicly.
* **SQL Injection Protection**: All SQLite queries use parameterized placeholders (`?`).
* **Safe HTML Rendering**: Descriptions and text fields are sanitized and HTML-escaped to prevent cross-site scripting (XSS).
* **No Secret Exposure**: Environment variables, API keys, and sensitive settings are never displayed in the UI or rendered in error pages.
* **No External Dependencies**: Custom Vanilla CSS and minimal JavaScript; no external CDN dependencies or paid UI libraries.

---

## Phase 9 — Job Recommendation Quality & Application Workflow

Phase 9 introduces an explainable, deterministic **Application Recommendation Layer** on top of the existing 100-point matching engine. While `match_score` answers *"How well does this job match my profile criteria?"*, the new `application_readiness_score` answers:

> **"How ready is this job for me to manually apply to right now?"**

Applications remain strictly **manual**. No auto-submitters, headless form fillers, or third-party paid/LLM APIs are used.

---

### 1. Application Readiness Score Formula (0–100)

The Readiness Score evaluates 5 deterministic components:

$$\text{Readiness Score} = \text{Match Quality (50)} + \text{Accessibility (15)} + \text{Experience Fit (15)} + \text{Skill Coverage (10)} + \text{Readiness Signals (10)}$$

#### A. Match Quality (50 Points Max)
Derived deterministically from the existing 100-point match score:
$$\text{Match Points} = \text{round}(\text{match\_score} \times 0.50)$$
* Example: 90 match score $\rightarrow$ 45.0 points
* Example: 80 match score $\rightarrow$ 40.0 points
* Example: 74 match score $\rightarrow$ 37.0 points

#### B. Application Accessibility (15 Points Max)
Evaluates whether a direct canonical posting URL exists and points to a recognized career board structure:
* **Valid direct job URL**: +10 points (valid `http`/`https` scheme and network location)
* **Known source or direct apply path**: +5 points (e.g. Lever, Greenhouse, Ashby, or paths containing `/jobs/`, `/postings/`, `/apply`, `/careers`)
* **Missing or invalid URL**: 0 points

#### C. Experience Fit (15 Points Max)
Deterministic parsing of structured experience criteria:
* **Explicit fresher / entry-level / 0–1 / 0–2 years**: +15 points
* **Unspecified / missing experience requirement**: +8 points
* **Explicit higher experience requirement (3+ years / senior / lead)**: 0 points

#### D. Skill Coverage (10 Points Max)
Calculated from matched profile skills:
* **5+ matched skills**: 10 points
* **3–4 matched skills**: 7 points
* **1–2 matched skills**: 4 points
* **0 matched skills**: 0 points

#### E. Application Readiness Signals (10 Points Max)
5 discrete metadata completeness signals (2 points each):
1. Direct apply URL available (+2)
2. Company and source known (+2)
3. Detailed job description available $\ge 50$ chars (+2)
4. Location explicitly specified (+2)
5. Job title clearly identified (+2)

---

### 2. Application Priority Rules

Every job is deterministically classified into an `ApplicationPriority`:

| Priority | Rules & Thresholds | Workflow Meaning |
| :--- | :--- | :--- |
| **URGENT** | Readiness $\ge 85$ **AND** Match Score $\ge 80$ (and status is not `APPLIED`, `INTERVIEW`, `OFFER`, `REJECTED`, or `NOT_INTERESTED`) | Apply today immediately. Top tier opportunity. |
| **HIGH** | Readiness $\ge 75$ **OR** Match Score $\ge 80$ | High fit; prioritize in the daily queue. |
| **NORMAL** | Readiness $\ge 60$ | Good opportunity; apply after urgent/high jobs. |
| **LOW** | Readiness $\ge 45$ | Lower readiness or missing critical information. |
| **SKIP** | Readiness $< 45$ | Low relevance or missing essential details. |

*Note: Inactive jobs (`APPLIED`, `REJECTED`, `NOT_INTERESTED`, `INTERVIEW`, `OFFER`) retain their priority for history, but are excluded from the `/apply-today` action queue.*

---

### 3. Skill-Gap Analysis

The deterministic analyzer compares job descriptions against the candidate's profile skills (`data/profile.json`) using a curated technical skills ontology:
* **Matched Skills**: Technologies present in profile and detected in the job listing.
* **Missing Skills**: Technologies required by the job that are not in candidate profile.
  * **Critical Gap**: Core languages/frameworks (e.g., Java, Spring Boot, C++, Go, Rust, .NET).
  * **Moderate Gap**: Databases, messaging, cloud platforms (e.g., Redis, Kafka, Kubernetes, AWS).
  * **Minor Gap**: Secondary tooling & methodologies (e.g., Linux, CI/CD, Terraform, Agile).

Technologies listed only in optional sections ("Nice to have", "Bonus", "Plus") are never elevated to critical gaps.

---

### 4. Explainable Match & Risk Reasons

Each recommended job generates human-readable, data-backed explanations:
* **Why This Job Matches**:
  * ✓ Role aligns with target position (e.g., Python Developer)
  * ✓ Matched technical skills (e.g., Python, FastAPI, SQL)
  * ✓ Preferred location hub or Remote / India eligible
  * ✓ Entry-level experience requirement
* **Possible Concerns**:
  * ⚠ Specific required technologies missing
  * ⚠ Higher experience requirement detected
  * ⚠ Weaker location preference
  * ⚠ Direct application URL missing

---

### 5. Application Checklist & Follow-Up Tracking

* **Informational Application Checklist**: A 10-step checklist covering description review, gap analysis, resume tailoring, portfolio preparation, manual portal submission, and status update.
* **Follow-up Tracking**: Record `follow_up_date` (YYYY-MM-DD) and `follow_up_notes` directly on the job detail page. Overdue or upcoming follow-ups are surfaced on the dashboard home page.

---

### 6. Daily Application Progress & Settings

Configure your daily application goal in `.env`:
```env
# Phase 9 Daily Target
DAILY_APPLICATION_TARGET=5
```

The system calculates progress using real database status records:
* **Target**: `DAILY_APPLICATION_TARGET` (default 5)
* **Applied Today**: Count of jobs with `status = 'APPLIED'` whose `status_updated_at` date equals today.
* **Remaining Today**: $\max(0, \text{Target} - \text{Applied Today})$.

---

### 7. Dashboard Enhancements

* **`/dashboard` Home Page**:
  * **Apply Today KPI Card**: Count of active actionable recommendations.
  * **Daily Application Target**: Real-time progress bar (e.g., `1 / 5 applied`).
  * **Urgent & High Priority**: Instant tally of top opportunities.
  * **Average Readiness**: Mean readiness score across active listings.
  * **Upcoming Follow-ups Table**: Real-time list of upcoming check-ins sorted by nearest date.
* **`/apply-today` Action Queue**:
  * Dedicated focused queue for manual applications.
  * Default view excludes already applied, interviewed, offered, or rejected jobs.
  * Filter by Priority (`Urgent`, `High`, `Normal`, `Low`), Minimum Readiness (`50+`, `60+`, `70+`, `80+`, `90+`), or Status.
  * Sort by Readiness Score, Match Score, Priority, Date Posted, or First Seen.
  * Quick-action buttons to directly transition jobs to `APPLIED`, `SHORTLISTED`, or `REJECTED`.
* **`/jobs/{job_id}` Job Detail**:
  * Application Summary & Match Summary cards.
  * Matched skills vs. Categorized Missing Skills pill badges.
  * "Why This Job Matches" list and "Possible Concerns" warning section.
  * Informational checklist.
  * Follow-up date picker and notes form (`POST /jobs/{job_id}/follow-up`).

---

### 8. Excel Export Enhancements

The `.xlsx` workbook generated by the pipeline now includes:
* **"Apply Today" Sheet**: Dedicated sheet containing all actionable high-priority jobs ordered by priority and readiness score.
* **New Columns across All Sheets**:
  * `Application Readiness`
  * `Application Priority`
  * `Profile Alignment`
  * `Missing Skills`
  * `Recommendation Reasons`
  * `Risk Reasons`
  * `Follow-up Date`
* **Workbook Navigation**: The primary active sheet remains `Top Matches`.

---

### 9. Running and Validating

#### Start the Dashboard
```powershell
venv\Scripts\python.exe -m app.dashboard
```
Open [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard) or [http://127.0.0.1:8000/apply-today](http://127.0.0.1:8000/apply-today).

#### Run the Automated Daily Pipeline
```cmd
scripts\run_daily_job_finder.bat
```

#### Run the Pytest Test Suite
```powershell
venv\Scripts\python.exe -m pytest -v
```
All 234 unit and integration tests pass with 0 failures and 0 skipped.

---

## Phase 10: Resume Intelligence & Job-Specific Application Preparation

Phase 10 introduces a deterministic **Resume Intelligence & Application Preparation Layer** designed to answer:
> **"How should I prepare for this specific job before I apply?"**

It builds on top of Phase 4 (`match_score`) and Phase 9 (`application_readiness_score`), without altering either of them, providing actionable preparation insights tailored to each individual job.

> **Important**: The system **does not** automatically modify or submit the candidate's resume or job application. It is strictly a personal-use, explainable advisory assistant for manual application preparation.

---

### 1. Resume Configuration & Privacy

Resume parsing and analysis are **100% local-first and private**. 
* **Zero External Calls**: Your resume text is never sent to OpenAI, Google, Anthropic, or any third-party resume API.
* **No Database Dumps**: Full resume text is never dumped into SQLite or printed into production logs.
* **Non-Destructive**: Resume files are strictly opened in read-only mode and are never overwritten or modified.

#### Configuration (`.env`)

```env
# Phase 10 Resume Configuration (Optional)
# Supports safe Windows absolute or relative paths to .pdf, .docx, .txt, or .md
# If left empty, the system automatically falls back to data/profile.json
RESUME_PATH=
```

#### Supported Formats & Profile Fallback
* **PDF**: Extracted locally using `pypdf`.
* **DOCX**: Extracted locally using `python-docx`.
* **TXT / Markdown**: Parsed directly via UTF-8 text readers.
* **Multi-Version Detection**: If a directory containing multiple resumes (e.g., `resume_backend.pdf`, `resume_ml.pdf`) is provided, the system parses all versions and automatically recommends the best-aligned version for each job.
* **Fallback Behavior**: If `RESUME_PATH` is left blank, points to a missing file, or encounters an unsupported file format, the pipeline logs a clean informational note and falls back to candidate data in `data/profile.json`.

---

### 2. Three Distinct Scoring Layers

The system maintains three completely independent, non-overlapping scores:

| Score | Question Answered | Formula Range |
|---|---|---|
| **Match Score** | *How well does the job match my target search profile?* | 0–100 (Role, Skills, Location, Exp) |
| **Application Readiness** | *How ready is this job for me to apply to today?* | 0–100 (Match, Direct URL, Recency, Status) |
| **Resume Alignment** | *How well does my resume communicate fit for this specific job?* | 0–100 (Role, Skills, Exp, Projects, Keywords) |

**Example**:
A job with Match Score 88, Readiness Score 87, and Resume Alignment 62 indicates that while the opportunity is an exceptional fit, your current resume needs targeted emphasis on specific projects or skills before submission.

---

### 3. Resume Alignment Score Formula (0–100)

The Resume Alignment Score is calculated deterministically across 5 dimensions:

1. **Role Alignment (30 points)**:
   * Target role match against job title (up to 15 points).
   * Resume experience and project titles matching job role words (up to 15 points).
2. **Skill Alignment (35 points)**:
   * Ratio of technical skills covered in candidate resume vs. total technical skills identified in the job description:
     * $\ge 80\% \rightarrow 35 \text{ pts}$
     * $\ge 60\% \rightarrow 28 \text{ pts}$
     * $\ge 40\% \rightarrow 20 \text{ pts}$
     * $\ge 20\% \rightarrow 14 \text{ pts}$
     * $> 0\% \rightarrow 8 \text{ pts}$
3. **Experience Alignment (15 points)**:
   * Evaluates internship and work experience against entry-level / junior expectations.
4. **Project Alignment (10 points)**:
   * Overlap score of candidate's featured projects with the technologies demanded by the job.
5. **Keyword Coverage (10 points)**:
   * Proportion of extracted high/medium-priority job keywords reflected in the resume.

#### Categorical Ratings
* **Strong Alignment**: 80–100
* **Good Alignment**: 65–79
* **Partial Alignment**: 50–64
* **Low Alignment**: 0–49

---

### 4. Deterministic Keyword & Skill Analysis

* **Keyword Prioritization**:
  * **High Priority**: Terms appearing in required sections (*"requirements"*, *"must have"*, *"qualifications"*, *"experience with"*).
  * **Medium Priority**: Terms appearing in responsibility sections (*"responsibilities"*, *"skills"*, *"preferred"*).
  * **Low Priority**: Terms appearing in optional sections (*"nice to have"*, *"bonus"*, *"optional"*).
* **Skills to Emphasize**: Highlights candidate skills that directly match the job requirements (sorted by requirement frequency and prominence).
* **Truthful Advisories (No False Claims)**:
  * The system **never** encourages keyword stuffing or fabricating skills.
  * For missing keywords not found in the candidate profile, the system provides a truthful disclaimer:
    > *"Potential concern: Job asks for [Skill], which is not present in your candidate profile. Do not add it unless you genuinely have this experience."*

---

### 5. Project & Experience Matching

* **Project Recommendation**: Evaluates existing candidate projects (from `profile.json` or resume) and ranks them using deterministic skill overlap, returning the best project and an explanation (e.g., *"Demonstrates hands-on implementation of Python, OpenCV, FastAPI"*).
* **Experience Recommendation**: Highlights the most relevant internship or experience entry matching the role.

---

### 6. Preparation Status Workflow & Notes

Each job tracks a dedicated preparation status separate from its application status:
* `NOT_REVIEWED`: Default initial state.
* `REVIEWED`: Job description and gap analysis reviewed.
* `RESUME_READY`: Tailored resume draft ready.
* `READY_TO_APPLY`: Candidate ready to initiate manual submission on employer portal.

Candidates can record custom `preparation_notes` (e.g., *"Highlight FastAPI microservices; attach ML resume version"*), stored independently from general application `notes`.

---

### 7. Dashboard Enhancements

* **`/resume-preparation`**: Dedicated queue showing all high-priority jobs (`URGENT`, `HIGH`) requiring preparation. Includes alignment score badges, skills to emphasize, missing keywords, recommended projects, concerns, and inline status updates.
* **`/jobs/{job_id}#resume-prep`**: Detailed preparation card with full checklist, skills breakdown, project details, and dedicated preparation notes form (`POST /jobs/{job_id}/preparation`).
* **KPI Metrics**: Dashboard cards for Preparation Urgent/High counts, Ready-to-Apply counts, and Average Resume Alignment.

---

### 8. Excel Export Enhancements

The exported Excel workbook (`data/exports/jobs_report_*.xlsx`) includes:
* **"Resume Preparation" Sheet**: Dedicated sheet containing all jobs ordered by resume alignment score.
* **9 New Phase 10 Columns Across All Sheets**:
  * `Resume Alignment`
  * `Resume Alignment Category`
  * `Skills to Emphasize`
  * `Missing Resume Keywords`
  * `Recommended Project`
  * `Recommended Experience`
  * `Resume Concerns`
  * `Recommended Resume`
  * `Preparation Status`

---

## Phase 11 — Application Command Center & Interview Preparation

Phase 11 introduces a unified **Application Command Center** and a deterministic **Interview Preparation Engine**, providing end-to-end guidance from the moment an application is shortlisted through interview scheduling and offer/rejection resolution.

> **CRITICAL SAFETY NOTICE**:
> This remains a **personal-use, local application**. Applications remain **strictly manual**. The system does **NOT** perform automatic job applications, form submissions, browser automation for submission, automated login, CAPTCHA bypass, or scrape credentials. Furthermore, all interview preparation questions and guidance are **100% deterministic and local**, derived strictly from job descriptions and candidate profile data without external LLM APIs, embeddings, or fabricated company claims.

### 1. End-to-End Application Workflow

```text
JOB FOUND
   ↓
MATCH SCORE (0-100)
   ↓
APPLICATION READINESS (0-100)
   ↓
RESUME ALIGNMENT (0-100)
   ↓
RESUME PREPARATION (NOT_REVIEWED → REVIEWED → RESUME_READY → READY_TO_APPLY)
   ↓
APPLY MANUALLY (User applies directly on career portal)
   ↓
APPLICATION TRACKING (Status: APPLIED, applied_at recorded)
   ↓
FOLLOW-UP (Due date tracking, follow-up notes)
   ↓
INTERVIEW PREPARATION (Deterministic topic extraction, project & technical Qs)
   ↓
INTERVIEW (Stage tracking: HR, Tech Screen, Coding, System Design, Behavioral)
   ↓
OFFER / REJECTION
```

---

### 2. Application Command Center (`/applications`)

A comprehensive dashboard for managing the active candidate pipeline:
* **Application Pipeline Bar**: Visual count and progression across all key lifecycle states:
  * `NEW` → `VIEWED` → `SHORTLISTED` → `APPLIED` → `INTERVIEW` → `OFFER`
  * With `REJECTED` and `NOT_INTERESTED` displayed separately.
* **Multi-Dimensional Filters**: Filter listings by Status, Priority (`URGENT`, `HIGH`, `NORMAL`, `LOW`), Minimum Match Score, Source, Follow-up Status (`due`, `overdue`, `upcoming`, `none`), and Interview Status (`SCHEDULED`, `COMPLETED`, `PASSED`, `FAILED`, `RESCHEDULED`, `none`).
* **Sorting Capabilities**: Sort by newest, oldest, highest match score, highest readiness, highest application priority, upcoming follow-up date, or upcoming interview date.
* **Rich Application Cards**: Displays match, readiness, resume alignment, applied date, interview schedule, follow-up alerts, and direct links to job portals and prep workspace.

---

### 3. Daily Action Plan (`/today`)

Answers the core question: **"What applications do I need to work on today?"**

Deterministically evaluates all jobs in the database and generates an ordered, actionable daily task queue across 7 strict priority tiers:

1. **Tier 1: Interview Today** (`URGENT_INTERVIEW`): Interview scheduled for today.
2. **Tier 2: Interview Soon** (`UPCOMING_INTERVIEW`): Interview scheduled within the next 3 days.
3. **Tier 3: Follow-up Due** (`FOLLOW_UP_DUE`): Follow-up date is today or overdue.
4. **Tier 4: Urgent Apply Today** (`URGENT_APPLY`): Recommendation priority is `URGENT` and job is not yet applied.
5. **Tier 5: High Priority Applications** (`HIGH_PRIORITY_APPLY`): Recommendation priority is `HIGH` and not yet applied.
6. **Tier 6: Resume Preparation Needed** (`RESUME_PREP_NEEDED`): High-priority relevant job with incomplete resume preparation (`NOT_REVIEWED` or `REVIEWED`).
7. **Tier 7: Other Recommended Jobs** (`GENERAL_RECOMMENDED`): Other relevant matches awaiting user review.

Each action card details **why** the action was flagged (e.g., *"Interview scheduled today: Technical Screening"*, *"Follow-up due: 2 days overdue"*, *"Urgent priority: High readiness (92)"*).

---

### 4. Deterministic Interview Preparation Engine (`/interview-prep`)

Answers the core question: **"I have an interview for this job. What should I prepare?"**

The interview preparation engine (`app/services/interview_preparation.py`) executes 100% locally with zero external LLM calls or paid APIs:

* **Technical Skills Ontology**: Extracts topics matching known skills from the job description (Python, JavaScript, TypeScript, React, Next.js, FastAPI, REST APIs, SQL, PostgreSQL, MongoDB, Machine Learning, Scikit-learn, OpenCV, NLP, Git) and identifies core concepts and sample technical questions.
* **Role-Specific Interview Modules**: Dynamically constructs focus areas and likely technical topics based on detected matched roles:
  * *Python Developer*: Python internals, OOP, data structures, exceptions, async/concurrency, FastAPI/Flask, ORMs.
  * *Backend Developer*: REST APIs, HTTP status codes, authentication/JWT, database indexing, transactions, API design, scalability.
  * *Full Stack Developer*: React component state, TypeScript, client-server lifecycle, state management, REST integration.
  * *AI/ML Engineer*: Model evaluation (precision/recall/F1/ROC-AUC), overfitting prevention, feature engineering, Scikit-learn pipelines.
* **Candidate Project Questions**: Leverages candidate's actual projects from `data/profile.json` (e.g., *Loan Application Fraud Detection*, *NeuroNest Notes & Bookmarks*) and generates questions relevant to the specific technologies required by the job.
* **Skill Gap Analysis**: Classifies technical skills into *Matched Skills*, *Skills to Revise*, and *Missing / Weaker Skills* (categorized by severity: critical, moderate, minor).
* **General HR / Behavioral Preparation**: Provides standard behavioral frameworks (STAR method) and common questions (*"Tell me about yourself"*, *"Why this role?"*, *"Overcoming technical roadblocks"*), clearly labeled as **General interview questions**.
* **Job-Specific Technical Questions**: Generates technical interview questions derived directly from the job description's extracted skills, clearly labeled as **"Likely questions based on job description (not company-specific)"**.
* **Questions to Ask the Employer**: Curated role-relevant questions to ask hiring managers and engineers.
* **Preparation Checklist & Status**: Tracks readiness through `NOT_STARTED` → `IN_PROGRESS` → `READY` → `COMPLETED`.

---

### 5. Application Timeline & Lifecycle Tracking

On each Job Detail page (`/jobs/{job_id}`):
* **Application Timeline Stepper**: Dynamically visualizes verified lifecycle milestones:
  * `Job Found` → `Viewed` → `Shortlisted` → `Resume Prepared` → `Applied` → `Follow-up` → `Interview Scheduled` → `Interview Completed` → `Offer`
  * Displays real timestamps (`first_seen_at`, `applied_at`, `follow_up_date`, `interview_date`) without fabricating historical events.
* **Persistent `applied_at`**: Transitioning a job to `APPLIED` sets `applied_at` to the current timestamp. Subsequent transitions to `INTERVIEW` or `OFFER` strictly preserve the original application timestamp.
* **Interview Tracking Form**: Record `interview_date`, `interview_stage` (HR, Technical Screening, Coding Round, Technical Interview, Managerial, System Design, Behavioral, Final, Other), `interview_status` (NOT_SCHEDULED, SCHEDULED, COMPLETED, PASSED, FAILED, RESCHEDULED), and `interview_notes`.

---

### 6. Excel Export Enhancements

The exported Excel workbook includes:
* **Sheet 6: "Applications"**: Filtered view of all jobs in `APPLIED`, `INTERVIEW`, or `OFFER` status.
* **Sheet 7: "Interview Preparation"**: Jobs with scheduled interviews or marked as ready for interview preparation.
* **6 New Phase 11 Columns Across All Sheets**:
  * `Applied At`
  * `Interview Date`
  * `Interview Stage`
  * `Interview Status`
  * `Interview Prep Status`
  * `Interview Notes`

---

## Phase 12 — Application Analytics & Strategy Optimization

Phase 12 delivers an end-to-end **Application Analytics & Strategy Optimization Dashboard** (`/analytics`), providing local, deterministic performance measurement to answer two critical strategic questions:
1. *"Is my job-search strategy actually working?"*
2. *"What should I change to get better results?"*

> **IMPORTANT SCIENTIFIC & SAFETY DISCLAIMER**:
> Analytics describe **observed application data and do not prove causation**. This remains a **100% local, personal application**. All metrics and recommendations are calculated deterministically using SQLite aggregations. There are **NO external analytics services, NO cloud uploads, NO paid APIs, and NO generative LLM inferences**.

### 1. Application Funnel Architecture

The pipeline funnel evaluates real database progression without fabricating historical events:

```text
Jobs Found (Total database volume)
   ↓
Relevant Jobs (Match Score ≥ 60)
   ↓
Recommended Jobs (Priority: URGENT, HIGH, NORMAL)
   ↓
Manual Applications (Status: APPLIED, INTERVIEW, OFFER — 1 record = 1 application)
   ↓
Interviews (Status: INTERVIEW or interview scheduled/completed)
   ↓
Offers (Status: OFFER)
```
* With `Rejected` and `Not Interested` displayed separately as terminal classifications.

---

### 2. Core Metrics & Conversion Rate Formulas

All rates feature **zero-denominator protection** (displaying `N/A` instead of `0%` or divide-by-zero errors when data is missing):

* **Application Rate**:
  $$\text{Application Rate} = \frac{\text{Applications}}{\text{Relevant Jobs}} \times 100$$
* **Recommendation → Application Rate**:
  $$\text{Rec} \rightarrow \text{App Rate} = \frac{\text{Applications}}{\text{Recommended Jobs}} \times 100$$
* **Interview Rate**:
  $$\text{Interview Rate} = \frac{\text{Interviews}}{\text{Applications}} \times 100$$
* **Offer Rate**:
  $$\text{Offer Rate} = \frac{\text{Offers}}{\text{Applications}} \times 100$$
* **Interview → Offer Rate**:
  $$\text{Interview} \rightarrow \text{Offer Rate} = \frac{\text{Offers}}{\text{Interviews}} \times 100$$

---

### 3. Small Dataset Protection

To protect the user from drawing misleading conclusions from early-stage job searching:
* **Threshold $\text{Applications} < 3$**: Automatically triggers a prominent limitation banner:
  > *"Limited Application Sample Size: Only N application(s) recorded. Statistical conversion trends require at least 3–5 tracked applications before drawing firm conclusions."*
* **Threshold $\text{Interviews} < 3$**: Advises accumulating further manual application volume before revising target roles or resume framing.
* **Threshold $\text{Jobs per Source} < 5$**: Labels Source Quality Score as `"Insufficient data"` rather than making strong claims.

---

### 4. Deterministic Source Quality Score (0–100)

Evaluates the genuine yield of each job board or ATS connector:

$$\text{Quality Score} = (\text{Relevance Rate} \times 0.40) + (\text{Recommended Rate} \times 0.25) + (\text{App Rate} \times 0.20) + (\text{Interview Rate} \times 0.15)$$

* **$\ge 75.0$**: Strong Quality
* **$50.0 - 74.9$**: Moderate Quality
* **$25.0 - 49.9$**: Developing
* **$< 25.0$**: Low Conversion
* **$< 5\text{ jobs}$**: Insufficient data (Protected)

---

### 5. Multi-Dimensional Performance Analysis

* **Role Performance**: Normalizes and groups opportunities across target roles from `profile.json` (*Python Developer, Backend Developer, Software Engineer, Full Stack Developer, ML Engineer, SDE Intern*).
* **Location Performance**: Aggregates opportunities across preferred geographies (*Bangalore / Bengaluru, Remote / India Eligible, Delhi / NCR, Ahmedabad, Pan India*).
* **Score Tiers Analysis**:
  * *Match Score Buckets*: `90–100` (Excellent), `80–89` (Strong), `70–79` (Good), `60–69` (Possible), `< 60` (Not Relevant).
  * *Readiness Score Buckets*: `85–100` (Urgent), `75–84` (High), `60–74` (Moderate), `< 60` (Low/Skip).
  * *Resume Alignment Buckets*: `80–100` (Strong Alignment), `65–79` (Good), `50–64` (Partial), `< 50` (Low).
* **Application Accessibility**: Compares `Easy Apply` vs `Direct Portal / External` application conversion.
* **Observed Technical Skills**: Quantifies frequency of skills (e.g. Python, SQL, FastAPI, React) appearing in submitted and interview applications (labeled strictly as *"Observed in your application data"*).

---

### 6. Daily Application Targets & Consistency Streak

* **Daily Target Tracking**: Reuses `DAILY_APPLICATION_TARGET` (default 5/day), tracking `applied_today`, `remaining`, `7-day daily average`, and `target achievement percentage`.
* **Application Consistency Streak**: Tracks consecutive calendar days where at least 1 manual application was submitted via `applied_at`. Automatic job scraping does not count toward the streak.

---

### 7. Excel Analytics Export

Exported workbooks (`data/exports/jobs_report_*.xlsx`) include a dedicated **Sheet 8: "Analytics"**:
* Overall pipeline funnel and conversion rate table
* Source connector performance breakdown
* Score tier distributions (Match and Readiness)
* Column auto-fit with header formatting

---

## Phase 13: Job Search Intelligence & Source Optimization

A deterministic, local-first intelligence layer that learns from historical collections to answer critical questions:
1. Which job sources are genuinely producing relevant, applicable opportunities?
2. Which sources produce recommended jobs?
3. Which target roles produce the strongest candidate pipelines?
4. Which geographic corridors produce the best match yields?
5. Which sources should receive increased or decreased search depth?
6. What search strategy and budget allocation should guide future daily collection runs?
7. What configured profile areas have insufficient historical coverage?

> [!IMPORTANT]
> **Core Principle**: Search Intelligence recommends where to focus future search effort. It does **not** automatically modify the user's profile or source configuration, change matcher weights, or submit job applications. The user remains completely in control.

---

### 1. Statistical Confidence & Small-Data Protection

To prevent overfitting or drawing unjustified conclusions from early or sparse collections:
* **`INSUFFICIENT_DATA` ($< 5$ jobs)**:
  * Prevents small samples (e.g. 2 jobs, 1 relevant) from being prematurely declared the "best source".
  * Source Quality Score is suppressed to `"Insufficient data"` ($None$).
  * Source action is set to `INSUFFICIENT_DATA` with `MONITOR` priority.
  * Search budget defaults to equal baseline allocation across active sources.
* **`LIMITED_DATA` ($5–9$ jobs)**:
  * Provides directional recommendations while clearly flagging sample limitations.
  * Quality scores unlock, but confidence remains guarded.
* **`ACTIONABLE_DATA` ($\ge 10$ jobs)**:
  * Full statistical confidence for firm source prioritization and search corridor decisions.

---

### 2. Source Search Depth Recommendations

Evaluates each job board / ATS connector and generates actionable guidance:
* **`INCREASE_SEARCH_DEPTH`**:
  * Triggered when a source demonstrates strong relevance yield ($\ge 50\%$) or high quality score ($\ge 60$) combined with high preferred/Indian geographic alignment ($\ge 30\%$).
  * Recommends expanding scraping frequency or company lists on this connector.
* **`MAINTAIN_SEARCH_DEPTH`**:
  * Triggered for operational sources with moderate, balanced conversion performance.
* **`REDUCE_SEARCH_DEPTH`**:
  * Triggered when a source produces low relevant yield ($< 20\%$) or consists predominantly of foreign-only listings ineligible for Indian candidates.
* **`MONITOR`**:
  * Assigned to blocked, rate-limited, placeholder, or disabled sources.
  * *Blocked Source Protection*: When a source encounters anti-bot (e.g. HTTP 403/429), it is **never** penalized as "bad quality"; the system explicitly reports that quality could not be evaluated due to access restrictions.
* **`INSUFFICIENT_DATA`**:
  * Assigned when sample size is below the 5-listing threshold.

---

### 3. Role & Location Corridor Intelligence

* **Target Role Intelligence**:
  * Analyzes each target role configured in `profile.json` (*Python Developer, Backend Developer, Software Engineer, Full Stack Developer, ML Engineer, SDE Intern*, etc.).
  * Calculates volume, relevant jobs, recommended jobs, average match score, average readiness score, and resume alignment.
  * Deterministically ranks roles (e.g. `"Software Engineer searches currently produce stronger opportunities than Python Developer searches"`).
* **Geographic Corridor Intelligence & India Eligibility**:
  * Groups locations across preferred corridors (*Bangalore / Bengaluru, Delhi / NCR, Noida, Ahmedabad, Pan India, Remote*).
  * Reuses Phase 6F regex intelligence to distinguish **India-eligible remote** from **foreign-only remote** (e.g. Canada, UK, Poland).
  * Foreign-only remote listings are isolated with `LOW` priority and excluded from India-eligible focus.
* **Role × Location Matrix**:
  * Cross-analyzes `Role × Location` pairs (e.g. *Software Engineer + Bangalore*, *AI Engineer + Remote India*).
  * Highlights high-yield corridors as `"Strong Opportunity"` or `"Promising Opportunity"`.

---

### 4. Search Coverage Gaps

* Automatically scans all target roles and preferred locations in `profile.json`.
* Identifies configured areas with 0 historical jobs or 0 relevant jobs.
* Flags them as `SEARCH_GAP` (`ROLE_GAP` or `LOCATION_GAP`).
* Uses careful, realistic phrasing: `"Insufficient historical coverage"` rather than `"There are no jobs"`.

---

### 5. Recommended Search Effort Allocation (Search Budget)

* Generates a recommended percentage distribution of future scraping effort across sources.
* Factors in source quality, relevant yield, preferred Indian location match, sample size, and endpoint reliability.
* **Normalization**: The allocated percentages strictly sum to **exactly 100.0%**.
* When sample size is small or data is insufficient, gracefully falls back to a neutral equal allocation (e.g. 25.0% each).
* Clearly labeled as a recommendation only—never modifies `.env` caps automatically.

---

### 6. Search Strategy Synthesis & Dashboard Integration

* **Dashboard Route**: Available at [`/search-intelligence`](http://127.0.0.1:8000/search-intelligence) and linked directly from the sidebar navigation.
* Displays:
  * Overall Strategy Status (`HEALTHY`, `DEVELOPING`, `DATA_LIMITED`, `NEEDS_ATTENTION`)
  * Data Confidence level badge (`ACTIONABLE_DATA`, `LIMITED_DATA`, `INSUFFICIENT_DATA`)
  * Ranked Discovery Corridors (Today's top 5 search priorities)
  * Key Recommended Actions & Active Safeguards
  * Normalized Search Budget visual distribution bar
  * Source Performance & Depth Recommendations table
  * Target Role & Geographic Corridor breakdowns
  * Top Role × Location Combinations table
  * Search Coverage Gaps exploration cards

---

### 7. Excel Search Intelligence Export

Exported workbooks (`data/exports/jobs_report_*.xlsx`) include a dedicated **Sheet 9: "Search Intelligence"**:
* Section 1: Search Strategy Header (Status, Confidence, Summary, Key Actions, Ranked Priorities)
* Section 2: Detailed Search Recommendations Table:
  * *Columns*: Recommendation Type, Source, Role, Location, Jobs Found, Relevant Jobs, Recommended Jobs, Average Match, Average Readiness, Confidence, Recommendation, Explanation.
* Section 3: Coverage Gaps & Search Budget Allocations.
* Preserves all 8 previous worksheets intact.

---

## Advanced Personal Job-Agent Workflow (Phase 14)

Phase 14 delivers a unified daily command center orchestrating search, evaluation, resume preparation, follow-up tracking, interview preparation, and analytics into a prioritized daily execution plan.

> **CRITICAL HUMAN-CONTROLLED NOTICE:**
> The Job Agent coordinates recommendations and actions. It does not automatically submit job applications or communicate with employers. All actual job applications remain strictly **MANUAL**.

---

### 1. Unified Daily Command Center

The Job Agent answers the core daily question: **"What should I do today?"** by analyzing current database state across the entire job-search lifecycle:

```text
Search (Phase 1-6)
  ↓
Review & Match (Phase 9)
  ↓
Resume Preparation (Phase 10)
  ↓
Manual Application (Human-Controlled)
  ↓
Follow-Up Intelligence (Phase 11)
  ↓
Interview Preparation (Phase 11)
  ↓
Funnel Analytics & Daily Goals (Phase 12)
  ↓
Search Intelligence & Source Optimization (Phase 13)
```

### 2. Action Prioritization Hierarchy

Actions are deterministically generated from live database records and ranked into four clear priority tiers:

* **`URGENT`**
  * Overdue follow-ups (`follow_up_date < today`).
  * Follow-ups scheduled for today (`follow_up_date == today`).
  * Imminent interviews scheduled within 3 days.
  * Application neglect alerts (e.g. applied > 5 days ago without a scheduled follow-up).
  * High-urgency ready-to-apply opportunities.
* **`HIGH`**
  * Top new match recommendations needing manual application.
  * Resume preparation for high-value jobs (Match $\ge 75$ or Priority `HIGH`/`URGENT`).
  * Interview preparation for scheduled interviews further out.
* **`MEDIUM`**
  * Routine recommended jobs (Match $\ge 60$).
  * Approaching follow-ups (due in 2–5 days).
  * Search Intelligence strategy review (Phase 13 corridors and gap review).
* **`LOW`**
  * Analytics funnel & daily application target progress check.
  * Lower-priority job reviews.

### 3. Orchestration Ranking Algorithm

The agent uses a deterministic orchestration score combining:
1. **Urgency Weight**: Overdue follow-ups (+160) > Imminent interviews (+150) > Neglected applications (+115) > Ready to apply (+85) > Resume prep (+75) > Strategy (+45) > Review (+40) > Analytics (+20).
2. **Quality & Fit Signals**: Match score ($35\%$), Application readiness score ($25\%$), Resume alignment score ($15\%$).
3. **Daily Target Urgency**: Prioritizes manual submissions when daily goal remains incomplete.

*Note: This is an orchestration score only. It does not alter underlying match or readiness formulas.*

### 4. Component Integrations

* **Resume Preparation (Phase 10)**:
  * For recommended jobs, identifies matched keywords, missing keywords, and recommended projects (*e.g., Loan Application Fraud Detection*).
  * Never fabricates resume credentials or automatically modifies user files.
* **Interview Preparation (Phase 11)**:
  * Automatically populates technical topics, likely technical questions, and a 6-step checklist for upcoming interviews.
  * Prioritizes interviews chronologically (earliest first).
* **Follow-up Intelligence & Neglect Detection**:
  * Tracks scheduled follow-ups and identifies neglected applications (> 5 days without a follow-up, or > 14 days without an update).
  * Uses objective, careful language (*"Needs attention: Applied 7 days ago with no follow-up scheduled"*).
* **Daily Application Target (Phase 12)**:
  * Integrates `DAILY_APPLICATION_TARGET` (default: 5) and displays real progress percentage and active streaks without synthetic numbers.
* **Search Intelligence (Phase 13)**:
  * Displays top source, role, and geographic corridors directly inside the daily command center.

### 5. Dashboard Route (`/job-agent`)

* Located at [`/job-agent`](http://127.0.0.1:8000/job-agent) and accessible from the primary sidebar navigation.
* Displays:
  * **Today's Summary**: 8 metric cards (Found Today, Relevant, Recommended, Applied Today, Target Remaining, Upcoming Interviews, Due Follow-ups, Overdue Actions).
  * **Target Progress Bar**: Real-time progress toward the 5-application daily target with active streak badge.
  * **Urgent Actions Queue**: Top priority tasks requiring immediate action today.
  * **Today's Applications**: Action cards for jobs ready for manual portal submission.
  * **Search Focus**: Top recommendations and hiring corridors from Phase 13.
  * **Safety Guardrails**: Transparent audit notices confirming zero auto-apply automation.

### 6. Excel Sheet 10: "Job Agent"

Exported workbooks now include a 10th dedicated sheet: **`Job Agent`**:
* **Columns**: Action Priority, Action Type, Job, Company, Match Score, Readiness, Resume Alignment, Lifecycle Status, Due Date, Recommended Action, Reason.
* Color-coded priority tiers (Soft Red for `URGENT`, Amber for `HIGH`, Blue for `MEDIUM`).
* Preserves all 9 previous sheets intact.

### 7. Explicit Safety Rules & Limitations

* **No Automated Applications**: The system never navigates portal forms, clicks submit buttons, or bypasses CAPTCHAs.
* **No External LLM / Paid APIs**: 100% deterministic, local-first Python logic.
* **No Silent Status Alterations**: User manual review is required to transition job states. Marking an agent action as complete does not mutate the database record.

---

## Phase 15 — Final Hardening & Production Readiness

Phase 15 completes the project lifecycle by solidifying operational safety, configuration integrity, diagnostic utilities, and automated database backup/recovery for everyday local use.

> **Core Philosophy**:
> The application discovers, scores, prioritizes, and prepares opportunities, but **does not automatically submit job applications**. All final applications remain strictly user-initiated and manual.

---

### 1. System Health & Environment Diagnostics

Validate your local environment, database schema, required directories, and dependencies at any time with a single command:

```powershell
python -m app --health
```

Output:
```text
==================================================
Daily Job Finder Automation - System Health Status
==================================================
Environment       : PASS
Configuration     : PASS
Database          : PASS
Profile           : PASS
Export Directory  : PASS
Log Directory     : PASS
Task Runner       : PASS
Backup Directory  : PASS
--------------------------------------------------
Overall           : HEALTHY
==================================================
```

### 2. Automated SQLite Database Backup

Safely backup the active SQLite database without stopping the application or locking tables:

```powershell
python scripts/backup_database.py
```

* **Storage Location**: `data/backups/jobs_YYYYMMDD_HHMMSS.db`
* **Safe Online API**: Uses SQLite's native `sqlite3.connect.backup()` streaming API.
* **Validation**: Immediately verifies the backup using `PRAGMA quick_check` and compares row counts against the active database.
* **Retention Policy**: Automatically purges backups older than `DATABASE_BACKUP_RETENTION_DAYS` (default: 30 days) that strictly match the backup filename pattern.

Example output:
```text
==================================================
SQLite Database Backup Successful
==================================================
Source:            data/jobs.db
Backup:            data/backups/jobs_20261009_004500.db
Source jobs:       7
Backup jobs:       7
Backup validation: PASS (Valid SQLite DB, 7 jobs verified)
Retention policy:  30 days
Backups retained:  1
Backups pruned:    0
==================================================
```

### 3. Safe Database Restore Tool

Restore your database from an explicitly selected timestamped backup:

```powershell
python scripts/restore_database.py data/backups/jobs_YYYYMMDD_HHMMSS.db
```

* **Interactive Confirmation**: Prompts for explicit verification token: `Type RESTORE to continue:`
* **Pre-Restore Safety Snapshot**: Automatically creates a safety backup (`data/backups/pre_restore_safety_*.db`) before touching the live database.
* **Integrity Validation**: Refuses non-SQLite files, corrupted backups, or backups missing the `jobs` table.
* **Automated Flag**: For testing or scheduled recovery, use `--yes` or `--confirm RESTORE`.

### 4. Read-Only Database Integrity Audit

Diagnose database consistency, verify application counts, detect duplicate records, and check lifecycle relationships without modifying any data:

```powershell
python scripts/audit_database.py
```

* **Strict Canonical Applications**: A job is only counted as an application when `status IN ('APPLIED', 'INTERVIEW', 'OFFER')`.
* **Historical Timestamp Auditing**: Historical `applied_at` timestamps on non-application jobs are safely reported as historical notices without altering the record.
* **Interview & Follow-up Consistency**: Identifies overdue follow-ups, date discrepancies, and missing statuses.
* **Score Bounds**: Confirms all match, readiness, and resume scores lie strictly within [0, 100].

### 5. Daily Runner & Scheduled Automation

* **Runner Batch Script**: `scripts\run_daily_job_finder.bat`
  * Path-independent execution from any working directory.
  * Virtual environment auto-detection (`venv` or `.venv`).
  * Process lock protection (`data/job_finder.lock`) preventing overlapping instances (exits with code 3).
  * Unique execution log generation (`data/logs/job_finder_YYYYMMDD_HHMMSS.log`) with 30-day retention.
* **Windows Task Scheduler**: Template located at `scripts/DailyJobFinderTask.xml` with setup documentation at `docs/windows-task-scheduler.md`.

### 6. Production Safety Guardrails

| Safety Rule | Status | Guarantee |
| :--- | :---: | :--- |
| **No Auto-Apply** | ✅ Enforced | Zero form submission, zero CAPTCHA bypass, zero stealth scraping. |
| **No External LLM** | ✅ Enforced | 100% deterministic local Python matching and scoring. |
| **No Sensitive Logging** | ✅ Enforced | Never logs passwords, tokens, cookies, resume text, or form data. |
| **Read-Only Diagnostics** | ✅ Enforced | Health checks and audits never mutate database records. |
| **Isolated Test Suite** | ✅ Enforced | 100% of test runs use isolated temporary databases; `data/jobs.db` is never modified by tests. |
| **Zero-State Safety** | ✅ Enforced | All dashboard routes and Excel exporter handle empty databases (0 jobs) gracefully without crashing. |


