"""Unit and integration tests for Phase 7A: Daily Run Reliability & Job Tracking Foundation."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import time
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest

from app.database.database import DatabaseManager
from app.models.job import Job, JobStatus
from app.services.collector import JobCollector
from app.services.deduplicator import JobDeduplicator
from app.services.excel_exporter import ExcelExporter, REPORT_COLUMNS
from app.services.job_tracker import JobTracker
from app.sources.naukri import NaukriJobSource


@pytest.fixture
def temp_db():
    """Create isolated SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_tracking.db"
        manager = DatabaseManager(db_path=db_path)
        yield manager


# ==============================================================================
# 1. DATABASE MIGRATION & UPSERT PRESERVATION TESTS
# ==============================================================================


def test_migration_preserves_historical_jobs(temp_db):
    """Verify pre-existing jobs survive schema migration without data loss or reset."""
    # Insert a job using raw SQL simulating pre-Phase 7A schema
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO jobs (
                source, source_job_id, title, company, location,
                url, description, easy_apply, date_posted,
                date_found, fingerprint, created_at, updated_at
            ) VALUES (
                'lever', 'lev-legacy-1', 'Legacy Engineer', 'OldCo', 'Remote',
                'https://jobs.lever.co/oldco/1', 'Old desc', 0, '1d ago',
                '2026-10-01T10:00:00+00:00', 'fp-legacy-1',
                '2026-10-01T10:00:00+00:00', '2026-10-01T10:00:00+00:00'
            );
            """
        )
        legacy_id = cursor.lastrowid
        conn.commit()

    # Re-initialize database to trigger migration logic
    temp_db.initialize()

    migrated_job = temp_db.get_job_by_id(legacy_id)
    assert migrated_job is not None
    assert migrated_job.title == "Legacy Engineer"
    assert migrated_job.status == JobStatus.NEW
    assert migrated_job.first_seen_at is not None
    assert migrated_job.first_seen_at.strftime("%Y-%m-%d") == "2026-10-01"


def test_existing_applied_status_preserved_on_repeated_run(temp_db):
    """Verify that an APPLIED job is NEVER reset to NEW by a later collection run."""
    job = Job(
        source="greenhouse",
        source_job_id="gh-701",
        title="Software Engineer Intern",
        company="HackerRank",
        location="Bangalore",
        url="https://boards.greenhouse.io/hackerrank/jobs/701",
    )
    # First discovery
    temp_db.save_job(job, run_id="RUN-001")
    assert job.status == JobStatus.NEW

    # User applies to the job
    tracker = JobTracker(temp_db)
    tracker.update_status(job.id, JobStatus.APPLIED, notes="Applied on company portal")
    updated = temp_db.get_job_by_id(job.id)
    assert updated.status == JobStatus.APPLIED
    assert updated.notes == "Applied on company portal"

    # Second discovery in tomorrow's pipeline run with updated description
    job_next_day = Job(
        source="greenhouse",
        source_job_id="gh-701",
        title="Software Engineer Intern",
        company="HackerRank",
        location="Bangalore",
        url="https://boards.greenhouse.io/hackerrank/jobs/701",
        description="Fresh description with newly added details.",
    )
    is_new = temp_db.save_job(job_next_day, run_id="RUN-002")
    assert is_new is False

    # Check that status remains APPLIED and notes persist
    persisted = temp_db.get_job_by_id(job.id)
    assert persisted.status == JobStatus.APPLIED
    assert persisted.notes == "Applied on company portal"
    assert persisted.description == "Fresh description with newly added details."
    assert persisted.last_seen_run_id == "RUN-002"


def test_first_seen_at_and_last_seen_at_lifecycle(temp_db):
    """Verify first_seen_at remains unchanged while last_seen_at and run_id update."""
    t1 = datetime(2026, 10, 5, 8, 0, 0, tzinfo=timezone.utc)
    job = Job(
        source="lever",
        source_job_id="lev-99",
        title="Backend Dev",
        company="Epifi",
        location="Bangalore",
        url="https://jobs.lever.co/epifi/99",
        first_seen_at=t1,
        date_found=t1,
    )
    temp_db.save_job(job, run_id="RUN-DAY-1")

    saved_v1 = temp_db.get_job_by_id(job.id)
    assert saved_v1.first_seen_at == t1
    assert saved_v1.last_seen_run_id == "RUN-DAY-1"

    # Second encounter on a later day
    time.sleep(0.01)
    job_v2 = Job(
        source="lever",
        source_job_id="lev-99",
        title="Backend Dev",
        company="Epifi",
        location="Bangalore",
        url="https://jobs.lever.co/epifi/99",
    )
    temp_db.save_job(job_v2, run_id="RUN-DAY-2")

    saved_v2 = temp_db.get_job_by_id(job.id)
    # first_seen_at strictly preserved
    assert saved_v2.first_seen_at == t1
    # last_seen_at strictly newer
    assert saved_v2.last_seen_at > t1
    # run_id updated
    assert saved_v2.last_seen_run_id == "RUN-DAY-2"


# ==============================================================================
# 2. STATUS TRACKING & SERVICE TESTS
# ==============================================================================


def test_all_job_statuses_accepted_and_validated(temp_db):
    """Verify all 8 JobStatus enum members are accepted and invalid statuses raise ValueError."""
    job = Job(
        source="lever",
        source_job_id="lev-status-test",
        title="Platform Engineer",
        company="Meesho",
        location="Bangalore",
        url="https://jobs.lever.co/meesho/test",
    )
    temp_db.save_job(job, run_id="RUN-TEST")
    tracker = JobTracker(temp_db)

    valid_statuses = [
        JobStatus.NEW,
        JobStatus.VIEWED,
        JobStatus.SHORTLISTED,
        JobStatus.APPLIED,
        JobStatus.REJECTED,
        JobStatus.NOT_INTERESTED,
        JobStatus.INTERVIEW,
        JobStatus.OFFER,
    ]

    for s in valid_statuses:
        success = tracker.update_status(job.id, s)
        assert success is True
        assert tracker.get_status(job.id) == s

    # String representations are also accepted
    assert tracker.update_status(job.id, "INTERVIEW") is True
    assert tracker.get_status(job.id) == JobStatus.INTERVIEW

    # Invalid status strings are rejected
    with pytest.raises(ValueError):
        tracker.update_status(job.id, "INVALID_STATUS")

    with pytest.raises(ValueError):
        tracker.update_status(job.id, "HIRED")


def test_status_update_modifies_timestamp_not_first_seen(temp_db):
    """Verify status_updated_at updates when status changes, but first_seen_at remains unchanged."""
    job = Job(
        source="lever",
        source_job_id="lev-time-test",
        title="Data Engineer",
        company="FamPay",
        location="Bangalore",
        url="https://jobs.lever.co/fampay/1",
    )
    temp_db.save_job(job, run_id="RUN-1")
    initial = temp_db.get_job_by_id(job.id)
    initial_first_seen = initial.first_seen_at

    time.sleep(0.01)
    tracker = JobTracker(temp_db)
    tracker.update_status(job.id, JobStatus.SHORTLISTED)

    updated = temp_db.get_job_by_id(job.id)
    assert updated.status == JobStatus.SHORTLISTED
    assert updated.status_updated_at is not None
    assert updated.first_seen_at == initial_first_seen


def test_tracker_update_notes(temp_db):
    """Verify updating job notes persists correctly."""
    job = Job(
        source="greenhouse",
        source_job_id="gh-note-test",
        title="QA Engineer",
        company="Instawork",
        location="Bangalore",
        url="https://boards.greenhouse.io/instawork/1",
    )
    temp_db.save_job(job)
    tracker = JobTracker(temp_db)

    tracker.update_notes(job.id, "Reached out to recruiter on LinkedIn.")
    persisted = temp_db.get_job_by_id(job.id)
    assert persisted.notes == "Reached out to recruiter on LinkedIn."


# ==============================================================================
# 3. NEW JOB DETECTION & EXCEL SHEET TESTS
# ==============================================================================


def test_excel_distinguishes_new_matches_from_all_relevant():
    """Verify genuinely new jobs appear in New Matches while previously seen jobs do not."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        exporter = ExcelExporter(exports_dir=tmp_dir)

        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        # Job 1: Newly discovered in run RUN-100 (score 85) -> New Matches + Top Matches + All Relevant
        j_new = Job(
            source="greenhouse",
            source_job_id="j-new",
            title="Backend Engineer",
            company="GitLab",
            location="Remote",
            url="https://boards.greenhouse.io/gitlab/new",
            match_score=85,
            match_category="Strong",
            first_seen_at=now,
            last_seen_at=now,
            last_seen_run_id="RUN-100",
        )
        j_new._is_new_in_run = True

        # Job 2: Previously discovered yesterday (score 82) -> Top Matches + All Relevant (NOT New Matches)
        j_old_top = Job(
            source="lever",
            source_job_id="j-old-top",
            title="Software Engineer",
            company="Meesho",
            location="Bangalore",
            url="https://jobs.lever.co/meesho/old",
            match_score=82,
            match_category="Strong",
            first_seen_at=yesterday,
            last_seen_at=now,
            last_seen_run_id="RUN-100",
        )
        j_old_top._is_new_in_run = False

        # Job 3: Previously discovered yesterday (score 65) -> All Relevant only (NOT New Matches)
        j_old_relevant = Job(
            source="lever",
            source_job_id="j-old-rel",
            title="Junior Dev",
            company="Paytm",
            location="Noida",
            url="https://jobs.lever.co/paytm/old",
            match_score=65,
            match_category="Possible",
            first_seen_at=yesterday,
            last_seen_at=now,
            last_seen_run_id="RUN-100",
        )
        j_old_relevant._is_new_in_run = False

        # Job 4: Low score (45) -> Excluded from all
        j_low = Job(
            source="naukri",
            title="Senior Architect",
            company="OldCo",
            location="Pune",
            url="https://naukri.com/arch",
            match_score=45,
            match_category="Not Relevant",
            first_seen_at=now,
            last_seen_at=now,
            last_seen_run_id="RUN-100",
        )

        export_path = exporter.export(
            [j_new, j_old_top, j_old_relevant, j_low],
            current_run_id="RUN-100",
        )

        wb = openpyxl.load_workbook(str(export_path))
        assert "New Matches" in wb.sheetnames
        assert "Top Matches" in wb.sheetnames
        assert "All Relevant Jobs" in wb.sheetnames

        # Sheet 1: New Matches (only j_new)
        ws_new = wb["New Matches"]
        assert ws_new.max_row == 2  # 1 header + 1 job
        assert ws_new.cell(row=2, column=REPORT_COLUMNS.index("Job Title") + 1).value == "Backend Engineer"

        # Sheet 2: Top Matches (j_new and j_old_top)
        ws_top = wb["Top Matches"]
        assert ws_top.max_row == 3  # 1 header + 2 jobs

        # Sheet 3: All Relevant Jobs (j_new, j_old_top, and j_old_relevant)
        ws_all = wb["All Relevant Jobs"]
        assert ws_all.max_row == 4  # 1 header + 3 jobs


