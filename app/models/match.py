"""Pydantic model representing deterministic job matching and scoring results."""

from typing import List
from pydantic import BaseModel, Field, model_validator


class MatchResult(BaseModel):
    """Complete, explainable scoring breakdown for a job against a user profile.

    Attributes:
        score: Total composite score between 0 and 100.
        category: Qualitative match grade ('Excellent', 'Strong', 'Good', 'Possible', 'Not Relevant').
        role_score: Points awarded for role/title alignment (0-40).
        skills_score: Points awarded for technical skills & keywords (0-30).
        location_score: Points awarded for geographic & remote preferences (0-20).
        experience_score: Points awarded for experience level suitability (0-10).
        matched_roles: Target profile roles identified in the posting.
        matched_skills: Profile skills identified in posting text.
        matched_locations: Preferred locations identified in posting.
        experience_match: Whether the job explicitly fits experience criteria.
        matched_keywords: Desirable positive keywords identified.
        excluded_reasons: Diagnostic reasons if negative keywords or conflicts were detected.
    """

    score: int = Field(..., ge=0, le=100, description="Total match score (0-100)")
    category: str = Field(..., description="Match category bucket")
    role_score: int = Field(..., ge=0, le=40, description="Role match score (0-40)")
    skills_score: int = Field(..., ge=0, le=30, description="Skills match score (0-30)")
    location_score: int = Field(..., ge=0, le=20, description="Location match score (0-20)")
    experience_score: int = Field(..., ge=0, le=10, description="Experience match score (0-10)")
    matched_roles: List[str] = Field(default_factory=list, description="Matched target roles")
    matched_skills: List[str] = Field(default_factory=list, description="Matched technical skills")
    matched_locations: List[str] = Field(default_factory=list, description="Matched locations")
    experience_match: bool = Field(default=False, description="Flag for experience suitability")
    matched_keywords: List[str] = Field(default_factory=list, description="Matched positive keywords")
    excluded_reasons: List[str] = Field(default_factory=list, description="Exclusion or penalty reasons")

    @model_validator(mode="after")
    def verify_score_consistency(self) -> "MatchResult":
        """Verify that component scores always sum up exactly to the total score."""
        calculated_total = (
            self.role_score + self.skills_score + self.location_score + self.experience_score
        )
        if self.score != calculated_total:
            raise ValueError(
                f"Inconsistent score: total score {self.score} does not match "
                f"sum of components ({self.role_score} + {self.skills_score} + "
                f"{self.location_score} + {self.experience_score} = {calculated_total})"
            )
        return self
