"""Tests for Task 15: Updated profile, experience rules, GenAI skill scoring."""
import pytest
from app.models.job import Job
from app.models.profile import JobProfile
from app.services.filter import JobFilter, match_level_title, match_below_profile_title


@pytest.fixture
def task15_profile():
    return JobProfile(
        target_roles=["Software Engineer", "AI Engineer", "GenAI Engineer", "SDE"],
        preferred_locations=["Bengaluru", "Delhi", "Noida", "Remote", "India"],
        skills=["Python", "RAG", "LangChain", "LLM", "FastAPI"],
        genai_skills=["RAG", "LangChain", "LLM"],
        negative_keywords=["Senior", "Lead", "Principal"],
        match_max_years=2,
        review_max_years=3,
    )


def make_job(title, exp_required=None, desc="", location="Bengaluru, India"):
    return Job(
        source="test",
        title=title,
        company="TestCo",
        location=location,
        url="https://example.com/job/1",
        description=desc,
        experience_required=exp_required,
    )


# --- Experience gate tests ---

def test_stated_2_years_is_match(task15_profile):
    """Stated minimum 2 years -> MATCH."""
    flt = JobFilter(profile=task15_profile)
    job = make_job("Software Engineer", exp_required="2 years")
    decision, reason = flt.classify_job(job)
    assert decision == "MATCH", f"Got {decision}: {reason}"
    assert "2 years" in reason or "Stated minimum 2" in reason


def test_stated_3_years_is_review(task15_profile):
    """Stated minimum 3 years -> REVIEW with 'stretch' reason."""
    flt = JobFilter(profile=task15_profile)
    job = make_job("Software Engineer", exp_required="3 years")
    decision, reason = flt.classify_job(job)
    assert decision == "REVIEW", f"Got {decision}: {reason}"
    assert "stretch" in reason.lower() or "3 years" in reason


def test_stated_4_years_is_reject(task15_profile):
    """Stated minimum 4 years -> REJECT."""
    flt = JobFilter(profile=task15_profile)
    job = make_job("Software Engineer", exp_required="4 years")
    decision, reason = flt.classify_job(job)
    assert decision == "REJECT", f"Got {decision}: {reason}"
    assert "4" in reason


def test_no_experience_stated_is_review(task15_profile):
    """No experience stated -> REVIEW 'experience not stated'."""
    flt = JobFilter(profile=task15_profile)
    job = make_job("Software Engineer", desc="Join our team to build amazing products.")
    decision, reason = flt.classify_job(job)
    assert decision == "REVIEW", f"Got {decision}: {reason}"
    assert "experience not stated" in reason.lower()


# --- Level title tests ---

def test_sde_ii_level_title_not_rejected():
    """SDE II should NOT be rejected by LEVEL_TITLE_PATTERN (goes to experience gate)."""
    result = match_level_title("SDE II")
    assert result is None, f"SDE II should not match LEVEL_TITLE_PATTERN, got: {result}"


def test_l5_level_title_not_rejected():
    """L5 should NOT be rejected by LEVEL_TITLE_PATTERN."""
    result = match_level_title("Software Engineer L5")
    assert result is None, f"L5 should not match LEVEL_TITLE_PATTERN, got: {result}"


def test_sde_iii_level_title_rejected():
    """SDE III should still be rejected by LEVEL_TITLE_PATTERN."""
    result = match_level_title("SDE III")
    assert result is not None, "SDE III should match LEVEL_TITLE_PATTERN"


def test_sde_ii_with_2_years_is_match(task15_profile):
    """'SDE II' title with 2 years experience stated -> MATCH (not rejected by level, exp OK)."""
    flt = JobFilter(profile=task15_profile)
    job = make_job("SDE II", exp_required="2 years")
    decision, reason = flt.classify_job(job)
    assert decision == "MATCH", f"Got {decision}: {reason}"


def test_sde_ii_no_experience_is_review(task15_profile):
    """'SDE II' title with no experience stated -> REVIEW."""
    flt = JobFilter(profile=task15_profile)
    job = make_job("SDE II", desc="Join our team.")
    decision, reason = flt.classify_job(job)
    assert decision == "REVIEW", f"Got {decision}: {reason}"


def test_sde_iii_is_reject(task15_profile):
    """'SDE III' title -> REJECT (level title)."""
    flt = JobFilter(profile=task15_profile)
    job = make_job("SDE III")
    decision, reason = flt.classify_job(job)
    assert decision == "REJECT", f"Got {decision}: {reason}"


