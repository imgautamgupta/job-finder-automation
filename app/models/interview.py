"""Data models and enumerations for Phase 11 Interview Tracking & Preparation."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InterviewStage(str, Enum):
    """Permitted interview stages."""
    HR = "HR"
    TECHNICAL_SCREENING = "Technical Screening"
    CODING_ROUND = "Coding Round"
    TECHNICAL_INTERVIEW = "Technical Interview"
    MANAGERIAL = "Managerial"
    SYSTEM_DESIGN = "System Design"
    BEHAVIORAL = "Behavioral"
    FINAL = "Final"
    OTHER = "Other"


class InterviewStatus(str, Enum):
    """Permitted interview schedule and outcome statuses."""
    NOT_SCHEDULED = "NOT_SCHEDULED"
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    RESCHEDULED = "RESCHEDULED"


class InterviewPrepStatus(str, Enum):
    """Permitted interview preparation progress statuses."""
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    COMPLETED = "COMPLETED"


class DailyActionPriority(int, Enum):
    """Priority order for the 'What should I work on today?' action plan."""
    INTERVIEW_TODAY = 1
    INTERVIEW_SOON = 2
    FOLLOW_UP_DUE = 3
    URGENT_APPLY = 4
    HIGH_APPLY = 5
    RESUME_PREP_NEEDED = 6
    OTHER_RECOMMENDED = 7


class DailyActionItem(BaseModel):
    """A prioritized actionable task for the user on a given day."""
    priority_rank: int = Field(..., description="Priority tier (1 to 7)")
    priority_label: str = Field(..., description="Human-readable priority title")
    badge_class: str = Field(..., description="CSS class for visual badge styling")
    action_type: str = Field(..., description="Category: INTERVIEW, FOLLOW_UP, APPLY, PREPARE")
    action_title: str = Field(..., description="Summary action headline")
    reason: str = Field(..., description="Deterministic explanation of why this action appears")
    job_id: int = Field(..., description="Database job ID")
    company: str = Field(..., description="Hiring company name")
    title: str = Field(..., description="Position / job title")
    location: Optional[str] = Field(default=None, description="Job location")
    job_url: str = Field(..., description="URL to the job posting")
    action_url: str = Field(..., description="Internal dashboard URL to execute action")
    action_btn_text: str = Field(..., description="Call to action button text")
    match_score: Optional[int] = Field(default=None)
    readiness_score: Optional[int] = Field(default=None)
    due_date: Optional[str] = Field(default=None, description="Due date if applicable (YYYY-MM-DD)")


class TechnicalTopic(BaseModel):
    """A technical skill topic with interview focus areas."""
    skill: str = Field(..., description="Technical skill name")
    category: str = Field(default="Core Skill", description="Skill category")
    focus_points: List[str] = Field(default_factory=list, description="Key concepts likely asked")


class ProjectQuestionSet(BaseModel):
    """Project-based interview talking points and questions."""
    project_name: str = Field(..., description="Name of featured candidate project")
    why_recommended: str = Field(..., description="Why this project aligns with the job")
    technologies: List[str] = Field(default_factory=list, description="Matching technologies")
    discussion_points: List[str] = Field(default_factory=list, description="In-depth technical questions")


class InterviewPreparationPackage(BaseModel):
    """Complete deterministic interview preparation package for a job."""
    job_id: int
    company: str
    title: str
    location: Optional[str] = None
    source: str
    url: str
    match_score: Optional[int] = None
    readiness_score: Optional[int] = None
    resume_alignment_score: Optional[int] = None
    status: str
    
    # 1. Why this job matches
    match_reasons: List[str] = Field(default_factory=list)
    
    # 2. Technical Preparation
    technical_topics: List[TechnicalTopic] = Field(default_factory=list)
    
    # 3. Role-Specific Topics
    role_topics: List[Dict[str, Any]] = Field(default_factory=list)
    
    # 4. Project Questions (based on candidate's real projects)
    project_questions: Optional[ProjectQuestionSet] = None
    
    # 5. Likely Technical Questions (clearly labeled: based on job description)
    likely_technical_questions: List[str] = Field(default_factory=list)
    
    # 6. General HR / Behavioral Questions (clearly labeled: general)
    hr_behavioral_questions: List[str] = Field(default_factory=list)
    
    # 7. Skill Gap Preparation (matched, revise, missing with truthful advice)
    matched_skills: List[str] = Field(default_factory=list)
    skills_to_revise: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    
    # 8. Questions to ask the employer
    questions_to_ask_employer: List[str] = Field(default_factory=list)
    
    # 9. Preparation Checklist
    checklist: List[str] = Field(default_factory=list)
    
    # 10. Interview Tracking Data
    interview_date: Optional[str] = None
    interview_stage: Optional[str] = None
    interview_status: str = "NOT_SCHEDULED"
    interview_notes: Optional[str] = None
    interview_preparation_status: str = "NOT_STARTED"