def test_excel_contains_all_20_columns_and_tracking_headers():
    """Verify all 17 existing columns plus 3 new tracking columns exist in order."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        exporter = ExcelExporter(exports_dir=tmp_dir)
        job = Job(
            source="lever",
            title="DevOps Engineer",
            company="JumpCloud",
            location="Bangalore",
            url="https://jobs.lever.co/jumpcloud/1",
            match_score=75,
            match_category="Good",
            notes="Need review",
            status=JobStatus.SHORTLISTED,
        )
        file_path = exporter.export([job])

        wb = openpyxl.load_workbook(str(file_path))
        ws = wb["All Relevant Jobs"]
        headers = [ws.cell(row=1, column=c).value for c in range(1, len(REPORT_COLUMNS) + 1)]

        # Check all required columns
        assert headers[:17] == [
            "Priority", "Match Score", "Match Category", "Company", "Job Title",
            "Location", "Source", "Easy Apply", "Date Posted", "Date Found",
            "Job URL", "Matched Roles", "Matched Skills", "Matched Locations",
            "Experience Match", "Excluded Reasons", "Notes",
        ]
        assert headers[17:20] == ["Status", "First Seen", "Last Seen"]
        # Verify Phase 9 extended columns are present
        assert "Application Readiness" in headers
        assert "Application Priority" in headers

        # Check data row
        assert ws.cell(row=2, column=17).value == "Need review"
        assert ws.cell(row=2, column=18).value == "SHORTLISTED"


# ==============================================================================
# 4. SOURCE FAILURE DISTINCTION & PIPELINE RUN RECORD TESTS
# ==============================================================================


def test_naukri_403_marked_as_blocked_not_zero_success():
    """Verify Naukri HTTP 403 sets status=BLOCKED with error message rather than looking successful with 0 jobs."""
    import asyncio
    source = NaukriJobSource(is_enabled=True)

    # Mock page.goto returning 403
    mock_response = AsyncMock()
    mock_response.status = 403

    mock_page = AsyncMock()
    mock_page.goto.return_value = mock_response

    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_playwright = AsyncMock()
    mock_playwright.chromium.launch.return_value = mock_browser

    with patch("playwright.async_api.async_playwright") as mock_pw_init:
        mock_pw_init.return_value.start = AsyncMock(return_value=mock_playwright)
        jobs = asyncio.run(source.collect_jobs(roles=["Python Developer"], locations=["Bangalore"]))

    assert len(jobs) == 0
    assert source.last_status == "BLOCKED"
    assert "403" in source.last_error


def test_collector_records_source_results_and_warnings():
    """Verify JobCollector correctly aggregates source statuses and flags warnings."""
    import asyncio
    mock_src_good = AsyncMock()
    mock_src_good.source_name = "lever"
    mock_src_good.is_enabled = True
    mock_src_good.last_status = "COMPLETED"
    mock_src_good.last_error = None
    mock_src_good.setup = AsyncMock()
    mock_src_good.teardown = AsyncMock()
    mock_src_good.collect_jobs = AsyncMock(return_value=[
        Job(source="lever", title="Eng", company="Co", location="Blr", url="https://ex.com/1")
    ])

    mock_src_blocked = AsyncMock()
    mock_src_blocked.source_name = "naukri"
    mock_src_blocked.is_enabled = True
    mock_src_blocked.last_status = "BLOCKED"
    mock_src_blocked.last_error = "HTTP 403 (Access Denied)"
    mock_src_blocked.setup = AsyncMock()
    mock_src_blocked.teardown = AsyncMock()
    mock_src_blocked.collect_jobs = AsyncMock(return_value=[])

    collector = JobCollector(sources=[mock_src_good, mock_src_blocked])
    jobs = asyncio.run(collector.collect_all(roles=["Eng"], locations=["Blr"]))

    assert len(jobs) == 1
    assert collector.has_source_warnings() is True

    res = collector.get_source_results()
    assert res["lever"]["status"] == "COMPLETED"
    assert res["lever"]["collected"] == 1

    assert res["naukri"]["status"] == "BLOCKED"
    assert res["naukri"]["collected"] == 0
    assert "403" in res["naukri"]["error"]


def test_pipeline_run_table_records_and_retrieval(temp_db):
    """Verify pipeline_runs table records run execution metrics and status."""
    run_id = "RUN-20261007-TEST"
    temp_db.create_pipeline_run(
        run_id=run_id,
        started_at=datetime.now(timezone.utc),
        status="RUNNING",
        sources_attempted=["lever", "greenhouse", "naukri"],
    )

    run_row = temp_db.get_pipeline_run(run_id)
    assert run_row is not None
    assert run_row["status"] == "RUNNING"
    assert "lever" in run_row["sources_attempted"]

    # Update on completion
    temp_db.update_pipeline_run(
        run_id=run_id,
        completed_at=datetime.now(timezone.utc),
        status="COMPLETED_WITH_SOURCE_WARNINGS",
        raw_collected=50,
        normalized=50,
        filtered=4,
        relevant=2,
        strong=1,
        excellent=0,
        new_jobs=2,
        duplicate_jobs=2,
        error_count=1,
        notes="Exported to excel",
    )

    updated_row = temp_db.get_pipeline_run(run_id)
    assert updated_row["status"] == "COMPLETED_WITH_SOURCE_WARNINGS"
    assert updated_row["raw_collected"] == 50
    assert updated_row["new_jobs"] == 2
    assert updated_row["duplicate_jobs"] == 2
    assert updated_row["error_count"] == 1
