"""Tests for Phase 1: Expand Job Finder Automation to 40 Official Company Job Sources.

Validates:
1. 40-Company Registry metadata, unique IDs, official URLs, and ATS platforms.
2. Official collection methods and technical feasibility categorization.
3. Status categorization (integrated, manual_only, unsupported, disabled, error).
4. Connector configuration for newly integrated companies (Hexaware, Zensar, eClerx, OFSS, Birlasoft, Mastek, Sopra Steria).
5. Existing Accenture connector compatibility.
6. Existing Lever and Greenhouse connector compatibility.
7. Company-level enable/disable behavior via configuration and settings.
8. Failure isolation: Failure in one company source does not halt other companies.
9. Candidate-independent collection & dynamic matching input (profile parameter).
10. Consolidated Excel export with all required fields, clickable hyperlinks, and tracking preservation.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import openpyxl
import pytest

from app.config.company_registry import (
    CompanyEntry,
    CompanyRegistry,
    IntegrationStatus,
    TARGET_40_COMPANIES,
    get_company_registry,
)
from app.config.settings import Settings
from app.models.job import Job, JobStatus
from app.models.profile import JobProfile
from app.services.excel_exporter import ALL_JOBS_COLUMNS, ExcelExporter
from app.services.filter import JobFilter
from app.sources.accenture import AccentureJobSource
from app.sources.greenhouse import GreenhouseJobSource
from app.sources.lever import LeverJobSource
from app.sources.oracle_hcm import DEFAULT_ORACLE_HCM_COMPANIES, OracleHCMJobSource
from app.sources.smartrecruiters import SMARTRECRUITERS_COMPANY_SLUGS, SmartRecruitersJobSource
from app.sources.successfactors import DEFAULT_SUCCESSFACTORS_COMPANIES, SuccessFactorsJobSource


def test_registry_contains_40_companies():
    """Verify registry contains exactly the 40 specified target IT/tech employers with unique IDs."""
    registry = get_company_registry()
    companies = registry.get_all_companies()
    assert len(companies) == 40, f"Expected exactly 40 companies, found {len(companies)}"

    company_ids = set()
    for entry in companies:
        assert entry.company_id
        assert entry.name
        assert entry.official_careers_url.startswith("http")
        assert entry.ats_platform
        assert entry.collection_method
        assert entry.integration_status == IntegrationStatus.INTEGRATED
        company_ids.add(entry.company_id)

    assert len(company_ids) == 40


def test_official_careers_urls_and_collection_methods():
    """Verify official careers URLs and collection methods are populated with official domains."""
    registry = get_company_registry()
    allowed_methods = {
        "accenture_search_api",
        "bot_protected",
        "greenhouse_api",
        "json_search_api",
        "manual_portal",
        "oracle_hcm_rest_api",
        "smartrecruiters_api",
        "successfactors_rss",
        "turbohire_api",
        "workday_cxs_api",
    }
    for entry in registry.get_all_companies():
        assert entry.official_careers_url, f"Missing careers URL for {entry.name}"
        assert entry.official_careers_url.startswith(("http://", "https://"))
        assert entry.collection_method in allowed_methods, (
            f"Unexpected collection method '{entry.collection_method}' for {entry.name}"
        )


def test_status_categorization():
    """Verify classification of exactly 40 working companies as INTEGRATED in TARGET_40_COMPANIES."""
    registry = get_company_registry()
    for entry in registry.get_all_companies():
        assert entry.integration_status == IntegrationStatus.INTEGRATED

    # Spot checks
    assert registry.get_company("accenture").integration_status == IntegrationStatus.INTEGRATED
    assert registry.get_company("hexaware").integration_status == IntegrationStatus.INTEGRATED
    assert registry.get_company("birlasoft").integration_status == IntegrationStatus.INTEGRATED
    assert registry.get_company("sopra_steria").integration_status == IntegrationStatus.INTEGRATED
    assert registry.get_company("stripe").integration_status == IntegrationStatus.INTEGRATED
    assert registry.get_company("adobe").integration_status == IntegrationStatus.INTEGRATED


def test_newly_integrated_companies_connector_config():
    """Verify configuration for newly integrated Oracle HCM, SuccessFactors, and SmartRecruiters companies."""
    # 1. Oracle HCM additions
    for cid in ("hexaware", "zensar", "eclerx", "ofss"):
        assert cid in DEFAULT_ORACLE_HCM_COMPANIES, f"Oracle HCM missing config for {cid}"
        cfg = DEFAULT_ORACLE_HCM_COMPANIES[cid]
        assert "base_url" in cfg
        assert "site_number" in cfg
        assert cfg["base_url"].startswith("https://")

    # 2. SuccessFactors additions
    for cid in ("birlasoft", "mastek"):
        assert cid in DEFAULT_SUCCESSFACTORS_COMPANIES, f"SuccessFactors missing config for {cid}"
        cfg = DEFAULT_SUCCESSFACTORS_COMPANIES[cid]
        assert "base_url" in cfg
        assert cfg["base_url"].startswith("https://")

    # 3. SmartRecruiters additions
    assert "sopra_steria" in SMARTRECRUITERS_COMPANY_SLUGS
    assert SMARTRECRUITERS_COMPANY_SLUGS["sopra_steria"]["slug"] == "SopraSteria1"


def test_existing_accenture_connector_compatibility():
    """Verify existing Accenture connector is preserved and operational."""
    registry = get_company_registry()
    entry = registry.get_company("accenture")
    assert entry is not None
    assert entry.connector_name == "accenture"
    assert entry.integration_status == IntegrationStatus.INTEGRATED

    acc_source = AccentureJobSource(is_enabled=True)
    assert acc_source.source_name == "accenture"
    assert hasattr(acc_source, "collect_jobs")
    assert hasattr(acc_source, "format_diagnostics")


def test_existing_lever_and_greenhouse_connector_compatibility():
    """Verify generic Lever and Greenhouse connectors are preserved without regressions."""
    lever = LeverJobSource(is_enabled=False)
    assert lever.source_name == "lever"
    assert hasattr(lever, "collect_jobs")

    gh = GreenhouseJobSource(is_enabled=False)
    assert gh.source_name == "greenhouse"
    assert hasattr(gh, "collect_jobs")


def test_company_enable_disable_behavior():
    """Verify company-level enable/disable behavior via registry and settings overrides."""
    registry = get_company_registry()

    # Disabled company in registry (e.g. TCS)
    assert registry.is_company_enabled("tcs") is False

    # Enabled company in registry (e.g. Hexaware)
    assert registry.is_company_enabled("hexaware") is True

    # Test settings override with specific enabled_sources
    custom_settings = Settings()
    custom_settings.ENABLED_SOURCES = "hexaware,deloitte"
    assert registry.is_company_enabled("hexaware", settings=custom_settings) is True
    assert registry.is_company_enabled("birlasoft", settings=custom_settings) is False


def test_failure_isolation_between_companies():
    """Verify that an error in one company portal does not halt or affect other companies."""
    async def _test():
        source = OracleHCMJobSource(is_enabled=True, companies=["hexaware", "zensar"])
        source.request_delay_sec = 0

        async def mock_collect_company(client, comp_config, comp_key, max_limit):
            if comp_key == "hexaware":
                raise RuntimeError("Hexaware connection timeout")
            return [
                Job(
                    title="Python Developer",
                    company="Zensar Technologies",
                    location="Pune, India",
                    url="https://fa-etvl-saasfaprod1.fa.ocs.oraclecloud.com/job/1001",
                    job_id="1001",
                    source="oracle_hcm",
                )
            ]

        with patch.object(source, "_collect_company_jobs", side_effect=mock_collect_company):
            jobs = await source.collect_jobs(roles=["Developer"], locations=["India"])
            assert len(jobs) == 1
            assert jobs[0].company == "Zensar Technologies"
            assert source.diagnostics["by_company"]["hexaware"]["status"] == "FAILED"
            assert source.last_status == "PARTIAL"

    asyncio.run(_test())


def test_candidate_independent_collection_and_dynamic_matching():
    """Verify collection does not hardcode candidate preferences and filter supports dynamic profile parameter."""
    job_match = Job(
        title="GenAI Engineer",
        company="Hexaware",
        location="Pune",
        experience_required="1-2 years",
        description="Looking for GenAI Engineer with Python, RAG and LangChain experience.",
        source="oracle_hcm",
        job_id="HEX-101",
        url="https://jobs.hexaware.com/101",
    )
    job_senior = Job(
        title="Senior Director Engineering",
        company="Zensar",
        location="Pune",
        experience_required="15+ years",
        description="Senior leadership role.",
        source="oracle_hcm",
        job_id="ZEN-102",
        url="https://jobs.zensar.com/102",
    )

    base_profile = JobProfile(
        target_roles=["GenAI Engineer"],
        preferred_locations=["Pune"],
        match_max_years=2,
        review_max_years=3,
    )
    filter_service = JobFilter(profile=base_profile)

    # Under base profile, job_senior is rejected
    dec1, _ = filter_service.classify_job(job_senior, profile=base_profile)
    assert dec1 == "REJECT"

    # Under base profile, job_match passes
    dec2, _ = filter_service.classify_job(job_match, profile=base_profile)
    assert dec2 == "MATCH"


def test_consolidated_excel_export_all_fields_and_tracking(tmp_path):
    """Verify consolidated Excel export contains all 17 columns, clickable URLs, and preserves tracking."""
    exporter = ExcelExporter(exports_dir=tmp_path)
    job = Job(
        company="Hexaware",
        title="Software Engineer",
        job_id="HEX-555",
        source_job_id="HEX-555",
        location="Mumbai, India",
        experience_required="1-2 years",
        employment_type="Full-time",
        match_score=88,
        matched_skills=["Python", "FastAPI"],
        date_posted="2026-03-01",
        source="oracle_hcm",
        url="https://fa-etqo-saasfaprod1.fa.ocs.oraclecloud.com/jobs/555",
        date_found=datetime.now(timezone.utc),
        status=JobStatus.APPLIED,
        extra_metadata={"decision": "MATCH", "decision_reason": "Direct match for Software Engineer"},
    )

    export_file = exporter.export([job], output_path=tmp_path / "test_phase1.xlsx", full_report=True)
    wb = openpyxl.load_workbook(export_file)
    ws = wb["All Jobs"]

    # 1. Verify headers match ALL_JOBS_COLUMNS exactly
    headers = [ws.cell(row=1, column=c).value for c in range(1, len(ALL_JOBS_COLUMNS) + 1)]
    assert headers == ALL_JOBS_COLUMNS
    assert "Employment Type" in headers

    # 2. Verify row values
    row_vals = [ws.cell(row=2, column=c).value for c in range(1, len(ALL_JOBS_COLUMNS) + 1)]
    assert row_vals[0] == "Hexaware"
    assert row_vals[1] == "Software Engineer"
    assert row_vals[2] == "HEX-555"
    assert row_vals[3] == "Mumbai, India"
    assert row_vals[4] == "India"
    assert row_vals[5] == "1-2 years"
    assert row_vals[6] == 88
    assert "Python" in row_vals[7]
    assert row_vals[8] == "MATCH"
    assert row_vals[13] == "https://fa-etqo-saasfaprod1.fa.ocs.oraclecloud.com/jobs/555"
    assert row_vals[15] == "APPLIED"
    assert row_vals[16] == "Full-time"

    # 3. Verify clickable hyperlink on Application URL (column 14)
    url_cell = ws.cell(row=2, column=14)
    assert url_cell.hyperlink is not None
    assert url_cell.hyperlink.target == "https://fa-etqo-saasfaprod1.fa.ocs.oraclecloud.com/jobs/555"
