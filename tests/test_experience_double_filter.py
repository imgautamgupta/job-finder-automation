"""Comprehensive tests for Experience Double Filter (Task 2).

Verifies:
1. MAX_REQUIRED_MIN_YEARS configuration.
2. Gate 1: Parsing minimum years from structured portal fields (ranges, 2+, minimum N, spelled-out, Unicode dashes).
3. Gate 2: Scanning full description text for stated minimum experience.
4. Gate 2 rejects even when Gate 1 passes.
5. MATCH only when both gates pass or title contains intern/trainee/graduate/fresher/entry level.
6. REVIEW with reason 'experience not stated' when neither gate finds experience info.
7. Location and seniority-title filters remain intact.
"""

import pytest
from app.models.job import Job
from app.models.profile import JobProfile
from app.services.filter import (
    JobFilter,
    parse_structured_experience_min,
    scan_description_experience_min,
    scan_description_experience,
    extract_qualifications_section,
)
from app.config.settings import get_settings


@pytest.fixture
def base_profile():
    return JobProfile(
        target_roles=["Python Developer", "Software Engineer", "Backend Developer", "Web Developer"],
        preferred_locations=["Bengaluru", "Bangalore", "Noida", "Delhi", "Remote"],
        negative_keywords=["Senior", "Lead", "Manager", "Director", "Architect"],
        preferences={"remote_allowed": True, "internship_allowed": True, "fresher_allowed": True},
    )


@pytest.fixture
def flt(base_profile):
    return JobFilter(profile=base_profile, max_required_min_years=1)


def _make_job(
    title: str = "Software Engineer",
    location: str = "Bengaluru, India",
    experience_required: str = None,
    description: str = "",
    **kwargs,
) -> Job:
    return Job(
        title=title,
        company="Accenture",
        location=location,
        source="accenture",
        url="https://example.com/job1",
        experience_required=experience_required,
        description=description,
        **kwargs,
    )


# =========================================================================
# 1. Config tests
# =========================================================================

def test_settings_has_max_required_min_years():
    settings = get_settings()
    assert hasattr(settings, "MAX_REQUIRED_MIN_YEARS")
    assert settings.MAX_REQUIRED_MIN_YEARS == 1


# =========================================================================
# 2. Gate 1 Structured Parser Unit Tests
# =========================================================================

class TestGate1StructuredParser:
    def test_ranges_numeric(self):
        assert parse_structured_experience_min("2-5 years") == 2
        assert parse_structured_experience_min("0-2 years") == 0
        assert parse_structured_experience_min("1-3 years") == 1
        assert parse_structured_experience_min("5-10 years") == 5
        assert parse_structured_experience_min("10-12 years") == 10

    def test_unicode_dashes(self):
        # En-dash (\u2013)
        assert parse_structured_experience_min("2\u20135 years") == 2
        # Em-dash (\u2014)
        assert parse_structured_experience_min("2\u20145 years") == 2
        # Minus sign (\u2212)
        assert parse_structured_experience_min("2\u22125 years") == 2
        # Word 'to'
        assert parse_structured_experience_min("2 to 5 years") == 2
        assert parse_structured_experience_min("0 to 2 years") == 0

    def test_plus_pattern(self):
        assert parse_structured_experience_min("2+ years") == 2
        assert parse_structured_experience_min("3+ yrs") == 3
        assert parse_structured_experience_min("2 + years") == 2
        assert parse_structured_experience_min("two plus years") == 2

    def test_minimum_pattern(self):
        assert parse_structured_experience_min("minimum 3 years") == 3
        assert parse_structured_experience_min("min 2 years") == 2
        assert parse_structured_experience_min("at least 2 years") == 2
        assert parse_structured_experience_min("minimum of 4 years") == 4

    def test_spelled_out_numbers(self):
        assert parse_structured_experience_min("two to five years") == 2
        assert parse_structured_experience_min("zero to two years") == 0
        assert parse_structured_experience_min("one to three years") == 1
        assert parse_structured_experience_min("minimum three years") == 3
        assert parse_structured_experience_min("at least two years") == 2

    def test_fresher_keywords(self):
        assert parse_structured_experience_min("Fresher") == 0
        assert parse_structured_experience_min("Entry Level") == 0
        assert parse_structured_experience_min("Internship") == 0
        assert parse_structured_experience_min("Graduate Trainee") == 0

    def test_no_info_cases(self):
        assert parse_structured_experience_min(None) is None
        assert parse_structured_experience_min("") is None
        assert parse_structured_experience_min("Not Specified") is None
        assert parse_structured_experience_min("unspecified") is None
        assert parse_structured_experience_min("N/A") is None


