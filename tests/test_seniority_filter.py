"""Tests for Seniority Title Filtering and Source Health PARTIAL Status (Task 8).

Verifies:
- Senior markers caught as whole words/abbreviations, case-insensitive, with/without period or hyphen:
  Sr, Sr., Snr, Senior, Lead, Principal, Staff, Manager, Director, Architect,
  Head of, Distinguished, Fellow, Consultant-level wording such as "Sr. Consultant".
- False-positive avoidance inside other words (Srinivas, Leader in a team name, Staffing, etc.).
- The PayPal ("Sr Software Engineer - Python", R0138315) and Visa
  ("Software Engineer - Sr. Consultant Level (SDET, Playwright)", REF089412W) jobs are REJECT.
- Source-health reports PARTIAL (with error count) when errors or rate limits occur.
"""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.job import Job
from app.models.profile import JobProfile
from app.services.filter import JobFilter, match_seniority_title
from app.sources.workday import WorkdayJobSource
from app.sources.smartrecruiters import SmartRecruitersJobSource
from app.database.database import DatabaseManager


# =========================================================================
# 1. Pattern Matching Tests for match_seniority_title
# =========================================================================

@pytest.mark.parametrize(
    "title,expected_marker",
    [
        ("Sr Software Engineer - Python", "Sr"),
        ("Sr. Software Engineer", "Sr."),
        ("Sr-Software Engineer", "Sr"),
        ("Software Engineer - Sr.", "Sr."),
        ("Snr Software Engineer", "Snr"),
        ("Snr. Software Engineer", "Snr."),
        ("Snr-Software Engineer", "Snr"),
        ("Senior Software Engineer", "Senior"),
        ("Senior-Developer", "Senior"),
        ("Lead Software Engineer", "Lead"),
        ("Tech Lead", "Lead"),
        ("Lead-Engineer", "Lead"),
        ("Principal Architect", "Principal"),
        ("Principal-Engineer", "Principal"),
        ("Staff Software Engineer", "Staff"),
        ("Staff-Engineer", "Staff"),
        ("Engineering Manager", "Manager"),
        ("Manager - Core Services", "Manager"),
        ("Director of Engineering", "Director"),
        ("Engineering Director", "Director"),
        ("Solutions Architect", "Architect"),
        ("Enterprise Architect", "Architect"),
        ("Head of Engineering", "Head of"),
        ("Head of AI & ML", "Head of"),
        ("Distinguished Engineer", "Distinguished"),
        ("Distinguished-Architect", "Distinguished"),
        ("Technical Fellow", "Fellow"),
        ("Engineering Fellow", "Fellow"),
        ("Senior Consultant", "Senior Consultant"),
        ("Sr. Consultant", "Sr. Consultant"),
        ("Sr Consultant", "Sr Consultant"),
        ("Sr.-Consultant", "Sr.-Consultant"),
        ("Lead Consultant", "Lead Consultant"),
        ("Principal Consultant", "Principal Consultant"),
        ("Staff Consultant", "Staff Consultant"),
        ("Software Engineer - Sr. Consultant Level (SDET, Playwright)", "Sr. Consultant Level"),
        ("Software Engineer - Consultant Level", "Consultant Level"),
    ],
)
def test_seniority_patterns_match(title: str, expected_marker: str):
    """Verify all required seniority markers and variations are caught."""
    matched = match_seniority_title(title)
    assert matched is not None, f"Expected '{title}' to match a senior marker, but got None"
    assert expected_marker.lower() in matched.lower() or matched.lower() in expected_marker.lower()


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer",
        "Junior Software Engineer",
        "Associate Software Engineer",
        "Associate Consultant",
        "Graduate Trainee",
        "Entry Level Software Engineer",
        "Python Developer",
        "Full Stack Developer",
        "Backend Developer",
        # False positives specifically required to be avoided
        "Software Engineer - Srinivas Team",
        "Srinivas Python Developer",
        "Team Leader Support Engineer",
        "Software Engineer - Leader Squad",
        "Software Engineer - Staffing Solutions",
        "Staffing Systems Developer",
        "Staffer Operations Assistant",
        "Software Engineer - Leadership Development",
        "Software Engineer - Management Information Systems",
        "Management Trainee - Tech",
        "Directorate Support Specialist",
        "Architecture Student Intern",
        "Software Engineering Fellowship Graduate",
        "Headless CMS Engineer",
    ],
)
def test_seniority_false_positives_avoided(title: str):
    """Verify words containing substrings of senior markers do NOT produce false positives."""
    matched = match_seniority_title(title)
    assert matched is None, f"Expected '{title}' NOT to match any senior marker, but got '{matched}'"


