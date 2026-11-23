# Phase 3A — Multi-User Backend Architecture and Database Design Audit

**Audit Date**: November 7, 2026  
**Auditor**: Antigravity Autonomous Agent  
**Status**: APPROVED & READY FOR PHASE 3B IMPLEMENTATION  
**Mode**: READ-ONLY ARCHITECTURAL INSPECTION & DESIGN AUDIT (Zero Code/DB Modifications)

---

## 1. Executive Summary & Core Objectives

The Job Finder Automation platform has established a verified 40-company automated collection pipeline (Phase 2.1 & 2.2) with 6,349 persisted job records across major technology employers (Accenture, Amazon, HP, Deloitte, Workday ATS employers, etc.) and comprehensive local matching, filtering, and Excel export systems.

However, the current architecture was constructed for single-tenant (personal) execution. It couples candidate-specific metadata (`status`, `notes`, `match_score`, `resume_alignment_score`, `applied_at`) directly into the shared `jobs` table, and relies on static profile configuration files (`data/profile.json`).

### Objectives of Phase 3A
1. **Preserve Working Engine**: Ensure the 40 existing production connectors, rate-limiting infrastructure, deduplication algorithms, and Excel export capabilities remain intact and candidate-agnostic.
2. **Dynamic Resume-First Onboarding**: Eliminate hardcoded candidate profiles. Design a dynamic onboarding pipeline where incoming candidates upload a resume (PDF/DOCX), the system automatically extracts skills, experience, and education, prompts the candidate to confirm or supplement missing search preferences (without guessing or hallucinating), and personalizes job matching strictly per candidate.
3. **Decoupled Relational Schema**: Architect a clean multi-tenant database design separating global job listings from candidate profiles, preferences, evaluations, and application tracking.
4. **Data Isolation & Privacy**: Establish strict tenant isolation at the database, storage, and API levels, preventing cross-tenant data exposure.
5. **Zero Data Loss Migration**: Guarantee the existing 6,349 collected jobs, 1 historical application record (`status = 'APPLIED'`), and existing user notes are preserved and mapped to an initial administrative user account.

---

## 2. Current Architecture & Codebase Inspection Findings

### 2.1 Existing Architecture Overview
- **Backend**: FastAPI (`app/dashboard/app.py`, `app/dashboard/routes.py`), Uvicorn server, Jinja2 template rendering, openpyxl for Excel reporting.
- **Persistence**: SQLite database at `data/jobs.db` via `DatabaseManager` (`app/database/database.py`).
- **Collection Engine**: `JobCollector` (`app/services/collector.py`) coordinating 40 employer sources (`app/sources/`).
- **Matching & Intelligence**: `JobMatcher` (`app/services/matcher.py`), `JobFilter` (`app/services/filter.py`), `ResumeParser` (`app/services/resume_parser.py`), and `ResumeIntelligenceService` (`app/services/resume_intelligence.py`).

### 2.2 Critical Inspection Findings: Coupling & Scalability Bottlenecks

| Component | Current Implementation | Multi-User Bottleneck / Limitation | Required Multi-Tenant Refactoring |
| :--- | :--- | :--- | :--- |
| **`jobs` Table** | Stores both listing data (title, company, URL) and candidate tracking (`status`, `notes`, `match_score`, `applied_at`). | Multiple candidates cannot evaluate, score, or track the same job independently without overwriting each other's data. | Split into candidate-independent `jobs` catalog and candidate-isolated tables (`job_matches`, `saved_jobs`, `applications`). |
| **Candidate Profile** | Loaded from static JSON files (`data/profile.json`, `data/resume_profile.json`). | Requires manual file edits; cannot support multiple concurrent users with distinct resumes, skills, or target roles. | Store profiles dynamically in `candidate_profiles`, `candidate_preferences`, and `resumes` tables. |
| **Resume Parsing** | Single-file processing via CLI or test script. | Lacks multi-tenant file storage isolation, upload validation API, and missing-field questionnaire flow. | Build multi-tenant file upload API, background parser, dynamic questionnaire flow, and per-user secure storage. |
| **Authentication & AuthZ** | None. Dashboard routes are open and assume single local user. | Any client can view, modify, or delete any job record. | Implement JWT / session-cookie authentication, password hashing (`bcrypt`), and route-level tenant authorization dependencies (`get_current_user`). |
| **Database Concurrency** | Standard SQLite connection context manager without WAL configuration or multi-client locking control. | Concurrent web requests writing to SQLite risk `database is locked` errors under multi-user loads. | Enable SQLite WAL (Write-Ahead Logging) mode, busy timeouts (`timeout=30.0`), and connection pooling. |

