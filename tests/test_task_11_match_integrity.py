"""Tests for Task 11: MATCH integrity, level title checks, location filters, and adapter qualification feeds."""

import pytest
from app.models.job import Job
from app.models.profile import JobProfile
from app.services.filter import (
    JobFilter,
    match_level_title,
    match_seniority_title,
    scan_description_experience,
)
from app.sources.company_json import CompanyJsonJobSource
from app.sources.oracle_hcm import OracleHCMJobSource, OracleHcmSource
from app.sources.successfactors import SuccessFactorsJobSource, parse_successfactors_location
from app.sources.turbohire import TurboHireJobSource


@pytest.fixture
def test_profile():
    return JobProfile(
        target_roles=[
            "Software Engineer",
            "Software Dev Engineer",
            "SDE",
            "Backend Engineer",
            "Backend Developer",
            "Python Developer",
            "Machine Learning Engineer",
            "AI Engineer",
        ],
        preferred_locations=["Bengaluru", "Bangalore", "Hyderabad", "Noida", "Remote"],
        negative_keywords=["Senior", "Lead", "Manager", "Director", "Architect"],
        preferences={
            "remote_allowed": True,
            "internship_allowed": True,
            "fresher_allowed": True,
        },
    )


class TestLevelTitleCheck:
    """Verify level II/III/IV/V and L5+ are rejected, keeping I/1/L4/Associate allowed."""

    def test_allowed_titles(self):
        allowed = [
            "Software Dev Engineer I, L4",
            "Software Dev Engineer I FTC",
            "Software Dev Engineer I",
            "Software Dev Engineer 1",
            "SDE 1",
            "SDE I",
            "Software Dev Engineer II",
            "Software Dev Engineer II, Paragon",
            "SDE 2",
            "SDE II",
            "Software Engineer 2",
            "Software Engineer L5",
            "Level 2 Engineer",
            "Level II Engineer",
            "Associate Software Engineer",
            "Associate Engineer",
            "Junior Software Engineer",
            "Software Engineer",
            "Backend Engineer",
            "Machine Learning Engineer (L3)",
            "Machine Learning Engineer (L4)",
            "Level 1 Engineer",
            "Associate Consultant",
            "QA Engineer 2",
            "Developer 2",
            "2nd Level Support Engineer",
        ]
        for title in allowed:
            marker = match_level_title(title)
            assert marker is None, f"Expected allowed title '{title}' but matched marker: {marker}"

    def test_rejected_titles(self):
        rejected = [
            "Engineer III",
            "SDE III",
            "SDE IV",
            "Software Engineer 3",
            "Software Engineer L6",
            "Level III Specialist",
            "Level IV Architect",
            "QA Engineer 3",
            "Developer 3",
            "3rd Level Support Engineer",
        ]
        for title in rejected:
            marker = match_level_title(title)
            assert marker is not None, f"Expected rejected title '{title}' to match marker but got None"

    def test_classify_job_allows_level_ii(self, test_profile):
        flt = JobFilter(profile=test_profile, max_required_min_years=1)
        job = Job(
            source="test",
            title="Software Dev Engineer II",
            company="Amazon",
            location="Bengaluru, India",
            experience_required="1+ years",
            description="Basic Qualifications:\n- 1+ years of non-internship professional software development experience",
            url="https://www.amazon.jobs/en/jobs/10495277",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "MATCH"

    def test_classify_job_rejects_level_iii(self, test_profile):
        flt = JobFilter(profile=test_profile, max_required_min_years=1)
        job = Job(
            source="test",
            title="Software Dev Engineer III",
            company="Amazon",
            location="Bengaluru, India",
            experience_required="1+ years",
            description="Basic Qualifications:\n- 1+ years of non-internship professional software development experience",
            url="https://www.amazon.jobs/en/jobs/10495277",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REJECT"
        assert "level" in reason.lower() or "iii" in reason.lower()
        assert "level title" in job.extra_metadata.get("all_failing_rules", "")

    def test_classify_job_allows_level_i_l4(self, test_profile):
        flt = JobFilter(profile=test_profile, max_required_min_years=1)
        job = Job(
            source="test",
            title="Software Dev Engineer I, L4",
            company="Amazon",
            location="Bengaluru, India",
            experience_required=None,
            description="Basic Qualifications:\n- Experience of 1 to 3 years as an SDE",
            url="https://www.amazon.jobs/en/jobs/10572929",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "MATCH"
        assert "Eligible" in reason


class TestMatchRuleIntegrity:
    """Verify MATCH is granted ONLY if stated min <= max_years OR fresher/entry title.
    If no experience info is found -> REVIEW 'experience not stated'.
    """

    def test_gate1_stated_min_under_limit_matches(self, test_profile):
        flt = JobFilter(profile=test_profile, max_required_min_years=1)
        job = Job(
            source="test",
            title="Software Engineer",
            company="TestCo",
            location="Bengaluru, India",
            experience_required="0-1 years",
            url="https://example.com/job1",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "MATCH"
        assert "Eligible" in reason

    def test_gate2_stated_min_under_limit_matches(self, test_profile):
        flt = JobFilter(profile=test_profile, max_required_min_years=1)
        job = Job(
            source="test",
            title="Software Engineer",
            company="Amazon",
            location="Bengaluru, India",
            experience_required=None,
            description="Basic Qualifications:\n- 1+ years of software development experience",
            url="https://example.com/job2",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "MATCH"
        assert "Eligible" in reason

    def test_fresher_title_matches_without_experience_info(self, test_profile):
        flt = JobFilter(profile=test_profile, max_required_min_years=1)
        # Titles stating fresher parse experience to 0 -> MATCH
        fresher_titles = [
            "Fresher Python Developer",
            "Software Engineer (Fresher)",
        ]
        for t in fresher_titles:
            job = Job(
                source="test",
                title=t,
                company="TestCo",
                location="Bengaluru, India",
                experience_required=None,
                description="Join our team working on backend infrastructure.",
                url="https://example.com/fresher",
            )
            decision, reason = flt.classify_job(job)
            assert decision == "MATCH", f"Expected MATCH for '{t}', got {decision}"

        # Task 15 update: intern and trainee titles are below candidate profile level -> REJECT
        intern_trainee_titles = [
            "Software Engineer Intern",
            "Graduate Software Engineer Trainee",
        ]
        for t in intern_trainee_titles:
            job = Job(
                source="test",
                title=t,
                company="TestCo",
                location="Bengaluru, India",
                experience_required=None,
                description="Join our team working on backend infrastructure.",
                url="https://example.com/intern",
            )
            decision, reason = flt.classify_job(job)
            assert decision == "REJECT", f"Expected REJECT for '{t}', got {decision}"
            assert "below profile level" in reason

    def test_no_experience_info_becomes_review(self, test_profile):
        flt = JobFilter(profile=test_profile, max_required_min_years=1)
        job = Job(
            source="test",
            title="Software Engineer",
            company="TestCo",
            location="Bengaluru, India",
            experience_required=None,
            description="Build scalable high throughput distributed systems.",
            url="https://example.com/no-exp",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REVIEW"
        assert reason == "experience not stated"


class TestLocationFilterAndOverseasRejection:
    """Verify non-India jobs (such as Capgemini Katowice) are rejected with reason 'location'."""

    def test_parse_successfactors_location_detects_katowice(self):
        loc = parse_successfactors_location(
            title="Software Engineer (Kernel)",
            description="Job description in Katowice",
            link="https://careers.capgemini.com/job/Katowice-Software-Engineer-%28Kernel%29/1439468133/",
        )
        assert loc == "Katowice"

    def test_classify_job_rejects_katowice_job_on_location(self, test_profile):
        flt = JobFilter(profile=test_profile, max_required_min_years=1)
        job = Job(
            source="test",
            title="Software Engineer (Kernel)",
            company="Capgemini",
            location="Katowice",
            url="https://careers.capgemini.com/job/Katowice-Software-Engineer-%28Kernel%29/1439468133/",
            description="Linux kernel engineer role in Katowice, Poland.",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REJECT"
        assert "preferred locations" in reason or "Katowice" in reason
        assert "location" in job.extra_metadata.get("all_failing_rules", "")


class TestAdapterQualificationFeeds:
    """Verify that Amazon, Infosys, Oracle, and TurboHire adapters feed full qualifications to Gate 2."""

    def test_amazon_adapter_feeds_all_qualifications(self):
        source = CompanyJsonJobSource(is_enabled=False)
        raw_amazon = {
            "id": "10572929",
            "title": "Software Dev Engineer I, L4",
            "city": "Bengaluru",
            "description": "<p>General team overview.</p>",
            "basic_qualifications": "<p>Bachelor's degree. Experience of 1 to 3 years as an SDE.</p>",
            "preferred_qualifications": "<p>Exposure to AWS and full-stack development.</p>",
            "posted_date": "March 15, 2026",
        }
        job = source.parse_amazon_job(raw_amazon, {"name": "Amazon", "base_url": "https://www.amazon.jobs"})
        assert job is not None
        assert "Basic Qualifications:" in job.description
        assert "Experience of 1 to 3 years as an SDE" in job.description
        assert "Preferred Qualifications:" in job.description

        # Gate 2 should successfully scan the qualification text
        years, snippet = scan_description_experience(job.description)
        assert years == 1
        assert "1 to 3 years" in snippet

    def test_infosys_adapter_feeds_all_requirements_and_experience(self):
        source = CompanyJsonJobSource(is_enabled=False)
        raw_infosys = {
            "referenceCode": "PRO-12345",
            "postingTitle": "Python Developer",
            "location": "Bangalore",
            "createdOn": "2026-03-20",
            "minExperienceLevel": 0,
            "maxExperienceLevel": 2,
            "postingDescription": "<p>Project details.</p>",
            "technicalRequirement": "<p>Python 3.12, FastAPI, PostgreSQL.</p>",
            "rolesResponsibilities": "<p>Design and implement microservices.</p>",
        }
        job = source.parse_infosys_job(raw_infosys, {"name": "Infosys", "base_apply_url": "https://career.infosys.com"})
        assert job is not None
        assert job.experience_required == "0-2 years"
        assert "Technical Requirements:" in job.description
        assert "Roles and Responsibilities:" in job.description

    def test_oracle_adapter_feeds_full_qualifications(self):
        source = OracleHCMJobSource(is_enabled=False)
        raw_oracle = {
            "Id": "999999",
            "Title": "Software Developer 1",
            "PrimaryLocation": "BENGALURU, KARNATAKA, India",
            "PostedDate": "2026-03-10",
            "ShortDescriptionStr": "Join Oracle Cloud Infrastructure team.",
            "ExternalQualificationsStr": "<p>Candidate must have 0-1 years of experience in Python or Java.</p>",
            "ExternalResponsibilitiesStr": "<p>Develop core cloud services.</p>",
        }
        job = source.parse_requisition(raw_oracle, {"name": "Oracle", "candidate_ui_base": "https://example.com/job"})
        assert job is not None
        assert "Qualifications:" in job.description
        assert "0-1 years" in job.description
        assert "Responsibilities:" in job.description

    def test_turbohire_adapter_populates_experience_and_skills(self):
        source = TurboHireJobSource(is_enabled=False)
        raw_flipkart = {
            "JobCode": "FIPL-100",
            "JobTitle": "Software Development Engineer - I",
            "Location": [{"City": "Bengaluru"}],
            "CreatedOn": "2026-03-18",
            "Experience": {"MinExp": 0, "MaxExp": 2},
            "JobDescV2": "<p>Design and build high scale services.</p>",
            "Skills": ["Python", "Algorithms", "Data Structures"],
        }
        job = source.parse_job_item(raw_flipkart, {"name": "Flipkart", "domain": "https://flipkart.turbohire.co"})
        assert job is not None
        assert job.experience_required == "0-2 years"
        assert "Required Skills:" in job.description
        assert "Python, Algorithms" in job.description
