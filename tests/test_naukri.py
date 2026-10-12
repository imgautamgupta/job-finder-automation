"""Unit tests for Naukri job collection and normalization (Phase 6A).

Tests use mock HTML fixtures and in-memory structures only.
No live external network requests are made during these tests.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.config.settings import Settings
from app.models.job import Job
from app.services.deduplicator import JobDeduplicator
from app.sources.naukri import (
    NaukriJobSource,
    build_naukri_search_url,
    extract_stable_job_id,
    parse_naukri_html_snippet,
    parse_naukri_job_card_dict,
)

# Realistic HTML snippet representing Naukri job card fixtures
SAMPLE_NAUKRI_HTML_CARD = """
<div class="srp-jobtuple-wrapper" data-job-id="250424009876">
    <div class="cust-job-tuple layout-wrapper">
        <div class="row1">
            <a class="title" href="/job-listings-python-backend-developer-acme-corp-delhi-0-to-2-years-250424009876?src=jobsearchDesk">
                Python Backend Developer
            </a>
        </div>
        <div class="row2">
            <a class="comp-name" href="https://www.naukri.com/acme-corp-jobs">Acme Corp</a>
            <span class="rating"><i class="star"></i>3.9</span>
        </div>
        <div class="row3">
            <span class="expwdth">0-2 Yrs</span>
            <span class="sal">3-6 Lacs PA</span>
            <span class="locWdth">Delhi / New Delhi, India</span>
        </div>
        <div class="row4">
            <div class="job-desc">Looking for Python developer proficient in FastAPI, REST APIs, PostgreSQL.</div>
        </div>
        <div class="row5">
            <span class="job-post-day">1 Day Ago</span>
            <button class="easy-apply-btn easy-apply">Easy Apply</button>
        </div>
    </div>
</div>
"""

SAMPLE_EXTERNAL_APPLY_CARD = """
<div class="srp-jobtuple-wrapper" data-job-id="120324001122">
    <div class="row1">
        <a class="title" href="https://www.naukri.com/job-listings-software-engineer-beta-ltd-bangalore-120324001122">
            Software Engineer
        </a>
    </div>
    <div class="row2">
        <a class="comp-name">Beta Ltd</a>
    </div>
    <div class="row3">
        <span class="locWdth">Bangalore, Karnataka</span>
    </div>
    <div class="row5">
        <span class="apply-type">Apply on company site</span>
    </div>
</div>
"""

SAMPLE_MINIMAL_CARD = """
<div class="srp-jobtuple-wrapper">
    <div class="row1">
        <a class="title" href="/job-listings-minimal-dev-tech-noida-998877665544">
            Web Developer Intern
        </a>
    </div>
    <div class="row2">
        <a class="subTitle">Gamma Systems</a>
    </div>
