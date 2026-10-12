"""Unit tests for Lever public job source (Phase 6B.1).

Tests use mock HTTP fixtures and in-memory structures only.
No live external network requests are made during these tests.
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
from app.services.matcher import JobMatcher
from app.sources.lever import (
    LeverJobSource,
    build_lever_postings_url,
    fetch_lever_postings_http,
    normalize_lever_location,
    parse_lever_posting,
)

# Realistic fixture representing a public Lever posting
SAMPLE_LEVER_POSTING_DICT = {
    "id": "4b6e22e5-7e3f-4e0e-9274-123456789abc",
    "text": "Infrastructure Engineer",
    "company": "Acme Technologies",
    "hostedUrl": "https://jobs.lever.co/acme/4b6e22e5-7e3f-4e0e-9274-123456789abc",
    "applyUrl": "https://jobs.lever.co/acme/4b6e22e5-7e3f-4e0e-9274-123456789abc/apply",
    "descriptionPlain": "We are looking for an Infrastructure Engineer proficient in Linux and Python.",
    "description": "<div><p>We are looking for an Infrastructure Engineer proficient in Linux and Python.</p></div>",
    "createdAt": 1704067200000,  # 2024-01-01 00:00:00 UTC
    "categories": {
        "commitment": "Full-time",
        "department": "Engineering",
        "team": "DevOps",
        "location": "Bangalore, India",
        "allLocations": ["Bangalore, India"],
        "level": "Entry Level",
    },
    "workplaceType": "onsite",
    "salaryRange": {
        "min": 800000,
        "max": 1400000,
        "currency": "INR",
        "interval": "per-year-salary",
    },
}


def _get_test_matcher() -> JobMatcher:
    """Helper to instantiate JobMatcher with the actual user profile."""
    profile = get_settings().load_profile()
    return JobMatcher(profile=profile)


# =====================================================================
# Test 1 — Disabled
# =====================================================================
def test_lever_disabled():
    """When LEVER_ENABLED=false, the connector makes no network requests and returns zero jobs."""
    settings = Settings(LEVER_ENABLED=False, LEVER_COMPANIES="sample-company")
    source = LeverJobSource(settings=settings)

    with patch("app.sources.lever.fetch_lever_postings_http") as mock_fetch:
        jobs = asyncio.run(source.collect_jobs(["Software Engineer"], ["Bangalore"]))
        assert jobs == []
        mock_fetch.assert_not_called()


# =====================================================================
# Test 2 — Empty company list
# =====================================================================
def test_lever_empty_company_list():
    """When LEVER_COMPANIES is empty, return zero jobs safely without failing."""
    settings = Settings(LEVER_ENABLED=True, LEVER_COMPANIES="   ")
    source = LeverJobSource(settings=settings)

    with patch("app.sources.lever.fetch_lever_postings_http") as mock_fetch:
        jobs = asyncio.run(source.collect_jobs(["Software Engineer"], ["Bangalore"]))
        assert jobs == []
        mock_fetch.assert_not_called()


# =====================================================================
# Test 3 — Valid posting normalization
# =====================================================================
def test_lever_valid_posting_normalization():
    """A valid mocked Lever posting produces a standardized Job object with expected fields."""
    job = parse_lever_posting(SAMPLE_LEVER_POSTING_DICT, company_id="acme")
    assert job is not None
    assert job.title == "Infrastructure Engineer"
    assert job.company == "Acme Technologies"
    assert job.source == "lever"
    assert job.source_job_id == "4b6e22e5-7e3f-4e0e-9274-123456789abc"
    assert job.job_id == "4b6e22e5-7e3f-4e0e-9274-123456789abc"
    assert job.location == "Bangalore, India"
    assert job.url == "https://jobs.lever.co/acme/4b6e22e5-7e3f-4e0e-9274-123456789abc"
    assert job.description == "We are looking for an Infrastructure Engineer proficient in Linux and Python."
    assert job.easy_apply is False  # Never inferred as Easy Apply
    assert job.date_posted == "2024-01-01"
    assert job.employment_type == "Full-time"
    assert job.experience_required == "Entry Level"
    assert job.salary == "800000 - 1400000 INR (per-year-salary)"
    assert job.extra_metadata["department"] == "Engineering"
    assert job.extra_metadata["lever_company_id"] == "acme"


# =====================================================================
# Test 4 — Stable source ID
# =====================================================================
def test_lever_stable_source_id():
    """Verify Lever posting ID becomes source_job_id and is not randomly generated."""
    posting = {
        "id": "lever-uuid-998877",
        "text": "Backend Developer",
    }
    job = parse_lever_posting(posting, company_id="acme-corp")
    assert job is not None
    assert job.source_job_id == "lever-uuid-998877"
    assert job.job_id == "lever-uuid-998877"


# =====================================================================
# Test 5 — Missing location
# =====================================================================
def test_lever_missing_location():
    """A posting without location produces job.location is None and does NOT become 'India'."""
    posting = {
        "id": "no-loc-123",
        "text": "Python Developer",
        "categories": {},
    }
    job = parse_lever_posting(posting, company_id="acme")
    assert job is not None
    assert job.location is None
    assert job.location != "India"

    # Verify deterministic matcher awards 0 location points for None
    matcher = _get_test_matcher()
    result = matcher.match(job)
    assert result.location_score == 0


# =====================================================================
# Test 6 — Remote location
# =====================================================================
def test_lever_remote_location():
    """A remote Lever posting is normalized correctly and recognized by matcher."""
    matcher = _get_test_matcher()

    # Case A: categories.location specifies Remote
    posting_a = {
        "id": "rem-1",
        "text": "Python Developer",
        "categories": {"location": "Remote"},
    }
    job_a = parse_lever_posting(posting_a, company_id="acme")
    assert job_a is not None
    assert job_a.location == "Remote"
    res_a = matcher.match(job_a)
    assert res_a.location_score == 18  # Remote preference score

    # Case B: workplaceType is 'remote'
    posting_b = {
        "id": "rem-2",
        "text": "Full Stack Developer",
        "categories": {},
        "workplaceType": "remote",
    }
    job_b = parse_lever_posting(posting_b, company_id="acme")
    assert job_b is not None
    assert job_b.location == "Remote"
    res_b = matcher.match(job_b)
    assert res_b.location_score == 18


# =====================================================================
# Test 7 — Bangalore / Bengaluru location
# =====================================================================
def test_lever_bangalore_bengaluru_location():
    """Bangalore and Bengaluru locations are preserved and score 18 points."""
    matcher = _get_test_matcher()

    # Bangalore
    posting_blr = {
        "id": "blr-1",
        "text": "Software Engineer",
        "categories": {"location": "Bangalore, India"},
    }
    job_blr = parse_lever_posting(posting_blr, company_id="acme")
    assert job_blr is not None
    assert job_blr.location == "Bangalore, India"
    assert matcher.match(job_blr).location_score == 18

    # Bengaluru
    posting_beng = {
        "id": "blr-2",
        "text": "Software Engineer",
        "categories": {"location": "Bengaluru, Karnataka, India"},
    }
    job_beng = parse_lever_posting(posting_beng, company_id="acme")
    assert job_beng is not None
    assert job_beng.location == "Bengaluru, Karnataka, India"
    assert matcher.match(job_beng).location_score == 18


# =====================================================================
# Test 8 — Delhi / Noida location
# =====================================================================
def test_lever_delhi_noida_location():
    """Delhi and Noida postings are preserved and receive top priority (20 points)."""
    matcher = _get_test_matcher()

    # Delhi
    posting_delhi = {
        "id": "del-1",
        "text": "Python Developer",
        "categories": {"location": "Delhi, India"},
    }
    job_delhi = parse_lever_posting(posting_delhi, company_id="acme")
    assert job_delhi is not None
    assert job_delhi.location == "Delhi, India"
    assert matcher.match(job_delhi).location_score == 20

    # Noida
    posting_noida = {
        "id": "noid-1",
        "text": "Python Developer",
        "categories": {"location": "Noida, Uttar Pradesh, India"},
    }
    job_noida = parse_lever_posting(posting_noida, company_id="acme")
    assert job_noida is not None
    assert job_noida.location == "Noida, Uttar Pradesh, India"
    assert matcher.match(job_noida).location_score == 20


# =====================================================================
# Test 9 — Mumbai location
# =====================================================================
def test_lever_mumbai_location():
    """Mumbai must remain Mumbai, must not become the generic India fallback, and scores 0."""
    posting_mum = {
        "id": "mum-1",
        "text": "Software Engineer",
        "categories": {"location": "Mumbai, India"},
    }
    job_mum = parse_lever_posting(posting_mum, company_id="acme")
    assert job_mum is not None
    assert job_mum.location == "Mumbai, India"
    assert job_mum.location != "India"

    matcher = _get_test_matcher()
    res = matcher.match(job_mum)
    assert res.location_score == 0  # Mumbai is not in preferred locations, receives 0 (not 12)


# =====================================================================
# Test 10 — Malformed posting handling
# =====================================================================
def test_lever_malformed_posting():
    """Malformed or incomplete Lever JSON entries are safely skipped."""
    assert parse_lever_posting({}, company_id="acme") is None
    assert parse_lever_posting({"text": "No ID"}, company_id="acme") is None
    assert parse_lever_posting({"id": "no-title"}, company_id="acme") is None
    assert parse_lever_posting("not a dict", company_id="acme") is None  # type: ignore
    assert parse_lever_posting(None, company_id="acme") is None  # type: ignore


# =====================================================================
# Test 11 — HTTP 403 handling
# =====================================================================
def test_lever_http_403():
    """HTTP 403 Forbidden returns empty list safely without raising unhandled exceptions."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.lever.co/v0/postings/restricted?mode=json",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )
        postings = fetch_lever_postings_http("restricted")
        assert postings == []


