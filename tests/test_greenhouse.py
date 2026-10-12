"""Unit tests for Greenhouse public job source (Phase 6C).

Tests use mock HTTP fixtures and in-memory structures only.
No live external network requests are made during unit test runs.
"""

import asyncio
import os
import tempfile
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from app.config.settings import Settings, get_settings
from app.database.database import DatabaseManager
from app.models.job import Job
from app.services.deduplicator import JobDeduplicator
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher
from app.sources.greenhouse import (
    GreenhouseJobSource,
    build_greenhouse_jobs_url,
    clean_html_description,
    fetch_greenhouse_postings_http,
    normalize_greenhouse_location,
    parse_greenhouse_posting,
)

SAMPLE_GREENHOUSE_POSTING = {
    "id": 8097321,
    "internal_job_id": 554433,
    "title": "Backend Software Engineer",
    "company_name": "Cloudflare, Inc.",
    "absolute_url": "https://boards.greenhouse.io/cloudflare/jobs/8097321",
    "location": {"name": "Hybrid"},
    "offices": [
        {"id": 101, "name": "Bangalore Office", "location": "Bangalore, India"},
        {"id": 102, "name": "Remote Hub", "location": "Remote"},
    ],
    "content": "&lt;div&gt;&lt;p&gt;We are seeking a Backend Software Engineer proficient in Python, FastAPI, and PostgreSQL.&lt;/p&gt;&lt;/div&gt;",
    "updated_at": "2024-03-15T10:30:00-04:00",
    "first_published": "2024-03-01T08:00:00Z",
    "metadata": [
        {"id": 1, "name": "Employment Type", "value": "Full-time"},
        {"id": 2, "name": "Experience Level", "value": "Entry Level"},
        {"id": 3, "name": "Compensation", "value": "$120,000 - $140,000 USD"},
    ],
}


def _get_test_matcher() -> JobMatcher:
    profile = get_settings().load_profile()
    return JobMatcher(profile=profile)


# =====================================================================
# Test 1 — Greenhouse source disabled
# =====================================================================
def test_greenhouse_disabled():
    """When GREENHOUSE_ENABLED=false, connector makes no network requests and returns empty list."""
    settings = Settings(GREENHOUSE_ENABLED=False, GREENHOUSE_COMPANIES="cloudflare")
    source = GreenhouseJobSource(settings=settings)

    with patch("app.sources.greenhouse.fetch_greenhouse_postings_http") as mock_fetch:
        jobs = asyncio.run(source.collect_jobs(["Software Engineer"], ["Bangalore"]))
        assert jobs == []
        mock_fetch.assert_not_called()


# =====================================================================
# Test 2 — Empty company configuration
# =====================================================================
def test_greenhouse_empty_company_list():
    """When GREENHOUSE_COMPANIES is empty, return empty list without failing."""
    settings = Settings(GREENHOUSE_ENABLED=True, GREENHOUSE_COMPANIES="   ")
    source = GreenhouseJobSource(settings=settings)

    with patch("app.sources.greenhouse.fetch_greenhouse_postings_http") as mock_fetch:
        jobs = asyncio.run(source.collect_jobs(["Software Engineer"], ["Bangalore"]))
        assert jobs == []
        mock_fetch.assert_not_called()


# =====================================================================
# Test 3 — Configurable collection limit
# =====================================================================
def test_greenhouse_configurable_collection_limit():
    """Verify GREENHOUSE_MAX_JOBS_PER_COMPANY is configurable via settings."""
    settings = Settings(
        GREENHOUSE_ENABLED=True,
        GREENHOUSE_COMPANIES="cloudflare",
        GREENHOUSE_MAX_JOBS_PER_COMPANY=25,
    )
    source = GreenhouseJobSource(settings=settings)
    assert source.max_jobs_per_company == 25


# =====================================================================
# Test 4 — Collection stops at configured limit
# =====================================================================
def test_greenhouse_collection_stops_at_limit():
    """Verify collector truncates raw postings to configured max_jobs_per_company."""
    settings = Settings(
        GREENHOUSE_ENABLED=True,
        GREENHOUSE_COMPANIES="cloudflare",
        GREENHOUSE_MAX_JOBS_PER_COMPANY=5,
        GREENHOUSE_REQUEST_DELAY_SEC=0.0,
    )
    source = GreenhouseJobSource(settings=settings)

    mock_postings = [
        {"id": 1000 + i, "title": f"Software Engineer {i}", "company_name": "Cloudflare"}
        for i in range(20)
    ]

    with patch("app.sources.greenhouse.fetch_greenhouse_postings_http", return_value=mock_postings):
        jobs = asyncio.run(source.collect_jobs(["Software Engineer"], ["Remote"]))
        assert len(jobs) == 5
        assert [j.source_job_id for j in jobs] == [str(1000 + i) for i in range(5)]


