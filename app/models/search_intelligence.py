"""Data models for Phase 13 Job Search Intelligence & Source Optimization."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RecommendationPriority(str, Enum):
    """Priority levels for intelligence recommendations and search rankings."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    MONITOR = "MONITOR"


class SourceActionRecommendation(str, Enum):
    """Recommended search effort action for a job source connector."""
    INCREASE_SEARCH_DEPTH = "INCREASE_SEARCH_DEPTH"
    MAINTAIN_SEARCH_DEPTH = "MAINTAIN_SEARCH_DEPTH"
    REDUCE_SEARCH_DEPTH = "REDUCE_SEARCH_DEPTH"
    MONITOR = "MONITOR"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DataConfidence(str, Enum):
    """Statistical confidence level protecting against small-dataset overfitting."""
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # < 5 jobs
    LIMITED_DATA = "LIMITED_DATA"            # 5-9 jobs
    ACTIONABLE_DATA = "ACTIONABLE_DATA"      # 10+ jobs


class StrategyStatus(str, Enum):
    """Overall health and operational status of current job search strategy."""
    HEALTHY = "HEALTHY"
    DEVELOPING = "DEVELOPING"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    DATA_LIMITED = "DATA_LIMITED"


class SearchGapType(str, Enum):
    """Category of underrepresented job search coverage."""
    ROLE_GAP = "ROLE_GAP"
    LOCATION_GAP = "LOCATION_GAP"
    ROLE_LOCATION_GAP = "ROLE_LOCATION_GAP"


class SourceSearchPerformance(BaseModel):
    """Detailed performance and optimization metrics for an individual source connector."""
    source: str
    jobs_found: int = 0
    relevant_jobs: int = 0
    recommended_jobs: int = 0
    applied_jobs: int = 0
    interview_jobs: int = 0
    offer_jobs: int = 0
    relevance_rate: Optional[float] = None
    recommendation_rate: Optional[float] = None
    application_rate: Optional[float] = None
    interview_rate: Optional[float] = None
    offer_rate: Optional[float] = None
    source_quality_score: Optional[float] = None
    quality_label: str = "Insufficient data"
    location_coverage: int = 0
    preferred_location_jobs: int = 0
    preferred_location_rate: Optional[float] = None
    india_eligible_jobs: int = 0
    india_eligible_rate: Optional[float] = None
    foreign_remote_jobs: int = 0
    confidence: DataConfidence = DataConfidence.INSUFFICIENT_DATA
    recommendation: SourceActionRecommendation = SourceActionRecommendation.INSUFFICIENT_DATA
    recommendation_priority: RecommendationPriority = RecommendationPriority.MONITOR
    recommendation_reason: str = ""
    reliability: str = "Unknown"


class RoleSearchPerformance(BaseModel):
    """Search yield and alignment metrics for a target profile role."""
    role_name: str
    jobs_found: int = 0
    relevant_jobs: int = 0
    recommended_jobs: int = 0
    applied_jobs: int = 0
    interview_jobs: int = 0
    offer_jobs: int = 0
    relevance_rate: Optional[float] = None
    recommendation_rate: Optional[float] = None
    avg_match_score: Optional[float] = None
    avg_readiness_score: Optional[float] = None
    avg_resume_alignment_score: Optional[float] = None
    confidence: DataConfidence = DataConfidence.INSUFFICIENT_DATA
    priority: RecommendationPriority = RecommendationPriority.MONITOR
    notes: str = ""


class LocationSearchPerformance(BaseModel):
    """Search yield and geographic alignment metrics for a preferred location."""
    location_name: str
    jobs_found: int = 0
    relevant_jobs: int = 0
    recommended_jobs: int = 0
    applied_jobs: int = 0
    interview_jobs: int = 0
    offer_jobs: int = 0
    india_eligible_remote: int = 0
    foreign_remote: int = 0
    relevance_rate: Optional[float] = None
    recommendation_rate: Optional[float] = None
    avg_match_score: Optional[float] = None
    avg_readiness_score: Optional[float] = None
    confidence: DataConfidence = DataConfidence.INSUFFICIENT_DATA
    priority: RecommendationPriority = RecommendationPriority.MONITOR
    notes: str = ""


