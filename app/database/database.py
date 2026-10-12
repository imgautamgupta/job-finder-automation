"""SQLite database persistence layer for previously discovered jobs and historical deduplication."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from app.models.job import Job, JobStatus, normalize_url
from app.models.interview import DailyActionItem, DailyActionPriority

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite storage, multi-level duplicate detection, and job history."""

    def __init__(self, db_path: Union[str, Path] = "data/jobs.db"):
        self.db_path = Path(db_path)
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager creating and automatically closing a sqlite3 connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        """Initialize or migrate the jobs table, tracking fields, pipeline_runs table, and indices."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create table with Phase 7A schema
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_job_id TEXT,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT NOT NULL,
                    url TEXT NOT NULL,
                    description TEXT,
                    easy_apply BOOLEAN DEFAULT 0,
                    date_posted TEXT,
                    date_found TEXT NOT NULL,
                    employment_type TEXT,
                    experience_required TEXT,
                    salary TEXT,
                    fingerprint TEXT NOT NULL,
                    raw_metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'NEW',
                    status_updated_at TIMESTAMP,
                    first_seen_at TIMESTAMP,
                    last_seen_at TIMESTAMP,
                    last_seen_run_id TEXT,
                    notes TEXT
                );
                """
            )

            # Check existing columns to support smooth migration from earlier phases
            cursor.execute("PRAGMA table_info(jobs);")
            columns = {row["name"] for row in cursor.fetchall()}

            if "source_job_id" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN source_job_id TEXT;")
            if "fingerprint" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN fingerprint TEXT;")
            if "updated_at" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
            if "status" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT 'NEW';")
                cursor.execute("UPDATE jobs SET status = 'NEW' WHERE status IS NULL;")
            if "status_updated_at" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN status_updated_at TIMESTAMP;")
            if "first_seen_at" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN first_seen_at TIMESTAMP;")
                cursor.execute("UPDATE jobs SET first_seen_at = COALESCE(created_at, date_found) WHERE first_seen_at IS NULL;")
            if "last_seen_at" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN last_seen_at TIMESTAMP;")
                cursor.execute("UPDATE jobs SET last_seen_at = COALESCE(updated_at, date_found) WHERE last_seen_at IS NULL;")
            if "last_seen_run_id" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN last_seen_run_id TEXT;")
            if "notes" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN notes TEXT;")
            if "match_score" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN match_score INTEGER DEFAULT 0;")
            if "match_category" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN match_category TEXT;")
            if "matched_roles" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN matched_roles TEXT;")
            if "matched_skills" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN matched_skills TEXT;")
            if "matched_locations" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN matched_locations TEXT;")
            if "experience_match" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN experience_match BOOLEAN DEFAULT 0;")
            if "excluded_reasons" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN excluded_reasons TEXT;")

            # Phase 9 Recommendation & Application Workflow Columns
            if "application_readiness_score" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN application_readiness_score INTEGER DEFAULT 0;")
            if "application_priority" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN application_priority TEXT DEFAULT 'SKIP';")
            if "missing_skills" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN missing_skills TEXT;")
            if "critical_gaps" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN critical_gaps TEXT;")
            if "moderate_gaps" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN moderate_gaps TEXT;")
            if "minor_gaps" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN minor_gaps TEXT;")
            if "recommendation_reasons" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN recommendation_reasons TEXT;")
            if "risk_reasons" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN risk_reasons TEXT;")
            if "profile_alignment" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN profile_alignment TEXT;")
            if "checklist" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN checklist TEXT;")
            if "follow_up_date" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN follow_up_date TEXT;")
            if "follow_up_notes" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN follow_up_notes TEXT;")

            # Phase 10 Resume Intelligence Columns
            if "resume_alignment_score" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN resume_alignment_score INTEGER DEFAULT 0;")
            if "resume_alignment_category" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN resume_alignment_category TEXT;")
            if "resume_matched_keywords" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN resume_matched_keywords TEXT;")
            if "resume_missing_keywords" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN resume_missing_keywords TEXT;")
            if "skills_to_emphasize" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN skills_to_emphasize TEXT;")
            if "recommended_project" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN recommended_project TEXT;")
            if "recommended_experience" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN recommended_experience TEXT;")
            if "resume_concerns" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN resume_concerns TEXT;")
            if "resume_suggestions" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN resume_suggestions TEXT;")
            if "preparation_status" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN preparation_status TEXT DEFAULT 'NOT_REVIEWED';")
            if "preparation_notes" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN preparation_notes TEXT;")
            if "recommended_resume" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN recommended_resume TEXT;")

            # Phase 11 Application Command Center & Interview Tracking Columns
            if "applied_at" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN applied_at TIMESTAMP;")
                cursor.execute(
                    "UPDATE jobs SET applied_at = status_updated_at WHERE status = 'APPLIED' AND applied_at IS NULL;"
                )
            if "interview_date" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN interview_date TEXT;")
            if "interview_stage" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN interview_stage TEXT;")
            if "interview_status" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN interview_status TEXT DEFAULT 'NOT_SCHEDULED';")
            if "interview_notes" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN interview_notes TEXT;")
            if "interview_preparation_status" not in columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN interview_preparation_status TEXT DEFAULT 'NOT_STARTED';")

            # Performance & Uniqueness Indices
            # Level 1 Index: Source + Source Job ID (unique when source_job_id is provided)
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_source_source_job_id
                ON jobs (source, source_job_id)
                WHERE source_job_id IS NOT NULL;
                """
            )

            # Level 3 Index: Fingerprint
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_fingerprint
                ON jobs (fingerprint);
                """
            )

            # Lookup Indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs (url);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_date_found ON jobs (date_found);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs (updated_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_first_seen_at ON jobs (first_seen_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_last_seen_at ON jobs (last_seen_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_last_seen_run_id ON jobs (last_seen_run_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs (match_score);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs (company);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs (location);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs (source);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_readiness ON jobs (application_readiness_score);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs (application_priority);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_follow_up_date ON jobs (follow_up_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_resume_alignment ON jobs (resume_alignment_score);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_prep_status ON jobs (preparation_status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_applied_at ON jobs (applied_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_interview_date ON jobs (interview_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_interview_status ON jobs (interview_status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_interview_prep_status ON jobs (interview_preparation_status);")

            # Pipeline Runs Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    sources_attempted TEXT,
                    raw_collected INTEGER DEFAULT 0,
                    normalized INTEGER DEFAULT 0,
                    filtered INTEGER DEFAULT 0,
                    relevant INTEGER DEFAULT 0,
                    strong INTEGER DEFAULT 0,
                    excellent INTEGER DEFAULT 0,
                    new_jobs INTEGER DEFAULT 0,
                    duplicate_jobs INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    notes TEXT,
                    source_results TEXT
                );
                """
            )
            cursor.execute("PRAGMA table_info(pipeline_runs);")
            pr_columns = {row["name"] for row in cursor.fetchall()}
            if "source_results" not in pr_columns:
                cursor.execute("ALTER TABLE pipeline_runs ADD COLUMN source_results TEXT;")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at ON pipeline_runs (started_at);")

            # One-time Phase 8 backfill: Populate stored match scores for existing jobs if unpopulated
            cursor.execute("SELECT id, title, company, location, url, description, experience_required FROM jobs WHERE match_score IS NULL OR match_score = 0;")
            unscored = cursor.fetchall()
            if unscored:
                try:
                    from app.config.settings import get_settings
                    from app.services.matcher import JobMatcher
                    settings = get_settings()
                    profile = settings.load_profile()
                    matcher = JobMatcher(profile=profile)
                    for r in unscored:
                        tj = Job(
                            id=r["id"],
                            source="unknown",
                            title=r["title"],
                            company=r["company"],
                            location=r["location"],
                            url=r["url"],
                            description=r["description"],
                            experience_required=r["experience_required"],
                        )
                        res = matcher.match(tj)
                        cursor.execute(
                            """
                            UPDATE jobs SET
                                match_score = ?,
                                match_category = ?,
                                matched_roles = ?,
                                matched_skills = ?,
                                matched_locations = ?,
                                experience_match = ?,
                                excluded_reasons = ?
                            WHERE id = ?;
                            """,
                            (
                                res.score,
                                res.category,
                                json.dumps(res.matched_roles),
                                json.dumps(res.matched_skills),
                                json.dumps(res.matched_locations),
                                1 if res.experience_match else 0,
                                json.dumps(res.excluded_reasons),
                                r["id"],
                            ),
                        )
                except Exception as bf_err:
                    logger.debug("One-time match score backfill notice: %s", bf_err)

            # One-time Phase 9 backfill: Populate recommendation analysis for existing jobs if unpopulated
            cursor.execute("SELECT id, source, source_job_id, title, company, location, url, description, easy_apply, experience_required, match_score, match_category, matched_roles, matched_skills, matched_locations, experience_match, excluded_reasons, status FROM jobs WHERE application_readiness_score IS NULL OR application_readiness_score = 0;")
            unrec = cursor.fetchall()
            if unrec:
                try:
                    from app.config.settings import get_settings
                    from app.services.recommender import JobRecommender
                    settings = get_settings()
                    profile = settings.load_profile()
                    recommender = JobRecommender(profile=profile)
                    for r in unrec:
                        roles_list = json.loads(r["matched_roles"]) if r["matched_roles"] else []
                        skills_list = json.loads(r["matched_skills"]) if r["matched_skills"] else []
                        locs_list = json.loads(r["matched_locations"]) if r["matched_locations"] else []
                        excl_list = json.loads(r["excluded_reasons"]) if r["excluded_reasons"] else []
                        try:
                            st = JobStatus(r["status"])
                        except Exception:
                            st = JobStatus.NEW

                        tj = Job(
                            id=r["id"],
                            source=r["source"] or "unknown",
                            source_job_id=r["source_job_id"],
                            title=r["title"],
                            company=r["company"],
                            location=r["location"],
                            url=r["url"],
                            description=r["description"],
                            easy_apply=bool(r["easy_apply"]),
                            experience_required=r["experience_required"],
                            match_score=r["match_score"] or 0,
                            match_category=r["match_category"],
                            matched_roles=roles_list,
                            matched_skills=skills_list,
                            matched_locations=locs_list,
                            experience_match=bool(r["experience_match"]),
                            excluded_reasons=excl_list,
                            status=st,
                        )
                        rec = recommender.recommend(tj)
                        cursor.execute(
                            """
                            UPDATE jobs SET
                                application_readiness_score = ?,
                                application_priority = ?,
                                missing_skills = ?,
                                critical_gaps = ?,
                                moderate_gaps = ?,
                                minor_gaps = ?,
                                recommendation_reasons = ?,
                                risk_reasons = ?,
                                profile_alignment = ?,
                                checklist = ?
                            WHERE id = ?;
                            """,
                            (
                                rec.application_readiness_score,
                                rec.application_priority.value,
                                json.dumps(rec.missing_skills),
                                json.dumps(rec.critical_gaps),
                                json.dumps(rec.moderate_gaps),
                                json.dumps(rec.minor_gaps),
                                json.dumps(rec.recommendation_reasons),
                                json.dumps(rec.risk_reasons),
                                rec.profile_alignment,
                                json.dumps(rec.checklist),
                                r["id"],
                            ),
                        )
                except Exception as bf_err9:
                    logger.debug("One-time recommendation backfill notice: %s", bf_err9)

            # One-time Phase 10 backfill: Populate resume preparation analysis for existing jobs if unpopulated
            cursor.execute("SELECT id, source, source_job_id, title, company, location, url, description, easy_apply, experience_required, match_score, match_category, matched_roles, matched_skills, matched_locations, experience_match, excluded_reasons, status, application_readiness_score, application_priority FROM jobs WHERE resume_alignment_score IS NULL OR resume_alignment_score = 0;")
            unprep = cursor.fetchall()
            if unprep:
                try:
                    from app.config.settings import get_settings
                    from app.services.resume_parser import ResumeParser
                    from app.services.resume_intelligence import ResumeIntelligenceService
                    settings = get_settings()
                    profile = settings.load_profile()
                    parser = ResumeParser()
                    resumes_map = parser.load_resumes(getattr(settings, "RESUME_PATH", ""))
                    resume_intel = ResumeIntelligenceService(profile=profile, resume_profiles=resumes_map)
                    for r in unprep:
                        roles_list = json.loads(r["matched_roles"]) if r["matched_roles"] else []
                        skills_list = json.loads(r["matched_skills"]) if r["matched_skills"] else []
                        locs_list = json.loads(r["matched_locations"]) if r["matched_locations"] else []
                        excl_list = json.loads(r["excluded_reasons"]) if r["excluded_reasons"] else []
                        try:
                            st = JobStatus(r["status"])
                        except Exception:
                            st = JobStatus.NEW

                        tj = Job(
                            id=r["id"],
                            source=r["source"] or "unknown",
                            source_job_id=r["source_job_id"],
                            title=r["title"],
                            company=r["company"],
                            location=r["location"],
                            url=r["url"],
                            description=r["description"],
                            easy_apply=bool(r["easy_apply"]),
                            experience_required=r["experience_required"],
                            match_score=r["match_score"] or 0,
                            match_category=r["match_category"],
                            matched_roles=roles_list,
                            matched_skills=skills_list,
                            matched_locations=locs_list,
                            experience_match=bool(r["experience_match"]),
                            excluded_reasons=excl_list,
                            status=st,
                        )
                        prep_analysis = resume_intel.analyze(tj)
                        cursor.execute(
                            """
                            UPDATE jobs SET
                                resume_alignment_score = ?,
                                resume_alignment_category = ?,
                                resume_matched_keywords = ?,
                                resume_missing_keywords = ?,
                                skills_to_emphasize = ?,
                                recommended_project = ?,
                                recommended_experience = ?,
                                resume_concerns = ?,
                                resume_suggestions = ?,
                                preparation_status = COALESCE(preparation_status, ?),
                                recommended_resume = ?
                            WHERE id = ?;
                            """,
                            (
                                prep_analysis.resume_alignment_score,
                                prep_analysis.resume_alignment_category,
                                json.dumps(prep_analysis.resume_matched_keywords),
                                json.dumps(prep_analysis.resume_missing_keywords),
                                json.dumps(prep_analysis.skills_to_emphasize),
                                prep_analysis.recommended_project,
                                prep_analysis.recommended_experience,
                                json.dumps(prep_analysis.resume_concerns),
                                json.dumps(prep_analysis.resume_suggestions),
                                prep_analysis.preparation_status.value if hasattr(prep_analysis.preparation_status, "value") else str(prep_analysis.preparation_status),
                                prep_analysis.recommended_resume,
                                r["id"],
                            ),
                        )
                except Exception as bf_err10:
                    logger.debug("One-time resume intelligence backfill notice: %s", bf_err10)

            conn.commit()
            logger.info("Database initialized successfully at %s", self.db_path)

    # Alias for backwards compatibility
    init_db = initialize

    def _find_existing_row(self, conn: sqlite3.Connection, job: Job) -> Optional[sqlite3.Row]:
        """Query for existing job row across all 3 deduplication levels in priority order:
        1. Source + Source Job ID
        2. Canonical URL
        3. Deterministic Fingerprint
        """
        cursor = conn.cursor()
        s_id = job.source_job_id or job.job_id

        # Level 1: Source + Source Job ID
        if s_id and s_id.strip():
            cursor.execute(
                "SELECT * FROM jobs WHERE source = ? AND source_job_id = ? LIMIT 1;",
                (job.source.strip(), s_id.strip()),
            )
            row = cursor.fetchone()
            if row:
                return row

        # Level 2: Canonical URL
        clean_url = normalize_url(job.url)
        if clean_url:
            cursor.execute("SELECT * FROM jobs WHERE url = ? LIMIT 1;", (clean_url,))
            row = cursor.fetchone()
            if row:
                return row

        # Level 3: Deterministic Fingerprint
        fp = job.fingerprint or job.compute_fingerprint()
        cursor.execute("SELECT * FROM jobs WHERE fingerprint = ? LIMIT 1;", (fp,))
        return cursor.fetchone()

    def job_exists(
        self,
        job: Union[Job, str],
        source: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> bool:
        """Check whether a job exists using multi-level duplicate detection.

        Args:
            job: Either a Job model instance or a URL string.
            source: Source name if job argument is a URL string.
            job_id: Platform job ID if job argument is a URL string.
        """
        with self.get_connection() as conn:
            if isinstance(job, Job):
                return self._find_existing_row(conn, job) is not None

            # String URL fallback
            cursor = conn.cursor()
            clean_url = normalize_url(job)
            cursor.execute("SELECT 1 FROM jobs WHERE url = ? LIMIT 1;", (clean_url,))
            if cursor.fetchone() is not None:
                return True

            if source and job_id:
                cursor.execute(
                    "SELECT 1 FROM jobs WHERE source = ? AND source_job_id = ? LIMIT 1;",
                    (source.strip(), job_id.strip()),
                )
                if cursor.fetchone() is not None:
                    return True

            return False

    def save_job(self, job: Job, run_id: Optional[str] = None) -> bool:
        """Save a single job into SQLite.

        - If new: Inserts a new record, sets created_at, updated_at, first_seen_at,
          last_seen_at, last_seen_run_id, and default status NEW. Returns True.
        - If existing: Refreshes mutable details (salary, description, easy_apply, etc.),
          refreshes updated_at, updates last_seen_at and last_seen_run_id.
          Preserves original status, status_updated_at, first_seen_at, notes,
          date_found, and created_at. Returns False.

        Args:
            job: Standardized Job instance.
            run_id: Unique execution identifier for the current pipeline run.

        Returns:
            True if newly inserted, False if already existed and was updated.
        """
        job.url = normalize_url(job.url)
        if not job.fingerprint:
            job.fingerprint = job.compute_fingerprint()

        s_id = job.source_job_id or job.job_id
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        effective_run_id = run_id or job.last_seen_run_id

        with self.get_connection() as conn:
            cursor = conn.cursor()
            existing_row = self._find_existing_row(conn, job)

            if existing_row:
                # Existing job: preserve identity and tracking state, refresh mutable info
                job.id = existing_row["id"]
                try:
                    job.date_found = datetime.fromisoformat(existing_row["date_found"])
                except Exception:
                    pass

                if "created_at" in existing_row.keys() and existing_row["created_at"]:
                    try:
                        job.created_at = datetime.fromisoformat(existing_row["created_at"])
                    except Exception:
                        pass

                # Preserve first_seen_at
                if "first_seen_at" in existing_row.keys() and existing_row["first_seen_at"]:
                    try:
                        job.first_seen_at = datetime.fromisoformat(existing_row["first_seen_at"])
                    except Exception:
                        pass
                elif job.created_at:
                    job.first_seen_at = job.created_at
                else:
                    job.first_seen_at = job.date_found

                # Preserve status & status_updated_at
                if "status" in existing_row.keys() and existing_row["status"]:
                    try:
                        job.status = JobStatus(existing_row["status"])
                    except Exception:
                        job.status = JobStatus.NEW
                if "status_updated_at" in existing_row.keys() and existing_row["status_updated_at"]:
                    try:
                        job.status_updated_at = datetime.fromisoformat(existing_row["status_updated_at"])
                    except Exception:
                        pass

                # Preserve notes
                if "notes" in existing_row.keys() and existing_row["notes"]:
                    job.notes = existing_row["notes"]

                # Preserve follow-up tracking
                if "follow_up_date" in existing_row.keys() and existing_row["follow_up_date"]:
                    job.follow_up_date = existing_row["follow_up_date"]
                if "follow_up_notes" in existing_row.keys() and existing_row["follow_up_notes"]:
                    job.follow_up_notes = existing_row["follow_up_notes"]

                # Preserve preparation tracking
                if "preparation_status" in existing_row.keys() and existing_row["preparation_status"]:
                    job.preparation_status = existing_row["preparation_status"]
                if "preparation_notes" in existing_row.keys() and existing_row["preparation_notes"]:
                    job.preparation_notes = existing_row["preparation_notes"]

                # Update last seen tracking
                job.last_seen_at = now_dt
                if effective_run_id:
                    job.last_seen_run_id = effective_run_id
                elif "last_seen_run_id" in existing_row.keys() and existing_row["last_seen_run_id"]:
                    job.last_seen_run_id = existing_row["last_seen_run_id"]

                prio_str = job.application_priority.value if hasattr(job.application_priority, "value") else (str(job.application_priority) if job.application_priority else None)
                prep_status_str = (
                    job.preparation_status.value
                    if hasattr(job.preparation_status, "value")
                    else (str(job.preparation_status) if job.preparation_status else "NOT_REVIEWED")
                )

                cursor.execute(
                    """
                    UPDATE jobs SET
                        title = ?,
                        company = ?,
                        location = ?,
                        url = ?,
                        description = COALESCE(?, description),
                        easy_apply = ?,
                        date_posted = COALESCE(?, date_posted),
                        employment_type = COALESCE(?, employment_type),
                        experience_required = COALESCE(?, experience_required),
                        salary = COALESCE(?, salary),
                        raw_metadata = ?,
                        updated_at = ?,
                        last_seen_at = ?,
                        last_seen_run_id = COALESCE(?, last_seen_run_id),
                        match_score = COALESCE(?, match_score),
                        match_category = COALESCE(?, match_category),
                        matched_roles = COALESCE(?, matched_roles),
                        matched_skills = COALESCE(?, matched_skills),
                        matched_locations = COALESCE(?, matched_locations),
                        experience_match = COALESCE(?, experience_match),
                        excluded_reasons = COALESCE(?, excluded_reasons),
                        application_readiness_score = COALESCE(?, application_readiness_score),
                        application_priority = COALESCE(?, application_priority),
                        missing_skills = COALESCE(?, missing_skills),
                        critical_gaps = COALESCE(?, critical_gaps),
                        moderate_gaps = COALESCE(?, moderate_gaps),
                        minor_gaps = COALESCE(?, minor_gaps),
                        recommendation_reasons = COALESCE(?, recommendation_reasons),
                        risk_reasons = COALESCE(?, risk_reasons),
                        profile_alignment = COALESCE(?, profile_alignment),
                        checklist = COALESCE(?, checklist),
                        resume_alignment_score = COALESCE(?, resume_alignment_score),
                        resume_alignment_category = COALESCE(?, resume_alignment_category),
                        resume_matched_keywords = COALESCE(?, resume_matched_keywords),
                        resume_missing_keywords = COALESCE(?, resume_missing_keywords),
                        skills_to_emphasize = COALESCE(?, skills_to_emphasize),
                        recommended_project = COALESCE(?, recommended_project),
                        recommended_experience = COALESCE(?, recommended_experience),
                        resume_concerns = COALESCE(?, resume_concerns),
                        resume_suggestions = COALESCE(?, resume_suggestions),
                        preparation_status = COALESCE(?, preparation_status),
                        preparation_notes = COALESCE(?, preparation_notes),
                        recommended_resume = COALESCE(?, recommended_resume),
                        applied_at = COALESCE(?, applied_at),
                        interview_date = COALESCE(?, interview_date),
                        interview_stage = COALESCE(?, interview_stage),
                        interview_status = COALESCE(?, interview_status),
                        interview_notes = COALESCE(?, interview_notes),
                        interview_preparation_status = COALESCE(?, interview_preparation_status)
                    WHERE id = ?;
                    """,
                    (
                        job.title,
                        job.company,
                        job.location or "Not Specified",
                        job.url,
                        job.description,
                        1 if job.easy_apply else 0,
                        job.date_posted,
                        job.employment_type,
                        job.experience_required,
                        job.salary,
                        json.dumps(job.extra_metadata or {}),
                        now_iso,
                        now_iso,
                        job.last_seen_run_id,
                        job.match_score,
                        job.match_category,
                        json.dumps(job.matched_roles) if job.matched_roles else None,
                        json.dumps(job.matched_skills) if job.matched_skills else None,
                        json.dumps(job.matched_locations) if job.matched_locations else None,
                        1 if job.experience_match else 0,
                        json.dumps(job.excluded_reasons) if job.excluded_reasons else None,
                        job.application_readiness_score,
                        prio_str,
                        json.dumps(job.missing_skills) if job.missing_skills else None,
                        json.dumps(job.critical_gaps) if job.critical_gaps else None,
                        json.dumps(job.moderate_gaps) if job.moderate_gaps else None,
                        json.dumps(job.minor_gaps) if job.minor_gaps else None,
                        json.dumps(job.recommendation_reasons) if job.recommendation_reasons else None,
                        json.dumps(job.risk_reasons) if job.risk_reasons else None,
                        job.profile_alignment,
                        json.dumps(job.checklist) if job.checklist else None,
                        job.resume_alignment_score,
                        job.resume_alignment_category,
                        json.dumps(job.resume_matched_keywords) if job.resume_matched_keywords else None,
                        json.dumps(job.resume_missing_keywords) if job.resume_missing_keywords else None,
                        json.dumps(job.skills_to_emphasize) if job.skills_to_emphasize else None,
                        job.recommended_project,
                        job.recommended_experience,
                        json.dumps(job.resume_concerns) if job.resume_concerns else None,
                        json.dumps(job.resume_suggestions) if job.resume_suggestions else None,
                        prep_status_str,
                        job.preparation_notes,
                        job.recommended_resume,
                        job.applied_at.isoformat() if job.applied_at else None,
                        job.interview_date,
                        job.interview_stage,
                        job.interview_status,
                        job.interview_notes,
                        job.interview_preparation_status,
                        existing_row["id"],
                    ),
                )
                conn.commit()
                logger.debug(
                    "Updated existing job ID %s: %s (status preserved: %s, last_seen_at: %s)",
                    existing_row["id"],
                    job.title,
                    job.status.value,
                    now_iso,
                )
                return False

            # New job: insert fresh record with tracking defaults
            first_seen_val = job.first_seen_at or now_dt
            first_seen_iso = first_seen_val.isoformat()
            last_seen_iso = now_iso
            job.first_seen_at = first_seen_val
            job.last_seen_at = now_dt
            job.last_seen_run_id = effective_run_id

            status_str = job.status.value if isinstance(job.status, JobStatus) else str(job.status or "NEW")
            status_up_iso = job.status_updated_at.isoformat() if job.status_updated_at else now_iso
            prio_str = job.application_priority.value if hasattr(job.application_priority, "value") else (str(job.application_priority) if job.application_priority else "SKIP")
            prep_status_str = (
                job.preparation_status.value
                if hasattr(job.preparation_status, "value")
                else (str(job.preparation_status) if job.preparation_status else "NOT_REVIEWED")
            )

            cursor.execute(
                """
                INSERT INTO jobs (
                    source, source_job_id, title, company, location,
                    url, description, easy_apply, date_posted,
                    date_found, employment_type, experience_required,
                    salary, fingerprint, raw_metadata, created_at, updated_at,
                    status, status_updated_at, first_seen_at, last_seen_at, last_seen_run_id, notes,
                    match_score, match_category, matched_roles, matched_skills, matched_locations,
                    experience_match, excluded_reasons,
                    application_readiness_score, application_priority, missing_skills,
                    critical_gaps, moderate_gaps, minor_gaps, recommendation_reasons,
                    risk_reasons, profile_alignment, checklist, follow_up_date, follow_up_notes,
                    resume_alignment_score, resume_alignment_category, resume_matched_keywords,
                    resume_missing_keywords, skills_to_emphasize, recommended_project,
                    recommended_experience, resume_concerns, resume_suggestions, preparation_status,
                    preparation_notes, recommended_resume, applied_at, interview_date, interview_stage,
                    interview_status, interview_notes, interview_preparation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    job.source,
                    s_id,
                    job.title,
                    job.company,
                    job.location or "Not Specified",
                    job.url,
                    job.description,
                    1 if job.easy_apply else 0,
                    job.date_posted,
                    job.date_found.isoformat(),
                    job.employment_type,
                    job.experience_required,
                    job.salary,
                    job.fingerprint,
                    json.dumps(job.extra_metadata or {}),
                    now_iso,
                    now_iso,
                    status_str,
                    status_up_iso,
                    first_seen_iso,
                    last_seen_iso,
                    effective_run_id,
                    job.notes,
                    job.match_score or 0,
                    job.match_category,
                    json.dumps(job.matched_roles or []),
                    json.dumps(job.matched_skills or []),
                    json.dumps(job.matched_locations or []),
                    1 if job.experience_match else 0,
                    json.dumps(job.excluded_reasons or []),
                    job.application_readiness_score or 0,
                    prio_str,
                    json.dumps(job.missing_skills or []),
                    json.dumps(job.critical_gaps or []),
                    json.dumps(job.moderate_gaps or []),
                    json.dumps(job.minor_gaps or []),
                    json.dumps(job.recommendation_reasons or []),
                    json.dumps(job.risk_reasons or []),
                    job.profile_alignment or "Weak alignment",
                    json.dumps(job.checklist or []),
                    job.follow_up_date,
                    job.follow_up_notes,
                    job.resume_alignment_score or 0,
                    job.resume_alignment_category,
                    json.dumps(job.resume_matched_keywords or []),
                    json.dumps(job.resume_missing_keywords or []),
                    json.dumps(job.skills_to_emphasize or []),
                    job.recommended_project,
                    job.recommended_experience,
                    json.dumps(job.resume_concerns or []),
                    json.dumps(job.resume_suggestions or []),
                    prep_status_str,
                    job.preparation_notes,
                    job.recommended_resume,
                    job.applied_at.isoformat() if job.applied_at else None,
                    job.interview_date,
                    job.interview_stage,
                    job.interview_status or "NOT_SCHEDULED",
                    job.interview_notes,
                    job.interview_preparation_status or "NOT_STARTED",
                ),
            )
            job.id = cursor.lastrowid
            conn.commit()
            logger.debug(
                "Inserted new job ID %s: %s (status: %s, run_id: %s)",
                job.id,
                job.title,
                status_str,
                effective_run_id,
            )
            return True

    def save_jobs(self, jobs: List[Job], run_id: Optional[str] = None) -> int:
        """Save a batch of jobs. Returns the number of newly added jobs."""
        inserted_count = 0
        for job in jobs:
            if self.save_job(job, run_id=run_id):
                inserted_count += 1
        return inserted_count

    def update_job_status(
        self,
        job_id: int,
        status: Union[JobStatus, str],
        notes: Optional[str] = None,
    ) -> bool:
        """Update tracking status and optionally notes for a specific job by ID.

        Validates the status against JobStatus enum.
        Sets status_updated_at to current timestamp.
        Sets applied_at when status changes to APPLIED (preserving existing applied_at if already set).
        Leaves first_seen_at, last_seen_at, and last_seen_run_id unchanged.

        Args:
            job_id: Primary key ID of the job in SQLite.
            status: JobStatus enum or valid status string.
            notes: Optional updated notes text.

        Returns:
            True if job was found and updated, False otherwise.
        """
        # Validate status value
        if isinstance(status, str):
            status_upper = status.strip().upper()
            try:
                valid_status = JobStatus(status_upper)
            except ValueError:
                raise ValueError(
                    f"Invalid status '{status}'. Must be one of: {[s.value for s in JobStatus]}"
                )
        elif isinstance(status, JobStatus):
            valid_status = status
        else:
            raise ValueError(f"Invalid status type: {type(status)}")

        now_iso = datetime.now(timezone.utc).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if valid_status == JobStatus.APPLIED:
                if notes is not None:
                    cursor.execute(
                        """
                        UPDATE jobs SET
                            status = ?,
                            status_updated_at = ?,
                            applied_at = COALESCE(applied_at, ?),
                            notes = ?,
                            updated_at = ?
                        WHERE id = ?;
                        """,
                        (valid_status.value, now_iso, now_iso, notes, now_iso, int(job_id)),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE jobs SET
                            status = ?,
                            status_updated_at = ?,
                            applied_at = COALESCE(applied_at, ?),
                            updated_at = ?
                        WHERE id = ?;
                        """,
                        (valid_status.value, now_iso, now_iso, now_iso, int(job_id)),
                    )
            else:
                if notes is not None:
                    cursor.execute(
                        """
                        UPDATE jobs SET
                            status = ?,
                            status_updated_at = ?,
                            notes = ?,
                            updated_at = ?
                        WHERE id = ?;
                        """,
                        (valid_status.value, now_iso, notes, now_iso, int(job_id)),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE jobs SET
                            status = ?,
                            status_updated_at = ?,
                            updated_at = ?
                        WHERE id = ?;
                        """,
                        (valid_status.value, now_iso, now_iso, int(job_id)),
                    )
            conn.commit()
            return cursor.rowcount > 0

    def update_job_notes(self, job_id: int, notes: str) -> bool:
        """Update notes for a specific job by ID."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE jobs SET notes = ?, updated_at = ? WHERE id = ?;",
                (notes, now_iso, int(job_id)),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_job_follow_up(
        self,
        job_id: int,
        follow_up_date: Optional[str] = None,
        follow_up_notes: Optional[str] = None,
    ) -> bool:
        """Update follow-up due date and notes for a specific job."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE jobs SET
                    follow_up_date = ?,
                    follow_up_notes = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (follow_up_date, follow_up_notes, now_iso, int(job_id)),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_preparation_status(
        self,
        job_id: int,
        status: Any,
        notes: Optional[str] = None,
    ) -> bool:
        """Update Phase 10 preparation status and optionally notes for a job."""
        if isinstance(status, str):
            status_val = status.strip().upper()
        elif hasattr(status, "value"):
            status_val = status.value
        else:
            status_val = str(status)

        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if notes is not None:
                cursor.execute(
                    """
                    UPDATE jobs SET
                        preparation_status = ?,
                        preparation_notes = ?,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (status_val, notes, now_iso, int(job_id)),
                )
            else:
                cursor.execute(
                    """
                    UPDATE jobs SET
                        preparation_status = ?,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (status_val, now_iso, int(job_id)),
                )
            conn.commit()
            return cursor.rowcount > 0

    def update_preparation_notes(self, job_id: int, notes: str) -> bool:
        """Update Phase 10 preparation notes for a job."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE jobs SET
                    preparation_notes = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (notes, now_iso, int(job_id)),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_interview(
        self,
        job_id: int,
        interview_date: Optional[str] = None,
        interview_stage: Optional[str] = None,
        interview_status: Optional[str] = None,
        interview_notes: Optional[str] = None,
        interview_preparation_status: Optional[str] = None,
    ) -> bool:
        """Update Phase 11 interview tracking fields for a job dynamically."""
        now_iso = datetime.now(timezone.utc).isoformat()
        updates = []
        params = []

        if interview_date is not None:
            updates.append("interview_date = ?")
            params.append(interview_date.strip() if interview_date.strip() else None)
        if interview_stage is not None:
            updates.append("interview_stage = ?")
            params.append(interview_stage.strip() if interview_stage.strip() else None)
        if interview_status is not None:
            updates.append("interview_status = ?")
            params.append(interview_status.strip().upper() if interview_status.strip() else "NOT_SCHEDULED")
        if interview_notes is not None:
            updates.append("interview_notes = ?")
            params.append(interview_notes.strip() if interview_notes.strip() else None)
        if interview_preparation_status is not None:
            updates.append("interview_preparation_status = ?")
            params.append(interview_preparation_status.strip().upper() if interview_preparation_status.strip() else "NOT_STARTED")

        if not updates:
            return True

        updates.append("updated_at = ?")
        params.append(now_iso)
        params.append(int(job_id))

        with self.get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ", ".join(updates)
            cursor.execute(
                f"UPDATE jobs SET {set_clause} WHERE id = ?;",
                tuple(params),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_interview_prep_status(
        self, job_id: int, status: str, notes: Optional[str] = None
    ) -> bool:
        """Update interview preparation status (NOT_STARTED, IN_PROGRESS, READY, COMPLETED) and optional notes."""
        now_iso = datetime.now(timezone.utc).isoformat()
        status_val = status.strip().upper() if status else "NOT_STARTED"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if notes is not None:
                cursor.execute(
                    """
                    UPDATE jobs SET
                        interview_preparation_status = ?,
                        interview_notes = ?,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (status_val, notes.strip() if notes.strip() else None, now_iso, int(job_id)),
                )
            else:
                cursor.execute(
                    """
                    UPDATE jobs SET
                        interview_preparation_status = ?,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (status_val, now_iso, int(job_id)),
                )
            conn.commit()
            return cursor.rowcount > 0

    def get_applications_pipeline_counts(self) -> Dict[str, int]:
        """Aggregate counts for the application command center pipeline stages."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'NEW' THEN 1 ELSE 0 END) AS count_new,
                    SUM(CASE WHEN status = 'VIEWED' THEN 1 ELSE 0 END) AS count_viewed,
                    SUM(CASE WHEN status = 'SHORTLISTED' THEN 1 ELSE 0 END) AS count_shortlisted,
                    SUM(CASE WHEN status = 'APPLIED' THEN 1 ELSE 0 END) AS count_applied,
                    SUM(CASE WHEN status = 'INTERVIEW' THEN 1 ELSE 0 END) AS count_interview,
                    SUM(CASE WHEN status = 'OFFER' THEN 1 ELSE 0 END) AS count_offer,
                    SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) AS count_rejected,
                    SUM(CASE WHEN status = 'NOT_INTERESTED' THEN 1 ELSE 0 END) AS count_not_interested,
                    COUNT(*) AS count_total
                FROM jobs;
                """
            )
            row = cursor.fetchone()
            if not row:
                return {s: 0 for s in ["NEW", "VIEWED", "SHORTLISTED", "APPLIED", "INTERVIEW", "OFFER", "REJECTED", "NOT_INTERESTED", "TOTAL"]}
            return {
                "NEW": row["count_new"] or 0,
                "VIEWED": row["count_viewed"] or 0,
                "SHORTLISTED": row["count_shortlisted"] or 0,
                "APPLIED": row["count_applied"] or 0,
                "INTERVIEW": row["count_interview"] or 0,
                "OFFER": row["count_offer"] or 0,
                "REJECTED": row["count_rejected"] or 0,
                "NOT_INTERESTED": row["count_not_interested"] or 0,
                "TOTAL": row["count_total"] or 0,
            }

    def get_applications_filtered(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        min_score: Optional[int] = None,
        min_readiness: Optional[int] = None,
        company: Optional[str] = None,
        role: Optional[str] = None,
        location: Optional[str] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
        applied_days: Optional[int] = None,
        follow_up_filter: Optional[str] = None,
        interview_status: Optional[str] = None,
        interview_filter: Optional[str] = None,
        sort_by: str = "newest",
        order: str = "desc",
        page: int = 1,
        per_page: int = 25,
    ) -> Tuple[List[Job], int]:
        """Query applications with advanced filtering and sorting for Application Command Center."""
        conditions = []
        params: List[Any] = []

        target_int_filter = interview_status or interview_filter

        if status and status.strip().upper() not in ("ALL", "ANY"):
            st = status.strip().upper()
            if st == "ACTIVE":
                conditions.append("status IN ('NEW', 'VIEWED', 'SHORTLISTED', 'APPLIED', 'INTERVIEW')")
            elif st == "IN_PROGRESS":
                conditions.append("status IN ('APPLIED', 'INTERVIEW')")
            else:
                conditions.append("status = ?")
                params.append(st)

        if priority and priority.strip().upper() not in ("ALL", "ANY"):
            conditions.append("application_priority = ?")
            params.append(priority.strip().upper())

        if min_score is not None and min_score > 0:
            conditions.append("match_score >= ?")
            params.append(int(min_score))

        if min_readiness is not None and min_readiness > 0:
            conditions.append("application_readiness_score >= ?")
            params.append(int(min_readiness))

        if company and company.strip():
            conditions.append("company LIKE ?")
            params.append(f"%{company.strip()}%")

        if role and role.strip():
            conditions.append("title LIKE ?")
            params.append(f"%{role.strip()}%")

        if location and location.strip():
            conditions.append("location LIKE ?")
            params.append(f"%{location.strip()}%")

        if source and source.strip().lower() not in ("all", "any"):
            conditions.append("LOWER(source) = ?")
            params.append(source.strip().lower())

        if search and search.strip():
            term = f"%{search.strip()}%"
            conditions.append("(title LIKE ? OR company LIKE ? OR location LIKE ? OR notes LIKE ? OR interview_notes LIKE ?)")
            params.extend([term, term, term, term, term])

        if applied_days is not None and applied_days >= 0:
            if applied_days == 0:
                conditions.append("date(applied_at) = date('now')")
            else:
                conditions.append("applied_at >= datetime('now', ?)")
                params.append(f"-{int(applied_days)} days")

        if follow_up_filter and follow_up_filter.strip().lower() not in ("all", "any"):
            fu = follow_up_filter.strip().lower()
            if fu == "due":
                conditions.append("follow_up_date IS NOT NULL AND follow_up_date != '' AND (follow_up_date <= date('now') OR follow_up_date <= date('now', 'localtime')) AND status NOT IN ('REJECTED', 'NOT_INTERESTED', 'OFFER')")
            elif fu == "overdue":
                conditions.append("follow_up_date IS NOT NULL AND follow_up_date != '' AND (follow_up_date < date('now') OR follow_up_date < date('now', 'localtime')) AND status NOT IN ('REJECTED', 'NOT_INTERESTED', 'OFFER')")
            elif fu == "upcoming":
                conditions.append("follow_up_date IS NOT NULL AND follow_up_date != '' AND (follow_up_date > date('now') AND follow_up_date > date('now', 'localtime')) AND status NOT IN ('REJECTED', 'NOT_INTERESTED', 'OFFER')")
            elif fu == "has_date":
                conditions.append("follow_up_date IS NOT NULL AND follow_up_date != ''")
            elif fu == "none":
                conditions.append("(follow_up_date IS NULL OR follow_up_date = '')")

        if target_int_filter and target_int_filter.strip().upper() not in ("ALL", "ANY"):
            ist = target_int_filter.strip().upper()
            if ist == "SCHEDULED":
                conditions.append("(interview_status = 'SCHEDULED' OR (interview_date IS NOT NULL AND interview_date != ''))")
            elif ist == "ACTIVE":
                conditions.append("(interview_status = 'SCHEDULED' OR status = 'INTERVIEW')")
            elif ist == "NONE":
                conditions.append("(interview_status IS NULL OR interview_status = 'NOT_SCHEDULED')")
            else:
                conditions.append("interview_status = ?")
                params.append(ist)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        allowed_sorts = {
            "newest": "COALESCE(first_seen_at, created_at)",
            "oldest": "COALESCE(first_seen_at, created_at)",
            "match_score": "match_score",
            "readiness": "application_readiness_score",
            "priority": "CASE application_priority WHEN 'URGENT' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'NORMAL' THEN 3 WHEN 'LOW' THEN 4 ELSE 5 END",
            "applied_at": "CASE WHEN applied_at IS NULL THEN 1 ELSE 0 END, applied_at",
            "follow_up": "CASE WHEN follow_up_date IS NULL OR follow_up_date = '' THEN 1 ELSE 0 END, follow_up_date",
            "interview_date": "CASE WHEN interview_date IS NULL OR interview_date = '' THEN 1 ELSE 0 END, interview_date",
            "company": "company",
            "title": "title",
        }
        sort_col = allowed_sorts.get(sort_by.lower(), "COALESCE(first_seen_at, created_at)")
        sort_dir = "ASC" if order.lower() == "asc" else "DESC"
        order_clause = f"ORDER BY {sort_col} {sort_dir}, id DESC"

        limit = max(1, min(100, int(per_page)))
        offset = max(0, (max(1, int(page)) - 1) * limit)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            count_sql = f"SELECT COUNT(*) AS total FROM jobs {where_clause};"
            cursor.execute(count_sql, params)
            total_count = cursor.fetchone()["total"]

            data_sql = f"SELECT * FROM jobs {where_clause} {order_clause} LIMIT ? OFFSET ?;"
            query_params = list(params) + [limit, offset]
            cursor.execute(data_sql, query_params)
            rows = cursor.fetchall()
            jobs = [self._row_to_job(row) for row in rows]

            return jobs, total_count

    def get_daily_actions(self, limit: int = 50) -> List[DailyActionItem]:
        """Aggregate prioritized daily actions for 'What should I work on today?'.

        Priority hierarchy (deterministic Section 12):
        1. Interview Today (interview_date == today)
        2. Interview Soon (today < interview_date <= today + 5 days)
        3. Follow-up Due (follow_up_date <= today, not inactive)
        4. Urgent Apply Today (priority URGENT, not applied/inactive)
        5. High Priority Applications (priority HIGH, not applied/inactive)
        6. Resume Preparation Needed (match_score >= 60, prep_status in (NOT_REVIEWED, REVIEWED), not applied/inactive)
        7. Other Recommended Jobs (priority NORMAL, not applied/inactive)
        """
        today_date = date.today()
        today_str = today_date.isoformat()
        five_days_ahead = (today_date + timedelta(days=5)).isoformat()

        actions: List[DailyActionItem] = []
        seen_job_ids: Set[int] = set()

        all_jobs = self.get_all_jobs()

        # Tier 1: Interview Today
        for j in all_jobs:
            if j.id not in seen_job_ids and j.interview_date:
                i_date_str = str(j.interview_date)[:10]
                if i_date_str == today_str and getattr(j, "interview_status", "") != "COMPLETED":
                    stage_lbl = getattr(j, "interview_stage", "") or "General Interview"
                    actions.append(
                        DailyActionItem(
                            priority_rank=1,
                            priority_label="Interview Today",
                            badge_class="priority-urgent",
                            action_type="INTERVIEW",
                            action_title=f"Interview Today with {j.company}",
                            reason=f"Interview scheduled for today ({stage_lbl}). Review interview questions and technical topics.",
                            job_id=j.id,
                            company=j.company,
                            title=j.title,
                            location=j.location,
                            job_url=j.url,
                            action_url=f"/interview-prep?job_id={j.id}",
                            action_btn_text="Prepare for Interview →",
                            match_score=j.match_score,
                            readiness_score=j.application_readiness_score,
                            due_date=j.interview_date,
                        )
                    )
                    seen_job_ids.add(j.id)

        # Tier 2: Interview Soon (Next 5 Days)
        for j in all_jobs:
            if j.id not in seen_job_ids and j.interview_date:
                i_date_str = str(j.interview_date)[:10]
                if today_str < i_date_str <= five_days_ahead and getattr(j, "interview_status", "") == "SCHEDULED":
                    stage_lbl = getattr(j, "interview_stage", "") or "Interview"
                    actions.append(
                        DailyActionItem(
                            priority_rank=2,
                            priority_label="Interview Soon",
                            badge_class="priority-high",
                            action_type="INTERVIEW",
                            action_title=f"Upcoming Interview with {j.company}",
                            reason=f"Interview scheduled for {i_date_str} ({stage_lbl}). Practice project and likely technical questions.",
                            job_id=j.id,
                            company=j.company,
                            title=j.title,
                            location=j.location,
                            job_url=j.url,
                            action_url=f"/interview-prep?job_id={j.id}",
                            action_btn_text="Open Prep Guide →",
                            match_score=j.match_score,
                            readiness_score=j.application_readiness_score,
                            due_date=j.interview_date,
                        )
                    )
                    seen_job_ids.add(j.id)

        # Tier 3: Follow-up Due (Today or Overdue)
        inactive_statuses = {"REJECTED", "NOT_INTERESTED", "OFFER"}
        for j in all_jobs:
            if j.id not in seen_job_ids and j.follow_up_date:
                fu_str = str(j.follow_up_date)[:10]
                st_val = j.status.value if hasattr(j.status, "value") else str(j.status)
                if fu_str <= today_str and st_val not in inactive_statuses:
                    try:
                        fu_date = date.fromisoformat(fu_str)
                        overdue_days = (today_date - fu_date).days
                    except Exception:
                        overdue_days = 0

                    if overdue_days > 0:
                        reason_msg = f"Follow-up overdue by {overdue_days} day{'s' if overdue_days != 1 else ''}. Send check-in note."
                    else:
                        reason_msg = "Follow-up due today. Check application status and reach out."

                    actions.append(
                        DailyActionItem(
                            priority_rank=3,
                            priority_label="Follow-up Due",
                            badge_class="priority-normal",
                            action_type="FOLLOW_UP",
                            action_title=f"Follow-up with {j.company}",
                            reason=reason_msg,
                            job_id=j.id,
                            company=j.company,
                            title=j.title,
                            location=j.location,
                            job_url=j.url,
                            action_url=f"/jobs/{j.id}#follow-up-card",
                            action_btn_text="Manage Follow-up →",
                            match_score=j.match_score,
                            readiness_score=j.application_readiness_score,
                            due_date=j.follow_up_date,
                        )
                    )
                    seen_job_ids.add(j.id)

        # Tier 4: Urgent Apply Today
        unapplied_excluded = {"APPLIED", "REJECTED", "NOT_INTERESTED", "INTERVIEW", "OFFER"}
        for j in all_jobs:
            if j.id not in seen_job_ids:
                st_val = j.status.value if hasattr(j.status, "value") else str(j.status)
                prio_val = j.application_priority.value if hasattr(j.application_priority, "value") else str(j.application_priority or "")
                if prio_val == "URGENT" and st_val not in unapplied_excluded:
                    actions.append(
                        DailyActionItem(
                            priority_rank=4,
                            priority_label="Urgent Application",
                            badge_class="priority-urgent",
                            action_type="APPLY",
                            action_title=f"Apply Urgently to {j.company}",
                            reason=f"Top recommendation — Readiness {j.application_readiness_score}/100, Match {j.match_score}/100.",
                            job_id=j.id,
                            company=j.company,
                            title=j.title,
                            location=j.location,
                            job_url=j.url,
                            action_url=f"/jobs/{j.id}",
                            action_btn_text="Review & Apply →",
                            match_score=j.match_score,
                            readiness_score=j.application_readiness_score,
                        )
                    )
                    seen_job_ids.add(j.id)

        # Tier 5: High Priority Applications
        for j in all_jobs:
            if j.id not in seen_job_ids:
                st_val = j.status.value if hasattr(j.status, "value") else str(j.status)
                prio_val = j.application_priority.value if hasattr(j.application_priority, "value") else str(j.application_priority or "")
                if prio_val == "HIGH" and st_val not in unapplied_excluded:
                    actions.append(
                        DailyActionItem(
                            priority_rank=5,
                            priority_label="High Priority",
                            badge_class="priority-high",
                            action_type="APPLY",
                            action_title=f"High Priority: {j.company}",
                            reason=f"Strong fit — Readiness {j.application_readiness_score}/100, Match {j.match_score}/100.",
                            job_id=j.id,
                            company=j.company,
                            title=j.title,
                            location=j.location,
                            job_url=j.url,
                            action_url=f"/jobs/{j.id}",
                            action_btn_text="Review & Apply →",
                            match_score=j.match_score,
                            readiness_score=j.application_readiness_score,
                        )
                    )
                    seen_job_ids.add(j.id)

        # Tier 6: Resume Preparation Needed
        for j in all_jobs:
            if j.id not in seen_job_ids:
                st_val = j.status.value if hasattr(j.status, "value") else str(j.status)
                prep_st = j.preparation_status.value if hasattr(j.preparation_status, "value") else str(j.preparation_status or "NOT_REVIEWED")
                if (j.match_score or 0) >= 60 and prep_st in ("NOT_REVIEWED", "REVIEWED") and st_val not in unapplied_excluded:
                    actions.append(
                        DailyActionItem(
                            priority_rank=6,
                            priority_label="Resume Prep Needed",
                            badge_class="priority-normal",
                            action_type="PREPARE",
                            action_title=f"Tailor Resume for {j.company}",
                            reason=f"Resume preparation pending ({prep_st}) — Alignment {j.resume_alignment_score or 'N/A'}/100.",
                            job_id=j.id,
                            company=j.company,
                            title=j.title,
                            location=j.location,
                            job_url=j.url,
                            action_url=f"/jobs/{j.id}#resume-prep",
                            action_btn_text="Prepare Resume →",
                            match_score=j.match_score,
                            readiness_score=j.application_readiness_score,
                        )
                    )
                    seen_job_ids.add(j.id)

        # Tier 7: Other Recommended Jobs
        for j in all_jobs:
            if j.id not in seen_job_ids:
                st_val = j.status.value if hasattr(j.status, "value") else str(j.status)
                prio_val = j.application_priority.value if hasattr(j.application_priority, "value") else str(j.application_priority or "")
                if prio_val == "NORMAL" and st_val not in unapplied_excluded:
                    actions.append(
                        DailyActionItem(
                            priority_rank=7,
                            priority_label="Recommended",
                            badge_class="priority-low",
                            action_type="APPLY",
                            action_title=f"Recommended Job: {j.company}",
                            reason=f"Normal priority candidate — Readiness {j.application_readiness_score}/100, Match {j.match_score}/100.",
                            job_id=j.id,
                            company=j.company,
                            title=j.title,
                            location=j.location,
                            job_url=j.url,
                            action_url=f"/jobs/{j.id}",
                            action_btn_text="Review Posting →",
                            match_score=j.match_score,
                            readiness_score=j.application_readiness_score,
                        )
                    )
                    seen_job_ids.add(j.id)

        return actions[:limit]

    def get_upcoming_follow_ups(self, limit: int = 10) -> List[Job]:
        """Retrieve upcoming and due follow-ups ordered by date ascending."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM jobs
                WHERE follow_up_date IS NOT NULL
                  AND follow_up_date != ''
                  AND status NOT IN ('REJECTED', 'NOT_INTERESTED', 'OFFER')
                ORDER BY follow_up_date ASC, id ASC
                LIMIT ?;
                """,
                (int(limit),),
            )
            rows = cursor.fetchall()
            return [self._row_to_job(r) for r in rows]

    def get_job_by_id(self, job_id: int) -> Optional[Job]:
        """Retrieve a single job by its database primary key ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ? LIMIT 1;", (int(job_id),))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def get_recent_jobs(self, limit: int = 50, days: Optional[int] = None) -> List[Job]:
        """Retrieve recent jobs, ordered from newest to oldest.

        Args:
            limit: Maximum number of jobs to return.
            days: Optional integer filter for jobs found within the last N days.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if days is not None:
                cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
                cursor.execute(
                    "SELECT * FROM jobs WHERE date_found >= ? ORDER BY date_found DESC LIMIT ?;",
                    (cutoff, int(limit)),
                )
            else:
                cursor.execute(
                    "SELECT * FROM jobs ORDER BY date_found DESC LIMIT ?;",
                    (int(limit),),
                )
            rows = cursor.fetchall()
            return [self._row_to_job(row) for row in rows]

    def get_jobs_by_date(self, target_date: Union[str, date, datetime]) -> List[Job]:
        """Retrieve jobs discovered on a specific date (YYYY-MM-DD)."""
        if isinstance(target_date, (date, datetime)):
            date_str = target_date.strftime("%Y-%m-%d")
        else:
            date_str = str(target_date)[:10]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Match date prefix in ISO timestamp (e.g. '2026-10-06%')
            cursor.execute(
                "SELECT * FROM jobs WHERE date_found LIKE ? ORDER BY date_found DESC;",
                (f"{date_str}%",),
            )
            rows = cursor.fetchall()
            return [self._row_to_job(row) for row in rows]

    def get_all_jobs(self, limit: Optional[int] = None) -> List[Job]:
        """Retrieve all stored jobs, ordered from newest to oldest."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM jobs ORDER BY date_found DESC"
            if limit:
                query += f" LIMIT {int(limit)}"
            cursor.execute(query)
            rows = cursor.fetchall()
            return [self._row_to_job(row) for row in rows]

    def create_pipeline_run(
        self,
        run_id: str,
        started_at: Optional[datetime] = None,
        status: str = "RUNNING",
        sources_attempted: Optional[List[str]] = None,
    ) -> None:
        """Create a new pipeline execution record in the pipeline_runs table."""
        start_iso = (started_at or datetime.now(timezone.utc)).isoformat()
        sources_str = ", ".join(sources_attempted) if sources_attempted else ""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO pipeline_runs (
                    run_id, started_at, status, sources_attempted
                ) VALUES (?, ?, ?, ?);
                """,
                (run_id, start_iso, status, sources_str),
            )
            conn.commit()

    def update_pipeline_run(
        self,
        run_id: str,
        completed_at: Optional[datetime] = None,
        status: Optional[str] = None,
        raw_collected: int = 0,
        normalized: int = 0,
        filtered: int = 0,
        relevant: int = 0,
        strong: int = 0,
        excellent: int = 0,
        new_jobs: int = 0,
        duplicate_jobs: int = 0,
        error_count: int = 0,
        notes: Optional[str] = None,
        source_results: Optional[str] = None,
    ) -> None:
        """Update metrics and completion status for a pipeline execution."""
        comp_iso = (completed_at or datetime.now(timezone.utc)).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE pipeline_runs SET
                    completed_at = ?,
                    status = COALESCE(?, status),
                    raw_collected = ?,
                    normalized = ?,
                    filtered = ?,
                    relevant = ?,
                    strong = ?,
                    excellent = ?,
                    new_jobs = ?,
                    duplicate_jobs = ?,
                    error_count = ?,
                    notes = COALESCE(?, notes),
                    source_results = COALESCE(?, source_results)
                WHERE run_id = ?;
                """,
                (
                    comp_iso,
                    status,
                    raw_collected,
                    normalized,
                    filtered,
                    relevant,
                    strong,
                    excellent,
                    new_jobs,
                    duplicate_jobs,
                    error_count,
                    notes,
                    source_results,
                    run_id,
                ),
            )
            conn.commit()

    def get_pipeline_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a pipeline run record by its run ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pipeline_runs WHERE run_id = ? LIMIT 1;", (run_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_recent_pipeline_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent pipeline execution runs."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?;",
                (int(limit),),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_dashboard_counts(self, daily_target: Optional[int] = None) -> Dict[str, Any]:
        """Aggregate summary statistics for the dashboard homepage."""
        today_iso = date.today().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'NEW' THEN 1 ELSE 0 END) AS new_jobs,
                    SUM(CASE WHEN match_score >= 90 THEN 1 ELSE 0 END) AS high_priority,
                    SUM(CASE WHEN match_score >= 80 THEN 1 ELSE 0 END) AS strong_matches,
                    SUM(CASE WHEN status = 'SHORTLISTED' THEN 1 ELSE 0 END) AS shortlisted,
                    SUM(CASE WHEN status = 'APPLIED' THEN 1 ELSE 0 END) AS applied,
                    SUM(CASE WHEN status = 'INTERVIEW' THEN 1 ELSE 0 END) AS interview,
                    SUM(CASE WHEN status = 'OFFER' THEN 1 ELSE 0 END) AS offers,
                    SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) AS rejected,
                    SUM(CASE WHEN status = 'NOT_INTERESTED' THEN 1 ELSE 0 END) AS not_interested,
                    SUM(CASE WHEN application_priority IN ('URGENT', 'HIGH', 'NORMAL') AND status NOT IN ('APPLIED', 'REJECTED', 'NOT_INTERESTED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS apply_today,
                    SUM(CASE WHEN application_priority = 'URGENT' AND status NOT IN ('APPLIED', 'REJECTED', 'NOT_INTERESTED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS urgent_applications,
                    SUM(CASE WHEN application_priority = 'HIGH' AND status NOT IN ('APPLIED', 'REJECTED', 'NOT_INTERESTED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS high_applications,
                    SUM(CASE WHEN application_priority = 'NORMAL' AND status NOT IN ('APPLIED', 'REJECTED', 'NOT_INTERESTED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS normal_applications,
                    SUM(CASE WHEN application_priority = 'LOW' AND status NOT IN ('APPLIED', 'REJECTED', 'NOT_INTERESTED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS low_applications,
                    SUM(CASE WHEN status = 'APPLIED' AND date(status_updated_at) = ? THEN 1 ELSE 0 END) AS applied_today,
                    SUM(CASE WHEN follow_up_date IS NOT NULL AND follow_up_date != '' AND (follow_up_date <= ? OR follow_up_date <= date('now')) AND status NOT IN ('REJECTED', 'NOT_INTERESTED', 'OFFER') THEN 1 ELSE 0 END) AS follow_ups_due,
                    SUM(CASE WHEN follow_up_date IS NOT NULL AND follow_up_date != '' AND (follow_up_date = ? OR follow_up_date = date('now')) AND status NOT IN ('REJECTED', 'NOT_INTERESTED', 'OFFER') THEN 1 ELSE 0 END) AS follow_ups_due_today,
                    SUM(CASE WHEN follow_up_date IS NOT NULL AND follow_up_date != '' AND (follow_up_date < ? OR follow_up_date < date('now')) AND status NOT IN ('REJECTED', 'NOT_INTERESTED', 'OFFER') THEN 1 ELSE 0 END) AS overdue_follow_ups,
                    SUM(CASE WHEN follow_up_date IS NOT NULL AND follow_up_date != '' AND (follow_up_date > ? AND follow_up_date > date('now')) AND status NOT IN ('REJECTED', 'NOT_INTERESTED', 'OFFER') THEN 1 ELSE 0 END) AS upcoming_follow_ups,
                    SUM(CASE WHEN interview_status = 'SCHEDULED' THEN 1 ELSE 0 END) AS interviews_scheduled,
                    SUM(CASE WHEN interview_date IS NOT NULL AND interview_date != '' AND interview_status = 'SCHEDULED' AND (interview_date >= ? OR interview_date >= date('now')) THEN 1 ELSE 0 END) AS interviews_upcoming,
                    SUM(CASE WHEN status = 'INTERVIEW' OR interview_status = 'SCHEDULED' THEN 1 ELSE 0 END) AS interviews_active,
                    AVG(CASE WHEN status NOT IN ('APPLIED', 'REJECTED', 'NOT_INTERESTED', 'INTERVIEW', 'OFFER') THEN application_readiness_score ELSE NULL END) AS avg_readiness,
                    SUM(CASE WHEN preparation_status = 'READY_TO_APPLY' THEN 1 ELSE 0 END) AS prep_ready_to_apply,
                    SUM(CASE WHEN application_priority IN ('URGENT', 'HIGH') AND status NOT IN ('APPLIED', 'REJECTED', 'NOT_INTERESTED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS prep_urgent_high,
                    AVG(CASE WHEN status NOT IN ('APPLIED', 'REJECTED', 'NOT_INTERESTED', 'INTERVIEW', 'OFFER') THEN resume_alignment_score ELSE NULL END) AS avg_resume_alignment
                FROM jobs;
                """,
                (today_iso, today_iso, today_iso, today_iso, today_iso, today_iso),
            )
            row = cursor.fetchone()
            if not row:
                res = {
                    "total": 0, "new_jobs": 0, "high_priority": 0, "strong_matches": 0,
                    "shortlisted": 0, "applied": 0, "interview": 0, "offers": 0,
                    "rejected": 0, "not_interested": 0,
                    "apply_today": 0, "urgent_applications": 0, "high_applications": 0,
                    "normal_applications": 0, "low_applications": 0,
                    "applied_today": 0, "follow_ups_due": 0, "follow_ups_due_today": 0, "overdue_follow_ups": 0,
                    "upcoming_follow_ups": 0, "interviews_scheduled": 0,
                    "interviews_upcoming": 0, "interviews_active": 0,
                    "avg_readiness": 0.0, "prep_ready_to_apply": 0, "prep_urgent_high": 0,
                    "avg_resume_alignment": 0.0,
                }
            else:
                avg_r = round(float(row["avg_readiness"]), 1) if row["avg_readiness"] is not None else 0.0
                avg_ra = round(float(row["avg_resume_alignment"]), 1) if row["avg_resume_alignment"] is not None else 0.0
                res = {
                    "total": row["total"] or 0,
                    "new_jobs": row["new_jobs"] or 0,
                    "high_priority": row["high_priority"] or 0,
                    "strong_matches": row["strong_matches"] or 0,
                    "shortlisted": row["shortlisted"] or 0,
                    "applied": row["applied"] or 0,
                    "interview": row["interview"] or 0,
                    "offers": row["offers"] or 0,
                    "rejected": row["rejected"] or 0,
                    "not_interested": row["not_interested"] or 0,
                    "apply_today": row["apply_today"] or 0,
                    "urgent_applications": row["urgent_applications"] or 0,
                    "high_applications": row["high_applications"] or 0,
                    "normal_applications": row["normal_applications"] or 0,
                    "low_applications": row["low_applications"] or 0,
                    "applied_today": row["applied_today"] or 0,
                    "follow_ups_due": row["follow_ups_due"] or 0,
                    "follow_ups_due_today": row["follow_ups_due_today"] or 0,
                    "overdue_follow_ups": row["overdue_follow_ups"] or 0,
                    "upcoming_follow_ups": row["upcoming_follow_ups"] or 0,
                    "interviews_scheduled": row["interviews_scheduled"] or 0,
                    "interviews_upcoming": row["interviews_upcoming"] or 0,
                    "interviews_active": row["interviews_active"] or 0,
                    "avg_readiness": avg_r,
                    "prep_ready_to_apply": row["prep_ready_to_apply"] or 0,
                    "prep_urgent_high": row["prep_urgent_high"] or 0,
                    "avg_resume_alignment": avg_ra,
                }
            if daily_target is not None:
                res["daily_target"] = daily_target
                res["remaining_today"] = max(0, daily_target - res["applied_today"])
            return res

    def get_distinct_sources(self) -> List[str]:
        """Retrieve distinct job source names present in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT source FROM jobs WHERE source IS NOT NULL ORDER BY source ASC;")
            return [row["source"] for row in cursor.fetchall()]

    def get_distinct_companies(self) -> List[str]:
        """Retrieve distinct hiring company names present in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT company FROM jobs WHERE company IS NOT NULL AND company != '' ORDER BY company ASC;")
            return [row["company"] for row in cursor.fetchall()]

    def get_distinct_locations(self) -> List[str]:
        """Retrieve distinct location strings present in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT location FROM jobs WHERE location IS NOT NULL AND location != '' ORDER BY location ASC;")
            return [row["location"] for row in cursor.fetchall()]

    def get_jobs_filtered(
        self,
        min_score: Optional[int] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        location: Optional[str] = None,
        company: Optional[str] = None,
        search: Optional[str] = None,
        first_seen_days: Optional[int] = None,
        priority: Optional[str] = None,
        min_readiness: Optional[int] = None,
        min_resume_alignment: Optional[int] = None,
        preparation_status: Optional[str] = None,
        prep_priority_only: bool = False,
        actionable_only: bool = False,
        exclude_inactive: bool = False,
        sort_by: str = "match_score",
        order: str = "desc",
        page: int = 1,
        per_page: int = 25,
    ) -> Tuple[List[Job], int]:
        """Query jobs with dynamic filters, sorting, and pagination.

        Safe against SQL injection using parameterized queries.
        """
        conditions = []
        params: List[Any] = []

        if min_score is not None and min_score > 0:
            conditions.append("match_score >= ?")
            params.append(int(min_score))

        if min_readiness is not None and min_readiness > 0:
            conditions.append("application_readiness_score >= ?")
            params.append(int(min_readiness))

        if min_resume_alignment is not None and min_resume_alignment > 0:
            conditions.append("resume_alignment_score >= ?")
            params.append(int(min_resume_alignment))

        if preparation_status and preparation_status.strip().upper() != "ALL":
            conditions.append("preparation_status = ?")
            params.append(preparation_status.strip().upper())

        if prep_priority_only:
            conditions.append("application_priority IN ('URGENT', 'HIGH')")
        elif actionable_only:
            conditions.append("application_priority IN ('URGENT', 'HIGH', 'NORMAL')")
        elif priority and priority.strip().upper() != "ALL":
            conditions.append("application_priority = ?")
            params.append(priority.strip().upper())

        if exclude_inactive or actionable_only:
            conditions.append("status NOT IN ('APPLIED', 'REJECTED', 'NOT_INTERESTED', 'INTERVIEW', 'OFFER')")

        if status and status.strip().upper() != "ALL":
            conditions.append("status = ?")
            params.append(status.strip().upper())

        if source and source.strip().lower() != "all":
            conditions.append("LOWER(source) = ?")
            params.append(source.strip().lower())

        if company and company.strip():
            conditions.append("company LIKE ?")
            params.append(f"%{company.strip()}%")

        if location and location.strip():
            conditions.append("location LIKE ?")
            params.append(f"%{location.strip()}%")

        if search and search.strip():
            term = f"%{search.strip()}%"
            conditions.append("(title LIKE ? OR company LIKE ? OR location LIKE ? OR description LIKE ?)")
            params.extend([term, term, term, term])

        if first_seen_days is not None:
            if first_seen_days == 0:
                # Today
                conditions.append("date(first_seen_at) = date('now')")
            elif first_seen_days > 0:
                conditions.append("first_seen_at >= datetime('now', ?)")
                params.append(f"-{int(first_seen_days)} days")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        allowed_sorts = {
            "match_score": "match_score",
            "application_readiness_score": "application_readiness_score",
            "readiness": "application_readiness_score",
            "resume_alignment_score": "resume_alignment_score",
            "resume_alignment": "resume_alignment_score",
            "preparation_status": "preparation_status",
            "priority": "CASE application_priority WHEN 'URGENT' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'NORMAL' THEN 3 WHEN 'LOW' THEN 4 ELSE 5 END",
            "date_posted": "date_posted",
            "first_seen_at": "first_seen_at",
            "last_seen_at": "last_seen_at",
            "created_at": "created_at",
            "title": "title",
            "company": "company",
        }
        sort_col = allowed_sorts.get(sort_by.lower(), "match_score")
        sort_dir = "ASC" if order.lower() == "asc" else "DESC"
        order_clause = f"ORDER BY {sort_col} {sort_dir}, id DESC"

        limit = max(1, min(100, int(per_page)))
        offset = max(0, (max(1, int(page)) - 1) * limit)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            count_sql = f"SELECT COUNT(*) AS total FROM jobs {where_clause};"
            cursor.execute(count_sql, params)
            total_count = cursor.fetchone()["total"]

            data_sql = f"SELECT * FROM jobs {where_clause} {order_clause} LIMIT ? OFFSET ?;"
            query_params = list(params) + [limit, offset]
            cursor.execute(data_sql, query_params)
            rows = cursor.fetchall()
            jobs = [self._row_to_job(row) for row in rows]

            return jobs, total_count

    def get_source_health(self) -> List[Dict[str, Any]]:
        """Retrieve latest health and status metrics for all configured sources."""
        from app.config.settings import get_settings
        settings = get_settings()

        recent_runs = self.get_recent_pipeline_runs(limit=1)
        latest_run = recent_runs[0] if recent_runs else None
        source_results: Dict[str, Any] = {}
        if latest_run and latest_run.get("source_results"):
            try:
                source_results = json.loads(latest_run["source_results"])
            except Exception:
                source_results = {}

        configured_sources = [
            ("lever", settings.LEVER_ENABLED, "api.lever.co"),
            ("greenhouse", settings.GREENHOUSE_ENABLED, "boards-api.greenhouse.io"),
            ("naukri", settings.NAUKRI_ENABLED, "naukri.com (Playwright)"),
            ("linkedin", True, "linkedin.com (Placeholder)"),
        ]

        health_list = []
        for src_name, is_enabled, endpoint in configured_sources:
            s_data = source_results.get(src_name, {})
            status = s_data.get("status")
            if not status:
                if not is_enabled:
                    status = "DISABLED"
                elif latest_run:
                    status = "COMPLETED" if latest_run.get("status") in ("COMPLETED", "COMPLETED_WITH_SOURCE_WARNINGS") else "UNKNOWN"
                else:
                    status = "IDLE"

            coll = s_data.get("collected", 0)
            err = s_data.get("error")

            health_list.append({
                "source": src_name.capitalize(),
                "enabled": is_enabled,
                "endpoint": endpoint,
                "status": status,
                "collected": coll,
                "error": err or "None",
                "last_run_id": latest_run.get("run_id") if latest_run else "None",
                "last_run_time": latest_run.get("completed_at") or latest_run.get("started_at") if latest_run else "Never",
            })
        return health_list

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        """Helper to convert a SQLite row back to a Job model instance."""
        date_found_val = row["date_found"]
        try:
            parsed_date_found = datetime.fromisoformat(date_found_val)
        except (ValueError, TypeError):
            parsed_date_found = datetime.now(timezone.utc)

        parsed_created_at = None
        if "created_at" in row.keys() and row["created_at"]:
            try:
                parsed_created_at = datetime.fromisoformat(row["created_at"])
            except Exception:
                pass

        parsed_updated_at = None
        if "updated_at" in row.keys() and row["updated_at"]:
            try:
                parsed_updated_at = datetime.fromisoformat(row["updated_at"])
            except Exception:
                pass

        parsed_status = JobStatus.NEW
        if "status" in row.keys() and row["status"]:
            try:
                parsed_status = JobStatus(row["status"])
            except ValueError:
                parsed_status = JobStatus.NEW

        parsed_status_updated = None
        if "status_updated_at" in row.keys() and row["status_updated_at"]:
            try:
                parsed_status_updated = datetime.fromisoformat(row["status_updated_at"])
            except Exception:
                pass

        parsed_first_seen = None
        if "first_seen_at" in row.keys() and row["first_seen_at"]:
            try:
                parsed_first_seen = datetime.fromisoformat(row["first_seen_at"])
            except Exception:
                pass
        if not parsed_first_seen:
            parsed_first_seen = parsed_created_at or parsed_date_found

        parsed_last_seen = None
        if "last_seen_at" in row.keys() and row["last_seen_at"]:
            try:
                parsed_last_seen = datetime.fromisoformat(row["last_seen_at"])
            except Exception:
                pass
        if not parsed_last_seen:
            parsed_last_seen = parsed_updated_at or parsed_date_found

        run_id_val = row["last_seen_run_id"] if "last_seen_run_id" in row.keys() else None
        notes_val = row["notes"] if "notes" in row.keys() else None

        raw_meta = {}
        if "raw_metadata" in row.keys() and row["raw_metadata"]:
            try:
                raw_meta = json.loads(row["raw_metadata"])
            except json.JSONDecodeError:
                raw_meta = {}

        s_id = row["source_job_id"] if "source_job_id" in row.keys() else None

        score_val = row["match_score"] if "match_score" in row.keys() else None
        cat_val = row["match_category"] if "match_category" in row.keys() else None

        roles_val: List[str] = []
        if "matched_roles" in row.keys() and row["matched_roles"]:
            try:
                roles_val = json.loads(row["matched_roles"])
            except Exception:
                roles_val = []

        skills_val: List[str] = []
        if "matched_skills" in row.keys() and row["matched_skills"]:
            try:
                skills_val = json.loads(row["matched_skills"])
            except Exception:
                skills_val = []

        locs_val: List[str] = []
        if "matched_locations" in row.keys() and row["matched_locations"]:
            try:
                locs_val = json.loads(row["matched_locations"])
            except Exception:
                locs_val = []

        exp_match_val = bool(row["experience_match"]) if "experience_match" in row.keys() else False

        excl_val: List[str] = []
        if "excluded_reasons" in row.keys() and row["excluded_reasons"]:
            try:
                excl_val = json.loads(row["excluded_reasons"])
            except Exception:
                excl_val = []

        readiness_val = row["application_readiness_score"] if "application_readiness_score" in row.keys() else None
        prio_val = None
        if "application_priority" in row.keys() and row["application_priority"]:
            try:
                from app.models.job import ApplicationPriority
                prio_val = ApplicationPriority(row["application_priority"])
            except Exception:
                prio_val = None

        missing_skills_val: List[str] = []
        if "missing_skills" in row.keys() and row["missing_skills"]:
            try:
                missing_skills_val = json.loads(row["missing_skills"])
            except Exception:
                missing_skills_val = []

        crit_gaps_val: List[str] = []
        if "critical_gaps" in row.keys() and row["critical_gaps"]:
            try:
                crit_gaps_val = json.loads(row["critical_gaps"])
            except Exception:
                crit_gaps_val = []

        mod_gaps_val: List[str] = []
        if "moderate_gaps" in row.keys() and row["moderate_gaps"]:
            try:
                mod_gaps_val = json.loads(row["moderate_gaps"])
            except Exception:
                mod_gaps_val = []

        min_gaps_val: List[str] = []
        if "minor_gaps" in row.keys() and row["minor_gaps"]:
            try:
                min_gaps_val = json.loads(row["minor_gaps"])
            except Exception:
                min_gaps_val = []

        rec_reasons_val: List[str] = []
        if "recommendation_reasons" in row.keys() and row["recommendation_reasons"]:
            try:
                rec_reasons_val = json.loads(row["recommendation_reasons"])
            except Exception:
                rec_reasons_val = []

        risk_reasons_val: List[str] = []
        if "risk_reasons" in row.keys() and row["risk_reasons"]:
            try:
                risk_reasons_val = json.loads(row["risk_reasons"])
            except Exception:
                risk_reasons_val = []

        profile_align_val = row["profile_alignment"] if "profile_alignment" in row.keys() else None

        checklist_val: List[str] = []
        if "checklist" in row.keys() and row["checklist"]:
            try:
                checklist_val = json.loads(row["checklist"])
            except Exception:
                checklist_val = []

        follow_up_date_val = row["follow_up_date"] if "follow_up_date" in row.keys() else None
        follow_up_notes_val = row["follow_up_notes"] if "follow_up_notes" in row.keys() else None

        resume_align_val = row["resume_alignment_score"] if "resume_alignment_score" in row.keys() else None
        resume_cat_val = row["resume_alignment_category"] if "resume_alignment_category" in row.keys() else None

        skills_to_emp_val: List[str] = []
        if "skills_to_emphasize" in row.keys() and row["skills_to_emphasize"]:
            try:
                skills_to_emp_val = json.loads(row["skills_to_emphasize"])
            except Exception:
                skills_to_emp_val = []

        resume_matched_kw_val: List[str] = []
        if "resume_matched_keywords" in row.keys() and row["resume_matched_keywords"]:
            try:
                resume_matched_kw_val = json.loads(row["resume_matched_keywords"])
            except Exception:
                resume_matched_kw_val = []

        resume_missing_kw_val: List[str] = []
        if "resume_missing_keywords" in row.keys() and row["resume_missing_keywords"]:
            try:
                resume_missing_kw_val = json.loads(row["resume_missing_keywords"])
            except Exception:
                resume_missing_kw_val = []

        rec_proj_val = row["recommended_project"] if "recommended_project" in row.keys() else None
        rec_exp_val = row["recommended_experience"] if "recommended_experience" in row.keys() else None

        resume_concerns_val: List[str] = []
        if "resume_concerns" in row.keys() and row["resume_concerns"]:
            try:
                resume_concerns_val = json.loads(row["resume_concerns"])
            except Exception:
                resume_concerns_val = []

        resume_suggestions_val: List[str] = []
        if "resume_suggestions" in row.keys() and row["resume_suggestions"]:
            try:
                resume_suggestions_val = json.loads(row["resume_suggestions"])
            except Exception:
                resume_suggestions_val = []

        prep_status_val = "NOT_REVIEWED"
        if "preparation_status" in row.keys() and row["preparation_status"]:
            prep_status_val = row["preparation_status"]

        prep_notes_val = row["preparation_notes"] if "preparation_notes" in row.keys() else None
        rec_resume_val = row["recommended_resume"] if "recommended_resume" in row.keys() else None

        applied_at_val = None
        if "applied_at" in row.keys() and row["applied_at"]:
            try:
                applied_at_val = datetime.fromisoformat(row["applied_at"])
            except Exception:
                pass

        interview_date_val = row["interview_date"] if "interview_date" in row.keys() else None
        interview_stage_val = row["interview_stage"] if "interview_stage" in row.keys() else None
        interview_status_val = (
            row["interview_status"]
            if "interview_status" in row.keys() and row["interview_status"]
            else "NOT_SCHEDULED"
        )
        interview_notes_val = row["interview_notes"] if "interview_notes" in row.keys() else None
        interview_prep_status_val = (
            row["interview_preparation_status"]
            if "interview_preparation_status" in row.keys() and row["interview_preparation_status"]
            else "NOT_STARTED"
        )

        return Job(
            id=row["id"],
            source=row["source"],
            source_job_id=s_id,
            job_id=s_id,
            title=row["title"],
            company=row["company"],
            location=row["location"],
            url=row["url"],
            description=row["description"],
            easy_apply=bool(row["easy_apply"]),
            date_posted=row["date_posted"],
            date_found=parsed_date_found,
            employment_type=row["employment_type"],
            experience_required=row["experience_required"],
            salary=row["salary"],
            fingerprint=row["fingerprint"] if "fingerprint" in row.keys() else None,
            created_at=parsed_created_at,
            updated_at=parsed_updated_at,
            extra_metadata=raw_meta,
            status=parsed_status,
            status_updated_at=parsed_status_updated,
            first_seen_at=parsed_first_seen,
            last_seen_at=parsed_last_seen,
            last_seen_run_id=run_id_val,
            notes=notes_val,
            match_score=score_val,
            match_category=cat_val,
            matched_roles=roles_val,
            matched_skills=skills_val,
            matched_locations=locs_val,
            experience_match=exp_match_val,
            excluded_reasons=excl_val,
            application_readiness_score=readiness_val,
            application_priority=prio_val,
            missing_skills=missing_skills_val,
            critical_gaps=crit_gaps_val,
            moderate_gaps=mod_gaps_val,
            minor_gaps=min_gaps_val,
            recommendation_reasons=rec_reasons_val,
            risk_reasons=risk_reasons_val,
            profile_alignment=profile_align_val,
            checklist=checklist_val,
            follow_up_date=follow_up_date_val,
            follow_up_notes=follow_up_notes_val,
            resume_alignment_score=resume_align_val,
            resume_alignment_category=resume_cat_val,
            skills_to_emphasize=skills_to_emp_val,
            resume_matched_keywords=resume_matched_kw_val,
            resume_missing_keywords=resume_missing_kw_val,
            recommended_project=rec_proj_val,
            recommended_experience=rec_exp_val,
            resume_concerns=resume_concerns_val,
            resume_suggestions=resume_suggestions_val,
            preparation_status=prep_status_val,
            preparation_notes=prep_notes_val,
            recommended_resume=rec_resume_val,
            applied_at=applied_at_val,
            interview_date=interview_date_val,
            interview_stage=interview_stage_val,
            interview_status=interview_status_val,
            interview_notes=interview_notes_val,
            interview_preparation_status=interview_prep_status_val,
        )

    # -------------------------------------------------------------------------
    # Phase 12: Application Analytics & Optimization Aggregations
    # -------------------------------------------------------------------------

    def _build_analytics_where(
        self,
        period: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source: Optional[str] = None,
        role: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Tuple[str, List[Any]]:
        """Construct WHERE clause and parameter list for analytics queries."""
        clauses = []
        params = []

        if start_date and end_date:
            clauses.append("date(COALESCE(first_seen_at, date_found)) >= ? AND date(COALESCE(first_seen_at, date_found)) <= ?")
            params.extend([start_date, end_date])
        elif period == "today":
            clauses.append("(date(COALESCE(first_seen_at, date_found)) = date('now', 'localtime') OR date(COALESCE(first_seen_at, date_found)) = date('now'))")
        elif period == "7d":
            clauses.append("(date(COALESCE(first_seen_at, date_found)) >= date('now', 'localtime', '-7 days') OR date(COALESCE(first_seen_at, date_found)) >= date('now', '-7 days'))")
        elif period == "30d":
            clauses.append("(date(COALESCE(first_seen_at, date_found)) >= date('now', 'localtime', '-30 days') OR date(COALESCE(first_seen_at, date_found)) >= date('now', '-30 days'))")
        elif period == "90d":
            clauses.append("(date(COALESCE(first_seen_at, date_found)) >= date('now', 'localtime', '-90 days') OR date(COALESCE(first_seen_at, date_found)) >= date('now', '-90 days'))")

        if source:
            clauses.append("LOWER(source) = LOWER(?)")
            params.append(source)

        if role:
            clauses.append("(LOWER(title) LIKE ? OR LOWER(COALESCE(matched_roles, '')) LIKE ?)")
            term = f"%{role.lower()}%"
            params.extend([term, term])

        if location:
            clauses.append("(LOWER(location) LIKE ? OR LOWER(COALESCE(matched_locations, '')) LIKE ?)")
            term = f"%{location.lower()}%"
            params.extend([term, term])

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return where_sql, params

    def get_analytics_summary(
        self,
        period: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source: Optional[str] = None,
        role: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate total funnel counts and averages for analytics dashboard."""
        where_sql, params = self._build_analytics_where(
            period=period,
            start_date=start_date,
            end_date=end_date,
            source=source,
            role=role,
            location=location,
        )

        query = f"""
            SELECT
                COUNT(*) AS total_jobs,
                SUM(CASE WHEN match_score >= 60 THEN 1 ELSE 0 END) AS relevant,
                SUM(CASE WHEN application_priority IN ('URGENT', 'HIGH', 'NORMAL') THEN 1 ELSE 0 END) AS recommended,
                SUM(CASE WHEN status IN ('APPLIED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS applied,
                SUM(CASE WHEN status = 'INTERVIEW' OR interview_status IN ('SCHEDULED', 'COMPLETED', 'PASSED', 'FAILED', 'RESCHEDULED') OR (interview_date IS NOT NULL AND interview_date != '') THEN 1 ELSE 0 END) AS interview,
                SUM(CASE WHEN status = 'OFFER' THEN 1 ELSE 0 END) AS offer,
                SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) AS rejected,
                SUM(CASE WHEN status = 'NOT_INTERESTED' THEN 1 ELSE 0 END) AS not_interested,
                AVG(CASE WHEN match_score >= 60 THEN match_score ELSE NULL END) AS avg_match,
                AVG(CASE WHEN match_score >= 60 THEN application_readiness_score ELSE NULL END) AS avg_readiness,
                AVG(CASE WHEN match_score >= 60 THEN resume_alignment_score ELSE NULL END) AS avg_resume_alignment
            FROM jobs
            {where_sql};
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            if not row:
                return {
                    "total_jobs": 0, "relevant": 0, "recommended": 0, "applied": 0,
                    "interview": 0, "offer": 0, "rejected": 0, "not_interested": 0,
                    "avg_match": 0.0, "avg_readiness": 0.0, "avg_resume_alignment": 0.0,
                }
            return {
                "total_jobs": row["total_jobs"] or 0,
                "relevant": row["relevant"] or 0,
                "recommended": row["recommended"] or 0,
                "applied": row["applied"] or 0,
                "interview": row["interview"] or 0,
                "offer": row["offer"] or 0,
                "rejected": row["rejected"] or 0,
                "not_interested": row["not_interested"] or 0,
                "avg_match": round(float(row["avg_match"]), 1) if row["avg_match"] is not None else 0.0,
                "avg_readiness": round(float(row["avg_readiness"]), 1) if row["avg_readiness"] is not None else 0.0,
                "avg_resume_alignment": round(float(row["avg_resume_alignment"]), 1) if row["avg_resume_alignment"] is not None else 0.0,
            }

    def get_daily_activity(
        self,
        period: str = "30d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """Retrieve daily application and discovery counts."""
        # Determine cutoff date
        date_filter = ""
        date_params: List[Any] = []
        if start_date and end_date:
            date_filter = "WHERE d >= ? AND d <= ?"
            date_params = [start_date, end_date]
        elif period == "today":
            date_filter = "WHERE d = date('now')"
        elif period == "7d":
            date_filter = "WHERE d >= date('now', '-7 days')"
        elif period == "30d":
            date_filter = "WHERE d >= date('now', '-30 days')"
        elif period == "90d":
            date_filter = "WHERE d >= date('now', '-90 days')"

        query = f"""
            WITH all_dates AS (
                SELECT DISTINCT date(COALESCE(first_seen_at, date_found)) AS d FROM jobs WHERE first_seen_at IS NOT NULL OR date_found IS NOT NULL
                UNION
                SELECT DISTINCT date(applied_at) AS d FROM jobs WHERE applied_at IS NOT NULL
                UNION
                SELECT DISTINCT date(interview_date) AS d FROM jobs WHERE interview_date IS NOT NULL
            ),
            filtered_dates AS (
                SELECT d FROM all_dates
                {date_filter}
            )
            SELECT
                fd.d AS date_str,
                (SELECT COUNT(*) FROM jobs WHERE date(COALESCE(first_seen_at, date_found)) = fd.d) AS jobs_found,
                (SELECT COUNT(*) FROM jobs WHERE date(COALESCE(first_seen_at, date_found)) = fd.d AND match_score >= 60) AS relevant,
                (SELECT COUNT(*) FROM jobs WHERE (date(applied_at) = fd.d OR (applied_at IS NULL AND status IN ('APPLIED', 'INTERVIEW', 'OFFER') AND date(status_updated_at) = fd.d))) AS applied,
                (SELECT COUNT(*) FROM jobs WHERE (date(interview_date) = fd.d OR (interview_date IS NULL AND status = 'INTERVIEW' AND date(status_updated_at) = fd.d))) AS interviews,
                (SELECT COUNT(*) FROM jobs WHERE status = 'OFFER' AND date(status_updated_at) = fd.d) AS offers
            FROM filtered_dates fd
            WHERE fd.d IS NOT NULL
            ORDER BY fd.d DESC
            LIMIT ?;
        """
        params = date_params + [limit]
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "date_str": r["date_str"],
                    "jobs_found": r["jobs_found"] or 0,
                    "relevant": r["relevant"] or 0,
                    "applied": r["applied"] or 0,
                    "interviews": r["interviews"] or 0,
                    "offers": r["offers"] or 0,
                }
                for r in rows
            ]

    def get_all_jobs_raw(self) -> List[Dict[str, Any]]:
        """Retrieve all job records with core tracking and evaluation attributes."""
        query = """
            SELECT
                id, source, source_job_id, title, company, location, url,
                match_score, match_category, matched_roles, matched_skills, matched_locations,
                experience_match, application_readiness_score, application_priority,
                resume_alignment_score, status, status_updated_at, applied_at,
                interview_date, interview_status, date_found, created_at, updated_at
            FROM jobs
            ORDER BY id ASC;
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return [dict(r) for r in cursor.fetchall()]

    def get_source_analytics(
        self,
        period: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve funnel breakdown grouped by job board / source connector."""
        where_sql, params = self._build_analytics_where(period=period, start_date=start_date, end_date=end_date)
        query = f"""
            SELECT
                source,
                COUNT(*) AS jobs_found,
                SUM(CASE WHEN match_score >= 60 THEN 1 ELSE 0 END) AS relevant,
                SUM(CASE WHEN application_priority IN ('URGENT', 'HIGH', 'NORMAL') THEN 1 ELSE 0 END) AS recommended,
                SUM(CASE WHEN status IN ('APPLIED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS applied,
                SUM(CASE WHEN status = 'INTERVIEW' OR interview_status IN ('SCHEDULED', 'COMPLETED', 'PASSED', 'FAILED', 'RESCHEDULED') OR (interview_date IS NOT NULL AND interview_date != '') THEN 1 ELSE 0 END) AS interview,
                SUM(CASE WHEN status = 'OFFER' THEN 1 ELSE 0 END) AS offer
            FROM jobs
            {where_sql}
            GROUP BY source
            ORDER BY relevant DESC, jobs_found DESC;
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_role_analytics(
        self,
        target_roles: Optional[List[str]] = None,
        period: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve funnel breakdown grouped by target role families."""
        if not target_roles:
            target_roles = [
                "Python Developer",
                "Backend Developer",
                "Software Engineer",
                "Full Stack Developer",
                "Web Developer",
                "ML Engineer",
                "AI Engineer",
                "SDE Intern",
            ]

        where_sql, params = self._build_analytics_where(period=period, start_date=start_date, end_date=end_date)

        results = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for role_name in target_roles:
                term = f"%{role_name.lower()}%"
                role_clause = "(LOWER(title) LIKE ? OR LOWER(COALESCE(matched_roles, '')) LIKE ?)"
                full_where = f"{where_sql} AND {role_clause}" if where_sql else f"WHERE {role_clause}"
                q_params = params + [term, term]

                q = f"""
                    SELECT
                        COUNT(*) AS jobs_found,
                        SUM(CASE WHEN match_score >= 60 THEN 1 ELSE 0 END) AS relevant,
                        SUM(CASE WHEN application_priority IN ('URGENT', 'HIGH', 'NORMAL') THEN 1 ELSE 0 END) AS recommended,
                        SUM(CASE WHEN status IN ('APPLIED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS applied,
                        SUM(CASE WHEN status = 'INTERVIEW' OR interview_status IN ('SCHEDULED', 'COMPLETED', 'PASSED', 'FAILED', 'RESCHEDULED') OR (interview_date IS NOT NULL AND interview_date != '') THEN 1 ELSE 0 END) AS interview,
                        SUM(CASE WHEN status = 'OFFER' THEN 1 ELSE 0 END) AS offer
                    FROM jobs
                    {full_where};
                """
                cursor.execute(q, q_params)
                row = cursor.fetchone()
                if row and (row["jobs_found"] or 0) > 0:
                    results.append({
                        "role_name": role_name,
                        "jobs_found": row["jobs_found"] or 0,
                        "relevant": row["relevant"] or 0,
                        "recommended": row["recommended"] or 0,
                        "applied": row["applied"] or 0,
                        "interview": row["interview"] or 0,
                        "offer": row["offer"] or 0,
                    })

        results.sort(key=lambda r: (r["applied"], r["relevant"], r["jobs_found"]), reverse=True)
        return results

    def get_location_analytics(
        self,
        preferred_locations: Optional[List[str]] = None,
        period: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve funnel breakdown grouped by location."""
        if not preferred_locations:
            preferred_locations = [
                "Bangalore",
                "Bengaluru",
                "Remote",
                "Delhi",
                "Noida",
                "Ahmedabad",
                "India",
            ]

        where_sql, params = self._build_analytics_where(period=period, start_date=start_date, end_date=end_date)
        results = []

        # Merge Bangalore and Bengaluru display
        loc_groups = {
            "Bangalore / Bengaluru": ["bangalore", "bengaluru"],
            "Remote / India Eligible": ["remote"],
            "Delhi / NCR": ["delhi", "noida", "gurgaon"],
            "Ahmedabad": ["ahmedabad"],
            "Pan India": ["india"],
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()
            for label, terms in loc_groups.items():
                loc_clauses = " OR ".join(["LOWER(location) LIKE ? OR LOWER(COALESCE(matched_locations, '')) LIKE ?" for _ in terms])
                full_where = f"{where_sql} AND ({loc_clauses})" if where_sql else f"WHERE ({loc_clauses})"
                term_params = []
                for t in terms:
                    term_params.extend([f"%{t}%", f"%{t}%"])
                q_params = params + term_params

                q = f"""
                    SELECT
                        COUNT(*) AS jobs_found,
                        SUM(CASE WHEN match_score >= 60 THEN 1 ELSE 0 END) AS relevant,
                        SUM(CASE WHEN application_priority IN ('URGENT', 'HIGH', 'NORMAL') THEN 1 ELSE 0 END) AS recommended,
                        SUM(CASE WHEN status IN ('APPLIED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS applied,
                        SUM(CASE WHEN status = 'INTERVIEW' OR interview_status IN ('SCHEDULED', 'COMPLETED', 'PASSED', 'FAILED', 'RESCHEDULED') OR (interview_date IS NOT NULL AND interview_date != '') THEN 1 ELSE 0 END) AS interview,
                        SUM(CASE WHEN status = 'OFFER' THEN 1 ELSE 0 END) AS offer
                    FROM jobs
                    {full_where};
                """
                cursor.execute(q, q_params)
                row = cursor.fetchone()
                if row and (row["jobs_found"] or 0) > 0:
                    results.append({
                        "location_name": label,
                        "jobs_found": row["jobs_found"] or 0,
                        "relevant": row["relevant"] or 0,
                        "recommended": row["recommended"] or 0,
                        "applied": row["applied"] or 0,
                        "interview": row["interview"] or 0,
                        "offer": row["offer"] or 0,
                    })

        results.sort(key=lambda r: (r["applied"], r["relevant"], r["jobs_found"]), reverse=True)
        return results

    def get_score_bucket_analytics(
        self,
        period: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Retrieve conversion performance by Match, Readiness, and Resume score buckets."""
        where_sql, params = self._build_analytics_where(period=period, start_date=start_date, end_date=end_date)
        prefix = f"{where_sql} AND" if where_sql else "WHERE"

        match_buckets = [
            ("90–100 (Excellent)", f"{prefix} match_score >= 90"),
            ("80–89 (Strong)", f"{prefix} match_score >= 80 AND match_score < 90"),
            ("70–79 (Good)", f"{prefix} match_score >= 70 AND match_score < 80"),
            ("60–69 (Possible)", f"{prefix} match_score >= 60 AND match_score < 70"),
            ("Below 60 (Not Relevant)", f"{prefix} match_score < 60"),
        ]

        readiness_buckets = [
            ("85–100 (Urgent / Very High)", f"{prefix} application_readiness_score >= 85"),
            ("75–84 (High)", f"{prefix} application_readiness_score >= 75 AND application_readiness_score < 85"),
            ("60–74 (Moderate)", f"{prefix} application_readiness_score >= 60 AND application_readiness_score < 75"),
            ("Below 60 (Low / Skip)", f"{prefix} application_readiness_score < 60"),
        ]

        resume_buckets = [
            ("80–100 (Strong Alignment)", f"{prefix} resume_alignment_score >= 80"),
            ("65–79 (Good Alignment)", f"{prefix} resume_alignment_score >= 65 AND resume_alignment_score < 80"),
            ("50–64 (Partial Alignment)", f"{prefix} resume_alignment_score >= 50 AND resume_alignment_score < 65"),
            ("0–49 (Low Alignment)", f"{prefix} resume_alignment_score < 50"),
        ]

        def _execute_buckets(buckets):
            bucket_results = []
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for label, clause in buckets:
                    q = f"""
                        SELECT
                            COUNT(*) AS jobs_count,
                            SUM(CASE WHEN status IN ('APPLIED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS applied,
                            SUM(CASE WHEN status = 'INTERVIEW' OR interview_status IN ('SCHEDULED', 'COMPLETED', 'PASSED', 'FAILED', 'RESCHEDULED') OR (interview_date IS NOT NULL AND interview_date != '') THEN 1 ELSE 0 END) AS interview,
                            SUM(CASE WHEN status = 'OFFER' THEN 1 ELSE 0 END) AS offer
                        FROM jobs
                        {clause};
                    """
                    cursor.execute(q, params)
                    r = cursor.fetchone()
                    app_count = r["applied"] or 0
                    int_count = r["interview"] or 0
                    int_rate = round((int_count / app_count) * 100, 1) if app_count > 0 else None
                    bucket_results.append({
                        "bucket_label": label,
                        "jobs_count": r["jobs_count"] or 0,
                        "applied": app_count,
                        "interview": int_count,
                        "offer": r["offer"] or 0,
                        "interview_rate": int_rate,
                    })
            return bucket_results

        return {
            "match_buckets": _execute_buckets(match_buckets),
            "readiness_buckets": _execute_buckets(readiness_buckets),
            "resume_buckets": _execute_buckets(resume_buckets),
        }

    def get_easy_apply_analytics(
        self,
        period: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Compare conversion performance for Easy Apply vs direct portal listings."""
        where_sql, params = self._build_analytics_where(period=period, start_date=start_date, end_date=end_date)
        query = f"""
            SELECT
                CASE
                    WHEN easy_apply = 1 THEN 'Easy Apply'
                    WHEN easy_apply = 0 THEN 'Direct Portal / External'
                    ELSE 'Not Specified'
                END AS type_label,
                SUM(CASE WHEN match_score >= 60 THEN 1 ELSE 0 END) AS relevant,
                SUM(CASE WHEN status IN ('APPLIED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS applied,
                SUM(CASE WHEN status = 'INTERVIEW' OR interview_status IN ('SCHEDULED', 'COMPLETED', 'PASSED', 'FAILED', 'RESCHEDULED') OR (interview_date IS NOT NULL AND interview_date != '') THEN 1 ELSE 0 END) AS interview,
                SUM(CASE WHEN status = 'OFFER' THEN 1 ELSE 0 END) AS offer
            FROM jobs
            {where_sql}
            GROUP BY type_label
            ORDER BY relevant DESC;
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "type_label": r["type_label"],
                    "relevant": r["relevant"] or 0,
                    "applied": r["applied"] or 0,
                    "interview": r["interview"] or 0,
                    "offer": r["offer"] or 0,
                }
                for r in rows
            ]

    def get_experience_analytics(
        self,
        period: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Compare outcomes by experience requirement fit."""
        where_sql, params = self._build_analytics_where(period=period, start_date=start_date, end_date=end_date)
        prefix = f"{where_sql} AND" if where_sql else "WHERE"

        categories = [
            ("Fresher / Entry Level / Internship", f"{prefix} (LOWER(COALESCE(experience_required, '')) LIKE '%fresher%' OR LOWER(COALESCE(experience_required, '')) LIKE '%entry%' OR LOWER(COALESCE(experience_required, '')) LIKE '%intern%' OR LOWER(title) LIKE '%intern%')"),
            ("0–1 Years", f"{prefix} (LOWER(COALESCE(experience_required, '')) LIKE '%0-1%' OR LOWER(COALESCE(experience_required, '')) LIKE '%0 to 1%' OR LOWER(COALESCE(experience_required, '')) LIKE '%1 year%')"),
            ("0–2 Years", f"{prefix} (LOWER(COALESCE(experience_required, '')) LIKE '%0-2%' OR LOWER(COALESCE(experience_required, '')) LIKE '%0 to 2%' OR LOWER(COALESCE(experience_required, '')) LIKE '%2 year%')"),
            ("Not Specified / Entry Compatible", f"{prefix} (experience_required IS NULL OR experience_required = '' OR experience_match = 1)"),
        ]

        results = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for label, clause in categories:
                q = f"""
                    SELECT
                        SUM(CASE WHEN match_score >= 60 THEN 1 ELSE 0 END) AS relevant,
                        SUM(CASE WHEN status IN ('APPLIED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS applied,
                        SUM(CASE WHEN status = 'INTERVIEW' OR interview_status IN ('SCHEDULED', 'COMPLETED', 'PASSED', 'FAILED', 'RESCHEDULED') OR (interview_date IS NOT NULL AND interview_date != '') THEN 1 ELSE 0 END) AS interview
                    FROM jobs
                    {clause};
                """
                cursor.execute(q, params)
                r = cursor.fetchone()
                if r:
                    results.append({
                        "level_label": label,
                        "relevant": r["relevant"] or 0,
                        "applied": r["applied"] or 0,
                        "interview": r["interview"] or 0,
                    })
        return results

    def get_skills_analytics(
        self,
        period: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 12,
    ) -> List[Dict[str, Any]]:
        """Analyze technical skills observed in applied and interview jobs."""
        where_sql, params = self._build_analytics_where(period=period, start_date=start_date, end_date=end_date)
        prefix = f"{where_sql} AND" if where_sql else "WHERE"

        query = f"""
            SELECT
                matched_skills,
                status,
                interview_status,
                interview_date
            FROM jobs
            {prefix} (status IN ('APPLIED', 'INTERVIEW', 'OFFER') OR applied_at IS NOT NULL)
            AND matched_skills IS NOT NULL AND matched_skills != '' AND matched_skills != '[]';
        """
        skill_counts: Dict[str, Dict[str, int]] = {}

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            for r in rows:
                raw_skills = r["matched_skills"]
                skills_list: List[str] = []
                try:
                    import json
                    parsed = json.loads(raw_skills)
                    if isinstance(parsed, list):
                        skills_list = [str(s) for s in parsed]
                    elif isinstance(parsed, str):
                        skills_list = [s.strip() for s in parsed.split(",") if s.strip()]
                except Exception:
                    skills_list = [s.strip() for s in raw_skills.split(",") if s.strip()]

                is_interview = (
                    r["status"] == "INTERVIEW"
                    or (r["interview_status"] and r["interview_status"] in ("SCHEDULED", "COMPLETED", "PASSED", "FAILED", "RESCHEDULED"))
                    or (r["interview_date"] is not None and r["interview_date"] != "")
                )
                is_offer = (r["status"] == "OFFER")

                for sk in skills_list:
                    sk_norm = sk.strip().title()
                    if not sk_norm:
                        continue
                    if sk_norm not in skill_counts:
                        skill_counts[sk_norm] = {"applied": 0, "interview": 0, "offer": 0}
                    skill_counts[sk_norm]["applied"] += 1
                    if is_interview:
                        skill_counts[sk_norm]["interview"] += 1
                    if is_offer:
                        skill_counts[sk_norm]["offer"] += 1

        sorted_skills = sorted(
            [
                {
                    "skill": k,
                    "applied_count": v["applied"],
                    "interview_count": v["interview"],
                    "offer_count": v["offer"],
                }
                for k, v in skill_counts.items()
            ],
            key=lambda x: (x["interview_count"], x["applied_count"]),
            reverse=True,
        )
        return sorted_skills[:limit]

    def get_application_streak(self) -> Dict[str, int]:
        """Calculate current and longest consecutive calendar days with at least 1 application."""
        query = """
            SELECT DISTINCT date(applied_at) AS app_date
            FROM jobs
            WHERE applied_at IS NOT NULL
              AND status IN ('APPLIED', 'INTERVIEW', 'OFFER', 'REJECTED')
            ORDER BY app_date DESC;
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            if not rows:
                return {"current_streak": 0, "longest_streak": 0}

            dates = [datetime.strptime(r["app_date"], "%Y-%m-%d").date() for r in rows if r["app_date"]]
            if not dates:
                return {"current_streak": 0, "longest_streak": 0}

            today = date.today()
            yesterday = today - timedelta(days=1)

            # Determine start of current streak
            current_streak = 0
            if dates[0] == today:
                check_date = today
            elif dates[0] == yesterday:
                check_date = yesterday
            else:
                check_date = None

            if check_date is not None:
                date_set = set(dates)
                curr = check_date
                while curr in date_set:
                    current_streak += 1
                    curr -= timedelta(days=1)

            # Calculate longest streak
            longest_streak = 0
            if dates:
                sorted_dates = sorted(set(dates))
                streak = 1
                for i in range(1, len(sorted_dates)):
                    if sorted_dates[i] == sorted_dates[i - 1] + timedelta(days=1):
                        streak += 1
                    else:
                        longest_streak = max(longest_streak, streak)
                        streak = 1
                longest_streak = max(longest_streak, streak)

            return {
                "current_streak": current_streak,
                "longest_streak": max(longest_streak, current_streak),
            }

    def get_daily_target_status(self, target: int = 5) -> Dict[str, Any]:
        """Evaluate today's application progress against target."""
        today_iso = date.today().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Applied today
            cursor.execute(
                """
                SELECT COUNT(*) AS applied_today
                FROM jobs
                WHERE (date(applied_at) = ? OR (applied_at IS NULL AND status IN ('APPLIED', 'INTERVIEW', 'OFFER') AND date(status_updated_at) = ?));
                """,
                (today_iso, today_iso),
            )
            r_today = cursor.fetchone()
            applied_today = r_today["applied_today"] or 0 if r_today else 0

            # 7-day total applied
            cursor.execute(
                """
                SELECT COUNT(*) AS seven_day_total
                FROM jobs
                WHERE (date(applied_at) >= date('now', '-7 days') OR (applied_at IS NULL AND status IN ('APPLIED', 'INTERVIEW', 'OFFER') AND date(status_updated_at) >= date('now', '-7 days')));
                """
            )
            r_7d = cursor.fetchone()
            seven_day_total = r_7d["seven_day_total"] or 0 if r_7d else 0
            seven_day_avg = round(seven_day_total / 7.0, 1)

            remaining = max(0, target - applied_today)
            achievement_percentage = round((applied_today / target) * 100, 1) if target > 0 else 0.0

            return {
                "target": target,
                "applied_today": applied_today,
                "remaining": remaining,
                "seven_day_avg": seven_day_avg,
                "achievement_percentage": achievement_percentage,
            }

    def get_weekly_comparison(self) -> Dict[str, Any]:
        """Compare current 7-day metrics against previous 7-day period."""
        query_current = """
            SELECT
                COUNT(*) AS jobs_found,
                SUM(CASE WHEN match_score >= 60 THEN 1 ELSE 0 END) AS relevant,
                SUM(CASE WHEN application_priority IN ('URGENT', 'HIGH', 'NORMAL') THEN 1 ELSE 0 END) AS recommended,
                SUM(CASE WHEN status IN ('APPLIED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS applied,
                SUM(CASE WHEN status = 'INTERVIEW' OR interview_status IN ('SCHEDULED', 'COMPLETED', 'PASSED', 'FAILED', 'RESCHEDULED') OR (interview_date IS NOT NULL AND interview_date != '') THEN 1 ELSE 0 END) AS interview,
                SUM(CASE WHEN status = 'OFFER' THEN 1 ELSE 0 END) AS offer,
                SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) AS rejected,
                AVG(CASE WHEN match_score >= 60 THEN match_score ELSE NULL END) AS avg_match,
                AVG(CASE WHEN match_score >= 60 THEN application_readiness_score ELSE NULL END) AS avg_readiness,
                AVG(CASE WHEN match_score >= 60 THEN resume_alignment_score ELSE NULL END) AS avg_resume_alignment
            FROM jobs
            WHERE date(COALESCE(first_seen_at, date_found)) >= date('now', '-7 days');
        """
        query_prev = """
            SELECT
                COUNT(*) AS jobs_found,
                SUM(CASE WHEN match_score >= 60 THEN 1 ELSE 0 END) AS relevant,
                SUM(CASE WHEN application_priority IN ('URGENT', 'HIGH', 'NORMAL') THEN 1 ELSE 0 END) AS recommended,
                SUM(CASE WHEN status IN ('APPLIED', 'INTERVIEW', 'OFFER') THEN 1 ELSE 0 END) AS applied,
                SUM(CASE WHEN status = 'INTERVIEW' OR interview_status IN ('SCHEDULED', 'COMPLETED', 'PASSED', 'FAILED', 'RESCHEDULED') OR (interview_date IS NOT NULL AND interview_date != '') THEN 1 ELSE 0 END) AS interview,
                SUM(CASE WHEN status = 'OFFER' THEN 1 ELSE 0 END) AS offer,
                SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) AS rejected,
                AVG(CASE WHEN match_score >= 60 THEN match_score ELSE NULL END) AS avg_match,
                AVG(CASE WHEN match_score >= 60 THEN application_readiness_score ELSE NULL END) AS avg_readiness,
                AVG(CASE WHEN match_score >= 60 THEN resume_alignment_score ELSE NULL END) AS avg_resume_alignment
            FROM jobs
            WHERE date(COALESCE(first_seen_at, date_found)) >= date('now', '-14 days')
              AND date(COALESCE(first_seen_at, date_found)) < date('now', '-7 days');
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query_current)
            cur = cursor.fetchone()
            cursor.execute(query_prev)
            prev = cursor.fetchone()

            def _clean(r):
                if not r:
                    return {
                        "jobs": 0, "relevant": 0, "recommended": 0, "applied": 0,
                        "interview": 0, "offer": 0, "rejected": 0,
                        "avg_match": 0.0, "avg_readiness": 0.0, "avg_resume_alignment": 0.0,
                    }
                return {
                    "jobs": r["jobs_found"] or 0,
                    "relevant": r["relevant"] or 0,
                    "recommended": r["recommended"] or 0,
                    "applied": r["applied"] or 0,
                    "interview": r["interview"] or 0,
                    "offer": r["offer"] or 0,
                    "rejected": r["rejected"] or 0,
                    "avg_match": round(float(r["avg_match"]), 1) if r["avg_match"] is not None else 0.0,
                    "avg_readiness": round(float(r["avg_readiness"]), 1) if r["avg_readiness"] is not None else 0.0,
                    "avg_resume_alignment": round(float(r["avg_resume_alignment"]), 1) if r["avg_resume_alignment"] is not None else 0.0,
                }

            c_dict = _clean(cur)
            p_dict = _clean(prev)
            return {
                "current_week_jobs": c_dict["jobs"],
                "current_week_relevant": c_dict["relevant"],
                "current_week_recommended": c_dict["recommended"],
                "current_week_applied": c_dict["applied"],
                "current_week_interviews": c_dict["interview"],
                "current_week_offers": c_dict["offer"],
                "current_week_rejected": c_dict["rejected"],
                "current_week_avg_match": c_dict["avg_match"],
                "current_week_avg_readiness": c_dict["avg_readiness"],
                "current_week_avg_resume_alignment": c_dict["avg_resume_alignment"],
                "previous_week_jobs": p_dict["jobs"],
                "previous_week_relevant": p_dict["relevant"],
                "previous_week_recommended": p_dict["recommended"],
                "previous_week_applied": p_dict["applied"],
                "previous_week_interviews": p_dict["interview"],
                "previous_week_offers": p_dict["offer"],
                "previous_week_rejected": p_dict["rejected"],
                "previous_week_avg_match": p_dict["avg_match"],
                "previous_week_avg_readiness": p_dict["avg_readiness"],
                "previous_week_avg_resume_alignment": p_dict["avg_resume_alignment"],
            }

    def check_database_health(self) -> dict[str, Any]:
        """Perform a strictly read-only health verification of the SQLite database.

        Verifies:
        - Database file accessibility and quick_check integrity.
        - Existence of all required tables (jobs, pipeline_runs).
        - Existence of core schema columns across phases 1-14.
        - Key index presence.
        - PRAGMA foreign_key_check.
        - Readability and count metrics.

        Does NOT mutate, delete, or recreate any data.

        Returns:
            Dict containing health metrics, status ('PASS'|'WARN'|'FAIL'), and error list.
        """
        errors: list[str] = []
        warnings: list[str] = []
        details: dict[str, Any] = {}

        if not self.db_path.exists():
            return {
                "status": "FAIL",
                "is_healthy": False,
                "db_path": str(self.db_path),
                "errors": [f"Database file does not exist: {self.db_path}"],
                "warnings": [],
                "details": {},
            }

        try:
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # 1. PRAGMA quick_check
                cursor.execute("PRAGMA quick_check;")
                qc_res = cursor.fetchone()
                integrity_ok = qc_res and qc_res[0] == "ok"
                details["integrity_check"] = qc_res[0] if qc_res else "unknown"
                if not integrity_ok:
                    errors.append(f"Integrity check failed: {details['integrity_check']}")

                # 2. Required tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = {row["name"] for row in cursor.fetchall()}
                details["tables"] = sorted(tables)
                required_tables = {"jobs", "pipeline_runs"}
                missing_tables = required_tables - tables
                if missing_tables:
                    errors.append(f"Missing required tables: {sorted(missing_tables)}")

                # 3. Column verification on jobs table
                if "jobs" in tables:
                    cursor.execute("PRAGMA table_info(jobs);")
                    job_cols = {row["name"] for row in cursor.fetchall()}
                    details["job_column_count"] = len(job_cols)
                    expected_core_cols = {
                        "id", "source", "title", "company", "location", "url",
                        "status", "fingerprint", "match_score", "application_readiness_score",
                        "application_priority", "resume_alignment_score", "applied_at",
                        "interview_status", "interview_date", "follow_up_date",
                    }
                    missing_core_cols = expected_core_cols - job_cols
                    if missing_core_cols:
                        errors.append(f"Missing expected columns in 'jobs': {sorted(missing_core_cols)}")

                # 4. Indexes verification
                cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
                indexes = {row["name"] for row in cursor.fetchall()}
                details["indexes_count"] = len(indexes)
                expected_indexes = {
                    "idx_jobs_source_source_job_id",
                    "idx_jobs_fingerprint",
                    "idx_jobs_status",
                    "idx_jobs_match_score",
                }
                missing_indexes = expected_indexes - indexes
                if missing_indexes:
                    warnings.append(f"Missing recommended indexes: {sorted(missing_indexes)}")

                # 5. Foreign keys check
                cursor.execute("PRAGMA foreign_key_check;")
                fk_violations = cursor.fetchall()
                details["foreign_key_violations"] = len(fk_violations)
                if fk_violations:
                    errors.append(f"Found {len(fk_violations)} foreign key violations")

                # 6. Read counts
                cursor.execute("SELECT COUNT(*) FROM jobs;")
                details["total_jobs"] = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM pipeline_runs;")
                details["total_pipeline_runs"] = cursor.fetchone()[0]

        except Exception as exc:
            errors.append(f"Database health check error: {exc}")

        is_healthy = len(errors) == 0
        status = "PASS" if is_healthy else "FAIL"
        if is_healthy and warnings:
            status = "WARN"

        return {
            "status": status,
            "is_healthy": is_healthy,
            "db_path": str(self.db_path),
            "errors": errors,
            "warnings": warnings,
            "details": details,
        }


