"""Data models for Phase 10 Resume Intelligence and Application Preparation."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PreparationStatus(str, Enum):
    """Workflow preparation status for high-priority applications."""
    NOT_REVIEWED = "NOT_REVIEWED"
    REVIEWED = "REVIEWED"
    RESUME_READY = "RESUME_READY"
    READY_TO_APPLY = "READY_TO_APPLY"


class CandidateProject(BaseModel):
    """Structured representation of a candidate project."""
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(default=None, description="Overview of the project")
    skills: List[str] = Field(default_factory=list, description="Technologies / skills used")
    highlights: List[str] = Field(default_factory=list, description="Key bullet points or achievements")
    url: Optional[str] = Field(default=None, description="GitHub repository or live demo link")


class CandidateExperience(BaseModel):
    """Structured representation of candidate work or internship experience."""
    title: str = Field(..., description="Role / position title")
    company: Optional[str] = Field(default=None, description="Organization / company name")
    experience_type: str = Field(default="work", description="Type: 'internship', 'work', etc.")
    description: Optional[str] = Field(default=None, description="Overview of role")
    skills: List[str] = Field(default_factory=list, description="Technologies / tools utilized")
    highlights: List[str] = Field(default_factory=list, description="Key bullet points")
    duration: Optional[str] = Field(default=None, description="Dates or duration string")


class ResumeProfile(BaseModel):
    """Structured local representation of a candidate resume."""
    name: Optional[str] = Field(default=None, description="Candidate name if found")
    summary: Optional[str] = Field(default=None, description="Professional summary / objective")
    skills: List[str] = Field(default_factory=list, description="Normalized skills")
    languages: List[str] = Field(default_factory=list, description="Programming languages")
    frameworks: List[str] = Field(default_factory=list, description="Frameworks and libraries")
    databases: List[str] = Field(default_factory=list, description="Databases and storage engines")
    tools: List[str] = Field(default_factory=list, description="Tools, cloud platforms, and utilities")
    experience: List[CandidateExperience] = Field(default_factory=list, description="Work experience items")
    internships: List[CandidateExperience] = Field(default_factory=list, description="Internship items")
    projects: List[CandidateProject] = Field(default_factory=list, description="Featured projects")
    education: List[str] = Field(default_factory=list, description="Education degrees / institutions")
    certifications: List[str] = Field(default_factory=list, description="Certifications and credentials")
    links: List[str] = Field(default_factory=list, description="Portfolio, GitHub, or LinkedIn links")
    source_file: Optional[str] = Field(default=None, description="Source filename or label")
    is_fallback: bool = Field(default=False, description="True if generated from profile.json fallback")


class CandidateProfile(BaseModel):
    """Combined candidate representation fusing profile.json (primary) and resume data."""
    skills: List[str] = Field(default_factory=list, description="All verified candidate skills")
    target_roles: List[str] = Field(default_factory=list, description="Target job positions")
    preferred_locations: List[str] = Field(default_factory=list, description="Preferred locations")
    projects: List[CandidateProject] = Field(default_factory=list, description="Available candidate projects")
    experience: List[CandidateExperience] = Field(default_factory=list, description="Candidate work experience")
    internships: List[CandidateExperience] = Field(default_factory=list, description="Candidate internships")
    resume_profile: Optional[ResumeProfile] = Field(default=None, description="Parsed resume representation")
    source_description: str = Field(default="data/profile.json", description="Human-readable origin description")
    resume_skills_set: List[str] = Field(default_factory=list, description="Skills explicitly visible in resume")


class ResumePreparationAnalysis(BaseModel):
    """Deterministic, explainable job-specific application preparation analysis."""
    job_id: Optional[int] = Field(default=None, description="Database job row ID")
    resume_alignment_score: int = Field(default=0, description="Resume alignment score (0-100)")
    resume_alignment_category: str = Field(default="Low Alignment", description="Categorical rating")
    skills_to_emphasize: List[str] = Field(default_factory=list, description="Skills to emphasize")
    resume_matched_keywords: List[str] = Field(default_factory=list, description="Job keywords visible in resume")
    resume_missing_keywords: List[str] = Field(default_factory=list, description="Job keywords not prominent in resume")
    recommended_project: Optional[str] = Field(default=None, description="Top recommended project name")
    recommended_project_details: Optional[Dict[str, Any]] = Field(default=None, description="Project match reasoning")
    recommended_experience: Optional[str] = Field(default=None, description="Top recommended experience title")
    recommended_experience_details: Optional[Dict[str, Any]] = Field(default=None, description="Experience reasoning")
    resume_concerns: List[str] = Field(default_factory=list, description="Deterministic warnings / concerns")
    resume_suggestions: List[str] = Field(default_factory=list, description="Actionable truthful improvement steps")
    recommended_resume: str = Field(default="Primary Resume", description="Best aligned resume version")
    preparation_status: PreparationStatus = Field(
        default=PreparationStatus.NOT_REVIEWED, description="Application preparation workflow state"
    )
    preparation_notes: Optional[str] = Field(default=None, description="User preparation notes")
    checklist: List[str] = Field(default_factory=list, description="Job-specific application checklist")
