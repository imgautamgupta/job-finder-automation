"""Unit and integration tests for Workday CXS career portal source connector.

Verifies:
- Config-driven company configuration (adding a company is a config change).
- Every job extracts: company, title, job ID, location, posting date, direct apply URL.
- India pre-filtering logic (accepts Indian locations, excludes overseas/false positives).
- Independent failure isolation (failure of one company does not crash pipeline).
- Offline collection using saved sample JSON files (labelled as samples).
"""

import asyncio
from datetime import datetime
import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.config.settings import Settings
from app.models.job import Job
from app.sources.workday import (
    DEFAULT_WORKDAY_COMPANIES,
    WorkdayJobSource,
    build_workday_direct_url,
    extract_workday_job_id,
    is_india_location,
)

SAMPLES_DIR = Path("tests/samples")


def test_workday_company_config_driven():
    """Verify adding a new company is purely a config change."""
    custom_json = json.dumps({
        "acme": {
            "name": "Acme Corp",
            "host": "acme.wd1.myworkdayjobs.com",
            "tenant": "acme",
            "site": "careers",
        }
    })
    settings = Settings(
        WORKDAY_ENABLED=True,
        WORKDAY_COMPANIES="adobe,acme",
        WORKDAY_CUSTOM_CONFIGS=custom_json,
    )
    source = WorkdayJobSource(settings=settings)

    assert "acme" in source.company_configs
    assert source.company_configs["acme"]["name"] == "Acme Corp"
    assert "acme" in source.configured_companies
    assert "adobe" in source.configured_companies


def test_workday_india_location_prefilter():
    """Verify India location pre-filtering logic."""
    # Valid Indian locations
    assert is_india_location("India, Bengaluru") is True
    assert is_india_location("Bangalore, Karnataka, India") is True
    assert is_india_location("Hyderabad, Telangana") is True
    assert is_india_location("Pune, Maharashtra, India") is True
    assert is_india_location("Mumbai, India") is True
    assert is_india_location("Gurgaon, Haryana, India") is True
    assert is_india_location("Remote - India") is True
    assert is_india_location("Chennai") is True

    # Invalid / Overseas locations
    assert is_india_location("San Jose, CA, United States") is False
    assert is_india_location("London, United Kingdom") is False
    assert is_india_location("Munich, Germany") is False
    assert is_india_location("") is False
    assert is_india_location(None) is False

    # False positive: Indianapolis (without India)
    assert is_india_location("Indianapolis, IN, United States") is False


def test_workday_parse_posting_from_saved_samples():
    """Verify parsing fields using saved sample JSON files labelled as samples."""
    adobe_sample_file = SAMPLES_DIR / "workday_adobe_sample.json"
    assert adobe_sample_file.exists(), "Sample file workday_adobe_sample.json missing"

    with open(adobe_sample_file, "r", encoding="utf-8") as f:
        adobe_data = json.load(f)

    postings = adobe_data.get("jobPostings", [])
    assert len(postings) > 0

    source = WorkdayJobSource()
    adobe_config = DEFAULT_WORKDAY_COMPANIES["adobe"]

    for p in postings:
        job = source.parse_workday_posting(p, adobe_config)
        assert job is not None
        assert job.company == "Adobe"
        assert job.title != ""
        assert job.job_id != ""
        assert job.location != ""
        assert job.date_posted != ""
        assert job.url.startswith("https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced/job/")
        assert job.source == "workday"


def test_workday_salesforce_sample_parsing():
    """Verify Salesforce sample parsing and job ID extraction."""
    sf_sample_file = SAMPLES_DIR / "workday_salesforce_sample.json"
    assert sf_sample_file.exists(), "Sample file workday_salesforce_sample.json missing"

    with open(sf_sample_file, "r", encoding="utf-8") as f:
        sf_data = json.load(f)

    postings = sf_data.get("jobPostings", [])
    assert len(postings) > 0

    source = WorkdayJobSource()
    sf_config = DEFAULT_WORKDAY_COMPANIES["salesforce"]

    first_posting = postings[0]
    job = source.parse_workday_posting(first_posting, sf_config)
    assert job is not None
    assert job.company == "Salesforce"
    assert job.job_id.startswith("JR") or len(job.job_id) > 3
    assert "salesforce.wd12.myworkdayjobs.com" in job.url


def test_workday_visa_sample_parsing():
    """Verify Visa sample parsing with direct apply URL."""
    visa_sample_file = SAMPLES_DIR / "workday_visa_sample.json"
    assert visa_sample_file.exists(), "Sample file workday_visa_sample.json missing"

    with open(visa_sample_file, "r", encoding="utf-8") as f:
        visa_data = json.load(f)

    postings = visa_data.get("jobPostings", [])
    assert len(postings) > 0

    source = WorkdayJobSource()
    visa_config = DEFAULT_WORKDAY_COMPANIES["visa"]

    first_posting = postings[0]
    job = source.parse_workday_posting(first_posting, visa_config)
    assert job is not None
    assert job.company == "Visa"
    assert "visa.wd5.myworkdayjobs.com" in job.url