</div>
"""


# ==============================================================================
# 1. Listing -> Job Model Conversion
# ==============================================================================

def test_naukri_listing_to_job_conversion():
    """Test 1: Convert realistic Naukri HTML card into a validated Job model."""
    jobs = parse_naukri_html_snippet(SAMPLE_NAUKRI_HTML_CARD)
    assert len(jobs) == 1
    job = jobs[0]

    assert isinstance(job, Job)
    assert job.title == "Python Backend Developer"
    assert job.company == "Acme Corp"
    assert "Delhi" in job.location
    assert job.source == "naukri"
    assert job.experience_required == "0-2 Yrs"
    assert job.salary == "3-6 Lacs PA"
    assert job.date_posted == "1 Day Ago"
    assert "FastAPI" in job.description


# ==============================================================================
# 2. Required Fields Populated
# ==============================================================================

def test_required_fields_populated_when_available():
    """Test 2: Ensure all core required Job fields are cleanly populated."""
    jobs = parse_naukri_html_snippet(SAMPLE_NAUKRI_HTML_CARD)
    job = jobs[0]

    assert job.title
    assert job.company
    assert job.location
    assert job.url.startswith("https://www.naukri.com")
    assert job.source == "naukri"
    assert job.date_found is not None


# ==============================================================================
# 3. Missing Optional Fields Handled Safely
# ==============================================================================

def test_missing_optional_fields_handled_safely():
    """Test 3: Missing optional attributes (salary, description, exp) default safely."""
    jobs = parse_naukri_html_snippet(SAMPLE_MINIMAL_CARD)
    assert len(jobs) == 1
    job = jobs[0]

    assert job.title == "Web Developer Intern"
    assert job.company == "Gamma Systems"
    assert job.salary is None
    assert job.description is None
    assert job.experience_required is None
    assert job.location is None  # Must remain None when omitted, never defaulted to India


# ==============================================================================
# 4. Source is Always "naukri"
# ==============================================================================

def test_source_is_always_naukri():
    """Test 4: Source is explicitly set to 'naukri' across all parser outputs."""
    jobs_sample = parse_naukri_html_snippet(SAMPLE_NAUKRI_HTML_CARD)
    assert jobs_sample[0].source == "naukri"

    source = NaukriJobSource()
    assert source.source_name == "naukri"


# ==============================================================================
# 5. URL is Preserved and Canonical
# ==============================================================================

def test_url_is_preserved_correctly():
    """Test 5: Relative links are prefixed with the base domain and tracking stripped."""
    jobs = parse_naukri_html_snippet(SAMPLE_NAUKRI_HTML_CARD)
    job = jobs[0]

    assert job.url.startswith("https://www.naukri.com/job-listings-python-backend-developer")
    # Tracking parameter 'src' should be stripped by canonicalization
    assert "src=jobsearchDesk" not in job.url


# ==============================================================================
# 6. Stable Source Job ID Extracted
# ==============================================================================

def test_stable_source_job_id_extracted():
    """Test 6: Extract stable numerical job IDs from data attributes or URL slugs."""
    jobs = parse_naukri_html_snippet(SAMPLE_NAUKRI_HTML_CARD)
    assert jobs[0].source_job_id == "250424009876"
    assert jobs[0].job_id == "250424009876"

    # From URL when attribute is missing
    extracted = extract_stable_job_id(
        data_job_id=None,
        url="https://www.naukri.com/job-listings-developer-120524005566?ref=search",
    )
    assert extracted == "120524005566"

    # When genuinely missing, returns None without crashing
    missing = extract_stable_job_id(data_job_id=None, url="https://example.com/job")
    assert missing is None


# ==============================================================================
# 7. Easy Apply is Never Guessed
# ==============================================================================

def test_easy_apply_never_guessed():
    """Test 7: Easy Apply is True only when explicit, False when external/unknown."""
    # Explicit Easy Apply
    jobs_easy = parse_naukri_html_snippet(SAMPLE_NAUKRI_HTML_CARD)
    assert jobs_easy[0].easy_apply is True

    # Explicit external apply
    jobs_ext = parse_naukri_html_snippet(SAMPLE_EXTERNAL_APPLY_CARD)
    assert jobs_ext[0].easy_apply is False

    # Omitted/unknown apply indicator -> False (never assume True)
    jobs_min = parse_naukri_html_snippet(SAMPLE_MINIMAL_CARD)
    assert jobs_min[0].easy_apply is False


# ==============================================================================
# 8. Deduplication Compatibility
# ==============================================================================

def test_duplicate_listings_compatible_with_deduplicator():
    """Test 8: Naukri listings with duplicate IDs are properly deduplicated."""
    job1 = parse_naukri_html_snippet(SAMPLE_NAUKRI_HTML_CARD)[0]
    # Simulate a second identical job
    job2 = parse_naukri_html_snippet(SAMPLE_NAUKRI_HTML_CARD)[0]

    mock_db = MagicMock()
    mock_db.job_exists.return_value = False
    mock_db.get_job_by_source_id.return_value = None
    mock_db.get_job_by_url.return_value = None
    mock_db.get_job_by_fingerprint.return_value = None

    dedup = JobDeduplicator(db_manager=mock_db)
    result = dedup.deduplicate([job1, job2])

    assert len(result) == 1
    assert result[0].source_job_id == "250424009876"


# ==============================================================================
# 9. Pagination and Search URL Construction
# ==============================================================================

def test_pagination_and_url_builder():
    """Test 9: Search URLs and pagination parameters are cleanly constructed."""
    url1 = build_naukri_search_url(role="Python Developer", location="Delhi", page_no=1)
    assert url1 == "https://www.naukri.com/python-developer-jobs-in-delhi"

    url2 = build_naukri_search_url(role="Backend Developer", location="Bangalore", page_no=2)
    assert url2 == "https://www.naukri.com/backend-developer-jobs-in-bangalore-2"

    url_remote = build_naukri_search_url(role="ML Engineer", location="Remote", page_no=1)
    assert url_remote == "https://www.naukri.com/ml-engineer-jobs"


# ==============================================================================
# 10. Collection Failure Does Not Crash
# ==============================================================================

def test_collection_failure_does_not_crash_pipeline():
    """Test 10: Browser or navigation errors are safely caught and return empty list."""
    import asyncio
    source = NaukriJobSource()

    # Simulate an error inside playwright navigation
    with patch("playwright.async_api.async_playwright") as mock_pw:
        mock_pw.side_effect = RuntimeError("Simulated browser failure")

        jobs = asyncio.run(
            source.collect_jobs(
                roles=["Python Developer"],
                locations=["Delhi"],
                max_results=5,
            )
        )
        assert isinstance(jobs, list)
        assert len(jobs) == 0


# ==============================================================================
# 11. No Fake Jobs Generated
# ==============================================================================

def test_no_fake_jobs_generated_on_empty_content():
    """Test 11: Empty, malformed, or 403 content yields 0 jobs, never fabricated data."""
    empty_jobs = parse_naukri_html_snippet("")
    assert empty_jobs == []

    denied_html = "<html><head><title>Access Denied</title></head><body><h1>403 Forbidden</h1></body></html>"
    denied_jobs = parse_naukri_html_snippet(denied_html)
    assert denied_jobs == []

    malformed_jobs = parse_naukri_html_snippet("<div>Invalid content with no job tuples</div>")
    assert malformed_jobs == []


# ==============================================================================
# 12. Configured Limits Respected
# ==============================================================================

def test_configured_limits_respected():
    """Test 12: Source respects custom NAUKRI_MAX_JOBS and NAUKRI_MAX_PAGES."""
    custom_settings = Settings(
        NAUKRI_MAX_JOBS=3,
        NAUKRI_MAX_PAGES=1,
        NAUKRI_REQUEST_DELAY_SEC=0.0,
    )
    source = NaukriJobSource(settings=custom_settings)
    assert source.max_jobs == 3
    assert source.max_pages == 1
    assert source.request_delay_sec == 0.0


def test_missing_naukri_location_remains_none_and_not_india():
    """Verify that a listing dictionary with omitted location does not default to India."""
    raw_card = {
        "title": "Software Engineer",
        "company": "Tech Corp",
        "url": "/job-listings-123456",
        # location omitted
    }
    job = parse_naukri_job_card_dict(raw_card)
    assert job is not None
    assert job.location is None