# =====================================================================
# Test 5 — Valid Greenhouse posting normalization
# =====================================================================
def test_greenhouse_valid_posting_normalization():
    """Verify valid Greenhouse posting normalizes to standardized Job schema."""
    job = parse_greenhouse_posting(SAMPLE_GREENHOUSE_POSTING, company_id="cloudflare")
    assert job is not None
    assert job.source == "greenhouse"
    assert job.source_job_id == "8097321"
    assert job.job_id == "8097321"
    assert job.title == "Backend Software Engineer"
    assert job.company == "Cloudflare, Inc."
    assert job.url == "https://boards.greenhouse.io/cloudflare/jobs/8097321"
    assert "Bangalore, India" in (job.location or "")
    assert "Remote" in (job.location or "")
    assert job.easy_apply is False  # Never guessed
    assert job.date_posted == "2024-03-01"
    assert job.employment_type == "Full-time"
    assert job.experience_required == "Entry Level"
    assert job.salary == "$120,000 - $140,000 USD"
    assert job.description is not None
    assert "Backend Software Engineer" in job.description
    assert job.extra_metadata["greenhouse_board_id"] == "cloudflare"


# =====================================================================
# Test 6 — Stable source_job_id
# =====================================================================
def test_greenhouse_stable_source_job_id():
    """Verify posting id becomes stable string source_job_id without randomness."""
    posting = {"id": 1234567, "title": "Python Developer"}
    job = parse_greenhouse_posting(posting, company_id="acme")
    assert job is not None
    assert job.source_job_id == "1234567"
    assert job.job_id == "1234567"


# =====================================================================
# Test 7 — Correct source value = 'greenhouse'
# =====================================================================
def test_greenhouse_source_name_is_greenhouse():
    """Verify job.source is strictly 'greenhouse'."""
    posting = {"id": 999, "title": "Developer"}
    job = parse_greenhouse_posting(posting, company_id="acme")
    assert job is not None
    assert job.source == "greenhouse"


# =====================================================================
# Test 8 — Missing location remains None
# =====================================================================
def test_greenhouse_missing_location_remains_none():
    """A posting with missing location produces None, never defaulted to 'India'."""
    posting = {"id": 101, "title": "Python Developer", "location": None, "offices": []}
    job = parse_greenhouse_posting(posting, company_id="acme")
    assert job is not None
    assert job.location is None
    assert job.location != "India"

    # Matcher should award 0 location score
    matcher = _get_test_matcher()
    assert matcher.match(job).location_score == 0


# =====================================================================
# Test 9 — Remote location remains Remote
# =====================================================================
def test_greenhouse_remote_location():
    """Explicit Remote location is preserved and scores 18 points."""
    matcher = _get_test_matcher()

    posting = {"id": 102, "title": "Python Developer", "location": {"name": "Remote"}}
    job = parse_greenhouse_posting(posting, company_id="acme")
    assert job is not None
    assert job.location == "Remote"
    assert matcher.match(job).location_score == 18


# =====================================================================
# Test 10 — Bangalore/Bengaluru location handling
# =====================================================================
def test_greenhouse_bangalore_bengaluru_location():
    """Bangalore and Bengaluru locations are recognized and score 18 points."""
    matcher = _get_test_matcher()

    posting_blr = {
        "id": 103,
        "title": "Software Engineer",
        "location": {"name": "Bangalore, Karnataka, India"},
    }
    job_blr = parse_greenhouse_posting(posting_blr, company_id="acme")
    assert job_blr is not None
    assert "Bangalore" in job_blr.location
    assert matcher.match(job_blr).location_score == 18

    posting_beng = {
        "id": 104,
        "title": "Software Engineer",
        "location": {"name": "Bengaluru, India"},
    }
    job_beng = parse_greenhouse_posting(posting_beng, company_id="acme")
    assert job_beng is not None
    assert "Bengaluru" in job_beng.location
    assert matcher.match(job_beng).location_score == 18


