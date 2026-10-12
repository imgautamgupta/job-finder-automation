"""Unit tests for services: filter, deduplicator, collector, and excel exporter."""

import tempfile
from pathlib import Path

from app.config.settings import JobProfile
from app.database.database import DatabaseManager
from app.models.job import Job
from app.services.collector import JobCollector
from app.services.deduplicator import JobDeduplicator, normalize_url
from app.services.excel_exporter import ExcelExporter
from app.services.filter import JobFilter
from app.sources.linkedin import LinkedInJobSource
from app.sources.naukri import NaukriJobSource


def test_url_normalization():
    url = "https://www.linkedin.com/jobs/view/12345/?trackingId=xyz&ref=search&utm_source=google"
    normalized = normalize_url(url)
    assert "trackingId" not in normalized
    assert "ref" not in normalized
    assert "utm_source" not in normalized
    assert normalized == "https://www.linkedin.com/jobs/view/12345"


def test_job_filter():
    profile = JobProfile(
        target_roles=["Software Engineer", "Backend Developer"],
        preferred_locations=["Bangalore", "Remote"],
        negative_keywords=["Lead", "Senior 10+ years"],
        remote_only=False,
    )
    job_filter = JobFilter(profile=profile)

    matching_job = Job(
        title="Junior Software Engineer",
        company="Tech Corp",
        location="Bangalore",
        source="linkedin",
        url="https://example.com/job/1",
    )
    assert job_filter.is_match(matching_job) is True

    negative_kw_job = Job(
        title="Lead Software Engineer",
        company="Tech Corp",
        location="Bangalore",
        source="linkedin",
        url="https://example.com/job/2",
    )
    assert job_filter.is_match(negative_kw_job) is False

    location_mismatch_job = Job(
        title="Backend Developer",
        company="Tech Corp",
        location="Mumbai",
        source="naukri",
        url="https://example.com/job/3",
    )
    assert job_filter.is_match(location_mismatch_job) is False


def test_job_deduplicator():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db = DatabaseManager(db_path=Path(tmp_dir) / "test.db")
        dedup = JobDeduplicator(db_manager=db)

        job1 = Job(
            title="Software Engineer",
            company="Alpha",
            location="Bangalore",
            source="linkedin",
            url="https://linkedin.com/jobs/1?ref=search",
            job_id="101",
        )
        job2 = Job(
            title="Software Engineer",
            company="Alpha",
            location="Bangalore",
            source="linkedin",
            url="https://linkedin.com/jobs/1?trk=123",  # same after normalization
            job_id="101",
        )
        job3 = Job(
            title="Backend Engineer",
            company="Beta",
            location="Remote",
            source="naukri",
            url="https://naukri.com/jobs/202",
            job_id="202",
        )

        deduped = dedup.deduplicate([job1, job2, job3])
        assert len(deduped) == 2

        # Save to db and re-run
        db.save_jobs(deduped)
        deduped_second_run = dedup.deduplicate([job1, job3])
        assert len(deduped_second_run) == 0


def test_excel_exporter():
    with tempfile.TemporaryDirectory() as tmp_dir:
        exporter = ExcelExporter(exports_dir=tmp_dir)
        job = Job(
            title="Python Developer",
            company="Open Source Org",
            location="Remote",
            source="linkedin",
            url="https://example.com/job/python-dev",
        )
        export_path = exporter.export([job])
        assert export_path.exists()
        assert export_path.suffix == ".xlsx"


def test_collector_registry():
    from app.sources.lever import LeverJobSource
    from app.sources.greenhouse import GreenhouseJobSource

    collector = JobCollector()
    linkedin = LinkedInJobSource()
    naukri = NaukriJobSource()
    lever = LeverJobSource(is_enabled=False)
    greenhouse = GreenhouseJobSource(is_enabled=False)

    collector.register_source(linkedin)
    collector.register_source(naukri)
    collector.register_source(lever)
    collector.register_source(greenhouse)

    assert "linkedin" in collector.registered_sources
    assert "naukri" in collector.registered_sources
    assert "lever" in collector.registered_sources
    assert "greenhouse" in collector.registered_sources