# =====================================================================
# Test 12 — HTTP 429 handling
# =====================================================================
def test_lever_http_429():
    """HTTP 429 Too Many Requests returns empty list safely without looping or crashing."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.lever.co/v0/postings/rate-limited?mode=json",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None,
        )
        postings = fetch_lever_postings_http("rate-limited")
        assert postings == []


# =====================================================================
# Test 13 — Multiple companies resilience
# =====================================================================
def test_lever_multiple_companies():
    """Failure in one configured company does not prevent processing of subsequent companies."""
    settings = Settings(
        LEVER_ENABLED=True,
        LEVER_COMPANIES="company-one, company-two",
        LEVER_REQUEST_DELAY_SEC=0.0,
    )
    source = LeverJobSource(settings=settings)

    def mock_fetch(company, *args, **kwargs):
        if company == "company-one":
            return []  # Simulate failure or restricted access
        if company == "company-two":
            return [
                {
                    "id": "comp2-job-1",
                    "text": "Python Developer",
                    "company": "Company Two",
                    "categories": {"location": "Remote"},
                }
            ]
        return []

    with patch("app.sources.lever.fetch_lever_postings_http", side_effect=mock_fetch):
        jobs = asyncio.run(source.collect_jobs(["Python Developer"], ["Remote"]))
        assert len(jobs) == 1
        assert jobs[0].company == "Company Two"
        assert jobs[0].source_job_id == "comp2-job-1"


# =====================================================================
# Test 14 — Max jobs per company
# =====================================================================
def test_lever_max_jobs_per_company():
    """Verify LEVER_MAX_JOBS_PER_COMPANY limits the collected jobs per company."""
    settings = Settings(
        LEVER_ENABLED=True,
        LEVER_COMPANIES="large-corp",
        LEVER_MAX_JOBS_PER_COMPANY=3,
        LEVER_REQUEST_DELAY_SEC=0.0,
    )
    source = LeverJobSource(settings=settings)

    mock_postings = [
        {"id": f"post-{i}", "text": f"Engineer {i}", "company": "Large Corp"}
        for i in range(10)
    ]

    with patch("app.sources.lever.fetch_lever_postings_http", return_value=mock_postings):
        jobs = asyncio.run(source.collect_jobs(["Engineer"], ["Remote"]))
        assert len(jobs) == 3


# =====================================================================
# Test 15 — Database deduplication
# =====================================================================
def test_lever_database_deduplication():
    """The same Lever posting collected twice is deduplicated based on source + source_job_id."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        db_mgr = DatabaseManager(db_path=db_path)
        deduplicator = JobDeduplicator(db_manager=db_mgr)

        posting_a = Job(
            source="lever",
            source_job_id="lever-unique-1234",
            job_id="lever-unique-1234",
            title="Backend Engineer",
            company="LeverTech",
            url="https://jobs.lever.co/levertech/lever-unique-1234",
            location="Bangalore",
        )
        posting_b = Job(
            source="lever",
            source_job_id="lever-unique-1234",
            job_id="lever-unique-1234",
            title="Backend Engineer",
            company="LeverTech",
            url="https://jobs.lever.co/levertech/lever-unique-1234",
            location="Bangalore",
        )

        # 1. Batch deduplication: two identical postings in one run become 1
        batch_unique = deduplicator.deduplicate([posting_a, posting_b])
        assert len(batch_unique) == 1

        # 2. Persist to database
        saved_count = db_mgr.save_jobs(batch_unique)
        assert saved_count == 1

        # 3. Historical deduplication in subsequent run: posting seen previously is dropped
        next_run_unique = deduplicator.deduplicate([posting_a])
        assert len(next_run_unique) == 0

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# =====================================================================
# Test 16 — Multi-location handling
# =====================================================================
def test_lever_multi_location():
    """Multi-location Lever postings preserve all locations in semicolon-separated string."""
    posting = {
        "id": "multi-loc-1",
        "text": "Full Stack Engineer",
        "categories": {
            "location": "Bangalore, India",
            "allLocations": ["Bangalore, India", "Remote", "San Francisco, CA"],
        },
    }
    job = parse_lever_posting(posting, company_id="acme")
    assert job is not None
    assert job.location == "Bangalore, India; Remote; San Francisco, CA"

    matcher = _get_test_matcher()
    res = matcher.match(job)
    # Bangalore is recognized with 18 points
    assert res.location_score == 18