# =====================================================================
# Test 11 — Delhi/Noida location handling
# =====================================================================
def test_greenhouse_delhi_noida_location():
    """Delhi and Noida postings are preserved and receive top priority (20 points)."""
    matcher = _get_test_matcher()

    posting_delhi = {
        "id": 105,
        "title": "Python Developer",
        "location": {"name": "New Delhi, India"},
    }
    job_delhi = parse_greenhouse_posting(posting_delhi, company_id="acme")
    assert job_delhi is not None
    assert matcher.match(job_delhi).location_score == 20

    posting_noida = {
        "id": 106,
        "title": "Python Developer",
        "location": {"name": "Noida, India"},
    }
    job_noida = parse_greenhouse_posting(posting_noida, company_id="acme")
    assert job_noida is not None
    assert matcher.match(job_noida).location_score == 20


# =====================================================================
# Test 12 — Multiple locations handling
# =====================================================================
def test_greenhouse_multiple_locations():
    """Multiple locations across location and offices are combined with semicolons."""
    posting = {
        "id": 107,
        "title": "Full Stack Developer",
        "location": {"name": "Hybrid"},
        "offices": [
            {"name": "Bangalore Office", "location": "Bangalore, India"},
            {"name": "London Office", "location": "London, United Kingdom"},
        ],
    }
    job = parse_greenhouse_posting(posting, company_id="acme")
    assert job is not None
    assert "Hybrid" in job.location
    assert "Bangalore, India" in job.location
    assert "London, United Kingdom" in job.location
    assert "; " in job.location


# =====================================================================
# Test 13 — Missing description handling
# =====================================================================
def test_greenhouse_missing_description():
    """When content is None or empty, description is None without crashing."""
    posting = {"id": 108, "title": "Python Developer", "content": None}
    job = parse_greenhouse_posting(posting, company_id="acme")
    assert job is not None
    assert job.description is None


# =====================================================================
# Test 14 — Malformed posting handling
# =====================================================================
def test_greenhouse_malformed_posting():
    """Malformed posting items return None safely without raising exceptions."""
    assert parse_greenhouse_posting({}, company_id="acme") is None
    assert parse_greenhouse_posting({"id": 123}, company_id="acme") is None  # Missing title
    assert parse_greenhouse_posting({"title": "Role"}, company_id="acme") is None  # Missing id
    assert parse_greenhouse_posting("not a dict", company_id="acme") is None  # type: ignore
    assert parse_greenhouse_posting(None, company_id="acme") is None  # type: ignore


# =====================================================================
# Test 15 — HTTP 403 handling
# =====================================================================
def test_greenhouse_http_403():
    """HTTP 403 Forbidden returns empty list safely without crashing."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://boards-api.greenhouse.io/v1/boards/restricted/jobs",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )
        postings = fetch_greenhouse_postings_http("restricted")
        assert postings == []


# =====================================================================
# Test 16 — HTTP 404 handling
# =====================================================================
def test_greenhouse_http_404():
    """HTTP 404 Not Found returns empty list safely without crashing."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://boards-api.greenhouse.io/v1/boards/unknown/jobs",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        postings = fetch_greenhouse_postings_http("unknown")
        assert postings == []


# =====================================================================
# Test 17 — HTTP 429 handling
# =====================================================================
def test_greenhouse_http_429():
    """HTTP 429 Too Many Requests returns empty list safely without crashing."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://boards-api.greenhouse.io/v1/boards/rate-limited/jobs",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None,
        )
        postings = fetch_greenhouse_postings_http("rate-limited")
        assert postings == []


# =====================================================================
# Test 18 — Timeout and connection error handling
# =====================================================================
def test_greenhouse_timeout_and_connection_error():
    """URLError and TimeoutError return empty list gracefully."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("Connection timed out")
        postings = fetch_greenhouse_postings_http("timeout-co")
        assert postings == []


