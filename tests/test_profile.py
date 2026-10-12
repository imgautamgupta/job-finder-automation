"""Unit tests for the User Profile and Search Criteria configuration system (Phase 2)."""

import json
import tempfile
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.config.settings import get_settings
from app.models.profile import JobProfile, SearchPreferences


def test_valid_profile_loads_successfully():
    """Test 1: Verify the project's data/profile.json loads and validates successfully."""
    settings = get_settings()
    profile = settings.load_profile()

    assert isinstance(profile, JobProfile)
    assert len(profile.target_roles) > 0
    assert len(profile.preferred_locations) > 0
    assert len(profile.skills) > 0
    assert len(profile.negative_keywords) > 0
    assert isinstance(profile.preferences, SearchPreferences)


def test_target_roles_loaded_correctly():
    """Test 2: Verify target roles match expected titles and have extra whitespace trimmed."""
    settings = get_settings()
    profile = settings.load_profile()

    expected_sample_roles = [
        "Python Developer",
        "Backend Developer",
        "Software Engineer",
        "Full Stack Developer",
        "ML Engineer",
        "AI Engineer",
        "SDE Intern",
    ]
    for role in expected_sample_roles:
        assert role in profile.target_roles

    # Verify whitespace trimming validator
    test_profile = JobProfile(target_roles=["  Python Developer  ", " Backend Developer "])
    assert test_profile.target_roles == ["Python Developer", "Backend Developer"]


def test_locations_loaded_correctly():
    """Test 3: Verify preferred locations are loaded correctly."""
    settings = get_settings()
    profile = settings.load_profile()

    assert "Delhi" in profile.preferred_locations
    assert "Noida" in profile.preferred_locations
    assert "Bangalore" in profile.preferred_locations
    assert "Bengaluru" in profile.preferred_locations
    assert "Ahmedabad" in profile.preferred_locations
    assert "Remote" in profile.preferred_locations
    assert "India" in profile.preferred_locations


def test_skills_loaded_correctly():
    """Test 4: Verify technical skills and combined positive keywords are loaded."""
    settings = get_settings()
    profile = settings.load_profile()

    sample_skills = [
        "Python",
        "FastAPI",
        "React",
        "PostgreSQL",
        "Machine Learning",
        "Docker" if "Docker" in profile.skills else "Git",
    ]
    for skill in sample_skills:
        assert skill in profile.skills

    # Verify all_positive_keywords combines skills and positive_keywords
    all_kws = profile.all_positive_keywords
    assert "Python" in all_kws
    assert "AI" in all_kws or "Artificial Intelligence" in all_kws


def test_negative_keywords_loaded_correctly():
    """Test 5: Verify excluded negative roles and keywords are loaded."""
    settings = get_settings()
    profile = settings.load_profile()

    sample_negative_kws = [
        "Senior",
        "Lead",
        "Principal",
        "Director",
        "Architect",
        "10+ years",
    ]
    for neg_kw in sample_negative_kws:
        assert neg_kw in profile.negative_keywords


def test_invalid_profile_data_raises_validation_error():
    """Test 6: Verify invalid data types raise useful Pydantic validation errors."""
    # target_roles must be a list
    with pytest.raises((ValidationError, TypeError)):
        JobProfile.model_validate({"target_roles": "not-a-list"})

    # list items must be strings
    with pytest.raises((ValidationError, TypeError)):
        JobProfile.model_validate({"skills": [123, 456]})

    # preferences must adhere to schema
    with pytest.raises((ValidationError, TypeError)):
        JobProfile.model_validate({"preferences": {"remote_allowed": "not-a-boolean-val"}})


def test_missing_profile_sections_defaults():
    """Test 7: Verify missing optional sections receive sensible defaults."""
    minimal_profile = JobProfile.model_validate({"target_roles": ["Python Developer"]})

    assert minimal_profile.target_roles == ["Python Developer"]
    assert minimal_profile.preferred_locations == []
    assert minimal_profile.skills == []
    assert minimal_profile.negative_keywords == []
    assert minimal_profile.preferences.remote_allowed is True
    assert minimal_profile.preferences.internship_allowed is True
    assert minimal_profile.preferences.fresher_allowed is True


def test_profile_file_errors():
    """Test error handling when loading from non-existent or malformed file."""
    with pytest.raises(FileNotFoundError):
        JobProfile.from_file("non_existent_profile_12345.json")

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
        tmp.write("{ invalid json syntax ...")
        tmp_path = Path(tmp.name)

    try:
        with pytest.raises(ValueError, match="Malformed JSON"):
            JobProfile.from_file(tmp_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