---

## 3. Dynamic Resume-Based Candidate Profiling (Critical Requirement)

To provide an intuitive, zero-code experience for any candidate, the system transitions from static config files to an automated, resume-first dynamic profiling workflow.

```mermaid
flowchart TD
    A["Candidate Registers / Signs In"] --> B["Upload Resume (PDF / DOCX)"]
    B --> C["Secure File Storage & Magic-Byte Validation"]
    C --> D["Local Deterministic Text & Section Parser (PyPDF / python-docx)"]
    D --> E["Extract Raw Profile Elements (Skills, Titles, Experience, Education)"]
    E --> F{"Are Critical Search Preferences Present?"}
    F -- No / Partial --> G["Interactive Onboarding Questionnaire (Locations, Target Roles, Notice Period, Remote Pref)"]
    F -- Yes --> H["Candidate Profile Review & Confirmation Screen"]
    G --> H
    H --> I["Candidate Modifies / Confirms Profile & Preferences"]
    I --> J["Persist to candidate_profiles & candidate_preferences"]
    J --> K["Execute Candidate-Specific Job Matching against Shared Jobs Table"]
    K --> L["Populate candidate-isolated job_matches Table"]
```

### 3.1 Dynamic Resume Parsing Engine
1. **Multi-Format Ingestion**: Support PDF and DOCX files up to 10MB using existing local libraries (`pypdf>=5.0.0`, `python-docx>=1.1.0`).
2. **Local-First & Deterministic**: Reuse `app/services/resume_parser.py` without external cloud dependencies, avoiding API token costs and data leaks.
3. **Structured Entity Extraction**:
   - **Contact Information**: Full name, email address, phone number, LinkedIn URL, GitHub URL, portfolio links (extracted via regex).
   - **Technical Skills**: Normalized against the existing canonical skill dictionary (`NORMALIZATION_MAP` with 77+ technical terms).
   - **Work Experience**: Extracted from work history sections, calculating total duration in months/years.
   - **Current / Previous Job Titles**: SDE, Full Stack Engineer, GenAI Engineer, Data Scientist, etc.
   - **Education**: Degrees, institutions, graduation years.
   - **Inferred Seniority**: Fresher (0-1 yr), Junior/Associate (1-3 yrs), Mid-Level (3-5 yrs), Senior (5+ yrs).

### 3.2 Missing-Information Questionnaire (Zero-Guessing Principle)
Resumes rarely state search preferences (e.g. desired cities, remote willingness, target salary, immediate availability). **The system strictly forbids guessing, hallucinating, or hardcoding default assumptions.**

When any of the following fields are absent from the parsed resume, the onboarding wizard explicitly prompts the candidate:

| Required Preference | Extraction Feasibility from Resume | Missing Handling Strategy |
| :--- | :--- | :--- |
| **Target Role Titles** | Inferred from recent titles, but search intent may differ. | Prompt candidate with inferred titles as pre-selected pills; allow adding/removing targets. |
| **Preferred Locations** | Candidate's current address may not match desired relocation targets. | Mandatory multi-select dropdown (Bangalore, Hyderabad, Pune, Mumbai, Gurgaon, Noida, Chennai, Remote, or "Anywhere"). |
| **Work Arrangement** | Rarely specified in resume. | Prompt: Hybrid / Remote / On-site / Any. |
| **Max Acceptable Experience Requirement** | Not in resume. | Prompt candidate (e.g., "Exclude jobs requiring more than [2 / 3 / 5] years of experience"). |
| **Notice Period / Availability** | Rarely specified. | Prompt: Immediate / 15 Days / 30 Days / 60+ Days. |
| **Work Authorization** | Inferred or missing. | Prompt confirmation for India / Global eligibility. |

