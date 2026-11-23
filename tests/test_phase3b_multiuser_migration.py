"""Automated test suite for Phase 3B: Multi-User Database Schema, Migration & Data Preservation."""

import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import pytest

from app.config.settings import Settings
from app.database.database import DatabaseManager
from app.database.migrations.migration_manager import MigrationManager
from app.database.migrations.security import hash_password, verify_password
from app.models.multiuser import (
    ApplicationRecord,
    CandidatePreferences,
    CandidateProfile,
    JobMatchRecord,
    SavedJobRecord,
    User,
    UserRole,
)


@pytest.fixture
def isolated_db_path(tmp_path):
    """Fixture providing a fresh isolated copy of the database for migration testing."""
    test_db = tmp_path / "test_jobs.db"
    # Copy baseline pre-migration backup
    backup_candidates = list(Path("data/backups").glob("jobs_backup_pre_phase3b_*.db"))
    if backup_candidates:
        src = sorted(backup_candidates)[-1]
    else:
        src = Path("data/jobs.db")
    shutil.copy2(src, test_db)
    return test_db


class TestPhase3BMigration:
    """Test suite verifying table creation, foreign keys, unique constraints, and data preservation."""

    def test_new_tables_creation(self, isolated_db_path):
        """Verify all 7 multi-user tables and schema_migrations table are created."""
        db = DatabaseManager(isolated_db_path)
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row["name"] for row in cursor.fetchall()}

        expected_tables = {
            "users",
            "candidate_profiles",
            "candidate_preferences",
            "resumes",
            "job_matches",
            "saved_jobs",
            "applications",
            "schema_migrations",
            "jobs",
            "pipeline_runs",
        }
        assert expected_tables.issubset(tables)

    def test_foreign_key_constraints(self, isolated_db_path):
        """Verify that foreign key violations are rejected by SQLite."""
        db = DatabaseManager(isolated_db_path)

        # 1. Invalid user_id in applications must raise IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO applications (user_id, job_id, status) VALUES (999999, 1, 'APPLIED');"
                )

        # 2. Invalid job_id in applications must raise IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO applications (user_id, job_id, status) VALUES (1, 999999, 'APPLIED');"
                )

        # 3. Invalid user_id in saved_jobs must raise IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO saved_jobs (user_id, job_id, candidate_notes) VALUES (999999, 1, 'Note');"
                )

    def test_unique_constraints(self, isolated_db_path):
        """Verify unique constraints on user email and candidate-job pairings."""
        db = DatabaseManager(isolated_db_path)

        # 1. Duplicate email in users
        with pytest.raises(sqlite3.IntegrityError):
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO users (email, password_hash, full_name) VALUES ('admin@jobfinder.local', 'h', 'Dup');"
                )

        # 2. Duplicate (user_id, job_id) in applications
        with pytest.raises(sqlite3.IntegrityError):
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO applications (user_id, job_id, status) VALUES (1, 7, 'INTERVIEWING');"
                )

        # 3. Duplicate (user_id, job_id) in saved_jobs
        with pytest.raises(sqlite3.IntegrityError):
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO saved_jobs (user_id, job_id, candidate_notes) VALUES (1, 2, 'Duplicate');"
                )

    def test_migration_idempotency(self, isolated_db_path):
        """Verify that applying migrations repeatedly causes no duplicate rows or failures."""
        mgr = MigrationManager(isolated_db_path)
        # First call applies pending migrations
        res1 = mgr.apply_all()
        assert len(res1) >= 1

        # Second call must be a safe idempotent no-op
        res2 = mgr.apply_all()
        assert res2 == []  # Already applied, zero changes

        with mgr._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users;")
            users_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM applications;")
            apps_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM saved_jobs;")
            saved_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM schema_migrations;")
            mig_count = cursor.fetchone()[0]

        assert users_count == 1
        assert apps_count == 1
        assert saved_count == 2
        assert mig_count == 1

    def test_migration_rollback_and_reapply(self, isolated_db_path):
        """Verify safe teardown and forward reapplication of migrations."""
        mgr = MigrationManager(isolated_db_path)
        mgr.apply_all()

        # Rollback version 1
        rollback_res = mgr.rollback(target_version=0)
        assert len(rollback_res) == 1
        assert rollback_res[0]["version"] == 1
        assert rollback_res[0]["action"] == "ROLLED_BACK"

        status_after = mgr.get_status()
        assert "users" not in status_after["tables"]
        assert "applications" not in status_after["tables"]
        assert "jobs" in status_after["tables"]  # Shared jobs untouched!
        assert status_after["jobs_count"] == 6349

        # Re-apply forward
        reapply_res = mgr.apply_all()
        assert len(reapply_res) == 1
        status_reapplied = mgr.get_status()
        assert "users" in status_reapplied["tables"]
        assert "applications" in status_reapplied["tables"]
        assert status_reapplied["jobs_count"] == 6349

    def test_existing_job_record_preservation(self, isolated_db_path):
        """Verify all 6,349 existing job listings remain intact in the shared catalog."""
        db = DatabaseManager(isolated_db_path)
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM jobs;")
            total_jobs = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT fingerprint) FROM jobs;")
            distinct_fp = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT source_job_id) FROM jobs WHERE source_job_id IS NOT NULL AND source_job_id != '';")
            distinct_ids = cursor.fetchone()[0]

        assert total_jobs == 6349
        assert distinct_fp == 6349
        assert distinct_ids == 6349

    def test_existing_application_status_preservation(self, isolated_db_path):
        """Verify the 1 existing APPLIED record (Job 7) is preserved in applications."""
        db = DatabaseManager(isolated_db_path)
        apps = db.get_user_applications(user_id=1)
        assert len(apps) == 1

        app = apps[0]
        assert app["job_id"] == 7
        assert app["status"] == "APPLIED"
        assert app["notes"] == "Applied directly via career site"
        assert app["applied_at"] == "2026-10-07T10:11:09.885271+00:00"
        assert app["company"] == "HackerRank Careers"
        assert app["title"] == "Software Development Engineer Intern"

    def test_existing_notes_preservation(self, isolated_db_path):
        """Verify both Job 2 and Job 7 custom notes are preserved in saved_jobs."""
        db = DatabaseManager(isolated_db_path)
        saved = db.get_user_saved_jobs(user_id=1)
        assert len(saved) == 2

        notes_by_job = {s["job_id"]: s["candidate_notes"] for s in saved}
        assert 2 in notes_by_job
        assert notes_by_job[2] == "Test note via dashboard"
        assert 7 in notes_by_job
        assert notes_by_job[7] == "Applied directly via career site"

    def test_candidate_ownership_relationships_and_isolation(self, isolated_db_path):
        """Verify strict multi-tenant isolation: Candidate B cannot see Candidate A's records."""
        db = DatabaseManager(isolated_db_path)

        # Create candidate B
        candidate_b_id = db.create_user(
            email="candidate_b@domain.com",
            password_hash=hash_password("SecureCandB!123"),
            full_name="Candidate B",
        )
        assert candidate_b_id > 1

        # Candidate B saves Job 5 and applies to Job 12
        db.save_job_for_user(candidate_b_id, 5, candidate_notes="Candidate B note on job 5")
        db.record_user_application(
            candidate_b_id,
            12,
            status="INTERVIEWING",
            interview_date="2026-11-15T14:00:00",
            notes="Round 1 scheduled",
        )

        # Verify Candidate A isolation
        cand_a_apps = db.get_user_applications(user_id=1)
        cand_a_saved = db.get_user_saved_jobs(user_id=1)
        assert len(cand_a_apps) == 1
        assert cand_a_apps[0]["job_id"] == 7
        assert all(s["job_id"] != 5 for s in cand_a_saved)

        # Verify Candidate B isolation
        cand_b_apps = db.get_user_applications(user_id=candidate_b_id)
        cand_b_saved = db.get_user_saved_jobs(user_id=candidate_b_id)
        assert len(cand_b_apps) == 1
        assert cand_b_apps[0]["job_id"] == 12
        assert cand_b_apps[0]["status"] == "INTERVIEWING"
        assert len(cand_b_saved) == 1
        assert cand_b_saved[0]["job_id"] == 5
        assert cand_b_saved[0]["candidate_notes"] == "Candidate B note on job 5"

    def test_password_hashing_security(self):
        """Verify PBKDF2-HMAC-SHA256 password hashing and constant-time verification."""
        password = "CandidateSecurePassword#2026"
        hashed = hash_password(password)

        assert hashed.startswith("pbkdf2:sha256:600000:")
        assert password not in hashed  # Plaintext never stored
        assert verify_password(password, hashed) is True
        assert verify_password("WrongPassword!", hashed) is False

    def test_backward_compatibility_with_existing_collection_pipeline(self, isolated_db_path):
        """Verify that existing collection methods on DatabaseManager continue working without regression."""
        db = DatabaseManager(isolated_db_path)
        health = db.check_database_health()
        assert health["status"] == "PASS"
        assert health["is_healthy"] is True
        assert health["details"]["foreign_key_violations"] == 0

        # Verify existing get_jobs_filtered works seamlessly
        jobs_page, total = db.get_jobs_filtered(per_page=10, page=1)
        assert total == 6349
        assert len(jobs_page) == 10
        assert hasattr(jobs_page[0], "title")
        assert hasattr(jobs_page[0], "company")

