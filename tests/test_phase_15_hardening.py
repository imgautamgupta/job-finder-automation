"""Comprehensive hardening and production readiness tests for Phase 15."""

from datetime import datetime, timedelta
import os
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.dashboard.app import app
import app.dashboard.routes as dashboard_routes
from app.database.database import DatabaseManager
from app.models.job import Job, JobStatus
from app.models.profile import JobProfile
from app.services.env_validator import EnvironmentValidator
from app.services.excel_exporter import ExcelExporter
from app.utils.lock import JobFinderLock, cleanup_old_logs
from scripts.backup_database import backup_database, purge_expired_backups, validate_backup
from scripts.restore_database import restore_database, validate_candidate_backup
from scripts.audit_database import audit_database


@pytest.fixture
def isolated_env(tmp_path):
    """Provide isolated paths for database, backups, exports, and logs."""
    data_dir = tmp_path / "data"
    backups_dir = data_dir / "backups"
    exports_dir = data_dir / "exports"
    logs_dir = data_dir / "logs"
    data_dir.mkdir()
    backups_dir.mkdir()
    exports_dir.mkdir()
    logs_dir.mkdir()

    db_path = data_dir / "jobs.db"
    lock_path = data_dir / "job_finder.lock"
    profile_path = data_dir / "profile.json"

    # Minimal valid profile
    profile = JobProfile(
        target_roles=["Backend Developer"],
        preferred_locations=["Bangalore", "Remote"],
        skills=["Python", "FastAPI"],
    )
    profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")

    settings = Settings(
        PROJECT_ROOT=tmp_path,
        DATABASE_PATH=db_path,
        BACKUPS_DIR=backups_dir,
        EXPORTS_DIR=exports_dir,
        LOGS_DIR=logs_dir,
        LOCK_FILE=lock_path,
        PROFILE_PATH=profile_path,
        DATABASE_BACKUP_RETENTION_DAYS=30,
    )
    return {
        "root": tmp_path,
        "settings": settings,
        "db_path": db_path,
        "backups_dir": backups_dir,
        "exports_dir": exports_dir,
        "logs_dir": logs_dir,
        "lock_path": lock_path,
        "profile_path": profile_path,
    }


def test_settings_validation_and_bounds(isolated_env):
    """Verify settings validation for log levels, schedules, and numeric bounds."""
    settings = isolated_env["settings"]

    # Valid settings
    assert settings.LOG_LEVEL == "INFO"
    assert settings.DATABASE_BACKUP_RETENTION_DAYS == 30

    # Invalid log level
    with pytest.raises(Exception):
        Settings(LOG_LEVEL="INVALID_LEVEL")

    # Invalid run time format
    with pytest.raises(Exception):
        Settings(DAILY_RUN_TIME="25:99")

    # Bounded values: MAX_RESULTS_PER_SOURCE < 1
    with pytest.raises(Exception):
        Settings(MAX_RESULTS_PER_SOURCE=0)

    # Safe dictionary serialization
    safe_repr = settings.safe_dict()
    assert isinstance(safe_repr["DATABASE_PATH"], str)
    assert isinstance(safe_repr["BACKUPS_DIR"], str)


def test_env_validator(isolated_env):
    """Verify startup EnvironmentValidator executes all checks on valid configuration."""
    validator = EnvironmentValidator(settings=isolated_env["settings"])
    ok, checks = validator.validate_all()
    assert ok is True
    check_names = {c.name for c in checks}
    assert "Python Version" in check_names
    assert "Profile File" in check_names
    assert "Database File" in check_names


def test_database_health_check(isolated_env):
    """Verify DatabaseManager.check_database_health accurately verifies database health."""
    db_path = isolated_env["db_path"]
    db = DatabaseManager(db_path=db_path)

    health = db.check_database_health()
    assert health["status"] == "PASS"
    assert health["is_healthy"] is True
    assert health["details"]["integrity_check"] == "ok"
    assert "jobs" in health["details"]["tables"]
    assert "pipeline_runs" in health["details"]["tables"]
    assert health["details"]["foreign_key_violations"] == 0