# =========================================================================
# 3. Gate 2 Description Scanner Unit Tests
# =========================================================================

class TestGate2DescriptionScanner:
    def test_ranges_numeric(self):
        assert scan_description_experience_min("Must have 2-5 years experience in Python.") == 2
        assert scan_description_experience_min("Looking for candidates with 0-2 years experience.") == 0

    def test_unicode_dashes(self):
        assert scan_description_experience_min("Candidate requires 2\u20135 years experience.") == 2
        assert scan_description_experience_min("Requires 2\u20145 years experience.") == 2
        assert scan_description_experience_min("Requires 2\u22125 years experience.") == 2
        assert scan_description_experience_min("Requires two to five years experience.") == 2

    def test_2_plus(self):
        assert scan_description_experience_min("Requires 2+ years of relevant experience.") == 2
        assert scan_description_experience_min("We need 2+ yrs in backend engineering.") == 2
        assert scan_description_experience_min("Applicant must have two plus years experience.") == 2

    def test_minimum_and_at_least(self):
        assert scan_description_experience_min("Minimum 3 years of React development required.") == 3
        assert scan_description_experience_min("At least 2 years in PostgreSQL database design.") == 2
        assert scan_description_experience_min("Requires at least two years experience.") == 2

    def test_spelled_out_numbers(self):
        assert scan_description_experience_min("two to five years of experience required.") == 2
        assert scan_description_experience_min("minimum three years of software engineering.") == 3
        assert scan_description_experience_min("at least two years of experience.") == 2

    def test_fresher_wording(self):
        assert scan_description_experience_min("Looking for freshers and entry-level developers.") == 0
        assert scan_description_experience_min("Internship position for recent graduates.") == 0

    def test_non_requirement_company_mentions(self):
        # Company history should not trigger false minimum requirements
        assert scan_description_experience_min("Our team has over 10 years of experience in AI.") is None
        assert scan_description_experience_min("Founded 5 years ago, we are growing rapidly.") is None
        assert scan_description_experience_min("General backend development without mentioning experience.") is None


# =========================================================================
# 4. JobFilter Integration Tests: Gate 1 and Gate 2
# =========================================================================