# =====================================================================
# Test 19 — Existing matcher/filter compatibility
# =====================================================================
def test_greenhouse_matcher_filter_compatibility():
    """Verify Greenhouse jobs run through existing JobFilter and JobMatcher seamlessly."""
    profile = get_settings().load_profile()
    job_filter = JobFilter(profile=profile)
    matcher = JobMatcher(profile=profile)

    job = Job(
        source="greenhouse",
        source_job_id="gh-match-1",
        job_id="gh-match-1",
        title="Software Engineer",
        company="Greenhouse Tech",
        location="Bangalore",
        url="https://boards.greenhouse.io/tech/jobs/1",
        description="Looking for candidate knowing Python, FastAPI, and PostgreSQL.",
    )

    assert job_filter.is_match(job) is True
    res = matcher.match(job)
    assert res.role_score == 40
    assert res.location_score == 18
    assert res.skills_score > 0
    assert res.category in ("Strong", "Good", "Excellent")


# =====================================================================
# Test 20 — Database deduplication
# =====================================================================
def test_greenhouse_database_deduplication():
    """Greenhouse job is stored, and identical record in same batch is deduplicated."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        db_mgr = DatabaseManager(db_path=db_path)
        deduplicator = JobDeduplicator(db_manager=db_mgr)

        job_a = Job(
            source="greenhouse",
            source_job_id="gh-unique-1234",
            job_id="gh-unique-1234",
            title="Backend Engineer",
            company="CloudCorp",
            url="https://boards.greenhouse.io/cloudcorp/jobs/gh-unique-1234",
            location="Bangalore",
        )
        job_b = Job(
            source="greenhouse",
            source_job_id="gh-unique-1234",
            job_id="gh-unique-1234",
            title="Backend Engineer",
            company="CloudCorp",
            url="https://boards.greenhouse.io/cloudcorp/jobs/gh-unique-1234",
            location="Bangalore",
        )

        unique_batch = deduplicator.deduplicate([job_a, job_b])
        assert len(unique_batch) == 1

        saved_count = db_mgr.save_jobs(unique_batch)
        assert saved_count == 1
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# =====================================================================
# Test 21 — Repeated collection does not create duplicates
# =====================================================================
def test_greenhouse_repeated_collection_no_duplicates():
    """Second collection run recognizes previously stored Greenhouse job as duplicate."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        db_mgr = DatabaseManager(db_path=db_path)
        deduplicator = JobDeduplicator(db_manager=db_mgr)

        job = Job(
            source="greenhouse",
            source_job_id="gh-repeat-999",
            job_id="gh-repeat-999",
            title="Python Developer",
            company="CloudCorp",
            url="https://boards.greenhouse.io/cloudcorp/jobs/gh-repeat-999",
            location="Remote",
        )

        # Run 1: save
        assert len(deduplicator.deduplicate([job])) == 1
        db_mgr.save_jobs([job])

        # Run 2: recognized as duplicate
        second_run = deduplicator.deduplicate([job])
        assert len(second_run) == 0
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# =====================================================================
# Test 22 — URL builder and description cleaner
# =====================================================================
def test_build_greenhouse_jobs_url():
    """Verify endpoint URL formatting."""
    assert build_greenhouse_jobs_url("cloudflare") == "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true"
    assert build_greenhouse_jobs_url("cloudflare", content=False) == "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs"


def test_clean_html_description():
    """Verify HTML description unescaping and tag stripping."""
    html_input = "&lt;h3&gt;Overview&lt;/h3&gt;&lt;p&gt;We need a &lt;strong&gt;developer&lt;/strong&gt;.&lt;/p&gt;"
    cleaned = clean_html_description(html_input)
    assert cleaned is not None
    assert "Overview" in cleaned
    assert "We need a developer." in cleaned
    assert "<" not in cleaned
    assert ">" not in cleaned


# =====================================================================
# Phase 6E Test 23 — Multi-company configuration and board lists
# =====================================================================
def test_phase_6e_greenhouse_multi_company():
    """Verify Greenhouse parses comma-separated boards and defaults to 25 jobs per company."""
    settings = Settings(
        _env_file=None,
        GREENHOUSE_ENABLED=True,
        GREENHOUSE_COMPANIES="stripe, rubrik, mongodb, gitlab, elastic",
    )
    assert settings.greenhouse_company_list == ["stripe", "rubrik", "mongodb", "gitlab", "elastic"]
    assert settings.GREENHOUSE_MAX_JOBS_PER_COMPANY == 25
    source = GreenhouseJobSource(settings=settings)
    assert source.companies == ["stripe", "rubrik", "mongodb", "gitlab", "elastic"]
    assert source.max_jobs_per_company == 25