# =========================================================================
# 2. Pipeline Filter Decisions (REJECT with clear reason)
# =========================================================================

def test_paypal_sr_engineer_rejected():
    """Verify PayPal 'Sr Software Engineer - Python' (R0138315) is classified as REJECT."""
    profile = JobProfile(
        target_roles=["Software Engineer", "Python Developer"],
        preferred_locations=["India", "Bengaluru", "Chennai"],
        negative_keywords=["Senior", "Lead", "Principal"],
        preferences={"remote_allowed": True},
    )
    job_filter = JobFilter(profile=profile)

    job = Job(
        title="Sr Software Engineer - Python",
        company="PayPal",
        location="Bengaluru, Karnataka, India",
        job_id="R0138315",
        source="workday",
        url="https://paypal.wd1.myworkdayjobs.com/en-US/PayPal-Jobs/job/R0138315",
        description="Sr Software Engineer - Python at PayPal.",
    )

    decision, reason = job_filter.classify_job(job)
    assert decision == "REJECT", f"Expected REJECT, got {decision}"
    assert "senior" in reason.lower()
    assert "sr" in reason.lower()
    assert job_filter.is_match(job) is False


def test_visa_sr_consultant_rejected():
    """Verify Visa 'Software Engineer - Sr. Consultant Level (SDET, Playwright)' (REF089412W) is classified as REJECT."""
    profile = JobProfile(
        target_roles=["Software Engineer"],
        preferred_locations=["India", "Bengaluru"],
        negative_keywords=["Senior", "Lead", "Principal"],
        preferences={"remote_allowed": True},
    )
    job_filter = JobFilter(profile=profile)

    job = Job(
        title="Software Engineer - Sr. Consultant Level (SDET, Playwright, Event Driven)",
        company="Visa",
        location="Bengaluru, Karnataka, India",
        job_id="REF089412W",
        source="workday",
        url="https://visa.wd5.myworkdayjobs.com/en-US/Visa-Jobs/job/REF089412W",
        description="Software Engineer - Sr. Consultant Level at Visa.",
    )

    decision, reason = job_filter.classify_job(job)
    assert decision == "REJECT", f"Expected REJECT, got {decision}"
    assert "senior" in reason.lower()
    assert job_filter.is_match(job) is False


def test_junior_job_with_senior_in_description_remains_matched():
    """Verify junior/entry-level job with 'senior' in description (e.g. reporting line) is NOT rejected by title filter."""
    profile = JobProfile(
        target_roles=["Software Engineer"],
        preferred_locations=["Bangalore"],
        negative_keywords=["Senior", "Lead"],
        preferences={"remote_allowed": True},
    )
    job_filter = JobFilter(profile=profile)

    job = Job(
        title="Software Engineer",
        company="Acme",
        location="Bangalore",
        source="lever",
        url="https://example.com/j1",
        description="You will work alongside senior engineers and staff architects on modern cloud systems.",
    )

    assert job_filter.is_match(job) is True


# =========================================================================
# 3. Source-Health PARTIAL Status Tests
# =========================================================================

def test_workday_source_health_partial_on_error():
    """Verify Workday source reports status=PARTIAL with error count when errors occur during collection."""
    source = WorkdayJobSource(companies=["adobe", "salesforce"])

    # Simulate Adobe succeeding with 5 jobs and Salesforce failing with HTTP 429
    source.diagnostics = {
        "total_collected": 5,
        "valid_normalized": 5,
        "overseas_skipped": 0,
        "missing_job_id": 0,
        "by_company": {
            "adobe": {
                "name": "Adobe",
                "status": "COMPLETED",
                "collected": 5,
                "available": 20,
                "error": None,
            },
            "salesforce": {
                "name": "Salesforce",
                "status": "PARTIAL",
                "collected": 2,
                "available": 10,
                "error": "HTTP 429",
            },
        },
    }

    # Verify formatting shows error details and collected count
    diag = source.format_diagnostics()
    assert "Salesforce: status=PARTIAL, collected=2, error=HTTP 429" in diag
    assert "Adobe: status=COMPLETED, collected=5" in diag


