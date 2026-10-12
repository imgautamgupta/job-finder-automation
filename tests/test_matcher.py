"""Unit tests for the Deterministic Job Matching and Scoring Engine (Phase 4)."""

import pytest

from app.config.settings import get_settings
from app.models.job import Job
from app.models.match import MatchResult
from app.models.profile import JobProfile
from app.services.matcher import JobMatcher, get_score_category


@pytest.fixture
def profile():
    """Load user preferences profile."""
    return get_settings().load_profile()


@pytest.fixture
def matcher(profile):
    """Instantiate JobMatcher with loaded profile."""
    return JobMatcher(profile=profile)


# ==============================================================================
# Role Matching Tests (Requirements 1 - 5)
# ==============================================================================

def test_exact_python_developer_match(matcher):
    """Test 1: Exact Python Developer title awards full role score (40)."""
    job = Job(
        source="linkedin",
        title="Python Developer",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/1",
    )
    result = matcher.match(job)
    assert result.role_score == 40
    assert "Python Developer" in result.matched_roles


def test_python_developer_intern_match(matcher):
    """Test 2: Title with Intern variation matches role directly."""
    job = Job(
        source="linkedin",
        title="Python Developer Intern",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/2",
    )
    result = matcher.match(job)
    assert result.role_score == 40
    assert any("Python Developer" in r for r in result.matched_roles)


def test_backend_developer_match(matcher):
    """Test 3: Backend Developer role is directly matched."""
    job = Job(
        source="linkedin",
        title="Backend Developer",
        company="Acme Corp",
        location="Remote",
        url="https://example.com/3",
    )
    result = matcher.match(job)
    assert result.role_score == 40
    assert "Backend Developer" in result.matched_roles


def test_unrelated_role_low_or_zero_score(matcher):
    """Test 4: Unrelated role (e.g. Sales Director) receives 0 role score."""
    job = Job(
        source="linkedin",
        title="Sales Executive / Regional Director",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/4",
    )
    result = matcher.match(job)
    assert result.role_score == 0
    assert len(result.matched_roles) == 0


def test_case_insensitive_role_matching(matcher):
    """Test 5: Case-insensitive title match."""
    job = Job(
        source="linkedin",
        title="pYtHoN dEvElOpEr",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/5",
    )
    result = matcher.match(job)
    assert result.role_score == 40


# ==============================================================================
# Skill Matching Tests (Requirements 6 - 9)
# ==============================================================================

def test_one_matching_skill(matcher):
    """Test 6: Single matching skill awards proportional skill points."""
    job = Job(
        source="linkedin",
        title="Python Developer",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/6",
        description="Looking for candidate knowing Python.",
    )
    result = matcher.match(job)
    assert "Python" in result.matched_skills
    assert result.skills_score == 6


def test_multiple_matching_skills(matcher):
    """Test 7: Multiple matching skills award higher score up to 30 max."""
    job = Job(
        source="linkedin",
        title="Python Developer",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/7",
        description="Requirements: Python, FastAPI, PostgreSQL, Docker, React, Git, MongoDB.",
    )
    result = matcher.match(job)
    assert len(result.matched_skills) >= 5
    assert result.skills_score == 30  # Capped at 30 points


def test_no_matching_skills(matcher):
    """Test 8: No matching skills gives 0 skill score."""
    job = Job(
        source="linkedin",
        title="Accountant",
        company="Finance Co",
        location="Delhi",
        url="https://example.com/8",
        description="Knowledge of QuickBooks, GAAP, Excel ledger.",
    )
    result = matcher.match(job)
    assert result.skills_score == 0
    assert len(result.matched_skills) == 0


def test_duplicate_skills_not_counted_twice(matcher):
    """Test 9: Repetitive mention of same skill is deduplicated."""
    job = Job(
        source="linkedin",
        title="Python Developer",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/9",
        description="Python, Python 3, write Python code with python idioms.",
    )
    result = matcher.match(job)
    assert result.matched_skills.count("Python") == 1
    assert result.skills_score == 6


# ==============================================================================
# Location Matching Tests (Requirements 10 - 13)
# ==============================================================================

