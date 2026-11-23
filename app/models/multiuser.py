"""Pydantic data models for multi-user architecture and candidate isolation (Phase 3B)."""

from datetime import datetime
from enum import Enum
import json
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class UserRole(str, Enum):
    """Access control roles for the platform."""
    ADMIN = "ADMIN"
    CANDIDATE = "CANDIDATE"


class User(BaseModel):
    """User account entity representing a registered candidate or administrator."""
    id: Optional[int] = None
    email: str
    password_hash: str
    full_name: str
    role: UserRole = UserRole.CANDIDATE
    is_active: bool = True
    created_at: Optional[Union[datetime, str]] = None
    updated_at: Optional[Union[datetime, str]] = None


class CandidateProfile(BaseModel):
    """Extracted professional profile details linked to a specific user."""
    id: Optional[int] = None
    user_id: int
    headline: Optional[str] = None
    total_experience_years: float = 0.0
    current_title: Optional[str] = None
    education_level: Optional[str] = None
    technical_skills: List[str] = Field(default_factory=list)
    domain_skills: List[str] = Field(default_factory=list)
    raw_extracted_text: Optional[str] = None
    created_at: Optional[Union[datetime, str]] = None
    updated_at: Optional[Union[datetime, str]] = None

    @field_validator("technical_skills", "domain_skills", mode="before")
    @classmethod
    def parse_json_list(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except Exception:
                return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, (list, tuple, set)):
            return [str(x) for x in v]
        return []


class CandidatePreferences(BaseModel):
    """Job search constraints and target criteria for a specific candidate."""
    id: Optional[int] = None
    user_id: int
    target_roles: List[str] = Field(default_factory=list)
    preferred_locations: List[str] = Field(default_factory=list)
    location_scope: str = "PREF_ONLY"
    work_arrangement: str = "ANY"
    max_required_years: int = 2
    match_min_score: int = 50
    notice_period: str = "IMMEDIATE"
    created_at: Optional[Union[datetime, str]] = None
    updated_at: Optional[Union[datetime, str]] = None

    @field_validator("target_roles", "preferred_locations", mode="before")
    @classmethod
    def parse_json_list(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except Exception:
                return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, (list, tuple, set)):
            return [str(x) for x in v]
        return []


class ResumeRecord(BaseModel):
    """Metadata and storage tracking for uploaded candidate resumes."""
    id: Optional[int] = None
    user_id: int
    original_filename: str
    stored_filename: str
    file_path: str
    file_size_bytes: int
    mime_type: str
    parsed_data_json: Optional[str] = None
    is_primary: bool = True
    uploaded_at: Optional[Union[datetime, str]] = None


class JobMatchRecord(BaseModel):
    """Evaluated match score and fit analysis for a user-job pair."""
    id: Optional[int] = None
    user_id: int
    job_id: int
    match_score: int = 0
    match_category: str = "NO_FIT"
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    match_reason: Optional[str] = None
    resume_alignment_score: int = 0
    evaluated_at: Optional[Union[datetime, str]] = None

    @field_validator("matched_skills", "missing_skills", mode="before")
    @classmethod
    def parse_json_list(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except Exception:
                return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, (list, tuple, set)):
            return [str(x) for x in v]
        return []


class SavedJobRecord(BaseModel):
    """Bookmarked job listing with private candidate notes."""
    id: Optional[int] = None
    user_id: int
    job_id: int
    candidate_notes: Optional[str] = None
    created_at: Optional[Union[datetime, str]] = None


class ApplicationRecord(BaseModel):
    """Application pipeline tracking for a candidate applying to a job."""
    id: Optional[int] = None
    user_id: int
    job_id: int
    resume_id: Optional[int] = None
    status: str = "APPLIED"
    applied_at: Optional[Union[datetime, str]] = None
    interview_date: Optional[Union[datetime, str]] = None
    interview_round: Optional[str] = None
    notes: Optional[str] = None
    salary_offered: Optional[str] = None
    created_at: Optional[Union[datetime, str]] = None
    updated_at: Optional[Union[datetime, str]] = None

