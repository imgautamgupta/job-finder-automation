"""Deterministic, local-first Job Search Intelligence & Source Optimization Service (Phase 13).

Analyzes historical job collections to optimize future search strategies across sources,
roles, and geographic regions. Protects against small-dataset overfitting and never
automatically alters profile configurations or submits applications.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from app.database.database import DatabaseManager
from app.models.profile import JobProfile
from app.models.search_intelligence import (
    DataConfidence,
    LocationSearchPerformance,
    RecommendationPriority,
    RoleLocationPerformance,
    RoleSearchPerformance,
    SearchGap,
    SearchGapType,
    SearchIntelligenceReport,
    SearchRecommendation,
    SearchStrategy,
    SourceActionRecommendation,
    SourceBudgetRecommendation,
    SourceLocationPerformance,
    SourceRecommendation,
    SourceRolePerformance,
    SourceSearchPerformance,
    StrategyStatus,
)
from app.services.analytics import AnalyticsService
from app.services.matcher import is_india_eligible_remote

logger = logging.getLogger(__name__)


# Default preferred locations if not specified in profile
DEFAULT_PREFERRED_LOCATIONS = [
    "Bangalore",
    "Bengaluru",
    "Delhi",
    "Noida",
    "Ahmedabad",
    "Remote",
    "India",
]

# Standard display groupings for preferred locations
LOCATION_GROUPS = {
    "Bangalore / Bengaluru": ["bangalore", "bengaluru"],
    "Delhi / NCR": ["delhi", "new delhi", "noida", "gurgaon", "gurugram"],
    "Remote (India Eligible)": ["remote", "anywhere"],
    "Ahmedabad": ["ahmedabad"],
    "Pan India": ["india"],
}


class SearchIntelligenceService:
    """Service generating deterministic search recommendations and source optimization metrics."""

    def __init__(self, db: Optional[DatabaseManager] = None, profile: Optional[JobProfile] = None):
        self.db = db
        self.profile = profile or self._load_profile_fallback()
        self.analytics_service = AnalyticsService(db=db, profile=self.profile)

    def _load_profile_fallback(self) -> JobProfile:
        """Load profile from settings if available, else default profile."""
        try:
            from app.config.settings import get_settings
            settings = get_settings()
            if settings.PROFILE_PATH.exists():
                with open(settings.PROFILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return JobProfile.model_validate(data)
        except Exception as e:
            logger.debug("Could not load profile from file: %s", e)
        return JobProfile(
            target_roles=[
                "Python Developer",
                "Backend Developer",
                "Software Engineer",
                "Full Stack Developer",
                "Web Developer",
                "ML Engineer",
                "AI Engineer",
                "SDE Intern",
            ],
            preferred_locations=DEFAULT_PREFERRED_LOCATIONS,
        )

    def _evaluate_confidence(self, sample_size: int) -> DataConfidence:
        """Apply deterministic small-data protection thresholds."""
        if sample_size < 5:
            return DataConfidence.INSUFFICIENT_DATA
        elif sample_size < 10:
            return DataConfidence.LIMITED_DATA
        return DataConfidence.ACTIONABLE_DATA

    def _job_matches_role(self, job: Dict[str, Any], role_name: str) -> bool:
        """Deterministic check if a job aligns with a specific target role."""
        r_lower = role_name.strip().lower()
        title_lower = (job.get("title") or "").strip().lower()
        if r_lower in title_lower:
            return True

        # Check matched_roles json field
        matched_roles_raw = job.get("matched_roles")
        if matched_roles_raw:
            try:
                if isinstance(matched_roles_raw, str):
                    roles_list = json.loads(matched_roles_raw)
                elif isinstance(matched_roles_raw, list):
                    roles_list = matched_roles_raw
                else:
                    roles_list = []
                for m in roles_list:
                    if r_lower in str(m).lower() or str(m).lower() in r_lower:
                        return True
            except Exception:
                if r_lower in str(matched_roles_raw).lower():
                    return True

        # Specific abbreviation mapping
        if "software engineer" in r_lower and ("sde" in title_lower or "software development engineer" in title_lower):
            return True
        if "backend developer" in r_lower and "backend engineer" in title_lower:
            return True
        if "full stack developer" in r_lower and "full stack engineer" in title_lower:
            return True
        if "ml engineer" in r_lower and ("machine learning" in title_lower or "ai engineer" in title_lower):
            return True

        return False

    def _job_matches_location_group(self, job: Dict[str, Any], group_name: str, terms: List[str]) -> bool:
        """Check if a job matches a geographic location grouping, respecting India eligibility."""
        loc_str = (job.get("location") or "").lower()
        matched_locs = str(job.get("matched_locations") or "").lower()

        # Handle Remote with India-eligibility distinction
        if "remote" in group_name.lower():
            if "remote" in loc_str or "anywhere" in loc_str or "distributed" in loc_str:
                return is_india_eligible_remote(job.get("location"))
            return False

        for term in terms:
            t = term.lower()
            if t in loc_str or t in matched_locs:
                return True
        return False

    def _is_preferred_location(self, location_str: Optional[str]) -> bool:
        """Check if job location falls within user's preferred geographic regions."""
        if not location_str:
            return False
        loc_lower = location_str.lower()
        pref_locs = self.profile.preferred_locations if self.profile else DEFAULT_PREFERRED_LOCATIONS
        for pref in pref_locs:
            p_lower = pref.lower()
            if p_lower == "remote":
                if is_india_eligible_remote(location_str):
                    return True
            elif p_lower in loc_lower:
                return True
        return False

    def compute_source_performance(
        self,
        jobs: List[Dict[str, Any]],
        health_data: Optional[List[Dict[str, Any]]] = None,
    ) -> List[SourceSearchPerformance]:
        """Calculate detailed source-level search metrics and depth recommendations."""
        health_by_source: Dict[str, Dict[str, Any]] = {}
        if health_data:
            for h in health_data:
                health_by_source[h["source"].lower()] = h

        # Aggregate raw metrics by source
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for j in jobs:
            src = (j.get("source") or "unknown").strip().lower()
            grouped.setdefault(src, []).append(j)

        # Include all configured sources even if 0 jobs collected
        all_sources: Set[str] = {"greenhouse", "lever", "naukri", "linkedin"}.union(grouped.keys())

        results: List[SourceSearchPerformance] = []
        for src in sorted(all_sources):
            src_jobs = grouped.get(src, [])
            found = len(src_jobs)
            relevant = sum(1 for j in src_jobs if (j.get("match_score") or 0) >= 60)
            recommended = sum(
                1 for j in src_jobs
                if str(j.get("application_priority") or "").upper() in ("URGENT", "HIGH", "NORMAL")
            )
            applied = sum(
                1 for j in src_jobs
                if j.get("status") in ("APPLIED", "INTERVIEW", "OFFER")
            )
            interview = sum(
                1 for j in src_jobs
                if j.get("status") == "INTERVIEW"
                or str(j.get("interview_status") or "").upper() in ("SCHEDULED", "COMPLETED", "PASSED", "FAILED", "RESCHEDULED")
                or (j.get("interview_date") is not None and str(j.get("interview_date")).strip() != "")
            )
            offer = sum(1 for j in src_jobs if j.get("status") == "OFFER")

            # Rates
            rel_rate = round((relevant / found) * 100.0, 1) if found > 0 else None
            rec_rate = round((recommended / found) * 100.0, 1) if found > 0 else None
            app_rate = round((applied / relevant) * 100.0, 1) if relevant > 0 else None
            int_rate = round((interview / applied) * 100.0, 1) if applied > 0 else None
            off_rate = round((offer / applied) * 100.0, 1) if applied > 0 else None

            # Source quality score using Phase 12 shared logic
            quality_score, quality_label = self.analytics_service.compute_source_quality_score(
                found, relevant, recommended, applied, interview, offer
            )

            # Location coverage & India eligibility
            pref_loc_count = sum(1 for j in src_jobs if self._is_preferred_location(j.get("location")))
            pref_loc_rate = round((pref_loc_count / found) * 100.0, 1) if found > 0 else None

            india_count = 0
            foreign_remote_count = 0
            for j in src_jobs:
                loc = j.get("location") or ""
                loc_lower = loc.lower()
                is_remote = "remote" in loc_lower or "anywhere" in loc_lower
                if is_india_eligible_remote(loc) or any(
                    city in loc_lower for city in ["india", "bangalore", "bengaluru", "delhi", "noida", "ahmedabad"]
                ):
                    india_count += 1
                elif is_remote:
                    foreign_remote_count += 1

            india_rate = round((india_count / found) * 100.0, 1) if found > 0 else None
            confidence = self._evaluate_confidence(found)

            # Determine source reliability from health check
            src_health = health_by_source.get(src, {})
            health_status = str(src_health.get("status") or "").upper()
            health_error = str(src_health.get("error") or "")
            is_enabled = src_health.get("enabled", True)

            if not is_enabled or health_status == "DISABLED":
                reliability = "Disabled"
            elif "BLOCKED" in health_status or "403" in health_error or "429" in health_error or "anti-bot" in health_error.lower():
                reliability = "Blocked"
            elif "PLACEHOLDER" in health_status or src == "linkedin":
                reliability = "Placeholder"
            elif health_status in ("COMPLETED", "COMPLETED_WITH_SOURCE_WARNINGS", "SUCCESS"):
                reliability = "Operational"
            else:
                reliability = "Unknown"

            # Formulate deterministic recommendation & priority
            if reliability == "Blocked":
                rec_action = SourceActionRecommendation.MONITOR
                rec_prio = RecommendationPriority.MONITOR
                rec_reason = "Endpoint blocked or rate limited (403/429); could not evaluate source quality reliably."
            elif reliability in ("Disabled", "Placeholder"):
                rec_action = SourceActionRecommendation.MONITOR
                rec_prio = RecommendationPriority.MONITOR
                rec_reason = f"Source connector is {reliability.lower()}; awaiting integration/activation."
            elif confidence == DataConfidence.INSUFFICIENT_DATA:
                rec_action = SourceActionRecommendation.INSUFFICIENT_DATA
                rec_prio = RecommendationPriority.MONITOR
                rec_reason = f"Only {found} listing(s) collected; Fewer than 5 jobs threshold for quality evaluation (insufficient historical data)."
            else:
                # We have LIMITED_DATA (5-9) or ACTIONABLE_DATA (10+)
                if ((quality_score or 0) >= 60.0 or (rel_rate or 0) >= 50.0) and ((pref_loc_rate or 0) >= 30.0 or (india_rate or 0) >= 50.0):
                    rec_action = SourceActionRecommendation.INCREASE_SEARCH_DEPTH
                    rec_prio = RecommendationPriority.CRITICAL if (confidence == DataConfidence.ACTIONABLE_DATA and (quality_score or 0) >= 75.0) else RecommendationPriority.HIGH
                    rec_reason = f"Strong relevance rate ({rel_rate}%) and high India/preferred location alignment ({pref_loc_rate}%)."
                elif ((foreign_remote_count > 0 and (india_rate or 0) < 30.0) or ((rel_rate or 0) < 20.0 and found >= 5)):
                    rec_action = SourceActionRecommendation.REDUCE_SEARCH_DEPTH
                    rec_prio = RecommendationPriority.MEDIUM
                    rec_reason = f"Low relevant yield ({rel_rate}%) or high proportion of foreign-only remote listings ({foreign_remote_count} foreign listings)."
                else:
                    rec_action = SourceActionRecommendation.MAINTAIN_SEARCH_DEPTH
                    rec_prio = RecommendationPriority.MEDIUM
                    rec_reason = f"Moderate conversion performance ({rel_rate}% relevance); maintain standard search depth."

            results.append(
                SourceSearchPerformance(
                    source=src.capitalize(),
                    jobs_found=found,
                    relevant_jobs=relevant,
                    recommended_jobs=recommended,
                    applied_jobs=applied,
                    interview_jobs=interview,
                    offer_jobs=offer,
                    relevance_rate=rel_rate,
                    recommendation_rate=rec_rate,
                    application_rate=app_rate,
                    interview_rate=int_rate,
                    offer_rate=off_rate,
                    source_quality_score=quality_score,
                    quality_label=quality_label,
                    location_coverage=pref_loc_count,
                    preferred_location_jobs=pref_loc_count,
                    preferred_location_rate=pref_loc_rate,
                    india_eligible_jobs=india_count,
                    india_eligible_rate=india_rate,
                    foreign_remote_jobs=foreign_remote_count,
                    confidence=confidence,
                    recommendation=rec_action,
                    recommendation_priority=rec_prio,
                    recommendation_reason=rec_reason,
                    reliability=reliability,
                )
            )

        # Sort: ACTIONABLE first, then highest relevant jobs, then found
        results.sort(
            key=lambda s: (
                0 if s.recommendation == SourceActionRecommendation.INCREASE_SEARCH_DEPTH else (
                    1 if s.recommendation == SourceActionRecommendation.MAINTAIN_SEARCH_DEPTH else 2
                ),
                -(s.relevant_jobs),
                -(s.jobs_found),
            )
        )
        return results

    def compute_role_performance(
        self,
        jobs: List[Dict[str, Any]],
        target_roles: Optional[List[str]] = None,
    ) -> List[RoleSearchPerformance]:
        """Calculate yield and match quality across target profile roles."""
        roles = target_roles or (self.profile.target_roles if self.profile else [
            "Python Developer", "Backend Developer", "Software Engineer", "Full Stack Developer",
            "Web Developer", "ML Engineer", "AI Engineer", "SDE Intern"
        ])

        results: List[RoleSearchPerformance] = []
        for role_name in roles:
            matching_jobs = [j for j in jobs if self._job_matches_role(j, role_name)]
            found = len(matching_jobs)
            relevant = sum(1 for j in matching_jobs if (j.get("match_score") or 0) >= 60)
            recommended = sum(
                1 for j in matching_jobs
                if str(j.get("application_priority") or "").upper() in ("URGENT", "HIGH", "NORMAL")
            )
            applied = sum(
                1 for j in matching_jobs
                if j.get("status") in ("APPLIED", "INTERVIEW", "OFFER")
            )
            interview = sum(
                1 for j in matching_jobs
                if j.get("status") == "INTERVIEW"
                or str(j.get("interview_status") or "").upper() in ("SCHEDULED", "COMPLETED", "PASSED", "FAILED", "RESCHEDULED")
                or (j.get("interview_date") is not None and str(j.get("interview_date")).strip() != "")
            )
            offer = sum(1 for j in matching_jobs if j.get("status") == "OFFER")

            rel_rate = round((relevant / found) * 100.0, 1) if found > 0 else None
            rec_rate = round((recommended / found) * 100.0, 1) if found > 0 else None

            match_scores = [j.get("match_score") or 0 for j in matching_jobs]
            avg_match = round(sum(match_scores) / found, 1) if found > 0 else None

            readiness_scores = [j.get("application_readiness_score") or 0 for j in matching_jobs]
            avg_readiness = round(sum(readiness_scores) / found, 1) if found > 0 else None

            resume_scores = [j.get("resume_alignment_score") or 0 for j in matching_jobs]
            avg_resume = round(sum(resume_scores) / found, 1) if found > 0 else None

            confidence = self._evaluate_confidence(found)

            # Priority assignment
            if found == 0:
                prio = RecommendationPriority.MONITOR
                notes = "Insufficient historical coverage in database."
            elif relevant >= 3 and (avg_match or 0) >= 75.0:
                prio = RecommendationPriority.HIGH
                notes = f"Strong opportunity pipeline: {relevant} relevant postings with {avg_match} avg match score."
            elif relevant >= 1:
                prio = RecommendationPriority.MEDIUM
                notes = f"Moderate yield: {relevant} relevant posting(s) with {avg_match} avg match score."
            elif found >= 5 and relevant == 0:
                prio = RecommendationPriority.LOW
                notes = "Low match relevance among historical postings."
            else:
                prio = RecommendationPriority.MONITOR
                notes = "Developing sample size; continue monitoring."

            results.append(
                RoleSearchPerformance(
                    role_name=role_name,
                    jobs_found=found,
                    relevant_jobs=relevant,
                    recommended_jobs=recommended,
                    applied_jobs=applied,
                    interview_jobs=interview,
                    offer_jobs=offer,
                    relevance_rate=rel_rate,
                    recommendation_rate=rec_rate,
                    avg_match_score=avg_match,
                    avg_readiness_score=avg_readiness,
                    avg_resume_alignment_score=avg_resume,
                    confidence=confidence,
                    priority=prio,
                    notes=notes,
                )
            )

        # Sort: HIGH, MEDIUM, LOW, MONITOR; then relevant DESC, avg_match DESC
        prio_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
            RecommendationPriority.MONITOR: 4,
        }
        results.sort(
            key=lambda r: (
                prio_order.get(r.priority, 5),
                -(r.relevant_jobs),
                -(r.avg_match_score or 0),
            )
        )
        return results

    def compute_location_performance(
        self,
        jobs: List[Dict[str, Any]],
        preferred_locations: Optional[List[str]] = None,
    ) -> List[LocationSearchPerformance]:
        """Calculate yield and geographic alignment across preferred locations."""
        results: List[LocationSearchPerformance] = []

        for group_label, terms in LOCATION_GROUPS.items():
            matching_jobs = [
                j for j in jobs
                if self._job_matches_location_group(j, group_label, terms)
            ]
            found = len(matching_jobs)
            relevant = sum(1 for j in matching_jobs if (j.get("match_score") or 0) >= 60)
            recommended = sum(
                1 for j in matching_jobs
                if str(j.get("application_priority") or "").upper() in ("URGENT", "HIGH", "NORMAL")
            )
            applied = sum(
                1 for j in matching_jobs
                if j.get("status") in ("APPLIED", "INTERVIEW", "OFFER")
            )
            interview = sum(
                1 for j in matching_jobs
                if j.get("status") == "INTERVIEW"
                or str(j.get("interview_status") or "").upper() in ("SCHEDULED", "COMPLETED", "PASSED", "FAILED", "RESCHEDULED")
                or (j.get("interview_date") is not None and str(j.get("interview_date")).strip() != "")
            )
            offer = sum(1 for j in matching_jobs if j.get("status") == "OFFER")

            rel_rate = round((relevant / found) * 100.0, 1) if found > 0 else None
            rec_rate = round((recommended / found) * 100.0, 1) if found > 0 else None

            match_scores = [j.get("match_score") or 0 for j in matching_jobs]
            avg_match = round(sum(match_scores) / found, 1) if found > 0 else None

            readiness_scores = [j.get("application_readiness_score") or 0 for j in matching_jobs]
            avg_readiness = round(sum(readiness_scores) / found, 1) if found > 0 else None

            india_remote_count = sum(1 for j in matching_jobs if is_india_eligible_remote(j.get("location")))
            foreign_remote_count = sum(
                1 for j in matching_jobs
                if ("remote" in str(j.get("location") or "").lower() or "anywhere" in str(j.get("location") or "").lower())
                and not is_india_eligible_remote(j.get("location"))
            )

            confidence = self._evaluate_confidence(found)

            if found == 0:
                prio = RecommendationPriority.MONITOR
                notes = "Insufficient historical coverage in database."
            elif relevant >= 3 and (avg_match or 0) >= 70.0:
                prio = RecommendationPriority.HIGH
                notes = f"Primary hiring corridor: {relevant} relevant postings with {avg_match} avg match."
            elif relevant >= 1:
                prio = RecommendationPriority.MEDIUM
                notes = f"Moderate yield: {relevant} relevant posting(s) with {avg_match} avg match."
            else:
                prio = RecommendationPriority.MONITOR
                notes = "Developing sample size; continue monitoring."

            results.append(
                LocationSearchPerformance(
                    location_name=group_label,
                    jobs_found=found,
                    relevant_jobs=relevant,
                    recommended_jobs=recommended,
                    applied_jobs=applied,
                    interview_jobs=interview,
                    offer_jobs=offer,
                    india_eligible_remote=india_remote_count,
                    foreign_remote=foreign_remote_count,
                    relevance_rate=rel_rate,
                    recommendation_rate=rec_rate,
                    avg_match_score=avg_match,
                    avg_readiness_score=avg_readiness,
                    confidence=confidence,
                    priority=prio,
                    notes=notes,
                )
            )

        # Also evaluate Foreign-only Remote explicitly for transparency
        foreign_jobs = [
            j for j in jobs
            if ("remote" in str(j.get("location") or "").lower() or "anywhere" in str(j.get("location") or "").lower())
            and not is_india_eligible_remote(j.get("location"))
        ]
        if foreign_jobs:
            f_found = len(foreign_jobs)
            f_rel = sum(1 for j in foreign_jobs if (j.get("match_score") or 0) >= 60)
            f_rec = sum(1 for j in foreign_jobs if str(j.get("application_priority") or "").upper() in ("URGENT", "HIGH", "NORMAL"))
            f_app = sum(1 for j in foreign_jobs if j.get("status") in ("APPLIED", "INTERVIEW", "OFFER"))
            f_avg_m = round(sum(j.get("match_score") or 0 for j in foreign_jobs) / f_found, 1)
            f_avg_r = round(sum(j.get("application_readiness_score") or 0 for j in foreign_jobs) / f_found, 1)

            results.append(
                LocationSearchPerformance(
                    location_name="Remote (Foreign Only - Excluded)",
                    jobs_found=f_found,
                    relevant_jobs=f_rel,
                    recommended_jobs=f_rec,
                    applied_jobs=f_app,
                    interview_jobs=0,
                    offer_jobs=0,
                    india_eligible_remote=0,
                    foreign_remote=f_found,
                    relevance_rate=round((f_rel / f_found) * 100, 1),
                    recommendation_rate=round((f_rec / f_found) * 100, 1),
                    avg_match_score=f_avg_m,
                    avg_readiness_score=f_avg_r,
                    confidence=self._evaluate_confidence(f_found),
                    priority=RecommendationPriority.LOW,
                    notes="Foreign geographic restrictions detected; excluded from India-eligible focus.",
                )
            )

        prio_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
            RecommendationPriority.MONITOR: 4,
        }
        results.sort(
            key=lambda loc: (
                prio_order.get(loc.priority, 5),
                -(loc.relevant_jobs),
                -(loc.avg_match_score or 0),
            )
        )
        return results

    def compute_role_location_matrix(
        self,
        jobs: List[Dict[str, Any]],
        target_roles: List[str],
    ) -> List[RoleLocationPerformance]:
        """Analyze productivity and match scores across Role × Location pairings."""
        combinations: List[RoleLocationPerformance] = []

        for role_name in target_roles:
            for group_label, terms in LOCATION_GROUPS.items():
                combo_jobs = [
                    j for j in jobs
                    if self._job_matches_role(j, role_name)
                    and self._job_matches_location_group(j, group_label, terms)
                ]
                if not combo_jobs:
                    continue

                found = len(combo_jobs)
                relevant = sum(1 for j in combo_jobs if (j.get("match_score") or 0) >= 60)
                recommended = sum(
                    1 for j in combo_jobs
                    if str(j.get("application_priority") or "").upper() in ("URGENT", "HIGH", "NORMAL")
                )
                applied = sum(
                    1 for j in combo_jobs
                    if j.get("status") in ("APPLIED", "INTERVIEW", "OFFER")
                )
                avg_m = round(sum(j.get("match_score") or 0 for j in combo_jobs) / found, 1)
                avg_r = round(sum(j.get("application_readiness_score") or 0 for j in combo_jobs) / found, 1)

                confidence = self._evaluate_confidence(found)

                if relevant >= 2 and avg_m >= 75.0:
                    prio = RecommendationPriority.HIGH
                    label = "Strong Opportunity"
                elif relevant >= 1:
                    prio = RecommendationPriority.MEDIUM
                    label = "Promising Opportunity"
                elif found >= 3 and relevant == 0:
                    prio = RecommendationPriority.LOW
                    label = "Low Relevance"
                else:
                    prio = RecommendationPriority.MONITOR
                    label = "Developing / Insufficient Data"

                combinations.append(
                    RoleLocationPerformance(
                        role_name=role_name,
                        location_name=group_label,
                        jobs_found=found,
                        relevant_jobs=relevant,
                        recommended_jobs=recommended,
                        applied_jobs=applied,
                        avg_match_score=avg_m,
                        avg_readiness_score=avg_r,
                        confidence=confidence,
                        priority=prio,
                        status_label=label,
                    )
                )

        combinations.sort(
            key=lambda c: (
                0 if c.priority == RecommendationPriority.HIGH else (1 if c.priority == RecommendationPriority.MEDIUM else 2),
                -(c.relevant_jobs),
                -(c.recommended_jobs),
                -(c.avg_match_score or 0),
            )
        )
        return combinations

    def compute_source_role_matrix(
        self,
        jobs: List[Dict[str, Any]],
        target_roles: List[str],
    ) -> List[SourceRolePerformance]:
        """Evaluate productivity of Source × Role pairs."""
        results: List[SourceRolePerformance] = []
        sources = sorted({(j.get("source") or "unknown").strip().lower() for j in jobs})

        for src in sources:
            for role_name in target_roles:
                pair_jobs = [
                    j for j in jobs
                    if (j.get("source") or "").strip().lower() == src
                    and self._job_matches_role(j, role_name)
                ]
                if not pair_jobs:
                    continue

                found = len(pair_jobs)
                relevant = sum(1 for j in pair_jobs if (j.get("match_score") or 0) >= 60)
                recommended = sum(
                    1 for j in pair_jobs
                    if str(j.get("application_priority") or "").upper() in ("URGENT", "HIGH", "NORMAL")
                )
                avg_m = round(sum(j.get("match_score") or 0 for j in pair_jobs) / found, 1)

                if found < 3:
                    assessment = "insufficient"
                elif relevant >= 3 and (relevant / found) >= 0.5:
                    assessment = "strong"
                elif relevant >= 1:
                    assessment = "moderate"
                elif found >= 3 and relevant == 0:
                    assessment = "weak"
                else:
                    assessment = "insufficient"

                results.append(
                    SourceRolePerformance(
                        source=src.capitalize(),
                        role_name=role_name,
                        jobs_found=found,
                        relevant_jobs=relevant,
                        recommended_jobs=recommended,
                        avg_match_score=avg_m,
                        assessment=assessment,
                        confidence=self._evaluate_confidence(found),
                    )
                )

        results.sort(key=lambda x: (-(x.relevant_jobs), -(x.jobs_found)))
        return results

    def compute_source_location_matrix(
        self,
        jobs: List[Dict[str, Any]],
    ) -> List[SourceLocationPerformance]:
        """Evaluate productivity of Source × Location pairs."""
        results: List[SourceLocationPerformance] = []
        sources = sorted({(j.get("source") or "unknown").strip().lower() for j in jobs})

        for src in sources:
            for group_label, terms in LOCATION_GROUPS.items():
                pair_jobs = [
                    j for j in jobs
                    if (j.get("source") or "").strip().lower() == src
                    and self._job_matches_location_group(j, group_label, terms)
                ]
                if not pair_jobs:
                    continue

                found = len(pair_jobs)
                relevant = sum(1 for j in pair_jobs if (j.get("match_score") or 0) >= 60)
                recommended = sum(
                    1 for j in pair_jobs
                    if str(j.get("application_priority") or "").upper() in ("URGENT", "HIGH", "NORMAL")
                )

                if found < 3:
                    assessment = "insufficient"
                elif relevant >= 2:
                    assessment = "strong"
                elif relevant >= 1:
                    assessment = "moderate"
                elif found >= 3 and relevant == 0:
                    assessment = "weak"
                else:
                    assessment = "insufficient"

                results.append(
                    SourceLocationPerformance(
                        source=src.capitalize(),
                        location_name=group_label,
                        jobs_found=found,
                        relevant_jobs=relevant,
                        recommended_jobs=recommended,
                        assessment=assessment,
                        confidence=self._evaluate_confidence(found),
                    )
                )

        results.sort(key=lambda x: (-(x.relevant_jobs), -(x.jobs_found)))
        return results

    def identify_search_gaps(
        self,
        target_roles: List[str],
        role_performances: List[RoleSearchPerformance],
        location_performances: List[LocationSearchPerformance],
    ) -> List[SearchGap]:
        """Identify configured profile targets with little or no historical representation."""
        gaps: List[SearchGap] = []

        # 1. Role coverage gaps
        role_dict = {r.role_name: r for r in role_performances}
        for r_name in target_roles:
            perf = role_dict.get(r_name)
            if not perf or perf.jobs_found == 0:
                gaps.append(
                    SearchGap(
                        gap_type=SearchGapType.ROLE_GAP,
                        item_name=r_name,
                        details="0 jobs recorded in database.",
                        suggestion="Insufficient historical coverage. Consider running targeted collection for this role.",
                    )
                )
            elif perf.relevant_jobs == 0 and perf.jobs_found < 3:
                gaps.append(
                    SearchGap(
                        gap_type=SearchGapType.ROLE_GAP,
                        item_name=r_name,
                        details=f"{perf.jobs_found} job(s) found, 0 relevant matching profile.",
                        suggestion="Insufficient historical coverage. Monitor further daily collection runs.",
                    )
                )

        # 2. Location coverage gaps
        for loc_perf in location_performances:
            if loc_perf.location_name.startswith("Remote (Foreign Only"):
                continue
            if loc_perf.jobs_found == 0:
                gaps.append(
                    SearchGap(
                        gap_type=SearchGapType.LOCATION_GAP,
                        item_name=loc_perf.location_name,
                        details="0 jobs recorded in database.",
                        suggestion="Insufficient historical coverage. Consider checking companies with presence in this region.",
                    )
                )
            elif loc_perf.relevant_jobs == 0 and loc_perf.jobs_found < 3:
                gaps.append(
                    SearchGap(
                        gap_type=SearchGapType.LOCATION_GAP,
                        item_name=loc_perf.location_name,
                        details=f"{loc_perf.jobs_found} job(s) found, 0 relevant.",
                        suggestion="Insufficient historical coverage. Monitor further daily collection runs.",
                    )
                )

        return gaps

    def compute_search_budget(
        self,
        source_performances: List[SourceSearchPerformance],
    ) -> List[SourceBudgetRecommendation]:
        """Calculate recommended daily search effort percentages summing exactly to 100%."""
        if not source_performances:
            return []

        # Standard configured sources
        target_sources = ["Greenhouse", "Lever", "Naukri", "Linkedin"]
        source_map = {s.source.capitalize(): s for s in source_performances}

        # Check total sample size
        total_jobs_collected = sum(s.jobs_found for s in source_performances)
        has_sufficient_data = total_jobs_collected >= 10 and any(s.jobs_found >= 5 for s in source_performances)

        allocations: List[SourceBudgetRecommendation] = []
        if not has_sufficient_data:
            # Neutral baseline allocation when data is insufficient
            equal_pct = round(100.0 / len(target_sources), 1)
            remainder = round(100.0 - (equal_pct * len(target_sources)), 1)
            for idx, src_name in enumerate(target_sources):
                pct = equal_pct + (remainder if idx == 0 else 0.0)
                allocations.append(
                    SourceBudgetRecommendation(
                        source=src_name,
                        allocated_percentage=round(pct, 1),
                        basis="Baseline neutral allocation (insufficient historical data to differentiate sources).",
                        confidence=DataConfidence.INSUFFICIENT_DATA,
                    )
                )
            return allocations

        # Actionable or limited dataset: compute weighted shares
        raw_weights: Dict[str, float] = {}
        bases: Dict[str, str] = {}
        confidences: Dict[str, DataConfidence] = {}

        for src_name in target_sources:
            s_perf = source_map.get(src_name)
            if not s_perf:
                raw_weights[src_name] = 0.1
                bases[src_name] = "Default unconfigured baseline share."
                confidences[src_name] = DataConfidence.INSUFFICIENT_DATA
                continue

            confidences[src_name] = s_perf.confidence

            # Reliability factor
            if s_perf.reliability == "Blocked":
                rel_factor = 0.2
                rel_note = "Reliability constrained by endpoint anti-bot/blocking"
            elif s_perf.reliability in ("Disabled", "Placeholder"):
                rel_factor = 0.1
                rel_note = "Inactive / placeholder connector"
            else:
                rel_factor = 1.0
                rel_note = "Healthy API connector"

            # Yield factor
            if s_perf.jobs_found >= 5:
                yield_factor = 0.5 + (0.5 * ((s_perf.relevance_rate or 0) / 100.0)) + (0.3 * ((s_perf.preferred_location_rate or 0) / 100.0))
                basis_text = f"{rel_note}; {s_perf.relevance_rate}% relevance yield; {s_perf.preferred_location_rate}% preferred location match."
            elif s_perf.jobs_found > 0:
                yield_factor = 0.4
                basis_text = f"{rel_note}; developing historical sample ({s_perf.jobs_found} jobs)."
            else:
                yield_factor = 0.2
                basis_text = f"{rel_note}; 0 historical listings collected."

            weight = rel_factor * yield_factor
            raw_weights[src_name] = weight
            bases[src_name] = basis_text

        # Normalize to 100.0%
        sum_weights = sum(raw_weights.values()) or 1.0
        pct_dict: Dict[str, float] = {}
        for src_name, w in raw_weights.items():
            pct = round((w / sum_weights) * 100.0, 1)
            pct_dict[src_name] = pct

        # Ensure exact 100.0% sum after rounding
        diff = round(100.0 - sum(pct_dict.values()), 1)
        if diff != 0.0:
            top_src = max(pct_dict.keys(), key=lambda k: pct_dict[k])
            pct_dict[top_src] = round(pct_dict[top_src] + diff, 1)

        for src_name in target_sources:
            allocations.append(
                SourceBudgetRecommendation(
                    source=src_name,
                    allocated_percentage=pct_dict[src_name],
                    basis=bases[src_name],
                    confidence=confidences.get(src_name, DataConfidence.INSUFFICIENT_DATA),
                )
            )

        allocations.sort(key=lambda a: -a.allocated_percentage)
        return allocations

    def generate_strategy(
        self,
        total_jobs: int,
        relevant_jobs: int,
        source_performances: List[SourceSearchPerformance],
        role_locations: List[RoleLocationPerformance],
        gaps: List[SearchGap],
    ) -> SearchStrategy:
        """Synthesize deterministic daily search priorities and operational observations."""
        warnings: List[str] = []

        # 1. Overall status & Data confidence
        has_blocked_source = any(s.reliability == "Blocked" for s in source_performances)
        if has_blocked_source:
            status = StrategyStatus.NEEDS_ATTENTION
            blocked_srcs = [s.source for s in source_performances if s.reliability == "Blocked"]
            warnings.append(
                f"Source connection restricted: {', '.join(blocked_srcs)} encountered anti-bot / rate limiting. "
                "Review collector intervals or run safe manual review."
            )
        elif total_jobs < 10:
            status = StrategyStatus.DATA_LIMITED
            warnings.append(
                f"Small historical sample size ({total_jobs} total listings). "
                "Recommendations are directional and will solidify as daily collections accumulate."
            )
        elif relevant_jobs >= 5:
            status = StrategyStatus.HEALTHY
        else:
            status = StrategyStatus.DEVELOPING

        # Data confidence
        if total_jobs >= 20:
            confidence = DataConfidence.ACTIONABLE_DATA
        elif total_jobs >= 5:
            confidence = DataConfidence.LIMITED_DATA
        else:
            confidence = DataConfidence.INSUFFICIENT_DATA

        # Foreign remote check warning
        foreign_count = sum(s.foreign_remote_jobs for s in source_performances)
        if foreign_count > 0:
            warnings.append(
                f"Detected {foreign_count} foreign-only remote opportunity(ies) in database. "
                "These are excluded from India-eligible priorities to keep recommendations realistic."
            )

        # 2. Ranked priorities (Top 5 Role + Location combinations)
        ranked_priorities: List[str] = []
        for idx, rl in enumerate(role_locations[:5], start=1):
            ranked_priorities.append(
                f"{idx}. {rl.role_name} + {rl.location_name} ({rl.priority.value})"
            )

        if not ranked_priorities:
            ranked_priorities.append("1. Software Engineer + Bangalore / Bengaluru (MONITOR - Insufficient data)")

        # 3. Key actions
        key_actions: List[str] = []
        increase_srcs = [s.source for s in source_performances if s.recommendation == SourceActionRecommendation.INCREASE_SEARCH_DEPTH]
        if increase_srcs:
            key_actions.append(f"Increase search depth on top producing source(s): {', '.join(increase_srcs)}.")
        else:
            key_actions.append("Maintain baseline search depth across enabled source connectors.")

        if role_locations:
            top_combo = role_locations[0]
            key_actions.append(f"Prioritize listings matching: {top_combo.role_name} in {top_combo.location_name}.")

        if gaps:
            key_actions.append(f"Explore underrepresented target areas: {gaps[0].item_name} ({gaps[0].gap_type.value}).")

        summary = (
            f"Strategy Status: {status.value} (Confidence: {confidence.value}). "
            f"Identified {relevant_jobs} relevant opportunities from {total_jobs} total listings across "
            f"{len(source_performances)} source connectors."
        )

        return SearchStrategy(
            overall_status=status,
            data_confidence=confidence,
            summary=summary,
            ranked_priorities=ranked_priorities,
            key_actions=key_actions,
            warnings=warnings,
        )

    def get_search_intelligence_report(
        self,
        jobs: Optional[List[Dict[str, Any]]] = None,
    ) -> SearchIntelligenceReport:
        """Construct the complete deterministic Phase 13 Search Intelligence report."""
        if jobs is not None:
            raw_jobs = jobs
            health_data = self.db.get_source_health() if self.db else []
        elif self.db:
            raw_jobs = self.db.get_all_jobs_raw()
            health_data = self.db.get_source_health()
        else:
            raw_jobs = []
            health_data = []

        total_jobs = len(raw_jobs)
        relevant_jobs = sum(1 for j in raw_jobs if (j.get("match_score") or 0) >= 60)
        recommended_jobs = sum(
            1 for j in raw_jobs
            if str(j.get("application_priority") or "").upper() in ("URGENT", "HIGH", "NORMAL")
        )
        applied_jobs = sum(
            1 for j in raw_jobs
            if j.get("status") in ("APPLIED", "INTERVIEW", "OFFER")
        )

        target_roles = self.profile.target_roles if self.profile else [
            "Python Developer", "Backend Developer", "Software Engineer", "Full Stack Developer",
            "Web Developer", "ML Engineer", "AI Engineer", "SDE Intern"
        ]

        # 1. Source Intelligence
        sources_perf = self.compute_source_performance(raw_jobs, health_data)

        # 2. Role Intelligence
        roles_perf = self.compute_role_performance(raw_jobs, target_roles)

        # 3. Location Intelligence
        locations_perf = self.compute_location_performance(raw_jobs)

        # 4. Role × Location Matrix
        role_locations = self.compute_role_location_matrix(raw_jobs, target_roles)

        # 5. Source × Role Matrix
        source_roles = self.compute_source_role_matrix(raw_jobs, target_roles)

        # 6. Source × Location Matrix
        source_locations = self.compute_source_location_matrix(raw_jobs)

        # 7. Search Coverage Gaps
        gaps = self.identify_search_gaps(target_roles, roles_perf, locations_perf)

        # 8. Search Budget Allocation
        budget_allocations = self.compute_search_budget(sources_perf)

        # 9. Source Recommendations
        source_recommendations = [
            SourceRecommendation(
                source=s.source,
                action=s.recommendation,
                priority=s.recommendation_priority,
                reason=s.recommendation_reason,
                confidence=s.confidence,
            )
            for s in sources_perf
        ]

        # 10. General Search Recommendations
        recommendations: List[SearchRecommendation] = []
        for s in sources_perf:
            if s.recommendation == SourceActionRecommendation.INCREASE_SEARCH_DEPTH:
                recommendations.append(
                    SearchRecommendation(
                        category="SOURCE",
                        title=f"Prioritize {s.source}",
                        recommendation=f"Increase search depth and review frequency for {s.source}.",
                        priority=s.recommendation_priority,
                        reason=s.recommendation_reason,
                        confidence=s.confidence,
                    )
                )
            elif s.recommendation == SourceActionRecommendation.REDUCE_SEARCH_DEPTH:
                recommendations.append(
                    SearchRecommendation(
                        category="SOURCE",
                        title=f"De-emphasize {s.source}",
                        recommendation=f"Reduce depth or refine filters on {s.source}.",
                        priority=s.recommendation_priority,
                        reason=s.recommendation_reason,
                        confidence=s.confidence,
                    )
                )

        if role_locations:
            top_combo = role_locations[0]
            if top_combo.priority in (RecommendationPriority.HIGH, RecommendationPriority.CRITICAL):
                recommendations.append(
                    SearchRecommendation(
                        category="COMBINATION",
                        title=f"Top Corridor: {top_combo.role_name} in {top_combo.location_name}",
                        recommendation=f"Focus daily queries on {top_combo.role_name} positions in {top_combo.location_name}.",
                        priority=top_combo.priority,
                        reason=f"Produces highest volume of relevant opportunities ({top_combo.relevant_jobs} relevant, {top_combo.avg_match_score} avg match).",
                        confidence=top_combo.confidence,
                    )
                )

        for gap in gaps[:3]:
            recommendations.append(
                SearchRecommendation(
                    category="GAP",
                    title=f"Coverage Gap: {gap.item_name}",
                    recommendation=gap.suggestion,
                    priority=RecommendationPriority.MEDIUM,
                    reason=gap.details,
                    confidence=DataConfidence.INSUFFICIENT_DATA,
                )
            )

        # 11. Strategy Synthesis
        strategy = self.generate_strategy(
            total_jobs, relevant_jobs, sources_perf, role_locations, gaps
        )

        overall_confidence = self._evaluate_confidence(total_jobs)

        return SearchIntelligenceReport(
            total_jobs=total_jobs,
            relevant_jobs=relevant_jobs,
            recommended_jobs=recommended_jobs,
            applied_jobs=applied_jobs,
            data_confidence=overall_confidence,
            strategy=strategy,
            sources=sources_perf,
            roles=roles_perf,
            locations=locations_perf,
            role_locations=role_locations,
            source_roles=source_roles,
            source_locations=source_locations,
            search_gaps=gaps,
            budget_allocations=budget_allocations,
            source_recommendations=source_recommendations,
            recommendations=recommendations,
            warnings=strategy.warnings,
        )
