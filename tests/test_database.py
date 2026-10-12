"""Unit tests for SQLite job storage and multi-level historical deduplication (Phase 3)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import time
import pytest

from app.database.database import DatabaseManager
from app.models.job import Job


@pytest.fixture
def temp_db():
    """Create a temporary database for test isolation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_jobs.db"
        manager = DatabaseManager(db_path=db_path)
        yield manager


def test_database_initializes_successfully(temp_db):
    """Test 1: Verify database schema initializes with all Phase 3 columns and indices."""
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(jobs);")
        columns = {row["name"]: row["type"] for row in cursor.fetchall()}

        required_cols = [
            "id",
            "source",
            "source_job_id",
            "title",
            "company",
            "location",
            "url",
            "description",
            "easy_apply",
            "date_posted",
            "date_found",
            "employment_type",
            "experience_required",
            "salary",
            "fingerprint",
            "created_at",
            "updated_at",
        ]
        for col in required_cols:
            assert col in columns, f"Column {col} missing from schema"


def test_job_insert_and_retrieval(temp_db):
    """Test 2 & 3: A job can be inserted and retrieved by ID."""
    job = Job(
        source="linkedin",
        source_job_id="1001",
        title="Python Developer",
        company="Alpha Corp",
        location="Bangalore",
        url="https://linkedin.com/jobs/view/1001",
        description="FastAPI and Postgres development.",
        easy_apply=True,
        salary="12-15 LPA",
    )

    is_new = temp_db.save_job(job)
    assert is_new is True
    assert job.id is not None

    retrieved = temp_db.get_job_by_id(job.id)
    assert retrieved is not None
    assert retrieved.title == "Python Developer"
    assert retrieved.company == "Alpha Corp"
    assert retrieved.source_job_id == "1001"
    assert retrieved.easy_apply is True
    assert retrieved.salary == "12-15 LPA"


def test_duplicate_source_job_id_detected(temp_db):
    """Test 4: Duplicate source + source_job_id is detected even with a different URL."""
    job1 = Job(
        source="linkedin",
        source_job_id="LK-999",
        title="Backend Engineer",
        company="Beta Inc",
        location="Remote",
        url="https://linkedin.com/jobs/view/original",
    )
    assert temp_db.save_job(job1) is True

    # Same source and source_job_id, but different URL
    job2 = Job(
        source="linkedin",
        source_job_id="LK-999",
        title="Backend Engineer",
        company="Beta Inc",
        location="Remote",
        url="https://linkedin.com/jobs/view/new-url-alias",
    )

    assert temp_db.job_exists(job2) is True
    is_new = temp_db.save_job(job2)
    assert is_new is False

    all_jobs = temp_db.get_all_jobs()
    assert len(all_jobs) == 1


def test_duplicate_canonical_url_detected(temp_db):
    """Test 5: Duplicate canonical URL is detected despite tracking parameters."""
    job1 = Job(
        source="naukri",
        title="Software Engineer",
        company="Gamma Ltd",
        location="Hyderabad",
        url="https://www.naukri.com/job-listings-gamma-123",
    )
    assert temp_db.save_job(job1) is True

    # Same URL with tracking parameters and no source_job_id
    job2 = Job(
        source="naukri",
        title="Software Engineer",
        company="Gamma Ltd",
        location="Hyderabad",
        url="https://www.naukri.com/job-listings-gamma-123?utm_source=feed&ref=jobsearch&trackingId=xyz",
    )

    assert temp_db.job_exists(job2) is True
    is_new = temp_db.save_job(job2)
    assert is_new is False
    assert len(temp_db.get_all_jobs()) == 1


def test_duplicate_fingerprint_detected(temp_db):
    """Test 6: Duplicate fingerprint is detected when neither source_job_id nor raw URL match exactly."""
    job1 = Job(
        source="custom",
        title="Data Scientist",
        company="Delta Analytics",
        location="Pune",
        url="https://custom.com/jobs/data-scientist",
    )
    assert temp_db.save_job(job1) is True

    # Job with same core details and fingerprint
    job2 = Job(
        source="custom",
        title="Data Scientist",
        company="Delta Analytics",
        location="Pune",
        url="https://custom.com/jobs/data-scientist/",  # Trailing slash gets canonicalized
    )

    assert job1.fingerprint == job2.fingerprint
    assert temp_db.job_exists(job2) is True
    assert temp_db.save_job(job2) is False
    assert len(temp_db.get_all_jobs()) == 1


def test_saving_same_job_twice_does_not_create_two_rows(temp_db):
    """Test 7: Saving identical job twice preserves exactly 1 database row."""
    job = Job(
        source="linkedin",
        source_job_id="LK-555",
        title="AI Engineer",
        company="Epsilon AI",
        location="Remote",
        url="https://linkedin.com/jobs/view/555",
    )
    assert temp_db.save_job(job) is True
    assert temp_db.save_job(job) is False
    assert len(temp_db.get_all_jobs()) == 1


