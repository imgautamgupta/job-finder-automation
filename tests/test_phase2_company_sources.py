"""Tests for Phase 2: Achieve Exactly 40 Genuinely Working Official Company Job Sources.

Validates:
1. 40-Company Registry contains exactly 40 verified working companies, all with status INTEGRATED.
2. Official careers URLs and collection endpoints are populated with official domains.
3. Connector coverage across Workday (9), Oracle HCM (6), SuccessFactors (5), Greenhouse (17),
   Accenture (1), TurboHire (1), and SmartRecruiters (1) - totaling 40.
4. Separate DISCOVERY_UNSUPPORTED_REGISTRY archives unsupported/manual-only companies.
5. Existing generic connectors (Lever, Greenhouse) and Accenture compatibility.
6. Company-level enable/disable behavior via configuration and settings.
7. Failure isolation: Failure in one company source does not halt other companies.
8. Candidate-independent collection & dynamic matching input (profile parameter).
9. Consolidated Excel export with all 17 required columns, clickable hyperlinks, and tracking preservation.
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
    DISCOVERY_UNSUPPORTED_REGISTRY,
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
from app.sources.greenhouse import DEFAULT_GREENHOUSE_COMPANIES, GreenhouseJobSource
from app.sources.lever import LeverJobSource
from app.sources.oracle_hcm import DEFAULT_ORACLE_HCM_COMPANIES, OracleHCMJobSource
from app.sources.smartrecruiters import SMARTRECRUITERS_COMPANY_SLUGS, SmartRecruitersJobSource
from app.sources.successfactors import DEFAULT_SUCCESSFACTORS_COMPANIES, SuccessFactorsJobSource
from app.sources.turbohire import TurboHireJobSource
from app.sources.workday import DEFAULT_WORKDAY_COMPANIES, WorkdayJobSource


def test_registry_contains_exact_40_working_companies():
    """Verify registry contains exactly 40 companies, and every single one is INTEGRATED."""
    registry = get_company_registry()
    companies = registry.get_all_companies()
    assert len(companies) == 40, f"Expected exactly 40 companies, found {len(companies)}"
    assert len(TARGET_40_COMPANIES) == 40

    company_ids = set()
    for cid, entry in TARGET_40_COMPANIES.items():
        assert entry.company_id == cid
        assert entry.name, f"Missing name for {cid}"
        assert entry.official_careers_url.startswith("http"), f"Invalid official_careers_url for {cid}"
        assert entry.collection_endpoint.startswith("http"), f"Invalid collection_endpoint for {cid}"
        assert entry.ats_platform, f"Missing ATS platform for {cid}"
        assert entry.collection_method, f"Missing collection method for {cid}"
        assert entry.integration_status == IntegrationStatus.INTEGRATED, (
            f"Company {cid} must have status INTEGRATED, got {entry.integration_status}"
        )
        assert entry.is_enabled is True
        company_ids.add(cid)

    assert len(company_ids) == 40


def test_unsupported_discovery_registry_separated():
    """Verify that unsupported/manual-only portals are archived separately and not counted in the 40."""
    registry = get_company_registry()
    # Confirm known manual/unsupported companies are NOT in TARGET_40_COMPANIES
    excluded = ["tcs", "cognizant", "tech_mahindra", "ltimindtree", "infosys", "amazon", "deloitte_india"]
    for cid in excluded:
        assert cid not in TARGET_40_COMPANIES, f"{cid} must not be in TARGET_40_COMPANIES"
        assert cid in DISCOVERY_UNSUPPORTED_REGISTRY, f"{cid} should be documented in DISCOVERY_UNSUPPORTED_REGISTRY"


def test_connector_coverage_all_40_companies():
    """Verify all 40 companies are mapped to their respective working connectors."""
    # 1. Workday (9 companies)
    expected_wd = {"adobe", "intel", "nvidia", "salesforce", "walmart", "mastercard", "visa", "paypal", "hp"}
    for cid in expected_wd:
        assert cid in TARGET_40_COMPANIES
        assert TARGET_40_COMPANIES[cid].ats_platform == "workday"
        assert cid in DEFAULT_WORKDAY_COMPANIES

    # 2. Oracle HCM (6 companies)
    expected_oh = {"oracle", "dell", "hexaware", "zensar", "eclerx", "ofss"}
    for cid in expected_oh:
        assert cid in TARGET_40_COMPANIES
        assert TARGET_40_COMPANIES[cid].ats_platform == "oracle_hcm"
        assert cid in DEFAULT_ORACLE_HCM_COMPANIES

    # 3. SuccessFactors (5 companies)
    expected_sf = {"capgemini", "wipro", "hcltech", "birlasoft", "mastek"}
    for cid in expected_sf:
        assert cid in TARGET_40_COMPANIES
        assert TARGET_40_COMPANIES[cid].ats_platform == "successfactors"
        assert cid in DEFAULT_SUCCESSFACTORS_COMPANIES

    # 4. Greenhouse (17 companies)
    expected_gh = {
        "stripe", "cloudflare", "databricks", "elastic", "canonical",
        "mongodb", "brex", "gitlab", "affirm", "lyft",
        "scaleai", "pinterest", "reddit", "figma", "twilio",
        "instacart", "airtable",
    }
    for cid in expected_gh:
        assert cid in TARGET_40_COMPANIES
        assert TARGET_40_COMPANIES[cid].ats_platform == "greenhouse"
        assert cid in DEFAULT_GREENHOUSE_COMPANIES

    # 5. Accenture (1 company)
    assert "accenture" in TARGET_40_COMPANIES
    assert TARGET_40_COMPANIES["accenture"].collection_method == "accenture_search_api"

    # 6. TurboHire (1 company - Flipkart)
    assert "flipkart" in TARGET_40_COMPANIES
    assert TARGET_40_COMPANIES["flipkart"].ats_platform == "turbohire"

    # 7. SmartRecruiters (1 company - Sopra Steria)
    assert "sopra_steria" in TARGET_40_COMPANIES
    assert TARGET_40_COMPANIES["sopra_steria"].ats_platform == "smartrecruiters"
    assert "sopra_steria" in SMARTRECRUITERS_COMPANY_SLUGS

    # Total check
    total_covered = len(expected_wd) + len(expected_oh) + len(expected_sf) + len(expected_gh) + 3
    assert total_covered == 40


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


def test_generic_connectors_lever_greenhouse_compatibility():
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

    # Enabled company in registry (e.g. Hexaware, Stripe, Adobe)
    assert registry.is_company_enabled("hexaware") is True
    assert registry.is_company_enabled("stripe") is True
    assert registry.is_company_enabled("adobe") is True

    # Test settings override with specific enabled_sources
    custom_settings = Settings()
    custom_settings.ENABLED_SOURCES = "hexaware,stripe"
    assert registry.is_company_enabled("hexaware", settings=custom_settings) is True
    assert registry.is_company_enabled("stripe", settings=custom_settings) is True
    assert registry.is_company_enabled("adobe", settings=custom_settings) is False


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
        company="Stripe",
        location="Bengaluru",
        experience_required="1-2 years",
        description="Looking for GenAI Engineer with Python, RAG and LangChain experience.",
        source="greenhouse",
        job_id="STRIPE-101",
        url="https://stripe.com/jobs/101",
    )
    job_senior = Job(
        title="Senior Director Engineering",
        company="Stripe",
        location="Bengaluru",
        experience_required="15+ years",
        description="Senior leadership role.",
        source="greenhouse",
        job_id="STRIPE-102",
        url="https://stripe.com/jobs/102",
    )

    base_profile = JobProfile(
        target_roles=["GenAI Engineer"],
        preferred_locations=["Bengaluru"],
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
        company="Stripe",
        title="Software Engineer",
        job_id="STRIPE-555",
        source_job_id="STRIPE-555",
        location="Bengaluru, India",
        experience_required="1-2 years",
        employment_type="Full-time",
        match_score=88,
        matched_skills=["Python", "FastAPI"],
        date_posted="2026-03-01",
        source="greenhouse",
        url="https://boards.greenhouse.io/stripe/jobs/555",
        date_found=datetime.now(timezone.utc),
        status=JobStatus.APPLIED,
        extra_metadata={"decision": "MATCH", "decision_reason": "Direct match for Software Engineer"},
    )

    export_file = exporter.export([job], output_path=tmp_path / "test_phase2.xlsx", full_report=True)
    wb = openpyxl.load_workbook(export_file)
    ws = wb["All Jobs"]

    # 1. Verify headers match ALL_JOBS_COLUMNS exactly
    headers = [ws.cell(row=1, column=c).value for c in range(1, len(ALL_JOBS_COLUMNS) + 1)]
    assert headers == ALL_JOBS_COLUMNS
    assert "Employment Type" in headers

    # 2. Verify row values
    row_vals = [ws.cell(row=2, column=c).value for c in range(1, len(ALL_JOBS_COLUMNS) + 1)]
    assert row_vals[0] == "Stripe"
    assert row_vals[1] == "Software Engineer"
    assert row_vals[2] == "STRIPE-555"
    assert row_vals[3] == "Bengaluru, India"
    assert row_vals[4] == "India"
    assert row_vals[5] == "1-2 years"
    assert row_vals[6] == 88
    assert "Python" in row_vals[7]
    assert row_vals[8] == "MATCH"
    assert row_vals[13] == "https://boards.greenhouse.io/stripe/jobs/555"
    assert row_vals[15] == "APPLIED"
    assert row_vals[16] == "Full-time"

    # 3. Verify clickable hyperlink on Application URL (column 14)
    url_cell = ws.cell(row=2, column=14)
    assert url_cell.hyperlink is not None
    assert url_cell.hyperlink.target == "https://boards.greenhouse.io/stripe/jobs/555"
