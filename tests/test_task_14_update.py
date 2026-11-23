"""Tests for Task 14 Update:
- HP Workday worldwide support (ENTRY_LEVEL_LOCATION_SCOPE=all)
- Deloitte SuccessFactors South Asia additions (India, Sri Lanka & Maldives, Mauritius)
- Country column in workbook and derive_country function
- Work authorization requirement flag in FilterService and ExcelExporter
- Daily summary Source and Country breakdowns
"""

import io
import logging
from unittest.mock import patch
import pytest

from app.config.settings import Settings
from app.models.job import Job
from app.models.profile import JobProfile, SearchPreferences
from app.services.excel_exporter import (
    ALL_JOBS_COLUMNS,
    MY_JOBS_COLUMNS,
    ExcelExporter,
    derive_country,
)
from app.services.filter import JobFilter, WORK_AUTH_PATTERN
from app.sources.successfactors import (
    DEFAULT_SUCCESSFACTORS_COMPANIES,
    SuccessFactorsJobSource,
)
from app.sources.workday import (
    DEFAULT_WORKDAY_COMPANIES,
    WorkdayJobSource,
    passes_title_location_prefilters,
)
from app.main import print_daily_summary


# ---------------------------------------------------------------------------
# Change 1: HP Workday
# ---------------------------------------------------------------------------

def test_hp_workday_registry():
    """Verify HP is configured in DEFAULT_WORKDAY_COMPANIES with worldwide location scope."""
    assert "hp" in DEFAULT_WORKDAY_COMPANIES
    hp_cfg = DEFAULT_WORKDAY_COMPANIES["hp"]
    assert hp_cfg["host"] == "hp.wd5.myworkdayjobs.com"
    assert hp_cfg["tenant"] == "hp"
    assert hp_cfg["site"] == "ExternalCareerSite"
    assert hp_cfg.get("location_scope") == "all"
    assert hp_cfg.get("applied_facets") == {}


def test_hp_passes_title_location_prefilters_worldwide():
    """Worldwide scope should bypass India-only prefilter."""
    # US job with worldwide scope should pass
    passed = passes_title_location_prefilters(
        "Software Engineer",
        "Palo Alto, California, United States",
        location_scope="all",
    )
    assert passed is True

    # US job without worldwide scope should fail location prefilter
    passed_no_scope = passes_title_location_prefilters(
        "Software Engineer",
        "Palo Alto, California, United States",
        location_scope=None,
    )
    assert passed_no_scope is False


# ---------------------------------------------------------------------------
# Change 2: Deloitte SuccessFactors
# ---------------------------------------------------------------------------

def test_deloitte_successfactors_registry():
    """Verify Deloitte India, Sri Lanka & Maldives, and Mauritius entries."""
    for key in ("deloitte_india", "deloitte_srilanka", "deloitte_mauritius"):
        assert key in DEFAULT_SUCCESSFACTORS_COMPANIES

    india = DEFAULT_SUCCESSFACTORS_COMPANIES["deloitte_india"]
    assert india["name"] == "Deloitte India"
    assert india["location_scope"] == "all"
    assert india["supports_role_queries"] is True

    sl = DEFAULT_SUCCESSFACTORS_COMPANIES["deloitte_srilanka"]
    assert sl["name"] == "Deloitte Sri Lanka & Maldives"
    assert sl["location_scope"] == "all"
    assert sl["sf_site_id"] == "718344"
    assert sl["default_keywords"] == "Sri Lanka"

    mau = DEFAULT_SUCCESSFACTORS_COMPANIES["deloitte_mauritius"]
    assert mau["name"] == "Deloitte Mauritius"
    assert mau["location_scope"] == "all"
    assert mau["sf_site_id"] == "718444"
    assert mau["default_keywords"] == "Mauritius"


# ---------------------------------------------------------------------------
# Change 4: derive_country and Excel columns
# ---------------------------------------------------------------------------

def test_derive_country():
    """Verify country derivation rules."""
    # Remote
    assert derive_country("Remote") == "Remote"
    assert derive_country("Remote, US") == "Remote"
    assert derive_country("Bengaluru (Remote)") == "Remote"

    # India
    assert derive_country("Bengaluru, Karnataka, India") == "India"
    assert derive_country("Pune, India") == "India"
    assert derive_country("Hyderabad") == "India"

    # United States
    assert derive_country("San Jose, CA, United States") == "United States"
    assert derive_country("Austin, Texas, USA") == "United States"
    assert derive_country("New York, NY") == "United States"

    # United Kingdom
    assert derive_country("London, UK") == "United Kingdom"
    assert derive_country("Manchester, England") == "United Kingdom"

    # South Asia & Indian Ocean
    assert derive_country("Colombo, Sri Lanka") == "Sri Lanka"
    assert derive_country("Ebene, Mauritius") == "Mauritius"
    assert derive_country("Port Louis, Mauritius") == "Mauritius"
    assert derive_country("Male, Maldives") == "Maldives"

    # Other countries
    assert derive_country("Toronto, Canada") == "Canada"
    assert derive_country("Berlin, Germany") == "Germany"
    assert derive_country("Sydney, Australia") == "Australia"
    assert derive_country("Singapore") == "Singapore"

    # Empty / Unknown
    assert derive_country("") == "Unknown"
    assert derive_country(None) == "Unknown"
    assert derive_country("Not Specified") == "Unknown"

    # Comma-separated fallback
    assert derive_country("Alpha City, BetaLand") == "Betaland"