# =====================================================================
# Phase 6B.3 Test 17 — Configurable collection limit
# =====================================================================
def test_configurable_collection_limit():
    """Verify LEVER_MAX_JOBS_PER_COMPANY is configurable via settings."""
    settings = Settings(
        LEVER_ENABLED=True,
        LEVER_COMPANIES="company-a",
        LEVER_MAX_JOBS_PER_COMPANY=25,
    )
    source = LeverJobSource(settings=settings)
    assert source.max_jobs_per_company == 25


# =====================================================================
# Phase 6B.3 Test 18 — Collection stops at configured limit
# =====================================================================
def test_collection_stops_at_configured_limit():
    """Verify collection stops precisely at the configured limit."""
    settings = Settings(
        LEVER_ENABLED=True,
        LEVER_COMPANIES="company-a",
        LEVER_MAX_JOBS_PER_COMPANY=7,
        LEVER_REQUEST_DELAY_SEC=0.0,
    )
    source = LeverJobSource(settings=settings)

    mock_postings = [
        {"id": f"job-{i}", "text": f"Software Engineer {i}", "company": "Company A"}
        for i in range(30)
    ]

    with patch("app.sources.lever.fetch_lever_postings_http", return_value=mock_postings):
        jobs = asyncio.run(source.collect_jobs(["Software Engineer"], ["Remote"]))
        assert len(jobs) == 7