def test_backup_database_creation_and_validation(isolated_env):
    """Verify safe database backup creates verified backup file matching source count."""
    db_path = isolated_env["db_path"]
    backups_dir = isolated_env["backups_dir"]
    db = DatabaseManager(db_path=db_path)

    # Insert sample jobs
    for i in range(3):
        job = Job(
            source="lever",
            source_job_id=f"bk-job-{i}",
            title=f"Engineer {i}",
            company="TechCorp",
            location="Remote",
            url=f"https://example.com/job/{i}",
            match_score=80,
            status=JobStatus.NEW,
        )
        db.save_job(job)

    result = backup_database(
        source_db=db_path,
        backup_dir=backups_dir,
        retention_days=30,
    )

    assert result["status"] == "PASS"
    assert result["source_jobs"] == 3
    assert result["backup_jobs"] == 3
    assert result["validation"] == "PASS"

    backup_file = Path(result["backup_path"])
    assert backup_file.exists()
    assert backup_file.stat().st_size > 0

    # Test standalone validate_backup helper
    is_valid, msg = validate_backup(backup_file, expected_jobs=3)
    assert is_valid is True

    # Test count mismatch detection
    is_valid_mismatch, _ = validate_backup(backup_file, expected_jobs=10)
    assert is_valid_mismatch is False


def test_backup_retention_purge(isolated_env):
    """Verify expired backups are purged while recent backups and other files are preserved."""
    backups_dir = isolated_env["backups_dir"]

    # Create dummy backup files
    # 1. Very old backup (45 days ago)
    old_ts = (datetime.now() - timedelta(days=45)).strftime("%Y%m%d_%H%M%S")
    old_file = backups_dir / f"jobs_{old_ts}.db"
    old_file.write_text("old", encoding="utf-8")

    # 2. Recent backup (2 days ago)
    recent_ts = (datetime.now() - timedelta(days=2)).strftime("%Y%m%d_%H%M%S")
    recent_file = backups_dir / f"jobs_{recent_ts}.db"
    recent_file.write_text("recent", encoding="utf-8")

    # 3. Non-backup file that must NEVER be deleted
    other_file = backups_dir / ".gitkeep"
    other_file.write_text("keep", encoding="utf-8")

    retained, deleted = purge_expired_backups(backups_dir, retention_days=30)

    assert deleted == 1
    assert retained == 1
    assert not old_file.exists()
    assert recent_file.exists()
    assert other_file.exists()


def test_restore_database(isolated_env):
    """Verify database restore works safely with confirmation and creates safety backup."""
    db_path = isolated_env["db_path"]
    backups_dir = isolated_env["backups_dir"]

    # 1. Create a live database with 1 job
    db = DatabaseManager(db_path=db_path)
    job1 = Job(
        source="lever",
        source_job_id="live-1",
        title="Live Job",
        company="LiveCorp",
        location="Remote",
        url="https://example.com/live",
        status=JobStatus.NEW,
    )
    db.save_job(job1)

    # 2. Create a backup file representing 2 different jobs
    backup_file = backups_dir / "jobs_20261001_120000.db"
    backup_db = DatabaseManager(db_path=backup_file)
    for i in range(2):
        bj = Job(
            source="lever",
            source_job_id=f"bk-{i}",
            title=f"Backup Job {i}",
            company="BkCorp",
            location="Remote",
            url=f"https://example.com/bk/{i}",
            status=JobStatus.NEW,
        )
        backup_db.save_job(bj)

    # 3. Restore with explicit auto_confirmed=True
    res = restore_database(
        backup_path=backup_file,
        target_db=db_path,
        auto_confirmed=True,
        safety_dir=backups_dir,
    )

    assert res["status"] == "PASS"
    assert res["restored_jobs"] == 2
    assert res["previous_jobs"] == 1

    # Safety backup was created
    safety_backup = Path(res["safety_backup"])
    assert safety_backup.exists()

    # Verify live DB now has 2 jobs
    db_after = DatabaseManager(db_path=db_path)
    jobs_after = db_after.get_all_jobs()
    assert len(jobs_after) == 2


def test_restore_database_safety_rejections(isolated_env):
    """Verify restore rejects invalid files, missing confirmation, or disallowed paths."""
    db_path = isolated_env["db_path"]
    backups_dir = isolated_env["backups_dir"]

    # Refuse without confirmation
    backup_file = backups_dir / "jobs_20261001_120000.db"
    backup_file.write_text("fake db", encoding="utf-8")

    with pytest.raises(ValueError):
        restore_database(
            backup_path=backup_file,
            target_db=db_path,
            auto_confirmed=True,
        )

    # Refuse non-SQLite file in validator
    is_valid, cnt, msg = validate_candidate_backup(backup_file)
    assert is_valid is False