def test_delhi_highest_location_score(matcher):
    """Delhi location receives highest location score (20)."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Delhi, India",
        url="https://example.com/delhi",
    )
    result = matcher.match(job)
    assert result.location_score == 20
    assert "Delhi" in result.matched_locations


def test_new_delhi_highest_location_score(matcher):
    """New Delhi location receives highest location score (20)."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="New Delhi, India",
        url="https://example.com/newdelhi",
    )
    result = matcher.match(job)
    assert result.location_score == 20
    assert "Delhi" in result.matched_locations


def test_noida_highest_location_score(matcher):
    """Noida location receives highest location score (20)."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Noida, Uttar Pradesh",
        url="https://example.com/noida",
    )
    result = matcher.match(job)
    assert result.location_score == 20
    assert "Noida" in result.matched_locations


def test_bangalore_location_match(matcher):
    """Bangalore location matches for high location score (18)."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Bangalore, Karnataka",
        url="https://example.com/10",
    )
    result = matcher.match(job)
    assert result.location_score == 18
    assert "Bangalore" in result.matched_locations


def test_bengaluru_matches_bangalore_preference(matcher):
    """Bengaluru matches Bangalore preference with high location score (18)."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Bengaluru, India",
        url="https://example.com/11",
    )
    result = matcher.match(job)
    assert result.location_score == 18
    assert any(loc in ("Bengaluru", "Bangalore") for loc in result.matched_locations)


def test_ahmedabad_medium_location_score(matcher):
    """Ahmedabad location receives medium location score (15)."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Ahmedabad, Gujarat",
        url="https://example.com/ahmedabad",
    )
    result = matcher.match(job)
    assert result.location_score == 15
    assert "Ahmedabad" in result.matched_locations


def test_remote_location_match(matcher):
    """Remote location matches when remote is allowed (18)."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Remote - Work from anywhere",
        url="https://example.com/12",
    )
    result = matcher.match(job)
    assert result.location_score == 18
    assert "Remote" in result.matched_locations


def test_india_broad_fallback_score(matcher):
    """Generic India location receives broad fallback score (12)."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="India",
        url="https://example.com/india",
    )
    result = matcher.match(job)
    assert result.location_score == 12
    assert "India" in result.matched_locations


def test_unrelated_location_gets_zero(matcher):
    """Unrelated international location receives 0 location points."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="London, United Kingdom",
        url="https://example.com/13",
    )
    result = matcher.match(job)
    assert result.location_score == 0
    assert len(result.matched_locations) == 0


def test_unrelated_indian_city_gets_zero(matcher):
    """Unrelated Indian city (e.g. Mumbai) does not falsely trigger India fallback."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Mumbai, Maharashtra, India",
        url="https://example.com/mumbai",
    )
    result = matcher.match(job)
    assert result.location_score == 0
    assert len(result.matched_locations) == 0


def test_pune_india_gets_zero(matcher):
    """Pune, India is an unrelated city and receives 0 location points."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Pune, India",
        url="https://example.com/pune",
    )
    result = matcher.match(job)
    assert result.location_score == 0
    assert len(result.matched_locations) == 0


def test_missing_location_receives_zero_and_no_fallback(matcher):
    """Missing location (None or empty) receives 0 points and no India fallback."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location=None,
        url="https://example.com/none-loc",
    )
    result = matcher.match(job)
    assert result.location_score == 0
    assert len(result.matched_locations) == 0


def test_unknown_location_string_receives_zero(matcher):
    """Unknown / not specified location string receives 0 points and no India fallback."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Unknown",
        url="https://example.com/unknown-loc",
    )
    result = matcher.match(job)
    assert result.location_score == 0
    assert len(result.matched_locations) == 0


def test_pan_india_fallback_score(matcher):
    """Explicit 'Pan India' location receives 12 points broad fallback."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Pan India",
        url="https://example.com/pan-india",
    )
    result = matcher.match(job)
    assert result.location_score == 12
    assert any(loc in ("Pan India", "India") for loc in result.matched_locations)


