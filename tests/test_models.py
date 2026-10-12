"""Unit tests for the Job model."""

from datetime import datetime
from app.models.job import Job


def test_job_model_creation():
    job = Job(
        title="  Software Engineer ",
        company=" Acme Corp ",
        location=" Bangalore ",
        source=" linkedin ",
        url=" https://example.com/job/123 ",
        description="Build Python backend services.",
        easy_apply=True,
        job_id="12345",
        employment_type="Full-time",
        experience_required="1-3 years",
    )

    assert job.title == "Software Engineer"
    assert job.company == "Acme Corp"
    assert job.location == "Bangalore"
    assert job.source == "linkedin"
    assert job.url == "https://example.com/job/123"
    assert job.easy_apply is True
    assert job.job_id == "12345"
    assert isinstance(job.date_found, datetime)
    assert job.deduplication_key == "linkedin::12345"


def test_job_deduplication_key_fallback():
    job = Job(
        title="Python Developer",
        company="Tech Co",
        location="Remote",
        source="naukri",
        url="https://example.com/job/abc",
    )
    assert job.deduplication_key == "fallback::techco::pythondeveloper"


def test_job_to_row_dict():
    job = Job(
        title="Backend Engineer",
        company="Fast Startup",
        location="Hyderabad",
        source="linkedin",
        url="https://example.com/job/999",
        easy_apply=False,
    )
    row = job.to_row_dict()
    assert row["Title"] == "Backend Engineer"
    assert row["Company"] == "Fast Startup"
    assert row["Source"] == "Linkedin"
    assert row["Easy Apply"] == "No"
    assert row["Job ID"] == "N/A"
