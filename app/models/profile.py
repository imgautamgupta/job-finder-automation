"""Pydantic models representing user job search preferences and profile."""

from pathlib import Path
from typing import Any, List, Optional, Union
import json

from pydantic import BaseModel, Field, field_validator, model_validator


class SearchPreferences(BaseModel):
    """User-specific flags and search constraints."""

    remote_allowed: bool = Field(
        default=True,
        description="Whether remote positions are accepted"
    )
    internship_allowed: bool = Field(
        default=True,
        description="Whether internship listings should be included"
    )
    fresher_allowed: bool = Field(
        default=True,
        description="Whether fresher openings should be included"
    )
    entry_level_allowed: bool = Field(
        default=True,
        description="Whether entry-level jobs should be included"
    )


class JobProfile(BaseModel):
    """Structured job search profile validating criteria from data/profile.json."""

    target_roles: List[str] = Field(
        default_factory=list,
        description="Target job position titles or roles"
    )
    preferred_locations: List[str] = Field(
        default_factory=list,
        description="Preferred geographic locations or cities"
    )
    experience_levels: List[str] = Field(
        default_factory=list,
        description="Accepted experience levels (e.g. Fresher, Entry Level, 0-1 years)"
    )
    skills: List[str] = Field(
        default_factory=list,
        description="Technical skills and tools"
    )
    positive_keywords: List[str] = Field(
        default_factory=list,
        description="Desirable keywords in job title or description"
    )
    negative_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords or role levels to strictly exclude"
    )
    preferences: SearchPreferences = Field(
        default_factory=SearchPreferences,
        description="Specific search behavior options"
    )

    projects: List[dict] = Field(
        default_factory=list,
        description="Candidate featured projects from profile"
    )
    experience: List[dict] = Field(
        default_factory=list,
        description="Candidate work/internship experience items from profile"
    )

    # Backwards-compatibility helper fields (optional in input)
    keywords: Optional[List[str]] = Field(
        default=None,
        description="Backwards-compatibility alias for positive_keywords"
    )
    remote_only: Optional[bool] = Field(
        default=None,
        description="Backwards-compatibility flag for strictly remote filtering"
    )
    employment_types: Optional[List[str]] = Field(
        default=None,
        description="Backwards-compatibility list of employment types"
    )

    @field_validator(
        "target_roles",
        "preferred_locations",
        "experience_levels",
        "skills",
        "positive_keywords",
        "negative_keywords",
        mode="before",
    )
    @classmethod
    def clean_string_list(cls, v: Any) -> Any:
        """Validate and clean list of strings, stripping extra whitespace."""
        if not isinstance(v, list):
            raise TypeError("Expected a list of strings")
        cleaned: List[str] = []
        for item in v:
            if not isinstance(item, str):
                raise TypeError(f"Item {item!r} is not a string")
            trimmed = item.strip()
            if trimmed:
                cleaned.append(trimmed)
        return cleaned

    @model_validator(mode="after")
    def handle_compatibility_aliases(self) -> "JobProfile":
        """Handle legacy keywords or remote_only fields gracefully."""
        if self.keywords and not self.positive_keywords:
            self.positive_keywords = self.keywords
        if self.remote_only is not None:
            # If remote_only is True, remote_allowed is True
            if self.remote_only:
                self.preferences.remote_allowed = True
        return self

    @property
    def all_positive_keywords(self) -> List[str]:
        """Deduplicated union of skills and positive keywords."""
        seen = set()
        result: List[str] = []
        for kw in self.skills + self.positive_keywords:
            low = kw.lower()
            if low not in seen:
                seen.add(low)
                result.append(kw)
        return result

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "JobProfile":
        """Load and validate profile from a JSON file path.

        Raises:
            FileNotFoundError: If the specified file does not exist.
            ValueError / ValidationError: If JSON syntax or schema validation fails.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Profile configuration file not found at: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON in profile file '{file_path}': {e}") from e

        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON root object (dictionary) in '{file_path}', got {type(data).__name__}")

        return cls.model_validate(data)
