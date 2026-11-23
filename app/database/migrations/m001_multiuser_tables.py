"""Migration 001: Multi-User Tables and Zero-Loss Tracking Migration (Phase 3B)."""

import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional

from app.database.migrations.security import generate_secure_token, hash_password

logger = logging.getLogger(__name__)

VERSION = 1
NAME = "001_multiuser_tables"


def up(conn: sqlite3.Connection, settings: Optional[Any] = None) -> Dict[str, Any]:
    """Apply migration: Create multi-user tables, provision initial owner account, and migrate tracking data.

    Must run inside a caller-managed transaction (conn).
    """
    cursor = conn.cursor()

    # 1. Users Table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'CANDIDATE',
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")

    # 2. Candidate Profiles Table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            headline TEXT,
            total_experience_years REAL DEFAULT 0.0,
            current_title TEXT,
            education_level TEXT,
            technical_skills TEXT,
            domain_skills TEXT,
            raw_extracted_text TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_user ON candidate_profiles(user_id);")

    # 3. Candidate Preferences Table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            target_roles TEXT NOT NULL,
            preferred_locations TEXT NOT NULL,
            location_scope TEXT DEFAULT 'PREF_ONLY',
            work_arrangement TEXT DEFAULT 'ANY',
            max_required_years INTEGER DEFAULT 2,
            match_min_score INTEGER DEFAULT 50,
            notice_period TEXT DEFAULT 'IMMEDIATE',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_preferences_user ON candidate_preferences(user_id);")

    # 4. Resumes Table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            file_path TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            mime_type TEXT NOT NULL,
            parsed_data_json TEXT,
            is_primary BOOLEAN NOT NULL DEFAULT 1,
            uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_resumes_user ON resumes(user_id);")

    # 5. Job Matches Table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS job_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            match_score INTEGER NOT NULL DEFAULT 0,
            match_category TEXT NOT NULL,
            matched_skills TEXT,
            missing_skills TEXT,
            match_reason TEXT,
            resume_alignment_score INTEGER DEFAULT 0,
            evaluated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
            UNIQUE(user_id, job_id)
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_user_score ON job_matches(user_id, match_score DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_user_cat ON job_matches(user_id, match_category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_job ON job_matches(job_id);")

    # 6. Saved Jobs Table
    cursor.execute(
        """
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
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_jobs(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_saved_job ON saved_jobs(job_id);")

    # 7. Applications Table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            resume_id INTEGER,
            status TEXT NOT NULL DEFAULT 'APPLIED',
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
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_apps_user_status ON applications(user_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_apps_job ON applications(job_id);")

    # 8. Safe Provisioning of Initial Owner/Admin Account
    initial_email = getattr(settings, "INITIAL_USER_EMAIL", "admin@jobfinder.local") if settings else "admin@jobfinder.local"
    initial_name = getattr(settings, "INITIAL_USER_NAME", "Primary Candidate") if settings else "Primary Candidate"
    initial_hash = getattr(settings, "INITIAL_USER_PASSWORD_HASH", None) if settings else None

    cursor.execute("SELECT id, email FROM users WHERE email = ? COLLATE NOCASE;", (initial_email,))
    existing_user = cursor.fetchone()

    generated_token = None
    if existing_user:
        user_id = existing_user["id"] if isinstance(existing_user, sqlite3.Row) else existing_user[0]
        logger.info(f"Reusing existing designated user ID {user_id} ({initial_email}).")
    else:
        if not initial_hash:
            generated_token = generate_secure_token(24)
            initial_hash = hash_password(generated_token)
            # Write setup confirmation to secure data directory
            try:
                setup_file = Path("data/.initial_admin_setup.json")
                setup_file.parent.mkdir(parents=True, exist_ok=True)
                setup_info = {
                    "email": initial_email,
                    "full_name": initial_name,
                    "role": "ADMIN",
                    "initial_setup_token": generated_token,
                    "notice": "This token can be used for initial setup or password reset when auth endpoints are enabled in Phase 3D.",
                }
                setup_file.write_text(json.dumps(setup_info, indent=2), encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not persist initial setup notice file: {e}")

        cursor.execute(
            """
            INSERT INTO users (email, password_hash, full_name, role)
            VALUES (?, ?, ?, 'ADMIN');
            """,
            (initial_email, initial_hash, initial_name),
        )
        user_id = cursor.lastrowid
        logger.info(f"Created initial designated owner account ID {user_id} ({initial_email}).")

    # 9. Seed Initial Preferences from profile.json if available
    profile_path = getattr(settings, "PROFILE_PATH", Path("data/profile.json")) if settings else Path("data/profile.json")
    if Path(profile_path).exists():
        try:
            profile_data = json.loads(Path(profile_path).read_text(encoding="utf-8"))
            target_roles = json.dumps(profile_data.get("target_roles", []))
            preferred_locations = json.dumps(profile_data.get("preferred_locations", []))
            match_max_years = profile_data.get("match_max_years", 2)
            cursor.execute(
                """
                INSERT OR IGNORE INTO candidate_preferences (
                    user_id, target_roles, preferred_locations, location_scope,
                    work_arrangement, max_required_years, match_min_score, notice_period
                ) VALUES (?, ?, ?, 'PREF_ONLY', 'ANY', ?, 50, 'IMMEDIATE');
                """,
                (user_id, target_roles, preferred_locations, match_max_years),
            )
        except Exception as e:
            logger.warning(f"Could not parse profile.json for initial preferences: {e}")

    # 10. Migrate Existing Application Tracking Data
    # 10a. Migrate APPLIED jobs into applications
    cursor.execute(
        """
        INSERT OR IGNORE INTO applications (user_id, job_id, status, applied_at, notes, created_at, updated_at)
        SELECT
            ?,
            id,
            status,
            applied_at,
            notes,
            COALESCE(status_updated_at, created_at, CURRENT_TIMESTAMP),
            COALESCE(updated_at, CURRENT_TIMESTAMP)
        FROM jobs
        WHERE status = 'APPLIED';
        """,
        (user_id,),
    )
    applied_migrated = cursor.rowcount

    # 10b. Migrate jobs with non-empty notes into saved_jobs
    cursor.execute(
        """
        INSERT OR IGNORE INTO saved_jobs (user_id, job_id, candidate_notes, created_at)
        SELECT
            ?,
            id,
            notes,
            COALESCE(status_updated_at, created_at, CURRENT_TIMESTAMP)
        FROM jobs
        WHERE notes IS NOT NULL AND TRIM(notes) != '';
        """,
        (user_id,),
    )
    notes_migrated = cursor.rowcount

    # 10c. Migrate historical match scores into job_matches
    cursor.execute(
        """
        INSERT OR IGNORE INTO job_matches (
            user_id, job_id, match_score, match_category, matched_skills,
            missing_skills, resume_alignment_score, evaluated_at
        )
        SELECT
            ?,
            id,
            COALESCE(match_score, 0),
            COALESCE(match_category, 'NO_FIT'),
            matched_skills,
            missing_skills,
            COALESCE(resume_alignment_score, 0),
            COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
        FROM jobs
        WHERE match_score > 0 OR match_category IS NOT NULL;
        """,
        (user_id,),
    )
    matches_migrated = cursor.rowcount

    return {
        "version": VERSION,
        "name": NAME,
        "user_id": user_id,
        "initial_email": initial_email,
        "applied_migrated": applied_migrated,
        "notes_migrated": notes_migrated,
        "matches_migrated": matches_migrated,
        "token_generated": bool(generated_token),
    }


def down(conn: sqlite3.Connection) -> None:
    """Revert migration: Drop multi-user tables safely.

    Preserves the shared 'jobs' and 'pipeline_runs' tables completely.
    """
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS applications;")
    cursor.execute("DROP TABLE IF EXISTS saved_jobs;")
    cursor.execute("DROP TABLE IF EXISTS job_matches;")
    cursor.execute("DROP TABLE IF EXISTS resumes;")
    cursor.execute("DROP TABLE IF EXISTS candidate_preferences;")
    cursor.execute("DROP TABLE IF EXISTS candidate_profiles;")
    cursor.execute("DROP TABLE IF EXISTS users;")

