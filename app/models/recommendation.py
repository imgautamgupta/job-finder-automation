"""Data models for Phase 9 job recommendations, readiness scores, and gap analyses."""

from typing import List, Optional
from pydantic import BaseModel, Field

from app.models.job import ApplicationPriority


class ApplicationRecommendation(BaseModel):
    """Detailed deterministic application recommendation analysis for a job."""

    job_id: Optional[int] = Field(default=None, description="Database job ID if persisted")
    match_score: int = Field(default=0, description="Inherited deterministic match score (0-100)")
    match_category: str = Field(default="Not Relevant", description="Qualitative match category")
    application_readiness_score: int = Field(default=0, description="Application readiness score (0-100)")
    application_priority: ApplicationPriority = Field(
        default=ApplicationPriority.SKIP, description="Application priority level"
    )
    matched_skills: List[str] = Field(
        default_factory=list, description="Skills present in profile and matched in job"
    )
    missing_skills: List[str] = Field(
        default_factory=list, description="Key skills requested by job but missing from profile"
    )
    critical_gaps: List[str] = Field(
        default_factory=list, description="Critical required skill gaps"
    )
    moderate_gaps: List[str] = Field(
        default_factory=list, description="Moderate skill gaps"
    )
    minor_gaps: List[str] = Field(
        default_factory=list, description="Minor/supporting skill gaps"
    )
    recommendation_reasons: List[str] = Field(
        default_factory=list, description="Deterministic reasons why this job matches"
    )
    risk_reasons: List[str] = Field(
        default_factory=list, description="Deterministic potential rejection concerns"
    )
    profile_alignment: str = Field(
        default="Weak alignment", description="Profile/resume alignment summary"
    )
    checklist: List[str] = Field(
        default_factory=list, description="Application preparation checklist"
    )

    @property
    def match_reasons(self) -> List[str]:
        """Alias for recommendation_reasons."""
        return self.recommendation_reasons