# =====================================================================
# Phase 6B.3 Test 19 — Jobs beyond the limit are not collected
# =====================================================================
def test_jobs_beyond_limit_are_not_collected():
    """Verify items beyond the configured batch limit are not parsed or included."""
    settings = Settings(
        LEVER_ENABLED=True,
        LEVER_COMPANIES="company-a",
        LEVER_MAX_JOBS_PER_COMPANY=3,
        LEVER_REQUEST_DELAY_SEC=0.0,
    )
    source = LeverJobSource(settings=settings)

    mock_postings = [
        {"id": f"job-id-{i}", "text": f"Role {i}", "company": "Company A"}
        for i in range(10)
    ]

    with patch("app.sources.lever.fetch_lever_postings_http", return_value=mock_postings):
        jobs = asyncio.run(source.collect_jobs(["Role"], ["Remote"]))
        collected_ids = {j.source_job_id for j in jobs}
        assert collected_ids == {"job-id-0", "job-id-1", "job-id-2"}
        for uncollected_idx in range(3, 10):
            assert f"job-id-uncollected-{uncollected_idx}" not in collected_ids


# =====================================================================
# Phase 6B.3 Test 20 — Malformed postings do not crash the collector
# =====================================================================
def test_malformed_postings_do_not_crash_collector():
    """Verify collector gracefully tolerates mixed malformed postings without crashing."""
    settings = Settings(
        LEVER_ENABLED=True,
        LEVER_COMPANIES="company-mixed",
        LEVER_MAX_JOBS_PER_COMPANY=10,
        LEVER_REQUEST_DELAY_SEC=0.0,
    )
    source = LeverJobSource(settings=settings)

    mixed_postings = [
        {"id": "valid-1", "text": "Backend Engineer", "company": "Mixed Corp"},
        None,
        {},
        "not-a-dict",
        {"id": "no-title"},
        {"text": "no-id"},
        {"id": "valid-2", "text": "Frontend Engineer", "company": "Mixed Corp"},
    ]

    with patch("app.sources.lever.fetch_lever_postings_http", return_value=mixed_postings):
        jobs = asyncio.run(source.collect_jobs(["Engineer"], ["Remote"]))
        assert len(jobs) == 2
        assert [j.source_job_id for j in jobs] == ["valid-1", "valid-2"]
        assert source.diagnostics["valid_normalized"] == 2
        assert source.diagnostics["invalid_skipped"] == 5