def test_workday_collect_jobs_sets_partial_status():
    """Verify Workday collection sets last_status='PARTIAL' and reports error count when one company fails."""
    source = WorkdayJobSource(companies=["adobe", "failing_co"])
    source.company_configs["failing_co"] = {
        "name": "Failing Corp",
        "host": "invalid.nonexistent.example",
        "tenant": "fail",
        "site": "jobs",
    }

    sample_post = {
        "title": "Software Engineer",
        "externalPath": "/job/123",
        "locationsText": "Bangalore, India",
        "postedOn": "Posted Today",
    }
    mock_adobe_resp = MagicMock()
    mock_adobe_resp.status_code = 200
    mock_adobe_resp.json.return_value = {"total": 1, "jobPostings": [sample_post]}

    async def mock_post(url, *args, **kwargs):
        if "adobe" in str(url):
            return mock_adobe_resp
        raise Exception("Connection refused (HTTP 500)")

    with patch("httpx.AsyncClient.post", side_effect=mock_post), \
         patch("httpx.AsyncClient.get", return_value=MagicMock(status_code=200)):
        jobs = asyncio.run(source.collect_jobs(roles=["Software Engineer"], locations=["India"], max_results=5))

    assert len(jobs) == 1
    assert source.last_status == "PARTIAL"
    assert "1 error(s)" in source.last_error
    assert "Failing Corp" in source.last_error


def test_smartrecruiters_sets_partial_status():
    """Verify SmartRecruiters collection sets last_status='PARTIAL' when one company hits an error."""
    source = SmartRecruitersJobSource(is_enabled=True, companies=["visa_sr", "failing_sr"])

    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.json.return_value = {
        "totalFound": 1,
        "content": [
            {
                "name": "Software Engineer",
                "id": "sr-101",
                "location": {"city": "Bangalore", "region": "Karnataka"},
                "releasedDate": "2026-10-15",
            }
        ],
    }

    mock_resp_err = MagicMock()
    mock_resp_err.status_code = 429

    async def mock_get(url, *args, **kwargs):
        if "visa_sr" in str(url):
            return mock_resp_ok
        return mock_resp_err

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        jobs = asyncio.run(source.collect_jobs(roles=["Software Engineer"], locations=["India"], max_results=5))

    assert len(jobs) == 1
    assert source.last_status == "PARTIAL"
    assert "1 error(s)" in source.last_error


def test_database_get_source_health_reflects_partial(tmp_path):
    """Verify database get_source_health reports PARTIAL status with error description."""
    db_file = tmp_path / "test_jobs.db"
    db = DatabaseManager(db_path=str(db_file))

    run_id = "test_run_partial_001"
    now_utc = datetime.now(timezone.utc)
    db.create_pipeline_run(
        run_id=run_id,
        started_at=now_utc,
        status="COMPLETED_WITH_SOURCE_WARNINGS",
        sources_attempted=["workday", "greenhouse"],
    )

    source_results = {
        "workday": {
            "source": "workday",
            "status": "PARTIAL",
            "collected": 15,
            "error": "1 error(s): Salesforce (HTTP 429)",
        },
        "greenhouse": {
            "source": "greenhouse",
            "status": "COMPLETED",
            "collected": 0,
            "error": None,
        },
    }

    db.update_pipeline_run(
        run_id=run_id,
        completed_at=now_utc,
        status="COMPLETED_WITH_SOURCE_WARNINGS",
        raw_collected=15,
        normalized=15,
        filtered=15,
        relevant=10,
        strong=5,
        source_results=json.dumps(source_results),
    )

    health = db.get_source_health()
    wd_health = next((h for h in health if h["source"] == "Workday"), None)
    assert wd_health is not None
    assert wd_health["status"] == "PARTIAL"
    assert wd_health["collected"] == 15
    assert "1 error(s)" in wd_health["error"]