class RoleLocationPerformance(BaseModel):
    """Matrix cell analyzing productivity of Role × Location combination."""
    role_name: str
    location_name: str
    jobs_found: int = 0
    relevant_jobs: int = 0
    recommended_jobs: int = 0
    applied_jobs: int = 0
    avg_match_score: Optional[float] = None
    avg_readiness_score: Optional[float] = None
    confidence: DataConfidence = DataConfidence.INSUFFICIENT_DATA
    priority: RecommendationPriority = RecommendationPriority.MONITOR
    status_label: str = ""


class SourceRolePerformance(BaseModel):
    """Productivity breakdown of Source × Role pairs."""
    source: str
    role_name: str
    jobs_found: int = 0
    relevant_jobs: int = 0
    recommended_jobs: int = 0
    avg_match_score: Optional[float] = None
    assessment: str = "insufficient"
    confidence: DataConfidence = DataConfidence.INSUFFICIENT_DATA


class SourceLocationPerformance(BaseModel):
    """Productivity breakdown of Source × Location pairs."""
    source: str
    location_name: str
    jobs_found: int = 0
    relevant_jobs: int = 0
    recommended_jobs: int = 0
    assessment: str = "insufficient"
    confidence: DataConfidence = DataConfidence.INSUFFICIENT_DATA


class SearchGap(BaseModel):
    """Underrepresented role or location area with insufficient historical data."""
    gap_type: SearchGapType
    item_name: str
    details: str
    suggestion: str


class SourceBudgetRecommendation(BaseModel):
    """Recommended proportional allocation of daily search effort (sums to 100%)."""
    source: str
    allocated_percentage: float
    basis: str
    confidence: DataConfidence


class SourceRecommendation(BaseModel):
    """Actionable recommendation for a specific source connector."""
    source: str
    action: SourceActionRecommendation
    priority: RecommendationPriority
    reason: str
    confidence: DataConfidence


class SearchRecommendation(BaseModel):
    """Deterministic, explainable strategy recommendation item."""
    category: str = Field(description="SOURCE, ROLE, LOCATION, COMBINATION, GAP, BUDGET, HEALTH")
    title: str
    recommendation: str
    priority: RecommendationPriority = RecommendationPriority.MEDIUM
    reason: str
    confidence: DataConfidence = DataConfidence.INSUFFICIENT_DATA


class SearchStrategy(BaseModel):
    """Synthesized deterministic search plan for the next collection cycle."""
    overall_status: StrategyStatus = StrategyStatus.HEALTHY
    data_confidence: DataConfidence = DataConfidence.INSUFFICIENT_DATA
    summary: str
    ranked_priorities: List[str] = Field(default_factory=list)
    key_actions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class SearchIntelligenceReport(BaseModel):
    """Unified Phase 13 Search Intelligence report."""
    total_jobs: int = 0
    relevant_jobs: int = 0
    recommended_jobs: int = 0
    applied_jobs: int = 0
    data_confidence: DataConfidence = DataConfidence.INSUFFICIENT_DATA
    strategy: SearchStrategy
    sources: List[SourceSearchPerformance] = Field(default_factory=list)
    roles: List[RoleSearchPerformance] = Field(default_factory=list)
    locations: List[LocationSearchPerformance] = Field(default_factory=list)
    role_locations: List[RoleLocationPerformance] = Field(default_factory=list)
    source_roles: List[SourceRolePerformance] = Field(default_factory=list)
    source_locations: List[SourceLocationPerformance] = Field(default_factory=list)
    search_gaps: List[SearchGap] = Field(default_factory=list)
    budget_allocations: List[SourceBudgetRecommendation] = Field(default_factory=list)
    source_recommendations: List[SourceRecommendation] = Field(default_factory=list)
    recommendations: List[SearchRecommendation] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