# =====================================================================
# Phase 6B.3 Test 21 — Existing matcher/filter behavior remains intact
# =====================================================================
def test_existing_matcher_filter_behavior_remains_intact():
    """Verify filter and matcher correctly score and filter Lever-originated jobs."""
    from app.services.filter import JobFilter

    matcher = _get_test_matcher()
    profile = get_settings().load_profile()
    job_filter = JobFilter(profile=profile)

    matching_lever_job = Job(
        source="lever",
        source_job_id="matching-1",
        job_id="matching-1",
        title="Software Engineer",
        company="Acme Lever",
        location="Bangalore",
        url="https://jobs.lever.co/acme/matching-1",
        description="Looking for Python, FastAPI, and PostgreSQL developer.",
    )

    assert job_filter.is_match(matching_lever_job) is True
    res = matcher.match(matching_lever_job)
    assert res.role_score == 40
    assert res.location_score == 18
    assert res.skills_score > 0
    assert res.category in ("Strong", "Good", "Excellent")

    unrelated_lever_job = Job(
        source="lever",
        source_job_id="unrelated-1",
        job_id="unrelated-1",
        title="Executive Office Assistant",
        company="Acme Lever",
        location="Paris, France",
        url="https://jobs.lever.co/acme/unrelated-1",
    )
    assert job_filter.is_match(unrelated_lever_job) is False


# =====================================================================
# Phase 6B.3 Test 22 — Lever diagnostics tracking and reporting
# =====================================================================
def test_lever_diagnostics_tracking_and_reporting():
    """Verify LeverJobSource accurately tracks and formats collection diagnostics."""
    settings = Settings(
        LEVER_ENABLED=True,
        LEVER_COMPANIES="corp-diag",
        LEVER_MAX_JOBS_PER_COMPANY=5,
        LEVER_REQUEST_DELAY_SEC=0.0,
    )
    source = LeverJobSource(settings=settings)

    mock_postings = [
        {"id": f"d-{i}", "text": "Software Engineer - Team A", "categories": {"location": "London, UK"}}
        for i in range(15)
    ]

    with patch("app.sources.lever.fetch_lever_postings_http", return_value=mock_postings):
        jobs = asyncio.run(source.collect_jobs(["Software Engineer"], ["London"]))
        assert len(jobs) == 5

        diag = source.diagnostics
        assert diag["available_postings"] == 15
        assert diag["collection_limit"] == 5
        assert diag["collected"] == 5
        assert diag["valid_normalized"] == 5
        assert diag["invalid_skipped"] == 0
        assert "London, UK" in diag["locations"]

        report = source.format_diagnostics(filtered_jobs=jobs, scored_jobs=jobs)
        assert "Available postings: 15" in report
        assert "Collection limit: 5" in report
        assert "Collected: 5" in report
        assert "Valid normalized jobs: 5" in report
        assert "Location distribution:" in report
        assert "Role distribution:" in report


# =====================================================================
# Phase 6B.3 Test 23 — URL builder optional limit
# =====================================================================
def test_build_lever_postings_url_optional_limit():
    """Verify URL construction with and without limit."""
    assert build_lever_postings_url("test-co") == "https://api.lever.co/v0/postings/test-co?mode=json"
    assert build_lever_postings_url("test-co", limit=25) == "https://api.lever.co/v0/postings/test-co?mode=json&limit=25"
    assert build_lever_postings_url("test-co", limit=None) == "https://api.lever.co/v0/postings/test-co?mode=json"


# =====================================================================
# Phase 6E Test 24 — Multi-company configuration and default limits
# =====================================================================
def test_phase_6e_lever_multi_company_and_default_limit():
    """Verify Lever parses comma-separated companies and defaults to 25 jobs per company."""
    settings = Settings(
        _env_file=None,
        LEVER_ENABLED=True,
        LEVER_COMPANIES="paytm, meesho , jumpcloud,fampay ,epifi",
    )
    assert settings.lever_company_list == ["paytm", "meesho", "jumpcloud", "fampay", "epifi"]
    assert settings.LEVER_MAX_JOBS_PER_COMPANY == 25
    source = LeverJobSource(settings=settings)
    assert source.companies == ["paytm", "meesho", "jumpcloud", "fampay", "epifi"]
    assert source.max_jobs_per_company == 25