# --- Below-profile title tests ---

def test_intern_title_is_reject(task15_profile):
    """'Software Engineer Intern' -> REJECT 'below profile level'."""
    flt = JobFilter(profile=task15_profile)
    job = make_job("Software Engineer Intern")
    decision, reason = flt.classify_job(job)
    assert decision == "REJECT", f"Got {decision}: {reason}"
    assert "below profile level" in reason.lower() or "below" in reason.lower()


def test_internship_title_is_reject(task15_profile):
    """'AI Internship' -> REJECT."""
    flt = JobFilter(profile=task15_profile)
    job = make_job("AI Internship")
    decision, reason = flt.classify_job(job)
    assert decision == "REJECT", f"Got {decision}: {reason}"


def test_trainee_title_is_reject(task15_profile):
    """'Software Trainee' -> REJECT."""
    flt = JobFilter(profile=task15_profile)
    job = make_job("Software Trainee")
    decision, reason = flt.classify_job(job)
    assert decision == "REJECT", f"Got {decision}: {reason}"


def test_match_below_profile_title_function():
    """match_below_profile_title returns match for intern/trainee/apprentice."""
    assert match_below_profile_title("Software Engineer Intern") is not None
    assert match_below_profile_title("AI Internship") is not None
    assert match_below_profile_title("Management Trainee") is not None
    assert match_below_profile_title("Apprentice Developer") is not None
    assert match_below_profile_title("Software Engineer") is None
    assert match_below_profile_title("Graduate Engineer") is None


# --- GenAI skill scoring test ---

def test_genai_skills_raise_score():
    """Jobs with GenAI skills (RAG, LangChain, LLM) should score higher than jobs with regular skills."""
    from app.services.matcher import JobMatcher

    profile = JobProfile(
        target_roles=["AI Engineer"],
        preferred_locations=["Bengaluru", "India"],
        skills=["Python", "RAG", "LangChain", "LLM", "FastAPI"],
        genai_skills=["RAG", "LangChain", "LLM"],
        positive_keywords=[],
        negative_keywords=[],
        match_max_years=2,
        review_max_years=3,
    )
    matcher = JobMatcher(profile=profile)

    genai_job = Job(
        source="test",
        title="AI Engineer",
        company="AIStartup",
        location="Bengaluru, India",
        url="https://example.com/j1",
        description="Build RAG pipelines using LangChain and LLM APIs for enterprise customers.",
    )
    regular_job = Job(
        source="test",
        title="AI Engineer",
        company="AIStartup",
        location="Bengaluru, India",
        url="https://example.com/j2",
        description="Build Python FastAPI backend services for enterprise customers.",
    )

    genai_result = matcher.match(genai_job)
    regular_result = matcher.match(regular_job)

    assert genai_result.score > regular_result.score, (
        f"GenAI job score {genai_result.score} should be > regular job score {regular_result.score}"
    )
    assert genai_result.skills_score > regular_result.skills_score


# --- Profile file tests ---

def test_profile_file_loads():
    """Profile file at data/profile.json loads successfully with new fields."""
    import json
    from pathlib import Path
    profile_path = Path("data/profile.json")
    assert profile_path.exists(), "data/profile.json must exist"
    
    with open(profile_path, "r") as f:
        data = json.load(f)
    
    profile = JobProfile.model_validate(data)
    assert profile.match_max_years == 2
    assert profile.review_max_years == 3
    assert len(profile.target_roles) >= 10
    assert len(profile.skills) >= 20
    assert len(profile.genai_skills) >= 5


def test_profile_no_personal_data():
    """Profile file must not contain personal identifiers."""
    import json
    from pathlib import Path
    profile_path = Path("data/profile.json")
    assert profile_path.exists()
    
    with open(profile_path, "r") as f:
        content = f.read()
    
    # Check for common personal data patterns
    import re
    # Phone numbers
    assert not re.search(r'\b\d{10}\b', content), "Profile contains 10-digit phone number"
    assert not re.search(r'\+91[-\s]?\d{10}', content), "Profile contains Indian phone number"
    # Email addresses
    assert not re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', content), "Profile contains email"
    # Common personal keywords should not appear as values (names)
    # Note: We check the values, not keys
    data = json.loads(content)
    flat_text = json.dumps(data)
    # Check for LinkedIn URLs with personal profiles
    assert "linkedin.com/in/" not in flat_text, "Profile contains LinkedIn personal URL"
    assert "github.com/" not in flat_text or "github.com/actions" in flat_text, "Profile may contain GitHub personal URL"