def test_description_with_india_does_not_falsely_match_location(matcher):
    """Unrelated city with 'India' in job description does not falsely trigger India fallback."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Hyderabad, Telangana",
        url="https://example.com/hyderabad",
        description="We are a leading tech company in India looking for engineers.",
    )
    result = matcher.match(job)
    assert result.location_score == 0
    assert len(result.matched_locations) == 0


def test_location_matching_case_insensitive(matcher):
    """Location matching is case-insensitive for all priority tiers."""
    job_delhi = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="dElHi",
        url="https://example.com/case-delhi",
    )
    assert matcher.match(job_delhi).location_score == 20

    job_blr = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="bEnGaLuRu",
        url="https://example.com/case-blr",
    )
    assert matcher.match(job_blr).location_score == 18

    job_remote = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="rEmOtE",
        url="https://example.com/case-remote",
    )
    assert matcher.match(job_remote).location_score == 18



# ==============================================================================
# Experience Matching Tests (Requirements 14 - 18)
# ==============================================================================

def test_fresher_job_matches(matcher):
    """Test 14: Job suitable for freshers receives full experience score (10)."""
    job = Job(
        source="linkedin",
        title="Junior Software Engineer",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/14",
        experience_required="Fresher / 0-1 years",
    )
    result = matcher.match(job)
    assert result.experience_score == 10
    assert result.experience_match is True


def test_internship_job_matches(matcher):
    """Test 15: Internship job receives full experience points."""
    job = Job(
        source="linkedin",
        title="SDE Intern",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/15",
    )
    result = matcher.match(job)
    assert result.experience_score == 10
    assert result.experience_match is True


def test_entry_level_job_matches(matcher):
    """Test 16: Entry-level designation receives full experience score."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/16",
        description="Entry level role for recent graduates.",
    )
    result = matcher.match(job)
    assert result.experience_score == 10
    assert result.experience_match is True


def test_senior_job_experience_score_zero(matcher):
    """Test 17: Senior / 5+ years job receives 0 experience score."""
    job = Job(
        source="linkedin",
        title="Staff Software Engineer",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/17",
        experience_required="7+ years of experience required",
    )
    result = matcher.match(job)
    assert result.experience_score == 0
    assert result.experience_match is False


def test_missing_experience_not_treated_as_perfect(matcher):
    """Test 18: Missing experience is not awarded full 10 points."""
    job = Job(
        source="linkedin",
        title="Software Engineer",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/18",
        experience_required=None,
        description="General software developer opening.",
    )
    result = matcher.match(job)
    assert result.experience_score < 10
    assert result.experience_match is False


# ==============================================================================
# Category Mapping Tests (Requirements 19 - 23)
# ==============================================================================

@pytest.mark.parametrize(
    "score,expected_category",
    [
        (100, "Excellent"),
        (90, "Excellent"),
        (89, "Strong"),
        (80, "Strong"),
        (79, "Good"),
        (70, "Good"),
        (69, "Possible"),
        (60, "Possible"),
        (59, "Not Relevant"),
        (0, "Not Relevant"),
    ],
)
def test_category_thresholds(score, expected_category):
    """Tests 19-23: Verify explicit category boundaries."""
    assert get_score_category(score) == expected_category


# ==============================================================================
# Score Consistency & Explainability (Requirements 24 - 29)
# ==============================================================================

def test_score_consistency_and_bounds(matcher):
    """Test 24 & 25: Components always add up to total score and stay in [0, 100]."""
    job = Job(
        source="linkedin",
        title="Python Developer",
        company="Acme Corp",
        location="Bangalore",
        url="https://example.com/24",
        description="FastAPI, PostgreSQL, React, Git.",
        experience_required="0-1 years",
    )
    result = matcher.match(job)

    # Consistency check
    assert (
        result.score
        == result.role_score
        + result.skills_score
        + result.location_score
        + result.experience_score
    )
    assert 0 <= result.score <= 100