def test_multiple_different_jobs_can_be_inserted(temp_db):
    """Test 8: Batch saving multiple distinct jobs creates multiple records."""
    jobs = [
        Job(
            source="linkedin",
            source_job_id=f"LK-{i}",
            title=f"Role {i}",
            company="Company",
            location="Remote",
            url=f"https://linkedin.com/jobs/{i}",
        )
        for i in range(5)
    ]
    inserted_count = temp_db.save_jobs(jobs)
    assert inserted_count == 5
    assert len(temp_db.get_all_jobs()) == 5


def test_get_recent_jobs(temp_db):
    """Test 9: Retrieve recent jobs with limit and days filter."""
    now = datetime.now(timezone.utc)
    old_job = Job(
        source="linkedin",
        source_job_id="OLD-1",
        title="Old Job",
        company="Co",
        location="Remote",
        url="https://linkedin.com/jobs/old",
        date_found=now - timedelta(days=10),
    )
    new_job = Job(
        source="linkedin",
        source_job_id="NEW-1",
        title="New Job",
        company="Co",
        location="Remote",
        url="https://linkedin.com/jobs/new",
        date_found=now,
    )
    temp_db.save_job(old_job)
    temp_db.save_job(new_job)

    # Limit check
    recent_limited = temp_db.get_recent_jobs(limit=1)
    assert len(recent_limited) == 1
    assert recent_limited[0].source_job_id == "NEW-1"

    # Days filter check (last 3 days)
    recent_filtered = temp_db.get_recent_jobs(days=3)
    assert len(recent_filtered) == 1
    assert recent_filtered[0].source_job_id == "NEW-1"


def test_get_jobs_by_date(temp_db):
    """Test 10: Retrieve jobs filtered by specific date string."""
    target_date = datetime(2026, 10, 6, 8, 0, 0, tzinfo=timezone.utc)
    other_date = datetime(2026, 9, 15, 8, 0, 0, tzinfo=timezone.utc)

    job1 = Job(
        source="linkedin",
        source_job_id="D1",
        title="Job Oct 6",
        company="Co",
        location="Remote",
        url="https://example.com/d1",
        date_found=target_date,
    )
    job2 = Job(
        source="linkedin",
        source_job_id="D2",
        title="Job Sep 15",
        company="Co",
        location="Remote",
        url="https://example.com/d2",
        date_found=other_date,
    )
    temp_db.save_job(job1)
    temp_db.save_job(job2)

    oct6_jobs = temp_db.get_jobs_by_date("2026-10-06")
    assert len(oct6_jobs) == 1
    assert oct6_jobs[0].title == "Job Oct 6"


def test_date_found_preserved_and_updated_at_changes(temp_db):
    """Test 11 & 12: Encountering an existing job preserves date_found and updates updated_at."""
    orig_found = datetime(2026, 10, 1, 8, 0, 0, tzinfo=timezone.utc)
    job_v1 = Job(
        source="linkedin",
        source_job_id="UP-100",
        title="Software Engineer",
        company="Evolving Tech",
        location="Bangalore",
        url="https://linkedin.com/jobs/view/up100",
        description="Initial description",
        date_found=orig_found,
    )

    # First discovery
    assert temp_db.save_job(job_v1) is True
    initial_record = temp_db.get_job_by_id(job_v1.id)
    assert initial_record.date_found == orig_found
    initial_updated_at = initial_record.updated_at

    # Small pause to guarantee timestamp progression
    time.sleep(0.05)

    # Second encounter on a later day with updated fields
    today_found = datetime(2026, 10, 6, 8, 0, 0, tzinfo=timezone.utc)
    job_v2 = Job(
        source="linkedin",
        source_job_id="UP-100",
        title="Software Engineer",
        company="Evolving Tech",
        location="Bangalore",
        url="https://linkedin.com/jobs/view/up100",
        description="Updated newer description with requirements",
        salary="20 LPA",
        date_found=today_found,
    )

    is_new = temp_db.save_job(job_v2)
    assert is_new is False  # Recognized as existing job

    updated_record = temp_db.get_job_by_id(job_v1.id)
    # 1. date_found MUST NOT be overwritten by the new encounter timestamp
    assert updated_record.date_found == orig_found
    # 2. updated_at MUST be newer than initial
    assert updated_record.updated_at > initial_updated_at
    # 3. Mutable details must be refreshed
    assert updated_record.salary == "20 LPA"
    assert "Updated newer description" in updated_record.description
    # 4. Total row count remains 1
    assert len(temp_db.get_all_jobs()) == 1
