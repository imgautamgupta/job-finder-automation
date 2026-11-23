"""Tests for Task 16 - Turn on all verified career portals.

Verifies:
1. ENABLED_SOURCES default configuration and CLI override parsing.
2. Per-source overrides do not leak:
   - ENTRY_LEVEL_LOCATION_SCOPE=all and ROLE_FILTER=off apply strictly to HP and Deloitte.
   - Non-India job from non-HP/Deloitte source is REJECT for location.
   - Non-target-role job from non-HP/Deloitte source is REJECT for role.
   - HP job outside India is NOT rejected for location.
   - Deloitte job with non-target role is NOT rejected for role.
3. Exporter filters disabled sources unless actively tracked (status != 'Not applied').
4. JobCollector timeout isolation.
"""

import asyncio
from datetime import datetime, timezone
import pytest

from app.config.settings import Settings
from app.models.job import Job, JobStatus
from app.models.profile import JobProfile
from app.services.filter import JobFilter, is_hp_or_deloitte_source
from app.services.collector import JobCollector
from app.sources.base import BaseJobSource
from app.main import resolve_source_connectors
from app.services.excel_exporter import is_job_actively_tracked, is_job_source_enabled, ExcelExporter


@pytest.fixture
def test_profile():
    return JobProfile(
        target_roles=["Software Engineer", "GenAI Engineer", "Python Developer"],
        preferred_locations=["Delhi NCR", "Bengaluru", "Ahmedabad", "Remote"],
        skills=["Python", "RAG", "LLM", "AWS"],
        negative_keywords=["Senior", "Lead", "Manager", "Staff", "Principal"],
        match_max_years=2,
        review_max_years=3,
    )


def test_enabled_sources_default_contains_all_verified_portals():
    """Verify ENABLED_SOURCES default config includes all verified portals."""
    settings = Settings()
    active_list = settings.enabled_sources_list
    assert len(active_list) >= 15
    # All verified portals must be present
    for portal in [
        "accenture", "workday", "adobe", "intel", "nvidia", "salesforce",
        "walmart", "mastercard", "visa", "paypal", "hp", "amazon", "infosys",
        "capgemini", "wipro", "hcltech", "deloitte_india", "deloitte_srilanka",
        "deloitte_mauritius", "oracle", "dell", "flipkart"
    ]:
        assert portal in active_list, f"Missing portal {portal} from ENABLED_SOURCES default"


def test_cli_sources_override():
    """Verify resolve_source_connectors with CLI override only enables specified portals."""
    settings = Settings()
    sources, active_tokens = resolve_source_connectors(settings, sources_override="hp,deloitte")

    assert set(active_tokens) == {"hp", "deloitte"}

    # Sources registered
    source_map = {s.source_name: s for s in sources}
    # Workday should be enabled only for hp
    assert source_map["workday"].is_enabled is True
    assert source_map["workday"].configured_companies == ["hp"]

    # SuccessFactors should be enabled for deloitte
    assert source_map["successfactors"].is_enabled is True
    assert all("deloitte" in c for c in source_map["successfactors"].configured_companies)

    # All others should be disabled
    assert source_map["accenture"].is_enabled is False
    assert source_map["company_json"].is_enabled is False
    assert source_map["oracle_hcm"].is_enabled is False
    assert source_map["turbohire"].is_enabled is False
    assert source_map["linkedin"].is_enabled is False


def test_per_source_override_does_not_leak_location_gate(test_profile):
    """A non-India job from a non-HP/Deloitte source must be REJECT for location."""
    jf = JobFilter(profile=test_profile)

    # 1. Non-India job from Amazon (company_json)
    amazon_job = Job(
        title="Software Engineer",
        company="Amazon",
        location="Seattle, WA, USA",
        source="company_json",
        url="https://amazon.jobs/en/jobs/12345",
        description="Write Python code. 1-2 years experience required.",
    )
    jf.classify_job(amazon_job)
    assert amazon_job.extra_metadata["decision"] == "REJECT"
    assert "location" in amazon_job.extra_metadata.get("decision_reason", "").lower()

    # 2. Non-India job from Accenture
    accenture_job = Job(
        title="Software Engineer",
        company="Accenture",
        location="London, United Kingdom",
        source="accenture",
        url="https://accenture.com/jobs/67890",
        description="Python programming. 2 years experience.",
    )
    jf.classify_job(accenture_job)
    assert accenture_job.extra_metadata["decision"] == "REJECT"
    assert "location" in accenture_job.extra_metadata.get("decision_reason", "").lower()

    # 3. Non-India job from Oracle
    oracle_job = Job(
        title="Software Engineer",
        company="Oracle",
        location="Austin, TX, USA",
        source="oracle_hcm",
        url="https://oracle.com/jobs/11223",
        description="Python development. 1-2 years experience.",
    )
    jf.classify_job(oracle_job)
    assert oracle_job.extra_metadata["decision"] == "REJECT"
    assert "location" in oracle_job.extra_metadata.get("decision_reason", "").lower()


def test_per_source_override_does_not_leak_role_gate(test_profile):
    """A non-target-role job from a non-HP/Deloitte source must be REJECT for role."""
    jf = JobFilter(profile=test_profile)

    # 1. Non-target role from Amazon in preferred location (Bengaluru)
    amazon_job = Job(
        title="Financial Analyst",
        company="Amazon",
        location="Bengaluru, Karnataka, India",
        source="company_json",
        url="https://amazon.jobs/en/jobs/54321",
        description="Accounting and finance. 1 year experience.",
    )
    jf.classify_job(amazon_job)
    assert amazon_job.extra_metadata["decision"] == "REJECT"
    assert "target roles" in amazon_job.extra_metadata.get("decision_reason", "").lower()

    # 2. Non-target role from Wipro in preferred location (Bengaluru)
    wipro_job = Job(
        title="Human Resources Specialist",
        company="Wipro",
        location="Bengaluru, Karnataka, India",
        source="successfactors",
        url="https://careers.wipro.com/job/98765",
        description="HR operations and recruitment. 2 years experience.",
    )
    jf.classify_job(wipro_job)
    assert wipro_job.extra_metadata["decision"] == "REJECT"
    assert "target roles" in wipro_job.extra_metadata.get("decision_reason", "").lower()


