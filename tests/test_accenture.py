"""Unit and regression tests for Accenture Careers job source connector and Excel export."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error
import pytest
import openpyxl

from app.config.settings import Settings
from app.models.job import Job, JobStatus
from app.models.profile import JobProfile
from app.services.excel_exporter import ExcelExporter, ACCENTURE_COLUMNS
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher
from app.sources.accenture import (
    AccentureJobSource,
    build_accenture_job_url,
    clean_html_text,
    determine_accenture_eligibility,
    extract_accenture_job_id,
    fetch_accenture_jobs_http,
    normalize_accenture_location,
    parse_accenture_job,
)


@pytest.fixture
def sample_accenture_raw():
    return {
        "country": "India",
        "updateDate": "2026-10-12T04:10:02.421-07:00",
        "jobScheduleDescription": "Full time",
        "employeeType": "Full-time",
        "title": "Python Developer",
        "jobDetailUrl": "https://www.accenture.com/{0}/careers/jobdetails?id=ATCI-12345-S67890_en&title=Python+Developer",
        "qualificationClean": "15 years full time education",
        "jobDescriptionClean": "Build Python backend APIs with FastAPI and PostgreSQL. 0-2 years experience required. Freshers eligible.",
        "postedDateText": "Posted within last 24 hours",
        "requisitionId": "ATCI-12345-S67890",
        "guid": "ATCI-12345-S67890_en",
        "location": ["Bengaluru"],
        "feedCity": "Bengaluru",
        "yearsOfExperience": "Experience: 0-2 years",
        "mustHaveSkills": ["Python", "FastAPI"],
        "goodToHaveSkills": ["PostgreSQL", "Git"],
        "careerLevel": "Associate",
    }


@pytest.fixture
def senior_accenture_raw():
    return {
        "country": "India",
        "updateDate": "2026-10-12T04:10:02.421-07:00",
        "employeeType": "Full-time",
        "title": "Senior Software Architect",
        "jobDetailUrl": "https://www.accenture.com/{0}/careers/jobdetails?id=ATCI-99999-S99999_en&title=Senior+Software+Architect",
        "jobDescriptionClean": "Lead architecture teams. Minimum 10 years of experience required. 10+ years experience in distributed systems.",
        "requisitionId": "ATCI-99999-S99999",
        "location": ["Bengaluru"],
        "yearsOfExperience": "Experience: 10-12 years",
        "mustHaveSkills": ["System Design"],
    }


# =========================================================================
# 1. Job ID Extraction Tests
# =========================================================================

def test_extract_job_id_from_requisition_id(sample_accenture_raw):
    """Test extracting official requisitionId."""
    job_id, is_avail = extract_accenture_job_id(sample_accenture_raw)
    assert job_id == "ATCI-12345-S67890"
    assert is_avail is True


def test_extract_job_id_from_guid():
    """Test extracting base Job ID from guid when requisitionId is absent."""
    item = {"guid": "ATCI-55555-S11111_en"}
    job_id, is_avail = extract_accenture_job_id(item)
    assert job_id == "ATCI-55555-S11111"
    assert is_avail is True


def test_extract_job_id_from_url_param():
    """Test extracting Job ID from URL parameters."""
    item = {"jobDetailUrl": "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-77777-S22222_en"}
    job_id, is_avail = extract_accenture_job_id(item)
    assert job_id == "ATCI-77777-S22222"
    assert is_avail is True


def test_extract_job_id_missing_handling():
    """Test missing Job ID preserves listing but returns None without inventing IDs."""
    item = {"title": "Developer", "location": ["Noida"]}
    job_id, is_avail = extract_accenture_job_id(item)
    assert job_id is None
    assert is_avail is False


# =========================================================================
# 2. Normalization & Helper Tests
# =========================================================================

def test_build_accenture_job_url(sample_accenture_raw):
    """Test replacing {0} with in-en in direct job URL."""
    url = build_accenture_job_url(sample_accenture_raw, country_site="in-en")
    assert url == "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-12345-S67890_en&title=Python+Developer"


def test_build_accenture_job_url_relative():
    """Test prepending accenture domain to relative URL."""
    item = {"jobDetailUrl": "/in-en/careers/jobdetails?id=123"}
    url = build_accenture_job_url(item)
    assert url == "https://www.accenture.com/in-en/careers/jobdetails?id=123"


def test_normalize_accenture_location():
    """Test location normalization with city list and country append."""
    assert normalize_accenture_location(["Bengaluru"], country="India") == "Bengaluru, India"
    assert normalize_accenture_location(["New Delhi", "Noida"], country="India") == "New Delhi, Noida, India"
    assert normalize_accenture_location("Noida, India", country="India") == "Noida, India"
    assert normalize_accenture_location(None) is None
    assert normalize_accenture_location("") is None
    assert normalize_accenture_location("Unknown") is None


def test_clean_html_text():
    """Test stripping tags, unescaping HTML, and preserving text."""
    raw = "<p>Role: <b>Python Developer</b></p><br/><div>Build &amp; maintain APIs.</div>"
    cleaned = clean_html_text(raw)
    assert "Python Developer" in cleaned
    assert "Build & maintain APIs." in cleaned
    assert "<" not in cleaned


# =========================================================================
# 3. Eligibility Determination Tests
# =========================================================================

def test_determine_eligibility_fresher():
    """Test 0-2 years, fresher, entry level are marked Eligible."""
    assert determine_accenture_eligibility("0-2 years") == "Eligible"
    assert determine_accenture_eligibility("Experience: 0-1 years") == "Eligible"
    assert determine_accenture_eligibility(None, description_text="Looking for freshers and graduates", job_title="Associate Developer") == "Eligible"


def test_determine_eligibility_senior():
    """Test 5+ years, 10-12 years, senior roles are marked Ineligible."""
    assert determine_accenture_eligibility("5-10 years") == "Ineligible"
    assert determine_accenture_eligibility("Experience: 10-12 years") == "Ineligible"
    assert determine_accenture_eligibility(None, job_title="Senior Principal Consultant") == "Ineligible"
    assert determine_accenture_eligibility(None, description_text="Minimum 5 years of experience is required") == "Ineligible"


def test_determine_eligibility_needs_review():
    """Test ambiguous or unspecified experience returns Needs Review, not assumed fresher."""
    # A generic title like "Engineer" without experience specification must NOT be assumed fresher-friendly
    assert determine_accenture_eligibility(None, description_text="Responsible for system operations.", job_title="Systems Engineer") == "Needs Review"
    assert determine_accenture_eligibility("", description_text="General software engineering", job_title="Software Engineer") == "Needs Review"


# =========================================================================
# 4. Job Parsing Tests
# =========================================================================

def test_parse_accenture_job_valid(sample_accenture_raw):
    """Test full parsing of valid raw job dictionary."""
    job = parse_accenture_job(sample_accenture_raw)
    assert job is not None
    assert job.source == "accenture"
    assert job.source_job_id == "ATCI-12345-S67890"
    assert job.job_id == "ATCI-12345-S67890"
    assert job.title == "Python Developer"
    assert job.company == "Accenture"
    assert "Bengaluru" in job.location
    assert "https://www.accenture.com/in-en/careers/jobdetails" in job.url
    assert job.easy_apply is False
    assert job.experience_required == "0-2 years"
    assert job.extra_metadata["job_id_available"] is True
    assert job.extra_metadata["eligibility"] == "Eligible"


def test_parse_accenture_job_missing_id():
    """Test parsing job when Job ID is absent preserves listing and flags UNAVAILABLE."""
    raw = {
        "title": "Web Developer",
        "jobDetailUrl": "https://www.accenture.com/in-en/careers/jobdetails?title=Web+Developer",
        "location": ["Noida"],
        "yearsOfExperience": "Experience: 0-2 years",
    }
    job = parse_accenture_job(raw)
    assert job is not None
    assert job.source_job_id is None
    assert job.job_id is None
    assert job.extra_metadata["job_id_available"] is False
    assert job.extra_metadata["official_job_id"] == "UNAVAILABLE"


def test_parse_accenture_job_invalid_records():
    """Test corrupt or invalid records return None safely."""
    assert parse_accenture_job({}) is None
    assert parse_accenture_job(None) is None
    assert parse_accenture_job({"location": ["Bengaluru"]}) is None  # missing title
    assert parse_accenture_job({"title": "   "}) is None


# =========================================================================
import asyncio

# =========================================================================
# 5. Connector Lifecycle & Collection Tests
# =========================================================================

def test_collect_jobs_disabled():
    """Test collect_jobs returns empty list when disabled."""
    source = AccentureJobSource(is_enabled=False)
    jobs = asyncio.run(source.collect_jobs(roles=["Python Developer"], locations=["Bengaluru"]))
    assert jobs == []
    assert source.last_status == "DISABLED"


def test_collect_jobs_pagination_and_deduplication(sample_accenture_raw):
    """Test collection across pages and deduplication across multiple queries."""
    job2 = dict(sample_accenture_raw)
    job2["requisitionId"] = "ATCI-22222-S33333"
    job2["title"] = "Backend Engineer"

    # Mock response
    mock_resp = {
        "totalHits": {"total": 2},
        "data": [sample_accenture_raw, job2],
    }

    settings = Settings(
        ACCENTURE_ENABLED=True,
        ACCENTURE_REQUEST_DELAY_SEC=0.0,
        ACCENTURE_MAX_JOBS=10,
    )
    source = AccentureJobSource(is_enabled=True, settings=settings)

    with patch("app.sources.accenture.fetch_accenture_jobs_http", return_value=mock_resp):
        jobs = asyncio.run(
            source.collect_jobs(
                roles=["Python Developer", "Backend Engineer"],
                locations=["Bengaluru"],
                max_results=10,
            )
        )

    # Both unique jobs collected; subsequent duplicate queries deduplicated
    assert len(jobs) == 2
    assert source.last_status == "COMPLETED"
    assert source.diagnostics["valid_normalized"] == 2


def test_collect_jobs_empty_response():
    """Test empty API response handled gracefully."""
    settings = Settings(ACCENTURE_ENABLED=True, ACCENTURE_REQUEST_DELAY_SEC=0.0)
    source = AccentureJobSource(is_enabled=True, settings=settings)

    with patch("app.sources.accenture.fetch_accenture_jobs_http", return_value={"totalHits": {"total": 0}, "data": []}):
        jobs = asyncio.run(source.collect_jobs(roles=["Python Developer"], locations=["Bengaluru"]))

    assert jobs == []
    assert source.last_status == "COMPLETED"


def test_collect_jobs_http_403_blocked():
    """Test HTTP 403 sets status BLOCKED and stops safely."""
    settings = Settings(ACCENTURE_ENABLED=True, ACCENTURE_REQUEST_DELAY_SEC=0.0)
    source = AccentureJobSource(is_enabled=True, settings=settings)

    mock_err = urllib.error.HTTPError(
        url="https://www.accenture.com/api/findjobs",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=None,
    )

    with patch("app.sources.accenture.fetch_accenture_jobs_http", side_effect=mock_err):
        jobs = asyncio.run(source.collect_jobs(roles=["Python Developer"], locations=["Bengaluru"]))

    assert jobs == []
    assert source.last_status == "BLOCKED"
    assert "access restricted" in (source.last_error or "").lower()


def test_collect_jobs_timeout_handled_gracefully():
    """Test network timeout is handled without crashing."""
    settings = Settings(ACCENTURE_ENABLED=True, ACCENTURE_REQUEST_DELAY_SEC=0.0)
    source = AccentureJobSource(is_enabled=True, settings=settings)

    with patch("app.sources.accenture.fetch_accenture_jobs_http", side_effect=TimeoutError("Request timed out")):
        jobs = asyncio.run(source.collect_jobs(roles=["Python Developer"], locations=["Bengaluru"]))

    assert jobs == []
    assert source.last_status == "COMPLETED"


# =========================================================================
# 6. Profile Matching & Filtering Tests
# =========================================================================

def test_accenture_profile_matching(sample_accenture_raw, senior_accenture_raw):
    """Test Accenture jobs against real profile preferences."""
    profile = JobProfile(
        target_roles=["Python Developer", "Software Engineer"],
        preferred_locations=["Bengaluru", "Delhi", "Noida", "Ahmedabad", "Remote"],
        skills=["Python", "FastAPI", "PostgreSQL", "Git"],
        negative_keywords=["Senior", "Lead", "10+ years", "5+ years"],
    )
    job_filter = JobFilter(profile=profile)
    matcher = JobMatcher(profile=profile)

    # 1. Junior Python Developer in Bengaluru -> Match
    fresher_job = parse_accenture_job(sample_accenture_raw)
    assert job_filter.is_match(fresher_job) is True
    match_res = matcher.match(fresher_job)
    assert match_res.score >= 80
    assert "Python" in match_res.matched_skills

    # 2. Senior Software Architect -> Excluded by negative keywords & experience
    senior_job = parse_accenture_job(senior_accenture_raw)
    assert job_filter.is_match(senior_job) is False

    # 3. Unrelated location (e.g. Hyderabad / Mumbai / Pune / Gurugram) -> Excluded
    hyderabad_raw = dict(sample_accenture_raw)
    hyderabad_raw["location"] = ["Hyderabad"]
    hyderabad_job = parse_accenture_job(hyderabad_raw)
    assert job_filter.is_match(hyderabad_job) is False


# =========================================================================
# 7. Excel Output Tests
# =========================================================================

def test_excel_export_accenture_worksheet(tmp_path, sample_accenture_raw):
    """Test Excel export produces dedicated Accenture worksheet with required columns and clickable links."""
    job = parse_accenture_job(sample_accenture_raw)
    job.match_score = 92
    job.matched_skills = ["Python", "FastAPI"]
    job.experience_match = True

    exporter = ExcelExporter(exports_dir=tmp_path)
    file_path = exporter.export([job], full_report=True)

    assert file_path.exists()
    wb = openpyxl.load_workbook(str(file_path))

    # Accenture sheet exists
    assert "Accenture" in wb.sheetnames
    ws_acc = wb["Accenture"]

    # Verify column headers exactly match ACCENTURE_COLUMNS
    headers = [ws_acc.cell(row=1, column=c).value for c in range(1, len(ACCENTURE_COLUMNS) + 1)]
    assert headers == ACCENTURE_COLUMNS

    # Row 2 data checks
    assert ws_acc.cell(row=2, column=ACCENTURE_COLUMNS.index("Match Score") + 1).value == 92  # Match Score
    assert ws_acc.cell(row=2, column=ACCENTURE_COLUMNS.index("Job Title") + 1).value == "Python Developer"  # Job Title
    assert ws_acc.cell(row=2, column=ACCENTURE_COLUMNS.index("Official Job ID") + 1).value == "ATCI-12345-S67890"  # Official Job ID
    assert "Bengaluru" in str(ws_acc.cell(row=2, column=ACCENTURE_COLUMNS.index("Location") + 1).value)  # Location
    assert ws_acc.cell(row=2, column=ACCENTURE_COLUMNS.index("Eligibility") + 1).value == "Eligible"  # Eligibility
    assert ws_acc.cell(row=2, column=ACCENTURE_COLUMNS.index("Company") + 1).value == "Accenture"  # Company
    assert ws_acc.cell(row=2, column=ACCENTURE_COLUMNS.index("Source") + 1).value == "Accenture"  # Source

    # Clickable Job URL
    url_col = ACCENTURE_COLUMNS.index("Direct Job URL") + 1
    url_cell = ws_acc.cell(row=2, column=url_col)
    assert "https://www.accenture.com/in-en/careers/jobdetails" in url_cell.value
    assert url_cell.hyperlink is not None
    assert url_cell.hyperlink.target == url_cell.value

    # Also verify the job is present in All Relevant Jobs and Top Matches
    ws_top = wb["Top Matches"]
    assert ws_top.max_row >= 2
    top_titles = [ws_top.cell(row=r, column=5).value for r in range(2, ws_top.max_row + 1)]
    assert "Python Developer" in top_titles


def test_excel_export_missing_job_id_labeled(tmp_path):
    """Test Excel export labels missing Job ID as UNAVAILABLE."""
    job = Job(
        source="accenture",
        title="Web Developer",
        company="Accenture",
        location="Noida, India",
        url="https://www.accenture.com/in-en/careers/jobdetails?id=sample",
        extra_metadata={"official_job_id": "UNAVAILABLE", "eligibility": "Needs Review"},
        match_score=65,
    )
    exporter = ExcelExporter(exports_dir=tmp_path)
    file_path = exporter.export([job], full_report=True)

    wb = openpyxl.load_workbook(str(file_path))
    ws_acc = wb["Accenture"]
    id_col = ACCENTURE_COLUMNS.index("Official Job ID") + 1
    assert ws_acc.cell(row=2, column=id_col).value == "UNAVAILABLE"


def test_accenture_diagnostics_formatting(sample_accenture_raw):
    """Test formatting diagnostic reports."""
    source = AccentureJobSource(is_enabled=True)
    job = parse_accenture_job(sample_accenture_raw)
    job.match_score = 90
    job.match_category = "Excellent"

    source.diagnostics["valid_normalized"] = 1
    source.diagnostics["collected"] = 1
    report = source.format_diagnostics(filtered_jobs=[job], scored_jobs=[job])

    assert "Accenture:" in report
    assert "Valid normalized jobs: 1" in report
    assert "Excellent: 1" in report


# =========================================================================
# 8. Pagination & Stopping Condition Regression Tests
# =========================================================================

def test_pagination_advances_start_index_for_subsequent_pages():
    """Verify that collection advances startIndex beyond 0 when more results are needed."""
    def mock_fetch(keyword, start_index=0, max_result_size=25, **kwargs):
        idx = int(start_index)
        size = int(max_result_size)
        return {
            "totalHits": {"total": 100},
            "data": [
                {
                    "title": f"Software Engineer {idx + i}",
                    "requisitionId": f"ATCI-REQ-{idx + i}",
                    "location": ["Bengaluru"],
                    "jobDescriptionClean": "0-2 years experience required.",
                }
                for i in range(size)
            ],
        }

    settings = Settings(ACCENTURE_ENABLED=True, ACCENTURE_MAX_JOBS=50, ACCENTURE_REQUEST_DELAY_SEC=0.0)
    source = AccentureJobSource(is_enabled=True, settings=settings)

    with patch("app.sources.accenture.fetch_accenture_jobs_http", side_effect=mock_fetch):
        jobs = asyncio.run(
            source.collect_jobs(roles=["Software Engineer"], locations=["Bengaluru"], max_results=50)
        )

    assert len(jobs) == 50
    assert source.diagnostics["queries_attempted"] == 1
    assert source.diagnostics["pages_requested"] == 2
    assert source.diagnostics["query_pages"]["Software Engineer"] == 2
    # Verify job IDs span across both pages
    job_ids = [j.source_job_id for j in jobs]
    assert "ATCI-REQ-0" in job_ids
    assert "ATCI-REQ-25" in job_ids


def test_pagination_stops_on_cycle_or_duplicate_page():
    """Verify that repeated page results trigger cycle detection and halt query pagination."""
    static_page = {
        "totalHits": {"total": 100},
        "data": [
            {
                "title": f"Python Dev {i}",
                "requisitionId": f"ATCI-CYCLE-{i}",
                "location": ["Bengaluru"],
            }
            for i in range(25)
        ],
    }

    settings = Settings(ACCENTURE_ENABLED=True, ACCENTURE_MAX_JOBS=50, ACCENTURE_REQUEST_DELAY_SEC=0.0)
    source = AccentureJobSource(is_enabled=True, settings=settings)

    # Returns the exact same page at any startIndex
    with patch("app.sources.accenture.fetch_accenture_jobs_http", return_value=static_page):
        jobs = asyncio.run(
            source.collect_jobs(roles=["Python Dev"], locations=["Bengaluru"], max_results=50)
        )

    assert len(jobs) == 25
    # First request fetches 25 jobs, second request detects cycle and halts
    assert source.diagnostics["pages_requested"] == 2
    assert source.last_status in ("COMPLETED", "PARTIAL")


def test_pagination_covers_all_target_roles():
    """Verify that multi-query collection covers all configured queries without stopping at query 1."""
    roles = [f"Target Role {i}" for i in range(10)]

    def mock_fetch(keyword, start_index=0, max_result_size=25, **kwargs):
        idx = int(start_index)
        size = int(max_result_size)
        return {
            "totalHits": {"total": 50},
            "data": [
                {
                    "title": f"{keyword} Job {idx + i}",
                    "requisitionId": f"REQ-{keyword.replace(' ', '_')}-{idx + i}",
                    "location": ["Bengaluru"],
                }
                for i in range(size)
            ],
        }

    settings = Settings(ACCENTURE_ENABLED=True, ACCENTURE_MAX_JOBS=20, ACCENTURE_REQUEST_DELAY_SEC=0.0)
    source = AccentureJobSource(is_enabled=True, settings=settings)

    with patch("app.sources.accenture.fetch_accenture_jobs_http", side_effect=mock_fetch):
        jobs = asyncio.run(
            source.collect_jobs(roles=roles, locations=["Bengaluru"], max_results=20)
        )

    assert len(jobs) == 20
    assert source.diagnostics["queries_attempted"] == 10


# =========================================================================
# 9. Matching, Extraction & Triaging Regression Tests
# =========================================================================

def test_experience_en_dash_and_fresher_patterns():
    """Verify Unicode en-dash, em-dash, 'to', and singular year patterns are recognized as Eligible."""
    assert determine_accenture_eligibility("0–2 years") == "Eligible"  # en-dash \u2013
    assert determine_accenture_eligibility("0—2 years") == "Eligible"  # em-dash \u2014
    assert determine_accenture_eligibility("0 to 2 years") == "Eligible"
    assert determine_accenture_eligibility("0-1 year") == "Eligible"
    assert determine_accenture_eligibility("0 to 1 year") == "Eligible"
    assert determine_accenture_eligibility("1-2 years") == "Eligible"
    assert determine_accenture_eligibility("0 years of experience") == "Eligible"
    assert determine_accenture_eligibility(None, job_title="Software Development Engineer Intern") == "Eligible"
    assert determine_accenture_eligibility(None, description_text="Looking for freshers or 2026 graduates") == "Eligible"


def test_intermediate_experience_marked_for_review():
    """Verify 2-5 years experience is NOT rejected as 5+ years and NOT declared fresher; marked Needs Review."""
    assert determine_accenture_eligibility("2-5 years") == "Needs Review"
    assert determine_accenture_eligibility("2–5 years") == "Needs Review"  # en-dash
    assert determine_accenture_eligibility("2 to 5 years") == "Needs Review"
    assert determine_accenture_eligibility("3-5 years") == "Needs Review"


def test_explicit_senior_experience_rejection():
    """Verify 5+ years, 5-10 years, 10-12 years, and senior titles remain strictly rejected."""
    assert determine_accenture_eligibility("5-10 years") == "Ineligible"
    assert determine_accenture_eligibility("10-12 years") == "Ineligible"
    assert determine_accenture_eligibility("5+ years") == "Ineligible"
    assert determine_accenture_eligibility("6+ years") == "Ineligible"
    assert determine_accenture_eligibility("10+ years") == "Ineligible"
    assert determine_accenture_eligibility(None, job_title="Lead Software Engineer") == "Ineligible"
    assert determine_accenture_eligibility(None, job_title="Principal Architect") == "Ineligible"
    assert determine_accenture_eligibility(None, job_title="Engineering Manager") == "Ineligible"
    assert determine_accenture_eligibility(None, description_text="Minimum 5 years of experience required in backend development.") == "Ineligible"


def test_unrelated_numbers_not_confused_with_experience():
    """Verify degrees, educational tenure, and company stats do not trigger false senior experience rejections."""
    desc_education = "Candidates must hold 15 years full time education. Work on modern Python microservices."
    assert determine_accenture_eligibility("0-2 years", description_text=desc_education, job_title="Associate Developer") == "Eligible"

    desc_company_age = "Accenture has operated for 10 years in this technology hub. Looking for entry level engineers."
    assert determine_accenture_eligibility("0-2 years", description_text=desc_company_age, job_title="Software Engineer") == "Eligible"


def test_missing_and_ambiguous_experience_requires_review():
    """Verify missing, empty, or ambiguous experience information returns Needs Review, not assumed eligible."""
    assert determine_accenture_eligibility(None, description_text="Develop web tools.", job_title="Software Engineer") == "Needs Review"
    assert determine_accenture_eligibility("", description_text="Develop backend APIs.", job_title="Backend Developer") == "Needs Review"
    assert determine_accenture_eligibility("Not Specified", description_text="Work in engineering.", job_title="Python Developer") == "Needs Review"


def test_classify_job_triaging_match_review_reject():
    """Test JobFilter.classify_job assigns MATCH, REVIEW, and REJECT with clear explanations."""
    profile = JobProfile(
        target_roles=["Python Developer", "Software Engineer", "Backend Developer"],
        preferred_locations=["Bengaluru", "Noida", "Delhi", "Remote"],
        negative_keywords=["Senior", "Lead", "Manager", "5+ years", "10+ years"],
        preferences={"remote_allowed": True, "internship_allowed": True, "fresher_allowed": True},
    )
    job_filter = JobFilter(profile=profile)

    # 1. MATCH: Target role, preferred location, explicit 0-2 yrs
    match_job = Job(
        title="Python Developer",
        location="Bengaluru, India",
        company="Accenture",
        source="accenture",
        url="https://example.com/match1",
        experience_required="0-2 years",
        extra_metadata={"eligibility": "Eligible"},
    )
    decision, reason = job_filter.classify_job(match_job)
    assert decision == "MATCH"
    assert "0-2" in reason or "Eligible" in reason
    assert match_job.extra_metadata["decision"] == "MATCH"

    # 2. REJECT by Gate 1: Target role, preferred location, intermediate 2-5 yrs (requires 2+ years)
    review_job = Job(
        title="Software Engineer",
        location="Bengaluru, India",
        company="Accenture",
        source="accenture",
        url="https://example.com/review1",
        experience_required="2-5 years",
        extra_metadata={"eligibility": "Needs Review"},
    )
    decision, reason = job_filter.classify_job(review_job)
    assert decision == "REJECT"
    assert "requires 2+ years" in reason
    assert review_job.extra_metadata["decision"] == "REJECT"

    # 3. REVIEW: Target role, preferred location, missing experience (experience not stated)
    review_job_unspecified = Job(
        title="Backend Developer",
        location="Noida, India",
        company="Accenture",
        source="accenture",
        url="https://example.com/review2",
        experience_required=None,
        extra_metadata={"eligibility": "Needs Review"},
    )
    decision, reason = job_filter.classify_job(review_job_unspecified)
    assert decision == "REVIEW"
    assert "experience not stated" in reason

    # 4. REJECT: Excluded location (Mumbai)
    reject_loc_job = Job(
        title="Python Developer",
        location="Mumbai, Maharashtra, India",
        company="Accenture",
        source="accenture",
        url="https://example.com/reject1",
        experience_required="0-2 years",
    )
    decision, reason = job_filter.classify_job(reject_loc_job)
    assert decision == "REJECT"
    assert "Mumbai" in reason or "preferred locations" in reason

    # 5. REJECT: Senior title
    reject_title_job = Job(
        title="Senior Python Developer",
        location="Bengaluru, India",
        company="Accenture",
        source="accenture",
        url="https://example.com/reject2",
        experience_required="0-2 years",
    )
    decision, reason = job_filter.classify_job(reject_title_job)
    assert decision == "REJECT"
    assert "Senior" in reason

    # 6. REJECT: High experience (5-10 years)
    reject_exp_job = Job(
        title="Python Developer",
        location="Bengaluru, India",
        company="Accenture",
        source="accenture",
        url="https://example.com/reject3",
        experience_required="5-10 years",
    )
    decision, reason = job_filter.classify_job(reject_exp_job)
    assert decision == "REJECT"
    assert "requires 5+ years" in reason

    # 7. REJECT: Role mismatch (e.g. HR / Recruiting)
    reject_role_job = Job(
        title="Recruiting Analyst - Talent Acquisition",
        location="Bengaluru, India",
        company="Accenture",
        source="accenture",
        url="https://example.com/reject4",
        experience_required="0-2 years",
    )
    decision, reason = job_filter.classify_job(reject_role_job)
    assert decision == "REJECT"
    assert "target roles" in reason


def test_multiple_locations_handling():
    """Verify multiple locations are accepted when at least one preferred location is present."""
    profile = JobProfile(
        target_roles=["Software Engineer"],
        preferred_locations=["Bengaluru", "Noida"],
        negative_keywords=["Senior"],
    )
    flt = JobFilter(profile=profile)

    # Contains Bengaluru (preferred) along with Mumbai (excluded)
    multi_job_allowed = Job(
        title="Software Engineer",
        location="Bengaluru, Mumbai, India",
        company="Accenture",
        source="accenture",
        url="https://example.com/multi1",
    )
    assert flt.is_match(multi_job_allowed) is True

    # Contains only excluded locations (Mumbai, Pune)
    multi_job_excluded = Job(
        title="Software Engineer",
        location="Mumbai, Pune, India",
        company="Accenture",
        source="accenture",
        url="https://example.com/multi2",
    )
    assert flt.is_match(multi_job_excluded) is False


def test_remote_india_eligibility_matching():
    """Verify remote roles are accepted only when eligible from India."""
    profile = JobProfile(
        target_roles=["Software Engineer"],
        preferred_locations=["Bengaluru", "Remote"],
        preferences={"remote_allowed": True},
    )
    flt = JobFilter(profile=profile)

    # India-eligible remote
    job_remote_in = Job(
        title="Software Engineer",
        location="Bangalore, India - Remote",
        company="Accenture",
        source="accenture",
        url="https://example.com/rem_in",
    )
    assert flt.is_match(job_remote_in) is True

    # Foreign remote (US)
    job_remote_us = Job(
        title="Software Engineer",
        location="Remote, United States",
        company="Accenture",
        source="accenture",
        url="https://example.com/rem_us",
    )
    assert flt.is_match(job_remote_us) is False


def test_excel_export_preserves_application_tracking(tmp_path):
    """Verify that exporting jobs preserves APPLIED status, notes, and interview data."""
    job_applied = Job(
        title="Python Developer",
        location="Bengaluru, India",
        company="Accenture",
        source="accenture",
        source_job_id="ATCI-APPLIED-1",
        url="https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-APPLIED-1",
        experience_required="0-2 years",
        match_score=90,
        status=JobStatus.APPLIED,
        notes="Applied via official portal on Monday",
        interview_date="2026-10-20",
        interview_stage="Technical Round 1",
        extra_metadata={"decision": "MATCH", "decision_reason": "Matches fresher criteria"},
    )

    exporter = ExcelExporter(exports_dir=tmp_path)
    file_path = exporter.export([job_applied], accenture_jobs=[job_applied], full_report=True)

    wb = openpyxl.load_workbook(str(file_path))
    ws_acc = wb["Accenture"]

    status_col = ACCENTURE_COLUMNS.index("Application Status") + 1
    decision_col = ACCENTURE_COLUMNS.index("Decision") + 1
    reason_col = ACCENTURE_COLUMNS.index("Decision Reason") + 1

    assert ws_acc.cell(row=2, column=status_col).value == "APPLIED"
    assert ws_acc.cell(row=2, column=decision_col).value == "MATCH"
    assert "fresher criteria" in str(ws_acc.cell(row=2, column=reason_col).value)