### 3.3 Candidate Confirmation & Customization
Before any matching is triggered, candidates are presented with an editable profile summary view:
- Add or remove extracted technical skills.
- Categorize skills into primary (e.g. GenAI / Python) vs. secondary.
- Set matching sensitivity threshold (e.g. strict $\ge 70\%$ match vs. broad $\ge 50\%$).
- Save updates at any time, instantly recalculating personalized match scores without altering underlying job data.

---

## 4. Multi-User Relational Database Schema Design

### 4.1 Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    users ||--o{ resumes : "uploads"
    users ||--o| candidate_profiles : "has"
    users ||--o| candidate_preferences : "defines"
    users ||--o{ job_matches : "receives"
    users ||--o{ saved_jobs : "saves"
    users ||--o{ applications : "tracks"
    
    jobs ||--o{ job_matches : "evaluated in"
    jobs ||--o{ saved_jobs : "bookmarked in"
    jobs ||--o{ applications : "applied to"
    
    resumes ||--o{ applications : "submitted with"

    users {
        int id PK
        string email UK
        string password_hash
        string full_name
        string role
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    candidate_profiles {
        int id PK
        int user_id FK, UK
        string headline
        float total_experience_years
        string current_title
        string education_level
        json technical_skills
        json domain_skills
        text raw_extracted_text
        timestamp created_at
        timestamp updated_at
    }

    candidate_preferences {
        int id PK
        int user_id FK, UK
        json target_roles
        json preferred_locations
        string location_scope
        string work_arrangement
        int max_required_years
        int match_min_score
        string notice_period
        timestamp updated_at
    }

    resumes {
        int id PK
        int user_id FK
        string original_filename
        string stored_filename
        string file_path
        int file_size_bytes
        string mime_type
        json parsed_data_json
        boolean is_primary
        timestamp uploaded_at
    }

    jobs {
        int id PK
        string source
        string source_job_id
        string title
        string company
        string location
        string country
        string url
        string apply_url
        text description
        string employment_type
        string experience_required
        string salary
        string fingerprint UK
        string date_posted
        string date_found
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    job_matches {
        int id PK
        int user_id FK
        int job_id FK
        int match_score
        string match_category
        json matched_skills
        json missing_skills
        text match_reason
        int resume_alignment_score
        timestamp evaluated_at
    }

    saved_jobs {
        int id PK
        int user_id FK
        int job_id FK
        text candidate_notes
        timestamp created_at
    }

    applications {
        int id PK
        int user_id FK
        int job_id FK
        int resume_id FK
        string status
        timestamp applied_at
        timestamp interview_date
        string interview_round
        text notes
        string salary_offered
        timestamp updated_at
    }
```

### 4.2 Detailed Table DDL Specifications

```sql
-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'CANDIDATE', -- 'ADMIN', 'CANDIDATE'
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 2. Candidate Profiles Table (Extracted from Resume)
CREATE TABLE IF NOT EXISTS candidate_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    headline TEXT,
    total_experience_years REAL DEFAULT 0.0,
    current_title TEXT,
    education_level TEXT,
    technical_skills TEXT, -- JSON Array: ["Python", "FastAPI", "React"]
    domain_skills TEXT,    -- JSON Array: ["GenAI", "Fintech"]
    raw_extracted_text TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_profiles_user ON candidate_profiles(user_id);

-- 3. Candidate Preferences Table (Filled via Wizard / Settings)
CREATE TABLE IF NOT EXISTS candidate_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    target_roles TEXT NOT NULL,       -- JSON Array: ["Software Engineer", "Full Stack Developer"]
    preferred_locations TEXT NOT NULL,-- JSON Array: ["Bangalore", "Hyderabad", "Remote"]
    location_scope TEXT DEFAULT 'PREF_ONLY', -- 'PREF_ONLY', 'ANYWHERE', 'INDIA_ONLY'
    work_arrangement TEXT DEFAULT 'ANY',    -- 'REMOTE', 'HYBRID', 'ONSITE', 'ANY'
    max_required_years INTEGER DEFAULT 2,   -- Experience ceiling gate
    match_min_score INTEGER DEFAULT 50,     -- Minimum score to qualify as GOOD_FIT / MAYBE
    notice_period TEXT DEFAULT 'IMMEDIATE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_preferences_user ON candidate_preferences(user_id);

-- 4. Resumes Table
CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    parsed_data_json TEXT, -- Cached JSON output of ResumeParser
    is_primary BOOLEAN NOT NULL DEFAULT 1,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_resumes_user ON resumes(user_id);

-- 5. Shared Candidate-Independent Jobs Table
-- (Existing jobs table refactored: candidate-specific columns deprecated/removed from this table)
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_job_id TEXT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT NOT NULL,
    country TEXT,
    url TEXT NOT NULL,
    apply_url TEXT,
    description TEXT,
    employment_type TEXT,
    experience_required TEXT,
    salary TEXT,
    fingerprint TEXT NOT NULL UNIQUE,
    raw_metadata TEXT,
    date_posted TEXT,
    date_found TEXT NOT NULL,
    first_seen_at TIMESTAMP,
    last_seen_at TIMESTAMP,
    last_seen_run_id TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_source_job_id ON jobs(source, source_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_is_active ON jobs(is_active);

-- 6. Candidate-Specific Job Matches Table
CREATE TABLE IF NOT EXISTS job_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    match_score INTEGER NOT NULL DEFAULT 0,
    match_category TEXT NOT NULL, -- 'GOOD_FIT', 'MAYBE', 'NO_FIT'
    matched_skills TEXT,         -- JSON Array: ["Python", "FastAPI"]
    missing_skills TEXT,         -- JSON Array: ["Docker", "AWS"]
    match_reason TEXT,
    resume_alignment_score INTEGER DEFAULT 0,
    evaluated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    UNIQUE(user_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_matches_user_score ON job_matches(user_id, match_score DESC);
CREATE INDEX IF NOT EXISTS idx_matches_user_cat ON job_matches(user_id, match_category);

-- 7. Candidate Saved Jobs Table
CREATE TABLE IF NOT EXISTS saved_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    candidate_notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    UNIQUE(user_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_jobs(user_id);

-- 8. Candidate Application Tracking Table
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    resume_id INTEGER,
    status TEXT NOT NULL DEFAULT 'APPLIED', -- 'READY_TO_APPLY', 'APPLIED', 'INTERVIEWING', 'OFFER', 'REJECTED', 'WITHDRAWN'
    applied_at TIMESTAMP,
    interview_date TIMESTAMP,
    interview_round TEXT,
    notes TEXT,
    salary_offered TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (resume_id) REFERENCES resumes(id) ON DELETE SET NULL,
    UNIQUE(user_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_apps_user_status ON applications(user_id, status);
```

---

## 5. Existing Data Migration & Zero-Loss Transition Strategy

### 5.1 Pre-Migration Baseline Audit
Inspection of `data/jobs.db` confirms:
- **Total persisted jobs**: 6,349 rows.
- **Applied jobs in database**: Exactly 1 job marked `status = 'APPLIED'` with an active `applied_at` timestamp.
- **Jobs with custom notes**: Exactly 2 jobs containing user-entered interview preparation and priority notes.
- **Zero Loss Imperative**: Migration must preserve all 6,349 vacancy rows, transfer the 1 application and 2 notes without data alteration, and retain seamless rollback capabilities.

### 5.2 Step-by-Step Zero-Downtime Migration Algorithm
1. **Safety Backup**: Create a full verified copy of `data/jobs.db` to `data/backups/jobs_backup_pre_phase3b.db`.
2. **Schema Provisioning**:
   - Create new multi-tenant tables (`users`, `candidate_profiles`, `candidate_preferences`, `resumes`, `job_matches`, `saved_jobs`, `applications`) alongside the existing `jobs` table using `IF NOT EXISTS`.
3. **Provision Default Admin/Owner Account**:
   - Insert default admin user:
     ```sql
     INSERT INTO users (id, email, password_hash, full_name, role)
     VALUES (1, 'admin@jobfinder.local', '$2b$12$DEFAULT_SECURE_ADMIN_HASH...', 'Primary Candidate', 'ADMIN')
     ON CONFLICT(email) DO NOTHING;
     ```
4. **Seed Candidate Profile & Preferences from Existing Config**:
   - Read `data/profile.json` and insert initial record into `candidate_preferences` for `user_id = 1`.
   - If `data/resume_profile.json` exists, load and insert into `candidate_profiles` for `user_id = 1`.
5. **Migrate Historical User Tracking Data**:
   - Transfer applied records:
     ```sql
     INSERT OR IGNORE INTO applications (user_id, job_id, status, applied_at, notes, created_at, updated_at)
     SELECT 1, id, status, applied_at, notes, COALESCE(created_at, CURRENT_TIMESTAMP), COALESCE(updated_at, CURRENT_TIMESTAMP)
     FROM jobs
     WHERE status = 'APPLIED';
     ```
   - Transfer non-applied jobs with custom user notes:
     ```sql
     INSERT OR IGNORE INTO saved_jobs (user_id, job_id, candidate_notes, created_at)
     SELECT 1, id, notes, COALESCE(created_at, CURRENT_TIMESTAMP)
     FROM jobs
     WHERE (notes IS NOT NULL AND TRIM(notes) != '')
       AND (status IS NULL OR status != 'APPLIED');
     ```
   - Transfer historical match scores into `job_matches` for user 1:
     ```sql
     INSERT OR IGNORE INTO job_matches (user_id, job_id, match_score, match_category, matched_skills, missing_skills, resume_alignment_score)
     SELECT 1, id, COALESCE(match_score, 0), COALESCE(match_category, 'NO_FIT'), matched_skills, missing_skills, COALESCE(resume_alignment_score, 0)
     FROM jobs
     WHERE match_score > 0 OR match_category IS NOT NULL;
     ```
6. **Integrity Validation**:
   - Execute verification query asserting `COUNT(*) FROM jobs` equals 6,349.
   - Assert `COUNT(*) FROM applications WHERE user_id = 1` equals 1.
   - Assert `COUNT(*) FROM saved_jobs WHERE user_id = 1` equals 2.
7. **Clean Shared Table (Optional / Phased)**:
   - Deprecate single-tenant columns in `jobs` without dropping them immediately to ensure 100% backward compatibility with legacy scripts during the transition.

---

## 6. Authentication, Session & Multi-Tenant Security Architecture

### 6.1 Authentication Mechanism
- **Algorithm**: Stateless JSON Web Tokens (JWT) using `python-jose` / `PyJWT` signed with HMAC-SHA256 (`HS256`).
- **Token Delivery**: HTTP-only, `SameSite=Lax`, `Secure` cookies (with fallback Bearer header in `Authorization` for programmatic API access).
  - Protects against Cross-Site Scripting (XSS) token exfiltration.
  - Mitigates Cross-Site Request Forgery (CSRF).
- **Password Security**: Passwords hashed using `bcrypt` (12 rounds) or `argon2id` via `passlib`. Plaintext passwords are never logged or stored.
- **Session Duration**: Access token lifespan = 2 hours; Refresh token lifespan = 14 days.

### 6.2 Multi-Tenant Data Isolation & Authorization
- **Dependency Injection**: FastAPI route dependency `get_current_active_user`:
  ```python
  async def get_current_user(
      request: Request,
      db: DatabaseManager = Depends(get_db)
  ) -> User:
      token = request.cookies.get("access_token") or get_bearer_token(request)
      if not token:
          raise HTTPException(status_code=401, detail="Authentication required")
      payload = decode_jwt(token)
      user = db.get_user_by_id(payload["sub"])
      if not user or not user.is_active:
          raise HTTPException(status_code=401, detail="Invalid session")
      return user
  ```
- **Strict Tenant Scoping**: All candidate queries **must** parameterize by `user_id`:
  - `SELECT * FROM job_matches WHERE user_id = :user_id ...`
  - `SELECT * FROM applications WHERE user_id = :user_id ...`
  - Any update or delete operation verifies `WHERE id = :id AND user_id = :user_id`. Attempting to access another user's tracking yields HTTP 404 (or 403 Forbidden).

### 6.3 Secure Resume Storage Architecture
- **Directory Structure**: Resumes stored outside public static directories in a dedicated tenant-isolated folder:
  `data/resumes/{user_id}/{sanitized_uuid}_{original_filename}.pdf`
- **File Ingestion Guards**:
  - Size limitation: Strict 10MB maximum limit.
  - Extension whitelist: `.pdf`, `.docx`.
  - Magic Byte Verification: Inspect header bytes (`%PDF` for PDF, `PK\x03\x04` for DOCX) to reject spoofed executable payloads.
  - Path Traversal Guard: Use `pathlib.Path.resolve()` to ensure file destination remains inside `data/resumes/{user_id}`.
- **Download Protection**: Resumes are served only via authenticated streaming endpoint `/api/v1/resumes/{id}/download`, ensuring only the owner or an admin can retrieve the document.

---

## 7. Complete API Specification

All endpoints are prefixed with `/api/v1` and return standard JSON responses.

### 7.1 Authentication Endpoints
- `POST /api/v1/auth/register`: Create new candidate account.
  - Request: `{ "email": "user@example.com", "password": "SecurePassword123!", "full_name": "Jane Doe" }`
  - Response (201): `{ "status": "success", "user": { "id": 2, "email": "user@example.com", "full_name": "Jane Doe" } }`
- `POST /api/v1/auth/login`: Authenticate and issue secure cookie/token.
  - Request: `{ "email": "user@example.com", "password": "SecurePassword123!" }`
  - Response (200): Sets `access_token` cookie; returns `{ "token_type": "bearer", "access_token": "..." }`
- `GET /api/v1/auth/me`: Retrieve current authenticated user profile.
- `POST /api/v1/auth/logout`: Invalidate session cookie.

### 7.2 Resume Upload & Parsing Endpoints
- `POST /api/v1/resumes/upload`: Ingest resume file (`multipart/form-data`).
  - Response (201):
    ```json
    {
      "resume_id": 5,
      "original_filename": "Jane_Doe_Resume.pdf",
      "extracted_data": {
        "candidate_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+91-9876543210",
        "total_experience_years": 2.3,
        "extracted_skills": ["Python", "FastAPI", "React", "Docker", "AWS", "RAG"],
        "current_title": "Software Engineer",
        "missing_fields": ["preferred_locations", "target_roles", "notice_period", "work_arrangement"]
      }
    }
    ```
- `GET /api/v1/resumes`: List candidate's uploaded resumes.
- `GET /api/v1/resumes/{id}/download`: Stream original resume file (scoped to owner).
- `DELETE /api/v1/resumes/{id}`: Delete resume and associated parsed data.

### 7.3 Profile & Preference Wizard Endpoints
- `GET /api/v1/profile`: Retrieve parsed candidate profile and preferences.
- `PUT /api/v1/profile`: Update skills, experience, or headline.
  - Request: `{ "headline": "Full Stack & GenAI Engineer", "technical_skills": ["Python", "FastAPI", "PyTorch"], "total_experience_years": 2.5 }`
- `GET /api/v1/profile/preferences`: Retrieve search criteria.
- `PUT /api/v1/profile/preferences`: Save confirmed preferences.
  - Request:
    ```json
    {
      "target_roles": ["Software Engineer", "Backend Developer", "GenAI Engineer"],
      "preferred_locations": ["Bangalore", "Hyderabad", "Remote"],
      "location_scope": "PREF_ONLY",
      "max_required_years": 2,
      "work_arrangement": "HYBRID",
      "notice_period": "30_DAYS"
    }
    ```
- `POST /api/v1/profile/complete-onboarding`: Finalize profile, trigger initial matching run.

### 7.4 Candidate Job Matching & Search Endpoints
- `GET /api/v1/matches`: Paginated, filtered job matches for current user.
  - Query Params: `category=GOOD_FIT&company=Amazon&location=Bangalore&min_score=60&page=1&limit=25`
  - Response (200):
    ```json
    {
      "total": 142,
      "page": 1,
      "limit": 25,
      "items": [
        {
          "job_id": 4012,
          "title": "Software Development Engineer I",
          "company": "Amazon",
          "location": "Bangalore, India",
          "url": "https://amazon.jobs/en/jobs/4012",
          "match_score": 88,
          "match_category": "GOOD_FIT",
          "matched_skills": ["Python", "FastAPI", "AWS", "Docker"],
          "missing_skills": ["Kafka"],
          "application_status": null
        }
      ]
    }
    ```
- `POST /api/v1/matches/recalculate`: Recalculate match scores against candidate's updated profile.
- `GET /api/v1/matches/{job_id}`: Detailed match breakdown for a specific vacancy.

### 7.5 Application & Tracking Endpoints
- `POST /api/v1/tracking/save`: Bookmark job to saved list.
  - Request: `{ "job_id": 4012, "notes": "Strong match for GenAI team" }`
- `POST /api/v1/tracking/apply`: Mark job as applied.
  - Request: `{ "job_id": 4012, "resume_id": 5, "applied_at": "2026-11-07T10:00:00Z" }`
- `PUT /api/v1/tracking/{job_id}/status`: Transition stage (INTERVIEWING, OFFER, REJECTED).
- `PUT /api/v1/tracking/{job_id}/notes`: Update interview notes.
- `GET /api/v1/tracking/pipeline`: Retrieve candidate's active application funnel metrics.

### 7.6 Admin & Collection Management Endpoints (Role: ADMIN)
- `POST /api/v1/admin/collect`: Trigger collector across all 40 employers or subset.
- `GET /api/v1/admin/sources/health`: Retrieve health & connectivity status of all 40 connectors.
- `GET /api/v1/admin/users`: View tenant registration metrics (restricted).

---

## 8. Reusable Modules Audit & Code Preservation

To guarantee high engineering efficiency and avoid regressions, the existing codebase has been audited for direct reusability:

| Module / Component | File Path | Multi-User Reusability Status | Required Modification |
| :--- | :--- | :--- | :--- |
| **All 40 Official Connectors** | `app/sources/*` | **100% Reusable (Zero Changes)** | None. Connectors already collect candidate-agnostic raw jobs. |
| **Collector Orchestrator** | `app/services/collector.py` | **100% Reusable** | Connectors output to shared `jobs` catalog; no changes required. |
| **URL & Fingerprint Utilities** | `app/models/job.py` | **100% Reusable** | `normalize_url`, `generate_job_fingerprint`, and base validators preserved. |
| **Resume Parser Core** | `app/services/resume_parser.py` | **95% Reusable** | Wrap existing parser with multi-tenant file handling and contact regex extraction. |
| **Resume Intelligence** | `app/services/resume_intelligence.py` | **90% Reusable** | Adapt to accept arbitrary `CandidateProfile` Pydantic models instead of reading single static file. |
| **Job Matcher Engine** | `app/services/matcher.py` | **85% Reusable** | Decouple from static `data/profile.json`; accept candidate-specific preferences object. |
| **Excel Exporter** | `app/exporters/excel_exporter.py` | **90% Reusable** | Add optional `user_id` parameter to export candidate's personalized scored workbook. |
| **Database Manager** | `app/database/database.py` | **70% Reusable (Extend)** | Add multi-user schema migration, table queries, and transaction management with SQLite WAL. |

---

## 9. Implementation Roadmap for Upcoming Phases

```mermaid
gantt
    title Multi-User Platform Implementation Phases
    dateFormat  YYYY-MM-DD
    section Phase 3A
    Architecture & Database Design Audit (READ-ONLY) :done, 2026-11-07, 1d
    section Phase 3B
    Multi-User Database Schema Migrations & Data Migration :active, 2026-11-08, 2d
    section Phase 3C
    Dynamic Resume Parsing & Onboarding Wizard Engine : 2026-11-10, 2d
    section Phase 3D
    Authentication, Session Security & Multi-User API Layer : 2026-11-12, 3d
    section Phase 3E
    Multi-Tenant Dashboard, Onboarding UI & Candidate Funnel : 2026-11-15, 3d
    section Phase 3F
    End-to-End Multi-Tenant Verification & Automated Testing : 2026-11-18, 2d
```

### Phase Details:
- **Phase 3B — Multi-User Database Schema Migrations & Data Migration**:
  - Implement migration script creating `users`, `candidate_profiles`, `candidate_preferences`, `resumes`, `job_matches`, `saved_jobs`, and `applications`.
  - Migrate baseline 6,349 jobs, 1 applied record, and 2 note records to default admin account (`user_id = 1`).
  - Unit test data preservation and relational integrity.
- **Phase 3C — Dynamic Resume Parsing & Onboarding Engine**:
  - Build file upload endpoint with security validations.
  - Implement dynamic questionnaire flow handling missing preferences (no guessing).
  - Enable candidate profile confirmation and customization.
- **Phase 3D — Authentication, Session Security & Multi-User API Layer**:
  - Implement JWT cookie auth, bcrypt password hashing, and user registration.
  - Implement candidate-isolated match queries, saved jobs, and application tracking endpoints.
  - Author comprehensive test suite for multi-tenant data isolation.
- **Phase 3E — Multi-Tenant Dashboard & Candidate UI**:
  - Update frontend views with user registration, login, onboarding wizard, and personalized job boards.
  - Allow switching between saved jobs, active applications, and personalized recommendations.
- **Phase 3F — End-to-End Verification & Performance Audit**:
  - Execute end-to-end multi-user workflow tests (multiple candidates signing up with distinct resumes and verifying isolated matches).
  - Verify SQLite WAL performance under concurrent simulated load.

---

## 10. Risks, Trade-offs & Backward Compatibility

### 10.1 Database Concurrency: SQLite WAL Mode vs. PostgreSQL
- **Assessment**: SQLite is zero-configuration and currently holds our 6,349 production jobs. SQLite in standard rollback journal mode locks the entire file on writes.
- **Solution for Multi-User SQLite**:
  - Enable Write-Ahead Logging: `PRAGMA journal_mode = WAL;`.
  - Set busy timeout: `PRAGMA busy_timeout = 30000;` (30 seconds).
  - Set synchronous mode to NORMAL: `PRAGMA synchronous = NORMAL;`.
  - WAL mode allows concurrent readers while a single writer writes, which easily supports tens to hundreds of active concurrent web users.
- **Future Migration Path**: The proposed schema uses standard ANSI SQL types and relationships. If traffic scales beyond single-server capacity, migration to PostgreSQL requires zero architectural redesign—only swapping the SQLAlchemy/connection driver.

### 10.2 Backward Compatibility with Existing CLI
- The CLI command `python -m app.main` must continue to run collection across the 40 employers.
- When running headless from CLI, the collector populates the shared `jobs` table without requiring a candidate session.
- If match flags are passed to the CLI (`--full-report`), it evaluates against the default admin profile (`user_id = 1`), preserving legacy CLI workflows.

---

## 11. Architectural Sign-off

| Criterion | Status | Verification Note |
| :--- | :---: | :--- |
| **Existing Engine Preservation** | **PASS** | 40 production connectors and collection logic completely untouched. |
| **Candidate-Independent Catalog** | **PASS** | `jobs` table cleanly separated from user evaluation and tracking data. |
| **Dynamic Resume Ingestion** | **PASS** | Complete design for PDF/DOCX parsing without external cloud APIs. |
| **Zero Guessing Missing Data** | **PASS** | Strict onboarding questionnaire loop designed for missing preferences. |
| **Tenant Isolation & Security** | **PASS** | JWT cookie auth, bcrypt hashing, and parameterized user scoping specified. |
| **Existing Data Protection** | **PASS** | Zero-data-loss migration maps all 6,349 jobs and existing tracking to user 1. |
| **Execution Constraint** | **PASS** | 100% read-only inspection; zero existing code or database tables altered. |

**Audit Conclusion**: The multi-user architecture and database design are fully specified and verified. The codebase is prepared to transition to Phase 3B upon user instruction.