def test_hp_and_deloitte_bypass_location_and_role_correctly(test_profile):
    """HP and Deloitte sources bypass location and role filters per Task 14/15/16 rules."""
    jf = JobFilter(profile=test_profile)

    # 1. HP job in Boise, Idaho, USA (non-India location) with 2 years exp
    hp_job = Job(
        title="Software Engineer",
        company="HP",
        location="Boise, Idaho, USA",
        source="workday",
        url="https://hp.wd5.myworkdayjobs.com/External/job/1",
        description="Software development. Minimum 2 years experience required.",
        extra_metadata={"company_key": "hp"},
    )
    assert is_hp_or_deloitte_source(hp_job) is True
    jf.classify_job(hp_job)
    # Must NOT be rejected for location
    assert hp_job.extra_metadata["decision"] == "MATCH"

    # 2. Deloitte job in Sri Lanka with non-target role "Tax Consultant"
    deloitte_job = Job(
        title="Tax Consultant",
        company="Deloitte Sri Lanka & Maldives",
        location="Colombo, Sri Lanka",
        source="successfactors",
        url="https://jobs2.deloitte.com/job/2",
        description="Tax advisory. Minimum 1 year experience required.",
        extra_metadata={"company_key": "deloitte_srilanka"},
    )
    assert is_hp_or_deloitte_source(deloitte_job) is True
    jf.classify_job(deloitte_job)
    # Must NOT be rejected for role or location
    assert deloitte_job.extra_metadata["decision"] == "MATCH"


def test_exporter_filters_disabled_sources_unless_actively_tracked(tmp_path):
    """Exporter includes enabled sources and actively tracked jobs, excluding untracked disabled sources."""
    enabled_tokens = ["hp", "deloitte_india"]

    # 1. Untracked job from enabled source (HP) -> INCLUDED
    job1 = Job(
        title="Software Engineer",
        company="HP",
        location="Boise, USA",
        source="workday",
        url="https://hp.wd5.myworkdayjobs.com/External/job/10",
        extra_metadata={"decision": "MATCH", "company_key": "hp"},
        status=JobStatus.NEW,
    )

    # 2. Untracked job from disabled source (Naukri) -> EXCLUDED
    job2 = Job(
        title="Software Engineer",
        company="Random Corp",
        location="Bengaluru, India",
        source="naukri",
        url="https://naukri.com/job/20",
        extra_metadata={"decision": "MATCH"},
        status=JobStatus.NEW,
    )

    # 3. Actively tracked job from disabled source (LinkedIn) -> INCLUDED because status is APPLIED
    job3 = Job(
        title="GenAI Engineer",
        company="OpenAI",
        location="Remote",
        source="linkedin",
        url="https://linkedin.com/jobs/view/30",
        extra_metadata={"decision": "MATCH"},
        status=JobStatus.APPLIED,
    )

    assert is_job_source_enabled(job1, enabled_tokens) is True
    assert is_job_source_enabled(job2, enabled_tokens) is False
    assert is_job_actively_tracked(job2) is False
    assert is_job_actively_tracked(job3) is True

    exporter = ExcelExporter(exports_dir=tmp_path)
    export_path = exporter.export_my_jobs(
        jobs=[job1, job2, job3],
        output_path=tmp_path / "test_my_jobs.xlsx",
        enabled_sources=enabled_tokens,
    )

    import openpyxl
    wb = openpyxl.load_workbook(export_path, read_only=True)
    ws = wb["My Jobs"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # Row 1 is header, Row 2 and 3 should be job1 and job3. job2 should NOT be present.
    assert len(rows) == 3
    companies = [r[2] for r in rows[1:]]
    assert "HP" in companies
    assert "OpenAI" in companies
    assert "Random Corp" not in companies


def test_job_collector_timeout_isolation():
    """Verify that a slow source times out and does not block the collection of other sources."""
    class FastSource(BaseJobSource):
        @property
        def source_name(self) -> str:
            return "fast_portal"

        async def collect_jobs(self, roles, locations, max_results=25):
            return [
                Job(title="Fast SDE", company="FastCo", location="Bengaluru", source="fast_portal", url="https://fast.co/1")
            ]

    class SlowSource(BaseJobSource):
        @property
        def source_name(self) -> str:
            return "slow_portal"

        async def collect_jobs(self, roles, locations, max_results=25):
            await asyncio.sleep(2.0)
            return [
                Job(title="Slow SDE", company="SlowCo", location="Bengaluru", source="slow_portal", url="https://slow.co/2")
            ]

    async def _run():
        collector = JobCollector(
            sources=[FastSource(is_enabled=True), SlowSource(is_enabled=True)],
            source_timeout_sec=0.2,  # 200ms timeout
        )

        jobs = await collector.collect_all(roles=["SDE"], locations=["India"])
        assert len(jobs) == 1
        assert jobs[0].company == "FastCo"

        results = collector.get_source_results()
        assert results["fast_portal"]["status"] == "COMPLETED"
        assert results["slow_portal"]["status"] == "FAILED"
        assert "Timed out" in results["slow_portal"]["error"]

    asyncio.run(_run())