def test_database_integrity_audit(isolated_env):
    """Verify read-only audit accurately identifies application counts, anomalies, and historical notes."""
    db_path = isolated_env["db_path"]
    db = DatabaseManager(db_path=db_path)

    # Add a legitimate APPLIED job
    applied_job = Job(
        source="lever",
        source_job_id="app-1",
        title="Applied Role",
        company="AppliedCorp",
        location="Remote",
        url="https://example.com/app",
        status=JobStatus.APPLIED,
    )
    db.save_job(applied_job)

    # Add a NEW job with historical applied_at timestamp
    historical_job = Job(
        source="greenhouse",
        source_job_id="hist-1",
        title="Historical Role",
        company="HistCorp",
        location="Remote",
        url="https://example.com/hist",
        status=JobStatus.NEW,
    )
    db.save_job(historical_job)

    # Manually attach historical applied_at timestamp to Job 2
    with db.get_connection() as conn:
        conn.execute("UPDATE jobs SET applied_at = '2026-10-01T10:00:00' WHERE id = 2;")
        conn.commit()

    report = audit_database(db_path=db_path)
    assert report["status"] == "PASS"
    assert report["total_jobs"] == 2
    assert report["valid_applications"] == 1  # strictly Job 1
    assert report["historical_notes_count"] == 1  # Job 2 note
    assert report["historical_notes"][0]["job_id"] == 2
    assert report["historical_notes"][0]["type"] == "HISTORICAL_APPLIED_TIMESTAMP"


def test_lock_concurrency_and_stale_recovery(isolated_env):
    """Verify lock acquisition, concurrency prevention, and safe stale recovery."""
    lock_file = isolated_env["lock_path"]

    # 1. First lock succeeds
    lock1 = JobFinderLock(lock_path=lock_file, run_id="run-1")
    assert lock1.acquire() is True

    # 2. Second lock fails while first is active
    lock2 = JobFinderLock(lock_path=lock_file, run_id="run-2")
    assert lock2.acquire() is False

    # 3. First lock releases
    lock1.release()
    assert not lock_file.exists()

    # 4. Stale lock recovery with dead PID
    import json
    stale_payload = {
        "pid": 9999999,  # Non-existent PID
        "started_at": "2026-01-01T00:00:00+00:00",
        "run_id": "stale-run",
    }
    lock_file.write_text(json.dumps(stale_payload), encoding="utf-8")

    # Acquiring should detect dead PID, clear stale lock, and succeed
    lock3 = JobFinderLock(lock_path=lock_file, run_id="run-3")
    assert lock3.acquire() is True
    lock3.release()


def test_dashboard_empty_database_safety(isolated_env, monkeypatch):
    """Verify all dashboard pages render gracefully without crashing on empty database."""
    db_path = isolated_env["db_path"]
    db = DatabaseManager(db_path=db_path)

    # Isolate routes to empty DB
    monkeypatch.setattr(dashboard_routes, "get_db", lambda: db)
    client = TestClient(app)

    endpoints = [
        "/dashboard",
        "/jobs",
        "/new-matches",
        "/shortlisted",
        "/applied",
        "/interviews",
        "/offers",
        "/pipeline-runs",
        "/source-health",
        "/apply-today",
        "/resume-preparation",
        "/applications",
        "/today",
        "/interview-prep",
        "/analytics",
        "/search-intelligence",
        "/job-agent",
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 200, f"Endpoint {endpoint} failed with {response.status_code}"


def test_excel_export_edge_cases(isolated_env):
    """Verify ExcelExporter generates all 10 sheets on empty dataset and unicode jobs."""
    exports_dir = isolated_env["exports_dir"]
    exporter = ExcelExporter(exports_dir=exports_dir)

    # 1. Zero jobs export
    empty_file = exporter.export([])
    assert empty_file.exists()

    import openpyxl
    wb_empty = openpyxl.load_workbook(empty_file)
    assert len(wb_empty.sheetnames) == 10

    # 2. Unicode and long content export
    unicode_job = Job(
        source="lever",
        title="Software Engineer (Backend) 🚀 日本語",
        company="Acme Corp <Global>",
        location="Bengaluru / Remote",
        url="https://example.com/job/unicode",
        description="Comprehensive technical description " * 100,
        match_score=95,
        status=JobStatus.NEW,
    )
    job_file = exporter.export([unicode_job])
    assert job_file.exists()

    wb_job = openpyxl.load_workbook(job_file)
    assert len(wb_job.sheetnames) == 10