class TestJobFilterDoubleGate:
    def test_gate1_rejects_2_to_5_years(self, flt):
        # Task 15 update: max_required_min_years=1 gives match_max=1, review_max=2.
        # Stated min=2 falls into stretch range (<= 2) -> REVIEW "stretch: asks 2 years".
        job = _make_job(experience_required="2-5 years")
        decision, reason = flt.classify_job(job)
        assert decision == "REVIEW"
        assert "stretch: asks 2 years" in reason
        assert flt.is_match(job) is True

    def test_gate1_rejects_2_plus_years(self, flt):
        # Task 15 update: stated min=2 with match_max=1, review_max=2 yields REVIEW.
        job = _make_job(experience_required="2+ years")
        decision, reason = flt.classify_job(job)
        assert decision == "REVIEW"
        assert "stretch: asks 2 years" in reason
        assert flt.is_match(job) is True

    def test_gate1_rejects_spelled_out_numbers(self, flt):
        # Task 15 update: stated min=2 with match_max=1, review_max=2 yields REVIEW.
        job = _make_job(experience_required="two to five years")
        decision, reason = flt.classify_job(job)
        assert decision == "REVIEW"
        assert "stretch: asks 2 years" in reason
        assert flt.is_match(job) is True

    def test_gate1_rejects_unicode_dashes(self, flt):
        # Task 15 update: stated min=2 with match_max=1, review_max=2 yields REVIEW.
        job = _make_job(experience_required="2\u20135 years")
        decision, reason = flt.classify_job(job)
        assert decision == "REVIEW"
        assert "stretch: asks 2 years" in reason
        assert flt.is_match(job) is True

    def test_gate1_rejects_3_plus_years(self, flt):
        # Task 15: stated min=3 > review_max_years (2) -> REJECT
        job = _make_job(experience_required="3-5 years")
        decision, reason = flt.classify_job(job)
        assert decision == "REJECT"
        assert "requires 3+ years" in reason
        assert flt.is_match(job) is False

    def test_gate2_rejects_even_when_gate1_passed(self, flt):
        # Gate 1 has 0-2 years (min=0 <= 1 passes Gate 1), but description requires minimum 3 years
        job = _make_job(
            experience_required="0-2 years",
            description="Minimum 3 years of production Python development required.",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REJECT"
        assert "requires 3+ years" in reason
        assert "minimum 3 years" in reason.lower()
        assert flt.is_match(job) is False

    def test_gate2_rejects_at_least_2_years_in_description(self, flt):
        # Task 15 update: stated min=2 with match_max=1, review_max=2 yields REVIEW "stretch: asks 2 years".
        job = _make_job(
            experience_required=None,
            description="At least 2 years of experience in distributed systems.",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REVIEW"
        assert "stretch: asks 2 years" in reason
        assert flt.is_match(job) is True

    def test_both_gates_pass_matches(self, flt):
        # Gate 1 has 0-2 years (min=0 <= 1), description has no conflicting requirement
        job = _make_job(
            experience_required="0-2 years",
            description="Build scalable web applications with FastAPI.",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "MATCH"
        assert flt.is_match(job) is True

    def test_1_year_requirement_matches(self, flt):
        # min = 1 <= MAX_REQUIRED_MIN_YEARS (1)
        job = _make_job(
            experience_required="1 year",
            description="At least 1 year of programming experience.",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "MATCH"
        assert flt.is_match(job) is True

    def test_no_info_regular_title_triggers_review(self, flt):
        # Neither gate finds info, title has no fresher keyword -> REVIEW
        job = _make_job(
            title="Software Engineer",
            experience_required=None,
            description="General software engineering position.",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REVIEW"
        assert reason == "experience not stated"
        # Since it passes role/location, is_match remains True for candidate review
        assert flt.is_match(job) is True

    def test_no_info_fresher_title_triggers_match(self, flt):
        # Task 15 update: candidate profile is beyond intern level.
        # Title with 'Intern' is rejected as below profile level.
        job = _make_job(
            title="Software Engineer Intern",
            experience_required=None,
            description="Join our team as an engineering intern.",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REJECT"
        assert "below profile level" in reason
        assert flt.is_match(job) is False

    def test_no_info_graduate_trainee_triggers_match(self, flt):
        # Task 15 update: candidate profile is beyond trainee level.
        # Title with 'Trainee' is rejected as below profile level.
        job = _make_job(
            title="Graduate Trainee Engineer",
            experience_required="Not Specified",
            description="Rotational graduate training program.",
        )
        flt.profile.target_roles.append("Graduate Trainee Engineer")
        decision, reason = flt.classify_job(job)
        assert decision == "REJECT"
        assert "below profile level" in reason
        assert flt.is_match(job) is False

    def test_senior_title_remains_rejected_regardless_of_experience(self, flt):
        job = _make_job(
            title="Senior Software Engineer",
            experience_required="0-1 years",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REJECT"
        assert "Senior" in reason
        assert flt.is_match(job) is False

    def test_unrelated_location_remains_rejected(self, flt):
        job = _make_job(
            title="Software Engineer",
            location="Mumbai, Maharashtra, India",
            experience_required="0-1 years",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REJECT"
        assert "Mumbai" in reason or "preferred locations" in reason
        assert flt.is_match(job) is False


class TestGate2ScopingAndCompanyHistory:
    """Tests for Task 11 ADDITIONS Part A & C: Gate 2 scoping, company history, and all failing rules."""

    def test_posted_days_ago_not_matched_as_years(self):
        desc = "Software Development Engineer at Adobe. Location: Noida, India. Posted: Posted 30+ Days Ago."
        val, snippet = scan_description_experience(desc)
        assert val is None
        assert snippet is None

    def test_company_history_phrases_ignored(self):
        samples = [
            "We have 30+ years of innovation in the technology sector.",
            "Serving global enterprise customers for over 50 years across 100 countries.",
            "Founded in 1993, since 1995 we have delivered world-class solutions.",
            "Intel has over 50 years of leadership in semiconductor technology.",
            "Celebrating over 30 years in business as an industry pioneer.",
        ]
        for s in samples:
            val, snippet = scan_description_experience(s)
            assert val is None, f"Expected None for company history '{s}', got {val} with snippet '{snippet}'"

    def test_above_15_years_treated_as_parse_error_never_rejects(self, flt, caplog):
        desc = "Qualifications: Must have minimum 25+ years of software architecture experience."
        import logging
        with caplog.at_level(logging.WARNING):
            val, snippet = scan_description_experience(desc)
        assert val is None
        assert any("above cutoff (15)" in r.message or "parse error" in r.message for r in caplog.records)

        # Job classification should not REJECT on Gate 2 when > 15 years
        job = _make_job(
            title="Software Engineer",
            location="Bangalore, Karnataka, India",
            experience_required="Not Specified",
            description="Qualifications: Must have minimum 25+ years of software architecture experience.",
        )
        decision, reason = flt.classify_job(job)
        # Should be REVIEW (experience not stated), NOT REJECT
        assert decision == "REVIEW"
        assert "25" not in reason

    def test_qualifications_section_extraction(self):
        full_text = (
            "About Us:\n"
            "We are a leading tech company with 40 years of innovation.\n\n"
            "Basic Qualifications:\n"
            "- Bachelor's degree in CS\n"
            "- 3+ years of experience in Python\n\n"
            "Preferred Qualifications:\n"
            "- Master's degree\n"
            "- 8+ years of experience in distributed systems\n"
        )
        res = extract_qualifications_section(full_text)
        assert res is not None
        sec, offset = res
        assert "3+ years" in sec
        assert "40 years of innovation" not in sec

        val, snippet = scan_description_experience(full_text)
        assert val == 3
        assert "3+" in snippet

    def test_candidate_tied_phrases_outside_section(self):
        # Description without explicit header, but with candidate-tied phrase
        desc1 = "In this role, you have 4+ years of experience in backend development."
        val1, snip1 = scan_description_experience(desc1)
        assert val1 == 4

        desc2 = "A minimum of 5 years of software engineering experience is expected."
        val2, snip2 = scan_description_experience(desc2)
        assert val2 == 5

        # Ambiguous phrase not candidate-tied and not in qualifications section
        desc3 = "Our platform has processed data for 10 years."
        val3, snip3 = scan_description_experience(desc3)
        assert val3 is None

    def test_matched_snippet_written_into_decision_reason(self, flt):
        job = _make_job(
            title="Software Engineer",
            location="Bangalore, Karnataka, India",
            experience_required="Not Specified",
            description="Requirements: 4+ years of experience in software development.",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REJECT"
        assert "requires 4+ years" in reason
        assert "('4+ years" in reason or "4+ years of experience" in reason

    def test_all_failing_rules_accumulated(self, flt):
        # Job failing both location (Mumbai) and seniority marker ("Lead")
        job = _make_job(
            title="Lead Software Engineer",
            location="Mumbai, Maharashtra, India",
            experience_required="0-1 years",
        )
        decision, reason = flt.classify_job(job)
        assert decision == "REJECT"
        all_rules = job.extra_metadata.get("all_failing_rules")
        assert all_rules is not None
        assert "location" in all_rules
        assert "seniority marker" in all_rules or "Lead" in all_rules
        assert ";" in all_rules  # Semicolon-separated list of all failing rules

