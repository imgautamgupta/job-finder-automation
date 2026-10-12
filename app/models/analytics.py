"""Data models for Phase 12 Application Analytics & Optimization."""

from typing import List, Optional
from pydantic import BaseModel, Field


class FunnelStageCount(BaseModel):
    """Cumulative & current counts across job search pipeline stages."""
    jobs_found: int = Field(default=0, description="Total jobs stored in database")
    relevant: int = Field(default=0, description="Jobs with match_score >= 60")
    recommended: int = Field(default=0, description="Jobs with application_priority in URGENT, HIGH, NORMAL")
    applied: int = Field(default=0, description="Jobs with status APPLIED, INTERVIEW, or OFFER")
    interview: int = Field(default=0, description="Jobs reaching interview stage or with interview records")
    offer: int = Field(default=0, description="Jobs reaching status OFFER")
    rejected: int = Field(default=0, description="Jobs marked REJECTED")
    not_interested: int = Field(default=0, description="Jobs marked NOT_INTERESTED")


class ConversionRates(BaseModel):
    """Conversion percentages across pipeline stages, handling zero denominators safely."""
    application_rate: Optional[float] = Field(default=None, description="Applied / Relevant * 100")
    recommendation_to_app_rate: Optional[float] = Field(default=None, description="Applied / Recommended * 100")
    interview_rate: Optional[float] = Field(default=None, description="Interviews / Applied * 100")
    offer_rate: Optional[float] = Field(default=None, description="Offers / Applied * 100")
    interview_to_offer_rate: Optional[float] = Field(default=None, description="Offers / Interviews * 100")


class SourceMetric(BaseModel):
    """Performance breakdown for a job board or ATS connector."""
    source: str
    jobs_found: int = 0
    relevant: int = 0
    recommended: int = 0
    applied: int = 0
    interview: int = 0
    offer: int = 0
    relevance_rate: Optional[float] = None
    application_rate: Optional[float] = None
    interview_rate: Optional[float] = None
    quality_score: Optional[float] = None
    quality_label: str = "Insufficient data"


class RoleMetric(BaseModel):
    """Performance breakdown for normalized target role families."""
    role_name: str
    jobs_found: int = 0
    relevant: int = 0
    recommended: int = 0
    applied: int = 0
    interview: int = 0
    offer: int = 0
    interview_rate: Optional[float] = None


class LocationMetric(BaseModel):
    """Performance breakdown for preferred geographic locations."""
    location_name: str
    jobs_found: int = 0
    relevant: int = 0
    recommended: int = 0
    applied: int = 0
    interview: int = 0
    offer: int = 0
    application_rate: Optional[float] = None
    interview_rate: Optional[float] = None


class ScoreBucketMetric(BaseModel):
    """Performance breakdown across score ranges (Match, Readiness, Resume Alignment)."""
    bucket_label: str
    jobs_count: int = 0
    applied: int = 0
    interview: int = 0
    offer: int = 0
    interview_rate: Optional[float] = None


class DailyActivityRow(BaseModel):
    """Application & discovery activity aggregated by date."""
    date_str: str
    jobs_found: int = 0
    relevant: int = 0
    applied: int = 0
    interviews: int = 0
    offers: int = 0


class WeeklyComparison(BaseModel):
    """Summary comparing current week performance against the previous week."""
    current_week_jobs: int = 0
    current_week_relevant: int = 0
    current_week_recommended: int = 0
    current_week_applied: int = 0
    current_week_interviews: int = 0
    current_week_offers: int = 0
    current_week_rejected: int = 0
    current_week_avg_match: float = 0.0
    current_week_avg_readiness: float = 0.0
    current_week_avg_resume_alignment: float = 0.0

    previous_week_jobs: int = 0
    previous_week_relevant: int = 0
    previous_week_recommended: int = 0
    previous_week_applied: int = 0
    previous_week_interviews: int = 0
    previous_week_offers: int = 0
    previous_week_rejected: int = 0
    previous_week_avg_match: float = 0.0
    previous_week_avg_readiness: float = 0.0
    previous_week_avg_resume_alignment: float = 0.0


class DailyTargetStatus(BaseModel):
    """Tracking progress toward daily manual application goals."""
    target: int = 5
    applied_today: int = 0
    remaining: int = 5
    seven_day_avg: float = 0.0
    achievement_percentage: float = 0.0


class ApplicationStreak(BaseModel):
    """Consecutive days with at least 1 manual application recorded."""
    current_streak: int = 0
    longest_streak: int = 0


class OptimizationInsight(BaseModel):
    """Deterministic, explainable strategy feedback item."""
    category: str = Field(description="POSITIVE, WARNING, SOURCE, VOLUME, LIMITATION, SUGGESTION")
    title: str
    message: str
    actionable: bool = False


class SkillMetric(BaseModel):
    """Observed skills across applied and interview stages."""
    skill: str
    applied_count: int = 0
    interview_count: int = 0
    offer_count: int = 0


class AccessibilityMetric(BaseModel):
    """Comparison of Easy Apply vs direct portal application outcomes."""
    type_label: str
    relevant: int = 0
    applied: int = 0
    interview: int = 0
    offer: int = 0


class ExperienceMetric(BaseModel):
    """Comparison of experience level requirement outcomes."""
    level_label: str
    relevant: int = 0
    applied: int = 0
    interview: int = 0


class AnalyticsReport(BaseModel):
    """Unified report containing all Phase 12 analytics aggregates."""
    funnel: FunnelStageCount
    conversion_rates: ConversionRates
    period: str = "all"
    sources: List[SourceMetric] = Field(default_factory=list)
    roles: List[RoleMetric] = Field(default_factory=list)
    locations: List[LocationMetric] = Field(default_factory=list)
    match_buckets: List[ScoreBucketMetric] = Field(default_factory=list)
    readiness_buckets: List[ScoreBucketMetric] = Field(default_factory=list)
    resume_buckets: List[ScoreBucketMetric] = Field(default_factory=list)
    easy_apply: List[AccessibilityMetric] = Field(default_factory=list)
    experience: List[ExperienceMetric] = Field(default_factory=list)
    skills: List[SkillMetric] = Field(default_factory=list)
    daily_activity: List[DailyActivityRow] = Field(default_factory=list)
    weekly: Optional[WeeklyComparison] = None
    daily_target: DailyTargetStatus = Field(default_factory=DailyTargetStatus)
    streak: ApplicationStreak = Field(default_factory=ApplicationStreak)
    insights: List[OptimizationInsight] = Field(default_factory=list)
    is_small_sample: bool = False