def test_explainability_entities_returned(matcher):
    """Test 26-28: Matched roles, skills, and locations are populated."""
    job = Job(
        source="naukri",
        title="Full Stack Developer",
        company="Fintech Corp",
        location="Bangalore",
        url="https://naukri.com/job/26",
        description="Working with React, TypeScript, Python, and SQL.",
        experience_required="Fresher",
    )
    result = matcher.match(job)

    assert "Full Stack Developer" in result.matched_roles
    assert "Python" in result.matched_skills
    assert "React" in result.matched_skills
    assert any(loc in ("Bangalore", "Bengaluru") for loc in result.matched_locations)


def test_exclusion_reasons_returned(matcher):
    """Test 29: Negative keywords populate excluded_reasons."""
    job = Job(
        source="linkedin",
        title="Lead Software Engineer",
        company="Big Tech",
        location="Bangalore",
        url="https://example.com/29",
        description="Requires 10+ years of architecture experience.",
    )
    result = matcher.match(job)

    assert len(result.excluded_reasons) > 0
    assert any("Lead" in r or "10+ years" in r for r in result.excluded_reasons)
    assert result.category in ("Not Relevant", "Possible")


# =====================================================================
# Phase 6F Tests — India-Aware Remote & Seniority Distinctions
# =====================================================================
def test_phase_6f_india_remote_score(matcher):
    """India-specific remote receives Remote score of 18."""
    job = Job(
        source="lever",
        title="Software Engineer",
        company="Acme Corp",
        location="Remote, India",
        url="https://example.com/in-rem1",
    )
    result = matcher.match(job)
    assert result.location_score == 18
    assert "Remote" in result.matched_locations


def test_phase_6f_india_hyphen_remote_score(matcher):
    """'India - Remote' receives Remote score of 18."""
    job = Job(
        source="lever",
        title="Software Engineer",
        company="Acme Corp",
        location="India - Remote",
        url="https://example.com/in-rem2",
    )
    result = matcher.match(job)
    assert result.location_score == 18
    assert "Remote" in result.matched_locations


def test_phase_6f_bangalore_remote_score(matcher):
    """'Bangalore, India - Remote' matches Bangalore preference (18)."""
    job = Job(
        source="lever",
        title="Software Engineer",
        company="Acme Corp",
        location="Bangalore, India - Remote",
        url="https://example.com/blr-rem",
    )
    result = matcher.match(job)
    assert result.location_score == 18
    assert "Bangalore" in result.matched_locations


def test_phase_6f_foreign_remote_scores_zero(matcher):
    """Foreign-only remote locations receive 0 location score for India search."""
    for foreign_loc in [
        "Remote, Canada",
        "Remote, Poland",
        "Remote, UK",
        "Remote - US",
        "Ankara, Türkiye - Remote",
    ]:
        job = Job(
            source="greenhouse",
            title="Software Engineer",
            company="Acme Corp",
            location=foreign_loc,
            url="https://example.com/foreign",
        )
        result = matcher.match(job)
        assert result.location_score == 0, f"Expected 0 for {foreign_loc}, got {result.location_score}"
        assert "Remote" not in result.matched_locations


def test_phase_6f_worldwide_remote_score(matcher):
    """Explicitly worldwide remote receives Remote score of 18."""
    job = Job(
        source="greenhouse",
        title="Software Engineer",
        company="Acme Corp",
        location="Remote - Worldwide",
        url="https://example.com/worldwide",
    )
    result = matcher.match(job)
    assert result.location_score == 18
    assert "Remote" in result.matched_locations


def test_phase_6f_missing_location_scores_zero(matcher):
    """Missing or None location receives 0 location score."""
    job = Job(
        source="lever",
        title="Software Engineer",
        company="Acme Corp",
        location=None,
        url="https://example.com/noloc",
    )
    result = matcher.match(job)
    assert result.location_score == 0
    assert result.matched_locations == []


def test_phase_6f_unrelated_indian_city_no_fallback(matcher):
    """Mumbai does not receive the generic India fallback score of 12."""
    job = Job(
        source="naukri",
        title="Software Engineer",
        company="Acme Corp",
        location="Mumbai, India",
        url="https://example.com/mumbai",
    )
    result = matcher.match(job)
    assert result.location_score == 0
    assert "India" not in result.matched_locations
