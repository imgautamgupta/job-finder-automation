"""
Regression tests for audit-identified filter and matcher issues.
Run with: pytest tests/test_audit_regression.py -v

Coverage:
  - Role match gaps: Backend Engineer, Machine Learning Engineer, SDE variants, DS/ML Intern
  - Remote eligibility bug: Singapore, Turkiye fallback
  - Negative keyword precision: Senior/Manager/Director/Lead correctly excluded
  - Location handling: Gurugram India exclusion, Noida/Delhi/Bangalore/Ahmedabad pass
"""

import unicodedata
import pytest

from app.config.settings import get_settings
from app.models.job import Job
from app.models.profile import JobProfile
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher, is_india_eligible_remote, has_explicit_seniority_experience


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(**kwargs):
    """Build a minimal JobProfile with test-safe defaults matching the audit findings."""
    defaults = dict(
        target_roles=[
            "Software Engineer", "Backend Developer", "Backend Engineer",
            "Machine Learning Engineer", "ML Engineer", "AI Engineer",
            "SDE", "SDE Intern", "DS/ML Intern",
            "Python Developer", "Full Stack Developer", "Web Developer",
        ],
        preferred_locations=["Delhi", "Noida", "Bangalore", "Bengaluru",
                             "Ahmedabad", "India", "Remote"],
        negative_keywords=["Senior", "Lead", "Principal", "Staff", "Manager",
                           "Director", "Architect", "5+ years", "7+ years", "10+ years"],
        preferences={"remote_allowed": True, "internship_allowed": True,
                     "fresher_allowed": True, "entry_level_allowed": True},
    )
    defaults.update(kwargs)
    return JobProfile(**defaults)


def _job(title, location, **kwargs):
    return Job(
        title=title, company="TestCo", location=location,
        source="greenhouse",
        url="https://test.example.com/" + title.replace(" ", "-"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Role match gap regression tests (Bug A fixes)
# ---------------------------------------------------------------------------

class TestRoleMatchGaps:
    """Roles previously excluded by NO_ROLE_MATCH that should pass after Bug A fix."""

    def test_backend_engineer_passes_role_check(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Backend Engineer", "Bangalore, India")) is True

    def test_backend_engineer_python_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Backend Engineer (Python)", "Bengaluru, Karnataka, India")) is True

    def test_backend_engineer_ruby_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Backend Engineer (Ruby)", "Bangalore; India")) is True

    def test_machine_learning_engineer_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Machine Learning Engineer", "Bangalore, India")) is True

    def test_machine_learning_engineer_leveled_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Machine Learning Engineer (L3)", "Hybrid in Bengaluru, India")) is True

    def test_sde_ii_passes_role_check(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("SDE II", "Noida, Uttar Pradesh")) is True

    def test_sde_iii_passes_role_check(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("SDE III", "Bangalore, India")) is True

    def test_sde_iv_passes_role_check(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("SDE IV", "Bangalore, India")) is True

    def test_sde_2_infra_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("SDE 2 Infra", "Noida, Uttar Pradesh")) is True

    def test_ds_ml_intern_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("DS/ML Intern", "Hybrid in Bengaluru, India")) is True

    def test_ai_engineer_still_passes(self):
        """Regression guard: AI Engineer was already passing."""
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("AI Engineer", "Bangalore, India")) is True

    def test_agentic_ai_engineer_still_passes(self):
        """Regression guard: Agentic AI Engineer was already passing."""
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Agentic AI Engineer", "Bangalore, India; India")) is True

    def test_software_development_engineer_intern_passes(self):
        """Regression guard: Software Development Engineer Intern was already passing."""
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job(
            "Software Development Engineer Intern",
            "Onsite in Bangalore; Hybrid in Bengaluru, India",
        )) is True

    def test_ldap_software_engineer_india_remote_passes(self):
        """Regression guard: LDAP Software Engineer - India was already passing."""
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("LDAP Software Engineer - India", "Bangalore, India - Remote")) is True

    def test_sde_boundary_rejects_unrelated_substrings(self):
        """Requirement #10 & Task A: 'SDE' alias must not match substrings inside words."""
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Residential Maintenance Tech", "Bangalore, India")) is False
        assert flt.is_match(_job("Inside Sales Specialist", "Bangalore, India")) is False
        assert flt.is_match(_job("Misdemeanor Defense Specialist", "Bangalore, India")) is False


# ---------------------------------------------------------------------------
# 2. Negative keyword precision guard
# ---------------------------------------------------------------------------