def test_cross_source_deduplication():
    """Verify jobs across multiple different sources are correctly deduplicated."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db = DatabaseManager(db_path=Path(tmp_dir) / "test.db")
        dedup = JobDeduplicator(db_manager=db)

        job_lever = Job(
            title="Software Engineer",
            company="Tech Corp",
            location="Bangalore",
            source="lever",
            source_job_id="lever-001",
            url="https://jobs.lever.co/tech/lever-001",
        )
        job_greenhouse = Job(
            title="Backend Developer",
            company="Cloud Corp",
            location="Remote",
            source="greenhouse",
            source_job_id="gh-001",
            url="https://boards.greenhouse.io/cloud/jobs/gh-001",
        )

        unique_jobs = dedup.deduplicate([job_lever, job_greenhouse])
        assert len(unique_jobs) == 2
        db.save_jobs(unique_jobs)

        # Subsequent run receives same jobs
        second_run = dedup.deduplicate([job_lever, job_greenhouse])
        assert len(second_run) == 0


def test_phase_6f_filter_negative_keywords_title_vs_desc():
    """Verify negative keywords reject titles and explicit requirements, but preserve team context."""
    profile = JobProfile(
        target_roles=["Software Engineer", "Backend Developer"],
        preferred_locations=["Bangalore", "Remote"],
        negative_keywords=["Senior", "Lead", "Manager", "5+ years"],
        preferences={"remote_allowed": True},
    )
    job_filter = JobFilter(profile=profile)

    # 1. Junior role mentioning senior in description must PASS
    job_junior = Job(
        title="Junior Backend Developer",
        company="Tech Corp",
        location="Bangalore",
        source="lever",
        url="https://example.com/j1",
        description="You will collaborate with senior engineers and report to the engineering manager.",
    )
    assert job_filter.is_match(job_junior) is True

    # 2. Senior in title must FAIL
    job_senior = Job(
        title="Senior Backend Developer",
        company="Tech Corp",
        location="Bangalore",
        source="lever",
        url="https://example.com/j2",
        description="General backend development.",
    )
    assert job_filter.is_match(job_senior) is False

    # 3. Explicit 5+ years experience required in description must FAIL
    job_explicit_exp = Job(
        title="Software Engineer",
        company="Tech Corp",
        location="Bangalore",
        source="lever",
        url="https://example.com/j3",
        description="Minimum 5+ years of experience required in distributed systems.",
    )
    assert job_filter.is_match(job_explicit_exp) is False

    # 4. Company age / team experience in description must PASS
    job_team_age = Job(
        title="Software Engineer",
        company="Tech Corp",
        location="Bangalore",
        source="lever",
        url="https://example.com/j4",
        description="Our team has over 10 years of experience in high-performance computing.",
    )
    assert job_filter.is_match(job_team_age) is True


def test_phase_6f_filter_remote_eligibility():
    """Verify filter passes India-eligible remote jobs but rejects foreign-only remote jobs."""
    profile = JobProfile(
        target_roles=["Software Engineer"],
        preferred_locations=["Bangalore", "Remote"],
        preferences={"remote_allowed": True},
    )
    job_filter = JobFilter(profile=profile)

    # India remote passes
    job_in_remote = Job(
        title="Software Engineer",
        company="Acme",
        location="Bangalore, India - Remote",
        source="lever",
        url="https://example.com/r1",
    )
    assert job_filter.is_match(job_in_remote) is True

    # Foreign remote fails
    job_foreign_remote = Job(
        title="Software Engineer",
        company="Acme",
        location="Remote, Canada; Remote, Poland; Remote, United Kingdom",
        source="greenhouse",
        url="https://example.com/r2",
    )
    assert job_filter.is_match(job_foreign_remote) is False