def test_excel_column_positions():
    """Verify Country column exists at expected position in both workbooks."""
    assert MY_JOBS_COLUMNS[4] == "Location"
    assert MY_JOBS_COLUMNS[5] == "Country"
    assert MY_JOBS_COLUMNS[6] == "Experience"

    assert ALL_JOBS_COLUMNS[3] == "Location"
    assert ALL_JOBS_COLUMNS[4] == "Country"
    assert ALL_JOBS_COLUMNS[5] == "Experience Requirement"


# ---------------------------------------------------------------------------
# Change 5: Work authorization flag
# ---------------------------------------------------------------------------

def test_work_auth_flag_detection():
    """Verify work auth regex and flag tagging on MATCH and REVIEW decisions."""
    profile = JobProfile(
        target_roles=["Software Engineer", "Backend Developer"],
        skills=["Python"],
        preferred_locations=["India", "Remote"],
        min_experience_years=0,
        max_experience_years=2,
        preferences=SearchPreferences(remote_allowed=True),
    )
    filter_service = JobFilter(profile=profile)

    # Job with work auth requirement in description
    j_match = Job(
        source="test",
        title="Software Engineer",
        company="GlobalTech",
        location="India",
        experience_required="0-1 years",
        description="Must have right to work in the host country. Visa sponsorship not provided.",
        url="https://example.com/job/match",
    )

    decision, reason = filter_service.classify_job(j_match)
    assert decision == "MATCH"
    assert "; check work-authorization requirement" in reason
    assert j_match.extra_metadata.get("work_auth_flag") is True

    # Review job with security clearance requirement
    j_review = Job(
        source="test",
        title="Backend Developer",
        company="GlobalTech",
        location="India",
        description="Great role. Security clearance required for all candidates.",
        url="https://example.com/job/review",
    )
    decision_rv, reason_rv = filter_service.classify_job(j_review)
    assert decision_rv == "REVIEW"
    assert "; check work-authorization requirement" in reason_rv
    assert j_review.extra_metadata.get("work_auth_flag") is True

    # Rejected job should not be changed to MATCH/REVIEW
    j_reject = Job(
        source="test",
        title="Senior Principal Architect",
        company="GlobalTech",
        location="India",
        experience_required="10+ years",
        description="US citizenship required.",
        url="https://example.com/job/reject",
    )
    decision_rj, reason_rj = filter_service.classify_job(j_reject)
    assert decision_rj == "REJECT"


def test_work_auth_in_my_jobs_excel(tmp_path):
    """Verify Why column in My Jobs sheet appends work-auth requirement note."""
    exporter = ExcelExporter()
    out_file = tmp_path / "My_Jobs_workauth.xlsx"

    job = Job(
        source="test",
        title="Junior Developer",
        company="WorldwideTech",
        location="Bengaluru, India",
        experience_required="0-1 years",
        decision="MATCH",
        decision_reason="Eligible entry-level role",
        url="https://example.com/job/1",
        extra_metadata={"work_auth_flag": True, "decision": "MATCH", "decision_reason": "Eligible entry-level role"},
    )

    exporter.export([job], output_path=out_file)

    import openpyxl
    wb = openpyxl.load_workbook(out_file)
    ws = wb["My Jobs"]
    # Column 8 is Why
    why_val = ws.cell(row=2, column=8).value
    assert "check work-authorization requirement" in why_val


# ---------------------------------------------------------------------------
# Change 6: Source Breakdown and Country Breakdown in Daily Summary
# ---------------------------------------------------------------------------

def test_daily_summary_breakdowns(capsys):
    """Verify Source Breakdown and Country Breakdown are printed in daily summary."""
    j1 = Job(
        source="workday",
        title="Software Engineer",
        company="HP",
        location="Palo Alto, United States",
        url="https://hp.wd5.myworkdayjobs.com/job/1",
        extra_metadata={"decision": "MATCH"},
    )
    j2 = Job(
        source="successfactors",
        title="Associate Consultant",
        company="Deloitte Mauritius",
        location="Ebene, Mauritius",
        url="https://deloitte.com/job/2",
        extra_metadata={"decision": "REVIEW"},
    )
    j3 = Job(
        source="workday",
        title="Senior Director",
        company="Adobe",
        location="Bengaluru, India",
        url="https://adobe.wd5.myworkdayjobs.com/job/3",
        extra_metadata={"decision": "REJECT"},
    )

    print_daily_summary(
        run_id="test-run-14",
        source_results={"workday": {"status": "COMPLETED", "collected": 2}, "successfactors": {"status": "COMPLETED", "collected": 1}},
        raw_count=3,
        new_count=3,
        duplicate_count=0,
        relevant_count=2,
        strong_count=1,
        excellent_count=1,
        run_status="COMPLETED",
        export_file="data/exports/My_Jobs_latest.xlsx",
        all_jobs=[j1, j2, j3],
    )

    captured = capsys.readouterr().out
    assert "Source Breakdown:" in captured
    assert "Workday" in captured
    assert "Successfactors" in captured
    assert "Country Breakdown:" in captured
    assert "United States" in captured
    assert "Mauritius" in captured
    assert "India" in captured
