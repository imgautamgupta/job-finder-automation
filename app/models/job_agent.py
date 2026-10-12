"""Strongly typed Pydantic models for Phase 14 Advanced Personal Job-Agent Workflow."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentActionType(str, Enum):
    """Categorization of discrete actions managed by the personal job agent."""
    REVIEW_JOB = "REVIEW_JOB"
    SHORTLIST_JOB = "SHORTLIST_JOB"
    PREPARE_RESUME = "PREPARE_RESUME"
    APPLY_MANUALLY = "APPLY_MANUALLY"
    FOLLOW_UP = "FOLLOW_UP"
    PREPARE_INTERVIEW = "PREPARE_INTERVIEW"
    UPDATE_APPLICATION = "UPDATE_APPLICATION"
    REVIEW_ANALYTICS = "REVIEW_ANALYTICS"
    REVIEW_SEARCH_STRATEGY = "REVIEW_SEARCH_STRATEGY"


class AgentActionPriority(str, Enum):
    """Deterministic urgency and priority hierarchy."""
    URGENT = "URGENT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AgentActionStatus(str, Enum):
    """Lifecycle status of a proposed action."""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AgentAction(BaseModel):
    """A single deterministic action proposed for the user's daily plan."""
    id: str
    action_type: AgentActionType
    priority: AgentActionPriority
    status: AgentActionStatus = AgentActionStatus.PENDING
    title: str
    description: str
    reason: str
    job_id: Optional[int] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    match_score: Optional[int] = None
    readiness_score: Optional[int] = None
    resume_score: Optional[int] = None
    lifecycle_status: Optional[str] = None
    due_date: Optional[str] = None
    skills_to_emphasize: List[str] = Field(default_factory=list)
    recommended_project: Optional[str] = None
    checklist: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DailyJobPlan(BaseModel):
    """The unified deterministic daily plan structured by priority tiers."""
    date: str
    actions: List[AgentAction] = Field(default_factory=list)
    urgent_actions: List[AgentAction] = Field(default_factory=list)
    high_actions: List[AgentAction] = Field(default_factory=list)
    medium_actions: List[AgentAction] = Field(default_factory=list)
    low_actions: List[AgentAction] = Field(default_factory=list)
    target_applied_today: int = 0
    target_daily: int = 5
    target_remaining: int = 5
    target_progress_pct: float = 0.0
    streak_days: int = 0


class JobAgentSummary(BaseModel):
    """High-level metrics for today's command center summary."""
    jobs_found_today: int = 0
    relevant_jobs: int = 0
    recommended_jobs: int = 0
    applications_today: int = 0
    target_remaining: int = 0
    interviews_upcoming: int = 0
    follow_ups_due: int = 0
    overdue_actions: int = 0


class JobAgentRecommendation(BaseModel):
    """Job-specific action card providing next steps and preparation guidance."""
    job_id: int
    title: str
    company: str
    location: str
    match_score: int
    readiness_score: int
    resume_alignment_score: int
    priority: AgentActionPriority
    next_action: AgentActionType
    preparation_summary: str
    skills_to_emphasize: List[str] = Field(default_factory=list)
    recommended_project: Optional[str] = None
    application_status: str
    url: Optional[str] = None


class JobAgentReport(BaseModel):
    """Complete unified report delivered to the dashboard and reporting layer."""
    generated_at: str
    summary: JobAgentSummary
    plan: DailyJobPlan
    today_applications: List[JobAgentRecommendation] = Field(default_factory=list)
    resume_prep_jobs: List[JobAgentRecommendation] = Field(default_factory=list)
    interview_prep_jobs: List[Dict[str, Any]] = Field(default_factory=list)
    follow_ups: List[Dict[str, Any]] = Field(default_factory=list)
    search_focus: List[Dict[str, Any]] = Field(default_factory=list)
    safety_notices: List[str] = Field(default_factory=list)
