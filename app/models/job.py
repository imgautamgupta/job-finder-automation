"""Standardized Job model representing a job listing across different sources."""

from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Dict, List, Optional
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from pydantic import BaseModel, Field, field_validator, model_validator

# Common tracking and referral parameters to strip when normalizing URLs
TRACKING_PARAMS = {
    # General UTM & Analytics
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_name",
    "_ga",
    "_gl",
    "mc_eid",
    "mc_cid",
    # Ad click IDs
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "msclkid",
    "yclid",
    # Platform-specific tracking/referral parameters
    "ref",
    "refid",
    "trackingid",
    "trk",
    "trkinfo",
    "midtoken",
    "currentjobid",
    "orgId",
    "position",
    "pageNum",
    "src",
}


def normalize_url(url: str) -> str:
    """Normalize a job URL into its canonical form.

    Strips tracking, referral, and analytics query parameters while preserving
    legitimate query parameters required to identify the posting. Sorts remaining
    query parameters deterministically.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        if not parsed.scheme or not parsed.netloc:
            return url.strip()

        # Filter out known tracking parameters (case-insensitive check)
        query_items = parse_qsl(parsed.query, keep_blank_values=False)
        filtered_query = [
            (k, v) for k, v in query_items if k.lower() not in TRACKING_PARAMS
        ]

        # Sort parameters deterministically
        filtered_query.sort(key=lambda item: (item[0], item[1]))
        new_query = urlencode(filtered_query)

        # Normalize path: remove redundant trailing slash if path length > 1
        clean_path = parsed.path.rstrip("/") if len(parsed.path) > 1 else parsed.path

        # Reassemble URL without fragments (fragments are client-side only)
        return urlunparse(
            (parsed.scheme.lower(), parsed.netloc.lower(), clean_path, parsed.params, new_query, "")
        )
    except Exception:
        return url.strip()


def generate_job_fingerprint(
    source: str,
    title: str,
    company: str,
    location: Optional[str],
    canonical_url: str,
) -> str:
    """Generate a deterministic SHA-256 fingerprint from core job attributes."""
    norm_source = source.strip().lower()
    norm_title = " ".join(title.strip().lower().split())
    norm_company = " ".join(company.strip().lower().split())
    norm_location = " ".join((location or "").strip().lower().split())
    norm_url = normalize_url(canonical_url).lower()
    payload = f"{norm_source}|{norm_title}|{norm_company}|{norm_location}|{norm_url}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JobStatus(str, Enum):
    """Permitted tracking status values for job listings."""
    NEW = "NEW"
    VIEWED = "VIEWED"
    SHORTLISTED = "SHORTLISTED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    NOT_INTERESTED = "NOT_INTERESTED"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"


class ApplicationPriority(str, Enum):
    """Permitted application priority levels for job recommendations (Phase 9)."""
    URGENT = "URGENT"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"
    SKIP = "SKIP"


class Job(BaseModel):
    """Standardized representation of a job listing across all sources.

    Attributes:
        id: Database primary key ID if stored in SQLite.
        source: Name of the platform where the job was found (e.g. 'linkedin', 'naukri').
        source_job_id: Unique identifier assigned by the source platform.
        job_id: Alias for source_job_id for backwards compatibility.
        title: Job position or title.
        company: Hiring organization name.
        location: City, state, country, or 'Remote' (None/Unknown if missing).
        url: Direct canonical link to the job post.
        description: Full or snippet description text.
        easy_apply: Flag indicating if one-click or Easy Apply is available.
        date_posted: When the job was posted as indicated on the source platform.
        date_found: Timestamp when our system discovered the job (defaults to UTC now).
        employment_type: E.g., 'Full-time', 'Part-time', 'Contract', 'Internship'.
        experience_required: Human-readable or standardized experience requirements.
        salary: Salary range or compensation details if provided.
        fingerprint: Deterministic SHA-256 hash representing stable job identity.
        created_at: Database record creation timestamp.
        updated_at: Database record last updated timestamp.
        extra_metadata: Optional dictionary for platform-specific raw attributes.
    """

    id: Optional[int] = Field(default=None, description="Database row ID")
    source: str = Field(..., description="Source platform name (e.g., linkedin, naukri)")
    source_job_id: Optional[str] = Field(default=None, description="Platform specific Source Job ID")
    job_id: Optional[str] = Field(default=None, description="Alias for source_job_id")
    title: str = Field(..., description="Job title or role name")
    company: str = Field(..., description="Hiring company name")
    location: Optional[str] = Field(default=None, description="Job location or Remote")
    url: str = Field(..., description="Canonical URL to the job post")
    description: Optional[str] = Field(default=None, description="Job description text")
    easy_apply: Optional[bool] = Field(default=False, description="Whether easy/direct apply is available")
    date_posted: Optional[str] = Field(default=None, description="Relative or absolute posted date")
    date_found: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the job was discovered"
    )
    employment_type: Optional[str] = Field(default=None, description="Employment type (e.g. Full-time)")
    experience_required: Optional[str] = Field(default=None, description="Experience requirements")
    salary: Optional[str] = Field(default=None, description="Compensation information if available")
    fingerprint: Optional[str] = Field(default=None, description="Deterministic SHA-256 fingerprint")
    match_score: Optional[int] = Field(default=None, description="Deterministic match score (0-100)")
    match_category: Optional[str] = Field(default=None, description="Match category grade")
    matched_roles: List[str] = Field(default_factory=list, description="Matched target roles")
    matched_skills: List[str] = Field(default_factory=list, description="Matched skills")
    matched_locations: List[str] = Field(default_factory=list, description="Matched locations")
    experience_match: bool = Field(default=False, description="Whether experience criteria matched")
    excluded_reasons: List[str] = Field(default_factory=list, description="Exclusion or penalty reasons")
    created_at: Optional[datetime] = Field(default=None, description="Database creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Database updated timestamp")
    extra_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Raw source metadata")
    status: JobStatus = Field(default=JobStatus.NEW, description="Application tracking status")
    status_updated_at: Optional[datetime] = Field(default=None, description="Timestamp of last status update")
    first_seen_at: Optional[datetime] = Field(default=None, description="Timestamp when job was first observed")
    last_seen_at: Optional[datetime] = Field(default=None, description="Timestamp when job was last observed")
    last_seen_run_id: Optional[str] = Field(default=None, description="Pipeline run ID when job was last observed")
    notes: Optional[str] = Field(default=None, description="User notes or comments on this job")

    # Phase 9 Recommendation & Application Workflow fields
    application_readiness_score: Optional[int] = Field(default=None, description="Application readiness score (0-100)")
    application_priority: Optional[ApplicationPriority] = Field(default=None, description="Application priority level")
    missing_skills: List[str] = Field(default_factory=list, description="Missing technical skills required by job")
    critical_gaps: List[str] = Field(default_factory=list, description="Critical missing skills")
    moderate_gaps: List[str] = Field(default_factory=list, description="Moderate missing skills")
    minor_gaps: List[str] = Field(default_factory=list, description="Minor missing skills")
    recommendation_reasons: List[str] = Field(default_factory=list, description="Deterministic reasons why job matches")
    risk_reasons: List[str] = Field(default_factory=list, description="Deterministic potential rejection concerns")
    profile_alignment: Optional[str] = Field(default=None, description="Profile alignment classification")
    checklist: List[str] = Field(default_factory=list, description="Application checklist")
    follow_up_date: Optional[str] = Field(default=None, description="Follow-up due date (YYYY-MM-DD)")
    follow_up_notes: Optional[str] = Field(default=None, description="Follow-up notes")

    # Phase 10 Resume Intelligence & Preparation Workflow fields
    resume_alignment_score: Optional[int] = Field(default=None, description="Deterministic resume alignment score (0-100)")
    resume_alignment_category: Optional[str] = Field(default=None, description="Resume alignment category")
    skills_to_emphasize: List[str] = Field(default_factory=list, description="Skills to emphasize for this job")
    resume_matched_keywords: List[str] = Field(default_factory=list, description="Job keywords visible in resume")
    resume_missing_keywords: List[str] = Field(default_factory=list, description="Job keywords not visible in resume")
    recommended_project: Optional[str] = Field(default=None, description="Recommended project to highlight")
    recommended_experience: Optional[str] = Field(default=None, description="Recommended experience / internship")
    resume_concerns: List[str] = Field(default_factory=list, description="Potential resume alignment concerns")
    resume_suggestions: List[str] = Field(default_factory=list, description="Actionable truthful resume suggestions")
    preparation_status: Any = Field(default="NOT_REVIEWED", description="Application preparation status")
    preparation_notes: Optional[str] = Field(default=None, description="User preparation notes")
    recommended_resume: Optional[str] = Field(default=None, description="Best aligned resume version name")

    # Phase 11 Application Command Center & Interview Tracking fields
    applied_at: Optional[datetime] = Field(default=None, description="Timestamp when user marked job as APPLIED")
    interview_date: Optional[str] = Field(default=None, description="Scheduled interview date (YYYY-MM-DD)")
    interview_stage: Optional[str] = Field(default=None, description="Interview stage (HR, Technical, etc.)")
    interview_status: Optional[str] = Field(default="NOT_SCHEDULED", description="Interview status")
    interview_notes: Optional[str] = Field(default=None, description="Interview preparation and feedback notes")
    interview_preparation_status: Optional[str] = Field(default="NOT_STARTED", description="Interview preparation status")

    def apply_match_result(self, result: Any) -> None:
        """Populate match score, category, and explanation attributes from a MatchResult."""
        self.match_score = result.score
        self.match_category = result.category
        self.matched_roles = list(result.matched_roles)
        self.matched_skills = list(result.matched_skills)
        self.matched_locations = list(result.matched_locations)
        self.experience_match = bool(result.experience_match)
        self.excluded_reasons = list(result.excluded_reasons)

    def apply_recommendation_result(self, rec: Any) -> None:
        """Populate recommendation attributes from an ApplicationRecommendation."""
        self.application_readiness_score = rec.application_readiness_score
        self.application_priority = rec.application_priority
        self.missing_skills = list(rec.missing_skills)
        self.critical_gaps = list(rec.critical_gaps)
        self.moderate_gaps = list(rec.moderate_gaps)
        self.minor_gaps = list(rec.minor_gaps)
        self.recommendation_reasons = list(rec.recommendation_reasons)
        self.risk_reasons = list(rec.risk_reasons)
        self.profile_alignment = rec.profile_alignment
        self.checklist = list(rec.checklist)

    def apply_resume_preparation(self, analysis: Any) -> None:
        """Populate Phase 10 resume preparation attributes from a ResumePreparationAnalysis."""
        self.resume_alignment_score = analysis.resume_alignment_score
        self.resume_alignment_category = analysis.resume_alignment_category
        self.skills_to_emphasize = list(analysis.skills_to_emphasize)
        self.resume_matched_keywords = list(analysis.resume_matched_keywords)
        self.resume_missing_keywords = list(analysis.resume_missing_keywords)
        self.recommended_project = analysis.recommended_project
        self.recommended_experience = analysis.recommended_experience
        self.resume_concerns = list(analysis.resume_concerns)
        self.resume_suggestions = list(analysis.resume_suggestions)
        self.recommended_resume = analysis.recommended_resume
        if analysis.preparation_status:
            self.preparation_status = (
                analysis.preparation_status.value
                if hasattr(analysis.preparation_status, "value")
                else str(analysis.preparation_status)
            )
        if analysis.preparation_notes is not None:
            self.preparation_notes = analysis.preparation_notes

    @field_validator("title", "company", "source", "url", mode="before")
    @classmethod
    def strip_strings(cls, v: Any) -> Any:
        """Strip unnecessary whitespace from core string fields."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("location", mode="before")
    @classmethod
    def normalize_location(cls, v: Any) -> Optional[str]:
        """Strip location whitespace, apply NFC Unicode normalization, and normalize empty/unknown strings to None."""
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = unicodedata.normalize("NFC", v.strip())
            if not cleaned or cleaned.lower() in ("unknown", "none", "n/a", "not specified"):
                return None
            return cleaned
        return v

    @model_validator(mode="after")
    def sync_fields(self) -> "Job":
        """Synchronize source_job_id/job_id, canonicalize URL, and compute fingerprint."""
        if self.source_job_id and not self.job_id:
            self.job_id = self.source_job_id
        elif self.job_id and not self.source_job_id:
            self.source_job_id = self.job_id

        # Normalize URL to canonical form
        canonical = normalize_url(self.url)
        if canonical:
            self.url = canonical

        if not self.fingerprint:
            self.fingerprint = self.compute_fingerprint()

        if self.first_seen_at is None and self.date_found is not None:
            self.first_seen_at = self.date_found
        if self.last_seen_at is None and self.date_found is not None:
            self.last_seen_at = self.date_found

        return self

    def compute_fingerprint(self) -> str:
        """Generate a deterministic SHA-256 fingerprint for this job."""
        return generate_job_fingerprint(
            source=self.source,
            title=self.title,
            company=self.company,
            location=self.location,
            canonical_url=self.url,
        )

    @property
    def deduplication_key(self) -> str:
        """Generate a normalized key for duplicate detection.
        Prefers (source, source_job_id) if source_job_id exists; otherwise falls back to company and title.
        """
        s_id = self.source_job_id or self.job_id
        if s_id:
            return f"{self.source.lower()}::{s_id.strip()}"
        clean_company = "".join(ch for ch in self.company.lower() if ch.isalnum())
        clean_title = "".join(ch for ch in self.title.lower() if ch.isalnum())
        return f"fallback::{clean_company}::{clean_title}"

    def to_row_dict(self) -> Dict[str, Any]:
        """Convert job to a flattened dictionary formatted for Excel/CSV exports."""
        s_id = self.source_job_id or self.job_id or "N/A"
        return {
            "Match Score": self.match_score if self.match_score is not None else "N/A",
            "Category": self.match_category or "N/A",
            "Job ID": s_id,
            "Title": self.title,
            "Company": self.company,
            "Location": self.location,
            "Source": self.source.capitalize(),
            "URL": self.url,
            "Easy Apply": "Yes" if self.easy_apply else "No",
            "Experience": self.experience_required or "Not Specified",
            "Employment Type": self.employment_type or "Not Specified",
            "Salary": self.salary or "Not Disclosed",
            "Date Posted": self.date_posted or "Unknown",
            "Date Found": self.date_found.strftime("%Y-%m-%d %H:%M:%S") if self.date_found else "",
            "Description": (self.description[:300] + "...") if self.description and len(self.description) > 300 else (self.description or ""),
            "Status": self.status.value if isinstance(self.status, JobStatus) else str(self.status or "NEW"),
            "First Seen": self.first_seen_at.strftime("%Y-%m-%d %H:%M:%S") if self.first_seen_at else "",
            "Last Seen": self.last_seen_at.strftime("%Y-%m-%d %H:%M:%S") if self.last_seen_at else "",
            "Notes": self.notes or "",
            "Application Readiness": self.application_readiness_score if self.application_readiness_score is not None else "N/A",
            "Application Priority": self.application_priority.value if isinstance(self.application_priority, ApplicationPriority) else str(self.application_priority or "N/A"),
            "Profile Alignment": self.profile_alignment or "N/A",
            "Missing Skills": ", ".join(self.missing_skills) if self.missing_skills else "None",
            "Recommendation Reasons": "; ".join(self.recommendation_reasons) if self.recommendation_reasons else "",
            "Risk Reasons": "; ".join(self.risk_reasons) if self.risk_reasons else "",
            "Follow-up Date": self.follow_up_date or "",
            "Resume Alignment": self.resume_alignment_score if self.resume_alignment_score is not None else "N/A",
            "Resume Alignment Category": self.resume_alignment_category or "N/A",
            "Skills to Emphasize": ", ".join(self.skills_to_emphasize) if self.skills_to_emphasize else "",
            "Missing Resume Keywords": ", ".join(self.resume_missing_keywords) if self.resume_missing_keywords else "",
            "Recommended Project": self.recommended_project or "",
            "Recommended Experience": self.recommended_experience or "",
            "Resume Concerns": "; ".join(self.resume_concerns) if self.resume_concerns else "",
            "Recommended Resume": self.recommended_resume or "",
            "Preparation Status": self.preparation_status.value if hasattr(self.preparation_status, "value") else str(self.preparation_status or "NOT_REVIEWED"),
            "Applied At": self.applied_at.strftime("%Y-%m-%d %H:%M:%S") if self.applied_at else "",
            "Interview Date": self.interview_date or "",
            "Interview Stage": self.interview_stage or "",
            "Interview Status": self.interview_status or "NOT_SCHEDULED",
            "Interview Prep Status": self.interview_preparation_status or "NOT_STARTED",
            "Interview Notes": self.interview_notes or "",
        }
