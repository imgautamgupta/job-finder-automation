import pytest
from app.models.job import Job
from app.models.profile import JobProfile
from app.services.filter import (
    JobFilter,
    parse_title_experience_min,
    parse_structured_experience_min,
)


@pytest.fixture
def sample_profile():
    return JobProfile(
        target_roles=["Software Engineer", "Backend Developer", "Python Developer"],
        preferred_locations=["Bengaluru", "Bangalore", "Noida", "Delhi", "Remote"],
        skills=["Python", "Java", "Django", "FastAPI"],
        negative_keywords=["Lead", "Senior", "Principal", "Manager"],
    )


def test_parse_title_experience_min():
    """Verify parsing of experience ranges from job titles."""
    # Months to years range
    assert parse_title_experience_min("Software Engineer (6months to 2 years experience, Java/Python)") == 0.5
    assert parse_title_experience_min("Software Engineer (6 months to 2 years experience)") == 0.5
    assert parse_title_experience_min("Software Engineer (6-12 months)") == 0.5
    assert parse_title_experience_min("Software Engineer (6 to 12 months)") == 0.5

    # Years range
    assert parse_title_experience_min("Software Engineer (0-2 years)") == 0
    assert parse_title_experience_min("Software Engineer - 0 to 2 yrs") == 0
    assert parse_title_experience_min("Software Engineer (1-3 years)") == 1
    assert parse_title_experience_min("Backend Developer (0.5 to 2 years)") == 0.5
    assert parse_title_experience_min("Systems Analyst (4 - 6 years of experience)") == 4

    # Fresher keywords
    assert parse_title_experience_min("Software Engineer (Fresher)") == 0
    assert parse_title_experience_min("Python Developer (Freshers)") == 0

    # No experience stated
    assert parse_title_experience_min("Software Engineer") is None
    assert parse_title_experience_min("Backend Developer - Payments") is None


def test_visa_job_classification(sample_profile):
    """Verify Visa job with '6months to 2 years' title becomes MATCH."""
    flt = JobFilter(profile=sample_profile, max_required_min_years=1)
    job = Job(
        source="workday",
        source_job_id="REF089294W",
        title="Software Engineer (6months to 2 years experience, Java/Python)",
        company="Visa",
        location="IN - Bengaluru, India",
        url="https://visa.wd5.myworkdayjobs.com/job/REF089294W",
        description="Visa is seeking a software engineer to develop core payment platforms.",
        experience_required=None,
    )

    decision, reason = flt.classify_job(job)
    assert decision == "MATCH"
    assert "Stated minimum 0.5 years matches criteria" in reason
    assert "Software Engineer" in reason


def test_title_fresher_yields_match(sample_profile):
    """Verify title with 'fresher' or '0-2 years' yields MATCH."""
    flt = JobFilter(profile=sample_profile, max_required_min_years=1)

    job1 = Job(
        source="company_json",
        title="Software Engineer (Fresher)",
        company="TechCorp",
        location="Bengaluru, India",
        url="https://techcorp.com/job/1",
        description="Join our team as a software engineer.",
    )
    decision1, reason1 = flt.classify_job(job1)
    assert decision1 == "MATCH"
    assert "Stated minimum 0 years matches criteria" in reason1

    job2 = Job(
        source="company_json",
        title="Software Engineer (0-2 years)",
        company="TechCorp",
        location="Bengaluru, India",
        url="https://techcorp.com/job/2",
        description="Looking for an engineer with early experience.",
    )
    decision2, reason2 = flt.classify_job(job2)
    assert decision2 == "MATCH"
    assert "Stated minimum 0 years matches criteria" in reason2


def test_title_experience_exceeding_max_yields_reject(sample_profile):
    """Verify title with experience > max_required_min_years is REJECTED without filter loosening."""
    flt = JobFilter(profile=sample_profile, max_required_min_years=1)

    job = Job(
        source="workday",
        title="Software Engineer (4 - 6 years of experience)",
        company="EnterpriseCo",
        location="Bengaluru, India",
        url="https://enterpriseco.com/job/3",
        description="Senior level engineering role.",
    )
    decision, reason = flt.classify_job(job)
    assert decision == "REJECT"
    assert "requires 4+ years" in reason
    assert "Gate 1: requires 4+ years" in job.extra_metadata.get("all_failing_rules", "")


def test_title_experience_with_mismatching_location_yields_reject(sample_profile):
    """Verify title experience <= max_required_min_years still REJECTS if location fails."""
    flt = JobFilter(profile=sample_profile, max_required_min_years=1)

    job = Job(
        source="workday",
        title="Software Engineer (6months to 2 years experience)",
        company="Visa",
        location="London, United Kingdom",
        url="https://visa.wd5.myworkdayjobs.com/job/REF089294W_UK",
        description="Job in UK.",
    )
    decision, reason = flt.classify_job(job)
    assert decision == "REJECT"
    assert "Location 'London, United Kingdom' is not in preferred locations" in reason
    assert "location" in job.extra_metadata.get("all_failing_rules", "")