class TestNegativeKeywordPrecision:
    """Senior/Manager/Director/Lead must continue to exclude correctly."""

    def test_senior_backend_engineer_excluded(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Senior Backend Engineer", "Bangalore, India")) is False

    def test_senior_ml_engineer_excluded(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Senior Machine Learning Engineer", "Bengaluru, Karnataka, India")) is False

    def test_engineering_manager_excluded(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Engineering Manager", "Bangalore, India")) is False

    def test_ai_engineering_manager_excluded(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("AI Engineering Manager", "Bangalore, India")) is False

    def test_lead_data_engineer_excluded(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Lead Data Engineer", "Bangalore, India")) is False

    def test_director_of_engineering_excluded(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Director of Engineering", "Bangalore, India")) is False

    def test_staff_applied_scientist_excluded(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Staff Applied Scientist", "Remote")) is False

    def test_senior_in_description_only_does_not_exclude(self):
        """Junior role mentioning senior in description must NOT be excluded."""
        flt = JobFilter(profile=_make_profile())
        job = _job(
            "Backend Engineer", "Bangalore, India",
            description="You will collaborate with senior engineers on the platform team.",
        )
        assert flt.is_match(job) is True

    def test_explicit_5plus_years_in_description_excludes(self):
        """Explicit '5+ years required' in description must exclude (existing rule guard)."""
        flt = JobFilter(profile=_make_profile())
        job = _job(
            "Software Engineer", "Noida, Uttar Pradesh",
            description="Minimum 5+ years of experience required in distributed systems.",
        )
        assert flt.is_match(job) is False

    def test_company_history_does_not_exclude(self):
        """'10 years of experience' about a company must NOT exclude."""
        flt = JobFilter(profile=_make_profile())
        job = _job(
            "Python Developer", "Delhi",
            description="Our team has over 10 years of experience building fintech products.",
        )
        assert flt.is_match(job) is True


# ---------------------------------------------------------------------------
# 3. is_india_eligible_remote() regression tests (Bug B fixes)
# ---------------------------------------------------------------------------

class TestIsIndiaEligibleRemote:

    # -- Should remain True (India-eligible) --

    def test_bangalore_india_remote_is_eligible(self):
        assert is_india_eligible_remote("Bangalore, India - Remote") is True

    def test_delhi_india_remote_is_eligible(self):
        assert is_india_eligible_remote("Delhi, India - Remote") is True

    def test_noida_india_remote_is_eligible(self):
        assert is_india_eligible_remote("Noida, Uttar Pradesh - Remote") is True

    def test_worldwide_no_foreign_is_eligible(self):
        assert is_india_eligible_remote("Remote - Worldwide") is True

    def test_globally_no_foreign_is_eligible(self):
        assert is_india_eligible_remote("Remote Globally") is True

    def test_bengaluru_india_remote_is_eligible(self):
        assert is_india_eligible_remote("Bengaluru, India - Remote") is True

    # -- Should remain False (foreign-only) --

    def test_us_remote_not_eligible(self):
        assert is_india_eligible_remote("Remote - US") is False

    def test_canada_remote_not_eligible(self):
        assert is_india_eligible_remote("Remote - Canada") is False

    def test_uk_remote_not_eligible(self):
        assert is_india_eligible_remote("Remote - UK") is False

    def test_multi_foreign_remote_not_eligible(self):
        assert is_india_eligible_remote(
            "Remote, Canada; Remote, Poland; Remote, United Kingdom"
        ) is False

    def test_sf_bay_area_remote_not_eligible(self):
        assert is_india_eligible_remote(
            "Remote in San Francisco Bay Area, Los Angeles, Seattle"
        ) is False

    # -- Bug-fix assertions (these require the fix to be applied) --

    def test_singapore_remote_not_eligible(self):
        """Bug B: Remote - Singapore must NOT be India-eligible (fallback was True)."""
        assert is_india_eligible_remote("Remote - Singapore") is False

    def test_turkiye_remote_ascii_not_eligible(self):
        """Bug B+C: Turkiye (ASCII) must NOT be India-eligible."""
        assert is_india_eligible_remote("Ankara, Turkiye - Remote") is False

    def test_turkiye_remote_unicode_not_eligible(self):
        """Bug C: Turkiye (Unicode u-umlaut) must NOT be India-eligible."""
        assert is_india_eligible_remote("Ankara, T\u00fcrkiye - Remote") is False

    def test_japan_remote_not_eligible(self):
        assert is_india_eligible_remote("Remote - Japan") is False

    def test_australia_remote_not_eligible(self):
        assert is_india_eligible_remote("Remote - Australia") is False

    def test_spain_remote_not_eligible(self):
        assert is_india_eligible_remote("Remote - Spain") is False

    def test_korea_remote_not_eligible(self):
        assert is_india_eligible_remote("Remote - Korea") is False

    def test_uae_remote_not_eligible(self):
        assert is_india_eligible_remote("Remote - UAE") is False

    def test_south_africa_remote_not_eligible(self):
        assert is_india_eligible_remote("Remote - South Africa") is False

    def test_turkiye_remote_nfd_not_eligible(self):
        """Task C: NFD decomposed Türkiye string must be normalized and rejected."""
        nfd_loc = unicodedata.normalize("NFD", "Ankara, Türkiye - Remote")
        assert is_india_eligible_remote(nfd_loc) is False

    def test_turkiye_remote_corrupted_replacement_char_not_eligible(self):
        """JumpCloud database variant with replacement char must be rejected."""
        assert is_india_eligible_remote("Ankara, T\ufffdrkiye - Remote") is False

    def test_unknown_remote_region_not_eligible(self):
        """Unknown remote regions with qualifiers must not silently default to India-eligible."""
        assert is_india_eligible_remote("Remote - NowhereLand") is False
        assert is_india_eligible_remote("NowhereLand - Remote") is False

    def test_bare_remote_preserved_eligible(self):
        """Bare remote without foreign qualifier preserves India eligibility."""
        assert is_india_eligible_remote("Remote") is True
        assert is_india_eligible_remote("Fully Remote") is True

    def test_non_remote_bangalore_not_eligible(self):
        """Non-remote office location must return False from is_india_eligible_remote."""
        assert is_india_eligible_remote("Bangalore, India") is False

    def test_empty_location_not_eligible(self):
        assert is_india_eligible_remote("") is False
        assert is_india_eligible_remote(None) is False


# ---------------------------------------------------------------------------
# 4. Location filter pass/fail (filter.py location check section)
# ---------------------------------------------------------------------------

class TestLocationFilter:

    def test_bangalore_onsite_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Software Engineer", "Bengaluru, Karnataka, India")) is True

    def test_bengaluru_hybrid_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Software Engineer", "Hybrid in Bengaluru, India")) is True

    def test_noida_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Backend Engineer", "Noida, Uttar Pradesh")) is True

    def test_delhi_ncr_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Backend Engineer", "Delhi NCR")) is True

    def test_ahmedabad_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Software Engineer", "Ahmedabad, Gujarat")) is True

    def test_gurugram_india_excluded(self):
        """Gurugram is in unrelated_cities; must NOT match India-broad fallback."""
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Software Engineer", "Gurugram; Gurugram, Haryana, India")) is False

    def test_bangalore_india_remote_passes(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Software Engineer", "Bangalore, India - Remote")) is True

    def test_foreign_remote_fails_location(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job(
            "Software Engineer",
            "Remote, Canada; Remote, Poland; Remote, United Kingdom",
        )) is False

    def test_us_only_job_fails(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Software Engineer", "United States")) is False

    def test_mumbai_not_preferred(self):
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Software Engineer", "Mumbai, Maharashtra")) is False

    def test_bengaluru_blr_notation_passes(self):
        """Non-standard 'Bengaluru - BLR1; Bengaluru - BLR2' format must pass."""
        flt = JobFilter(profile=_make_profile())
        assert flt.is_match(_job("Software Engineer", "Bengaluru - BLR1; Bengaluru - BLR2")) is True


# ---------------------------------------------------------------------------
# 5. has_explicit_seniority_experience() precision
# ---------------------------------------------------------------------------

class TestSeniorityExperienceDetection:

    def test_minimum_5_years_detected(self):
        assert has_explicit_seniority_experience(
            "Minimum 5 years of experience required in backend development."
        ) is True

    def test_5plus_years_required_detected(self):
        assert has_explicit_seniority_experience("5+ years of experience required in Python.") is True

    def test_at_least_7_years_detected(self):
        assert has_explicit_seniority_experience(
            "At least 7 years of experience in machine learning."
        ) is True

    def test_company_history_not_detected(self):
        assert has_explicit_seniority_experience(
            "Our team has 10 years of experience in the industry."
        ) is False

    def test_0_to_2_years_not_detected(self):
        assert has_explicit_seniority_experience("0-2 years of experience preferred.") is False

    def test_empty_text_not_detected(self):
        assert has_explicit_seniority_experience("") is False
        assert has_explicit_seniority_experience(None) is False


# ---------------------------------------------------------------------------
# 6. Experience scoring precision (Task C)
# ---------------------------------------------------------------------------

class TestExperienceScoring:
    """Experience scorer should handle 2 years, 0-2 years, up to 2 years safely without false penalties."""

    def test_0_to_2_years_scores_full_points(self):
        matcher = JobMatcher(profile=_make_profile())
        job = _job(
            "Backend Engineer", "Bangalore, India",
            experience_required="0-2 years",
            description="Looking for passionate engineers.",
        )
        res = matcher.match(job)
        assert res.experience_score == 10
        assert res.experience_match is True

    def test_up_to_2_years_in_description_scores_full_points(self):
        matcher = JobMatcher(profile=_make_profile())
        job = _job(
            "Backend Engineer", "Bangalore, India",
            description="Candidate should have up to 2 years of relevant experience in Python.",
        )
        res = matcher.match(job)
        assert res.experience_score == 10
        assert res.experience_match is True

    def test_1_to_2_years_scores_full_points(self):
        matcher = JobMatcher(profile=_make_profile())
        job = _job(
            "Machine Learning Engineer", "Bangalore, India",
            description="1-2 years experience in deep learning preferred.",
        )
        res = matcher.match(job)
        assert res.experience_score == 10
        assert res.experience_match is True

    def test_casual_mention_of_2_years_not_penalized(self):
        matcher = JobMatcher(profile=_make_profile())
        job = _job(
            "Software Engineer", "Bangalore, India",
            description="Our startup was founded 2 years ago and we have grown to 50 engineers.",
        )
        res = matcher.match(job)
        # Should NOT be penalized to 0; awards unspecified/general 5 points
        assert res.experience_score == 5
        assert res.experience_match is False

    def test_sde_iii_scores_zero_experience(self):
        matcher = JobMatcher(profile=_make_profile())
        job = _job(
            "SDE III", "Bangalore, India",
            description="Own architecture and high-throughput systems.",
        )
        res = matcher.match(job)
        assert res.experience_score == 0
        assert res.experience_match is False

    def test_sde_iv_scores_zero_experience(self):
        matcher = JobMatcher(profile=_make_profile())
        job = _job(
            "SDE IV", "Bangalore, India",
            description="Drive technical roadmap across multiple orgs.",
        )
        res = matcher.match(job)
        assert res.experience_score == 0
        assert res.experience_match is False

    def test_explicit_senior_requirement_scores_zero(self):
        matcher = JobMatcher(profile=_make_profile())
        job = _job(
            "Backend Engineer", "Bangalore, India",
            description="Requires at least 5 years of production experience in Python.",
        )
        res = matcher.match(job)
        assert res.experience_score == 0
        assert res.experience_match is False


# ---------------------------------------------------------------------------
# 7. Real profile.json configuration integration
# ---------------------------------------------------------------------------

class TestRealProfileIntegration:
    """Validate that actual data/profile.json successfully matches all target aliases and excludes senior roles."""

    @pytest.fixture
    def real_filter(self):
        settings = get_settings()
        profile = settings.load_profile()
        return JobFilter(profile=profile)

    def test_backend_engineer_python_matches_real_profile(self, real_filter):
        job = _job("Backend Engineer (Python)", "Bangalore, India")
        assert real_filter.is_match(job) is True

    def test_backend_engineer_ruby_matches_real_profile(self, real_filter):
        job = _job("Backend Engineer (Ruby)", "Bangalore, India")
        assert real_filter.is_match(job) is True

    def test_machine_learning_engineer_matches_real_profile(self, real_filter):
        job = _job("Machine Learning Engineer", "Bangalore, India")
        assert real_filter.is_match(job) is True

    def test_machine_learning_engineer_l3_matches_real_profile(self, real_filter):
        job = _job("Machine Learning Engineer (L3)", "Hybrid in Bengaluru, India")
        assert real_filter.is_match(job) is True

    def test_ds_ml_intern_matches_real_profile(self, real_filter):
        job = _job("DS/ML Intern", "Hybrid in Bengaluru, India")
        assert real_filter.is_match(job) is True

    def test_software_development_engineer_intern_matches_real_profile(self, real_filter):
        job = _job("Software Development Engineer Intern", "Bangalore, India")
        assert real_filter.is_match(job) is True

    def test_sde_ii_matches_real_profile(self, real_filter):
        job = _job("SDE II", "Noida, Uttar Pradesh")
        assert real_filter.is_match(job) is True

    def test_senior_backend_engineer_excluded_by_real_profile(self, real_filter):
        job = _job("Senior Backend Engineer", "Bangalore, India")
        assert real_filter.is_match(job) is False

    def test_engineering_manager_excluded_by_real_profile(self, real_filter):
        job = _job("Engineering Manager", "Bangalore, India")
        assert real_filter.is_match(job) is False