def test_workday_independent_failure_isolation():
    """Verify that failure of one company does not crash other companies or pipeline."""
    adobe_sample_file = SAMPLES_DIR / "workday_adobe_sample.json"
    with open(adobe_sample_file, "r", encoding="utf-8") as f:
        adobe_data = json.load(f)

    source = WorkdayJobSource(companies=["adobe", "failing_co"])
    source.request_delay_sec = 0.0
    # Register failing_co with bad host
    source.company_configs["failing_co"] = {
        "name": "Failing Corp",
        "host": "invalid.nonexistent.domain.example",
        "tenant": "fail",
        "site": "jobs",
    }

    # Mock client where adobe succeeds and failing_co raises exception
    mock_adobe_resp = MagicMock()
    mock_adobe_resp.status_code = 200
    mock_adobe_resp.json.return_value = adobe_data

    async def mock_post(url, *args, **kwargs):
        if "adobe" in str(url):
            return mock_adobe_resp
        raise Exception("Network timeout")

    with patch("httpx.AsyncClient.post", side_effect=mock_post), \
         patch("httpx.AsyncClient.get", return_value=MagicMock(status_code=200)):
        jobs = asyncio.run(source.collect_jobs(roles=["Software Engineer"], locations=["India"], max_results=5))

    assert len(jobs) > 0
    assert any(j.company == "Adobe" for j in jobs)
    # Check diagnostics show independent health status
    assert source.diagnostics["by_company"]["adobe"]["status"] in ("COMPLETED", "PARTIAL")
    assert source.diagnostics["by_company"]["failing_co"]["status"] == "FAILED"
    assert "Network timeout" in source.diagnostics["by_company"]["failing_co"]["error"]


def test_workday_diagnostics_formatting():
    """Verify diagnostics report formatting."""
    source = WorkdayJobSource()
    source.diagnostics = {
        "total_collected": 15,
        "valid_normalized": 15,
        "overseas_skipped": 2,
        "missing_job_id": 0,
        "by_company": {
            "adobe": {"name": "Adobe", "status": "COMPLETED", "collected": 10, "available": 55, "error": None},
            "intel": {"name": "Intel", "status": "COMPLETED", "collected": 5, "available": 74, "error": None},
        },
    }
    report = source.format_diagnostics()
    assert "Workday CXS Diagnostics:" in report
    assert "Adobe: status=COMPLETED, collected=10" in report
    assert "Intel: status=COMPLETED, collected=5" in report


def test_workday_clean_html_description():
    """Verify HTML cleanup preserves readability and strips tags."""
    from app.sources.workday import clean_html_description
    raw_html = "<p><b>Role:</b> Software Developer</p><br/><ul><li>3+ years experience</li></ul>"
    cleaned = clean_html_description(raw_html)
    assert cleaned is not None
    assert "Role: Software Developer" in cleaned
    assert "3+ years experience" in cleaned
    assert "<" not in cleaned


def test_workday_passes_title_location_prefilters():
    """Verify pre-filter selects only relevant title and location candidates."""
    from app.sources.workday import passes_title_location_prefilters

    # 1. Matches: Software Development Engineer in Noida
    j1 = Job(
        source="workday",
        title="Software Development Engineer",
        company="Adobe",
        location="Noida, India",
        job_id="WD-1",
        url="https://example.com",
    )
    assert passes_title_location_prefilters(j1, target_roles=["Software Engineer", "Backend Developer"]) is True

    # 2. Excluded by Seniority Marker: Senior Software Engineer
    j2 = Job(
        source="workday",
        title="Senior Software Engineer",
        company="Adobe",
        location="Noida, India",
        job_id="WD-2",
        url="https://example.com",
    )
    assert passes_title_location_prefilters(j2, target_roles=["Software Engineer"]) is False

    # 3. Excluded by Level Marker: Scientist IV / Engineer II
    j3 = Job(
        source="workday",
        title="Computer Scientist II",
        company="Adobe",
        location="Noida, India",
        job_id="WD-3",
        url="https://example.com",
    )
    assert passes_title_location_prefilters(j3, target_roles=["Computer Scientist"]) is False

    # 4. Excluded by Location: Overseas
    j4 = Job(
        source="workday",
        title="Software Engineer",
        company="Adobe",
        location="San Jose, CA, USA",
        job_id="WD-4",
        url="https://example.com",
    )
    assert passes_title_location_prefilters(j4, target_roles=["Software Engineer"]) is False


def test_workday_fetch_detail_for_prefiltered_jobs():
    """Verify detail text is fetched for prefiltered candidates and per-run limit is enforced."""
    settings = Settings(
        WORKDAY_ENABLED=True,
        WORKDAY_COMPANIES="adobe",
        WORKDAY_FETCH_DETAILS=True,
        WORKDAY_MAX_DETAILS_PER_RUN=1,
        WORKDAY_DETAIL_DELAY_SEC=0.0,
    )
    source = WorkdayJobSource(settings=settings)

    list_payload = {
        "total": 2,
        "jobPostings": [
            {
                "title": "Software Development Engineer",
                "externalPath": "/job/Noida/SDE_R1",
                "locationsText": "Noida, India",
                "postedOn": "Posted 2 Days Ago",
                "bulletFields": ["R1"],
            },
            {
                "title": "Software Engineer",
                "externalPath": "/job/Bangalore/SE_R2",
                "locationsText": "Bangalore, India",
                "postedOn": "Posted 5 Days Ago",
                "bulletFields": ["R2"],
            },
        ],
    }

    detail_html = "<p><b>Requirements:</b> 4+ years of software development experience.</p>"

    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "wday/cxs" in str(url):
            resp.json.return_value = {"jobPostingInfo": {"jobDescription": detail_html}}
        return resp

    async def mock_post(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = list_payload
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post), \
         patch("httpx.AsyncClient.get", side_effect=mock_get):
        jobs = asyncio.run(source.collect_jobs(roles=["Software Engineer", "Software Development Engineer"], locations=["India"], max_results=5))

    assert len(jobs) == 2
    # First job should have fetched detail
    assert "4+ years of software development experience" in jobs[0].description
    # Second job should not have fetched detail due to WORKDAY_MAX_DETAILS_PER_RUN=1
    assert "4+ years" not in jobs[1].description
    assert source.diagnostics["details_fetched"] == 1

