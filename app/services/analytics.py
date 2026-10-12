"""Deterministic, explainable application analytics and optimization service (Phase 12).

Calculates pipeline conversion rates, time-series activity, source/role/location metrics,
score bucket breakdowns, deterministic source quality scores, and actionable strategy insights.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.database.database import DatabaseManager
from app.models.analytics import (
    AccessibilityMetric,
    AnalyticsReport,
    ApplicationStreak,
    ConversionRates,
    DailyActivityRow,
    DailyTargetStatus,
    ExperienceMetric,
    FunnelStageCount,
    LocationMetric,
    OptimizationInsight,
    RoleMetric,
    ScoreBucketMetric,
    SkillMetric,
    SourceMetric,
    WeeklyComparison,
)
from app.models.profile import JobProfile

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service orchestrating application funnel analytics and optimization insights."""

    def __init__(self, db: DatabaseManager, profile: Optional[JobProfile] = None):
        self.db = db
        self.profile = profile

    def compute_source_quality_score(
        self,
        jobs_found: int,
        relevant: int,
        recommended: int,
        applied: int,
        interview: int,
        offer: int,
    ) -> Tuple[Optional[float], str]:
        """Calculate a deterministic 0-100 source quality score.

        Formula:
          - Relevance Rate (40% weight): (relevant / jobs_found) * 100
          - Recommended Rate (25% weight): (recommended / jobs_found) * 100
          - Application Conversion (20% weight): (applied / relevant) * 100 if relevant > 0 else 0
          - Interview Conversion (15% weight): (interview / applied) * 100 if applied > 0 else 0

        Small Sample Protection:
          If jobs_found < 5, returns (None, 'Insufficient data') to prevent overfitting.
        """
        if jobs_found < 5:
            return None, "Insufficient data"

        relevance_rate = (relevant / jobs_found) * 100.0
        rec_rate = (recommended / jobs_found) * 100.0
        app_rate = (applied / relevant * 100.0) if relevant > 0 else 0.0
        int_rate = (interview / applied * 100.0) if applied > 0 else 0.0

        score = (
            (relevance_rate * 0.40)
            + (rec_rate * 0.25)
            + (app_rate * 0.20)
            + (int_rate * 0.15)
        )
        score = round(min(100.0, max(0.0, score)), 1)

        if score >= 75.0:
            label = "Strong Quality"
        elif score >= 50.0:
            label = "Moderate Quality"
        elif score >= 25.0:
            label = "Developing"
        else:
            label = "Low Conversion"

        return score, label

    def generate_insights(self, report: AnalyticsReport) -> List[OptimizationInsight]:
        """Generate deterministic, data-backed optimization insights and observations."""
        insights: List[OptimizationInsight] = []
        funnel = report.funnel
        daily = report.daily_target

        # 1. Small Dataset Protection
        if funnel.applied < 3:
            insights.append(
                OptimizationInsight(
                    category="LIMITATION",
                    title="Limited Application Sample Size",
                    message=(
                        f"Only {funnel.applied} application(s) recorded in total. "
                        "Statistical conversion trends (such as interview rate and offer rate) "
                        "require at least 3–5 tracked manual applications before drawing firm conclusions."
                    ),
                    actionable=False,
                )
            )

        if funnel.interview < 3 and funnel.applied >= 3:
            insights.append(
                OptimizationInsight(
                    category="LIMITATION",
                    title="Limited Interview Outcomes",
                    message=(
                        f"You have {funnel.applied} submitted application(s) and {funnel.interview} interview(s). "
                        "More outcome data is needed before revising resume positioning or search filters."
                    ),
                    actionable=False,
                )
            )

        # 2. Pipeline Volume & Conversion Observations
        if funnel.jobs_found > 0 and funnel.relevant > 0:
            rel_pct = round((funnel.relevant / funnel.jobs_found) * 100, 1)
            if rel_pct >= 60.0:
                insights.append(
                    OptimizationInsight(
                        category="POSITIVE",
                        title="High Relevance Yield",
                        message=(
                            f"Strong filtering performance: {rel_pct}% ({funnel.relevant}/{funnel.jobs_found}) "
                            "of discovered opportunities match your target profile rules."
                        ),
                        actionable=False,
                    )
                )

        if funnel.recommended >= 3 and funnel.applied == 0:
            insights.append(
                OptimizationInsight(
                    category="WARNING",
                    title="Pending Application Pipeline",
                    message=(
                        f"Discovery is outpacing manual submission: you have {funnel.recommended} recommended "
                        "opportunities awaiting review, but 0 manual applications recorded."
                    ),
                    actionable=True,
                )
            )
        elif funnel.recommended >= 5 and (funnel.applied / funnel.recommended) < 0.3:
            insights.append(
                OptimizationInsight(
                    category="VOLUME",
                    title="Manual Applications Lagging Discovery",
                    message=(
                        f"You have submitted {funnel.applied} application(s) out of {funnel.recommended} recommended "
                        f"opportunities ({round((funnel.applied / funnel.recommended) * 100, 1)}% application rate). "
                        "Consider reviewing your Apply Today queue to increase submissions."
                    ),
                    actionable=True,
                )
            )

        # 3. Daily Target Progress
        if daily.remaining > 0:
            insights.append(
                OptimizationInsight(
                    category="SUGGESTION",
                    title="Daily Application Target",
                    message=(
                        f"Daily goal: {daily.target} applications. You have completed {daily.applied_today} today "
                        f"({daily.remaining} remaining to reach 100% target achievement)."
                    ),
                    actionable=True,
                )
            )
        elif daily.applied_today >= daily.target and daily.target > 0:
            insights.append(
                OptimizationInsight(
                    category="POSITIVE",
                    title="Daily Target Achieved",
                    message=f"Goal met! You have completed {daily.applied_today}/{daily.target} applications today.",
                    actionable=False,
                )
            )

        # 4. Source Observations
        if report.sources:
            qualified_sources = [s for s in report.sources if s.jobs_found >= 5]
            if qualified_sources:
                best_source = max(
                    qualified_sources,
                    key=lambda s: (s.relevance_rate or 0.0, s.relevant),
                )
                if (best_source.relevance_rate or 0.0) >= 50.0:
                    insights.append(
                        OptimizationInsight(
                            category="SOURCE",
                            title=f"Top Performing Source: {best_source.source.title()}",
                            message=(
                                f"{best_source.source.title()} produces your highest relevance rate "
                                f"({best_source.relevance_rate}%, {best_source.relevant}/{best_source.jobs_found} jobs). "
                                "Prioritize reviewing listings from this board."
                            ),
                            actionable=True,
                        )
                    )
            else:
                insights.append(
                    OptimizationInsight(
                        category="SOURCE",
                        title="Source Sample Developing",
                        message=(
                            "All job boards currently have fewer than 5 listings in the selected window. "
                            "Quality scores will unlock as more daily collection runs accumulate."
                        ),
                        actionable=False,
                    )
                )

        # 5. Score Performance Observations
        high_match = next((b for b in report.match_buckets if "80–89" in b.bucket_label or "90–100" in b.bucket_label), None)
        if high_match and high_match.jobs_count > 0:
            insights.append(
                OptimizationInsight(
                    category="POSITIVE",
                    title="Quality Job Targeting",
                    message=(
                        f"You have identified {high_match.jobs_count} job(s) in high match score tiers (80–100). "
                        "Applying to these roles provides maximum alignment with your skills and preferred stack."
                    ),
                    actionable=False,
                )
            )

        return insights

    def get_report(
        self,
        period: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source: Optional[str] = None,
        role: Optional[str] = None,
        location: Optional[str] = None,
        daily_target: int = 5,
    ) -> AnalyticsReport:
        """Construct the complete Phase 12 analytics report."""
        # 1. Summary counts
        summary = self.db.get_analytics_summary(
            period=period,
            start_date=start_date,
            end_date=end_date,
            source=source,
            role=role,
            location=location,
        )

        funnel = FunnelStageCount(
            jobs_found=summary["total_jobs"],
            relevant=summary["relevant"],
            recommended=summary["recommended"],
            applied=summary["applied"],
            interview=summary["interview"],
            offer=summary["offer"],
            rejected=summary["rejected"],
            not_interested=summary["not_interested"],
        )

        # 2. Conversion Rates (with zero denominator protection)
        app_rate = (
            round((funnel.applied / funnel.relevant) * 100.0, 1)
            if funnel.relevant > 0
            else None
        )
        rec_to_app_rate = (
            round((funnel.applied / funnel.recommended) * 100.0, 1)
            if funnel.recommended > 0
            else None
        )
        int_rate = (
            round((funnel.interview / funnel.applied) * 100.0, 1)
            if funnel.applied > 0
            else None
        )
        offer_rate = (
            round((funnel.offer / funnel.applied) * 100.0, 1)
            if funnel.applied > 0
            else None
        )
        int_to_offer_rate = (
            round((funnel.offer / funnel.interview) * 100.0, 1)
            if funnel.interview > 0
            else None
        )

        conversion_rates = ConversionRates(
            application_rate=app_rate,
            recommendation_to_app_rate=rec_to_app_rate,
            interview_rate=int_rate,
            offer_rate=offer_rate,
            interview_to_offer_rate=int_to_offer_rate,
        )

        # 3. Source Analytics & Quality Score
        raw_sources = self.db.get_source_analytics(
            period=period, start_date=start_date, end_date=end_date
        )
        source_metrics: List[SourceMetric] = []
        for s in raw_sources:
            found = s["jobs_found"]
            rel = s["relevant"]
            rec = s["recommended"]
            app = s["applied"]
            inter = s["interview"]
            off = s["offer"]

            r_rate = round((rel / found) * 100.0, 1) if found > 0 else None
            a_rate = round((app / rel) * 100.0, 1) if rel > 0 else None
            i_rate = round((inter / app) * 100.0, 1) if app > 0 else None

            q_score, q_label = self.compute_source_quality_score(
                found, rel, rec, app, inter, off
            )
            source_metrics.append(
                SourceMetric(
                    source=s["source"],
                    jobs_found=found,
                    relevant=rel,
                    recommended=rec,
                    applied=app,
                    interview=inter,
                    offer=off,
                    relevance_rate=r_rate,
                    application_rate=a_rate,
                    interview_rate=i_rate,
                    quality_score=q_score,
                    quality_label=q_label,
                )
            )

        # 4. Role Analytics
        target_roles = self.profile.target_roles if self.profile else None
        raw_roles = self.db.get_role_analytics(
            target_roles=target_roles,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
        role_metrics: List[RoleMetric] = []
        for r in raw_roles:
            app = r["applied"]
            inter = r["interview"]
            i_rate = round((inter / app) * 100.0, 1) if app > 0 else None
            role_metrics.append(
                RoleMetric(
                    role_name=r["role_name"],
                    jobs_found=r["jobs_found"],
                    relevant=r["relevant"],
                    recommended=r["recommended"],
                    applied=app,
                    interview=inter,
                    offer=r["offer"],
                    interview_rate=i_rate,
                )
            )

        # 5. Location Analytics
        pref_locs = self.profile.preferred_locations if self.profile else None
        raw_locations = self.db.get_location_analytics(
            preferred_locations=pref_locs,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
        location_metrics: List[LocationMetric] = []
        for loc in raw_locations:
            rel = loc["relevant"]
            app = loc["applied"]
            inter = loc["interview"]
            a_rate = round((app / rel) * 100.0, 1) if rel > 0 else None
            i_rate = round((inter / app) * 100.0, 1) if app > 0 else None
            location_metrics.append(
                LocationMetric(
                    location_name=loc["location_name"],
                    jobs_found=loc["jobs_found"],
                    relevant=rel,
                    recommended=loc["recommended"],
                    applied=app,
                    interview=inter,
                    offer=loc["offer"],
                    application_rate=a_rate,
                    interview_rate=i_rate,
                )
            )

        # 6. Score Bucket Analytics
        raw_buckets = self.db.get_score_bucket_analytics(
            period=period, start_date=start_date, end_date=end_date
        )
        match_buckets = [
            ScoreBucketMetric(
                bucket_label=b["bucket_label"],
                jobs_count=b["jobs_count"],
                applied=b["applied"],
                interview=b["interview"],
                offer=b["offer"],
                interview_rate=b["interview_rate"],
            )
            for b in raw_buckets["match_buckets"]
        ]
        readiness_buckets = [
            ScoreBucketMetric(
                bucket_label=b["bucket_label"],
                jobs_count=b["jobs_count"],
                applied=b["applied"],
                interview=b["interview"],
                offer=b["offer"],
                interview_rate=b["interview_rate"],
            )
            for b in raw_buckets["readiness_buckets"]
        ]
        resume_buckets = [
            ScoreBucketMetric(
                bucket_label=b["bucket_label"],
                jobs_count=b["jobs_count"],
                applied=b["applied"],
                interview=b["interview"],
                offer=b["offer"],
                interview_rate=b["interview_rate"],
            )
            for b in raw_buckets["resume_buckets"]
        ]

        # 7. Easy Apply & Experience Fit
        raw_easy = self.db.get_easy_apply_analytics(
            period=period, start_date=start_date, end_date=end_date
        )
        easy_apply_metrics = [
            AccessibilityMetric(
                type_label=e["type_label"],
                relevant=e["relevant"],
                applied=e["applied"],
                interview=e["interview"],
                offer=e["offer"],
            )
            for e in raw_easy
        ]

        raw_exp = self.db.get_experience_analytics(
            period=period, start_date=start_date, end_date=end_date
        )
        exp_metrics = [
            ExperienceMetric(
                level_label=ex["level_label"],
                relevant=ex["relevant"],
                applied=ex["applied"],
                interview=ex["interview"],
            )
            for ex in raw_exp
        ]

        # 8. Observed Skills
        raw_skills = self.db.get_skills_analytics(
            period=period, start_date=start_date, end_date=end_date
        )
        skill_metrics = [
            SkillMetric(
                skill=sk["skill"],
                applied_count=sk["applied_count"],
                interview_count=sk["interview_count"],
                offer_count=sk["offer_count"],
            )
            for sk in raw_skills
        ]

        # 9. Daily Activity
        raw_daily = self.db.get_daily_activity(
            period=period if period in ("today", "7d", "30d", "90d") else "30d",
            start_date=start_date,
            end_date=end_date,
        )
        daily_rows = [
            DailyActivityRow(
                date_str=d["date_str"],
                jobs_found=d["jobs_found"],
                relevant=d["relevant"],
                applied=d["applied"],
                interviews=d["interviews"],
                offers=d["offers"],
            )
            for d in raw_daily
        ]

        # 10. Weekly Comparison
        raw_weekly = self.db.get_weekly_comparison()
        weekly_comp = WeeklyComparison(**raw_weekly) if raw_weekly else None

        # 11. Daily Target Progress & Streaks
        raw_target = self.db.get_daily_target_status(target=daily_target)
        daily_target_status = DailyTargetStatus(**raw_target)

        raw_streak = self.db.get_application_streak()
        streak = ApplicationStreak(**raw_streak)

        # Assemble Report
        report = AnalyticsReport(
            funnel=funnel,
            conversion_rates=conversion_rates,
            period=period,
            sources=source_metrics,
            roles=role_metrics,
            locations=location_metrics,
            match_buckets=match_buckets,
            readiness_buckets=readiness_buckets,
            resume_buckets=resume_buckets,
            easy_apply=easy_apply_metrics,
            experience=exp_metrics,
            skills=skill_metrics,
            daily_activity=daily_rows,
            weekly=weekly_comp,
            daily_target=daily_target_status,
            streak=streak,
            is_small_sample=(funnel.applied < 3),
        )

        # 12. Generate deterministic insights
        report.insights = self.generate_insights(report)

        return report
