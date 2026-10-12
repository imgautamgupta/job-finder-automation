"""Deterministic, local-first Personal Job Agent Workflow Service (Phase 14).

Orchestrates search recommendations, resume intelligence, manual application workflow,
follow-ups, interview preparation, application analytics, and daily targets into a
unified command center.

CRITICAL SAFETY GUARANTEES:
1. Zero automated form submission or browser automation for applying.
2. Zero external LLM or paid API usage (100% deterministic & local-first).
3. Zero silent lifecycle status alterations or historical data modifications.
4. All actual job applications remain strictly HUMAN-CONTROLLED.
"""

from datetime import date, datetime
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from app.database.database import DatabaseManager
from app.models.job import ApplicationPriority, Job, JobStatus
from app.models.job_agent import (
    AgentAction,
    AgentActionPriority,
    AgentActionStatus,
    AgentActionType,
    DailyJobPlan,
    JobAgentRecommendation,
    JobAgentReport,
    JobAgentSummary,
)
from app.models.profile import JobProfile
from app.services.analytics import AnalyticsService
from app.services.interview_preparation import InterviewPreparationService
from app.services.recommender import JobRecommender
from app.services.resume_intelligence import ResumeIntelligenceService
from app.services.search_intelligence import SearchIntelligenceService

logger = logging.getLogger(__name__)

SAFETY_NOTICES = [
    "Human-in-the-loop: All job applications remain strictly manual. The agent never auto-applies.",
    "Deterministic & Local: No external LLMs, paid APIs, or third-party web scrapers are used.",
    "Integrity: No credentials, browser cookies, CAPTCHA solvers, or stealth browsers are employed.",
    "Data Safety: Lifecycle states and application history are never altered silently.",
]


class JobAgentService:
    """Central orchestration service for the Advanced Personal Job-Agent Workflow."""

    # In-memory action overrides for user interactive sessions (does NOT alter DB)
    _action_state_overrides: Dict[str, AgentActionStatus] = {}

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        profile: Optional[JobProfile] = None,
        recommender: Optional[JobRecommender] = None,
        resume_service: Optional[ResumeIntelligenceService] = None,
        interview_service: Optional[InterviewPreparationService] = None,
        analytics_service: Optional[AnalyticsService] = None,
        search_intelligence_service: Optional[SearchIntelligenceService] = None,
    ):
        self.db = db
        self.profile = profile or self._load_profile_fallback()
        self.recommender = recommender or JobRecommender(self.profile)
        self.resume_service = resume_service or ResumeIntelligenceService(self.profile)
        self.interview_service = interview_service or InterviewPreparationService(self.profile)
        self.analytics_service = analytics_service or (AnalyticsService(db=self.db, profile=self.profile) if self.db else None)
        self.search_intelligence_service = search_intelligence_service or SearchIntelligenceService(db=self.db, profile=self.profile)

    def _load_profile_fallback(self) -> JobProfile:
        """Load job profile from settings or sensible deterministic default."""
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
            preferred_locations=["Bangalore", "Bengaluru", "Delhi", "Noida", "Remote", "India"],
            skills=["Python", "FastAPI", "SQL", "Git", "REST APIs"],
        )

    def mark_action_status(self, action_id: str, status: AgentActionStatus) -> None:
        """Explicitly record a user override for an action status without touching the database."""
        self._action_state_overrides[action_id] = status

    def clear_action_overrides(self) -> None:
        """Clear session action overrides."""
        self._action_state_overrides.clear()

    # -------------------------------------------------------------------------
    # ACTION GENERATORS
    # -------------------------------------------------------------------------

    def _generate_follow_up_actions(self, jobs: List[Job], today_str: str) -> List[AgentAction]:
        """Detect due, overdue, and neglected follow-ups."""
        actions: List[AgentAction] = []
        today_d = date.fromisoformat(today_str)

        for j in jobs:
            st = j.status.value if hasattr(j.status, "value") else str(j.status)
            if st in ("REJECTED", "NOT_INTERESTED", "OFFER"):
                continue

            # Case 1: Scheduled follow-up date exists
            if j.follow_up_date:
                try:
                    # Support ISO strings like YYYY-MM-DD or full timestamps
                    fu_str = str(j.follow_up_date).split("T")[0].split(" ")[0].strip()
                    fu_d = date.fromisoformat(fu_str)
                    diff_days = (fu_d - today_d).days

                    if diff_days < 0:
                        actions.append(
                            AgentAction(
                                id=f"act_followup_overdue_{j.id}",
                                action_type=AgentActionType.FOLLOW_UP,
                                priority=AgentActionPriority.URGENT,
                                title=f"Overdue Follow-up: {j.company}",
                                description=f"Follow-up for {j.title} at {j.company} was due on {fu_str} ({abs(diff_days)} day(s) ago).",
                                reason=f"Follow-up scheduled for {fu_str} is overdue. Prompt polite follow-up increases recruiter response rate.",
                                job_id=j.id,
                                job_title=j.title,
                                company=j.company,
                                match_score=j.match_score,
                                readiness_score=j.application_readiness_score,
                                resume_score=j.resume_alignment_score,
                                lifecycle_status=st,
                                due_date=fu_str,
                                checklist=[
                                    "Review original application details and job requirements",
                                    "Draft polite inquiry regarding application status",
                                    "Send message via portal or email manually",
                                    "Update follow-up notes in tracker",
                                ],
                            )
                        )
                    elif diff_days == 0:
                        actions.append(
                            AgentAction(
                                id=f"act_followup_today_{j.id}",
                                action_type=AgentActionType.FOLLOW_UP,
                                priority=AgentActionPriority.URGENT,
                                title=f"Follow-up Due Today: {j.company}",
                                description=f"Follow-up for {j.title} at {j.company} is scheduled for today.",
                                reason=f"Today ({today_str}) is the scheduled follow-up date for this active application.",
                                job_id=j.id,
                                job_title=j.title,
                                company=j.company,
                                match_score=j.match_score,
                                readiness_score=j.application_readiness_score,
                                resume_score=j.resume_alignment_score,
                                lifecycle_status=st,
                                due_date=fu_str,
                                checklist=[
                                    "Review job posting and initial submission date",
                                    "Prepare concise follow-up email/message",
                                    "Send manually through appropriate channel",
                                    "Update next follow-up date in application tracker",
                                ],
                            )
                        )
                    elif 1 <= diff_days <= 3:
                        actions.append(
                            AgentAction(
                                id=f"act_followup_upcoming_{j.id}",
                                action_type=AgentActionType.FOLLOW_UP,
                                priority=AgentActionPriority.MEDIUM,
                                title=f"Approaching Follow-up: {j.company}",
                                description=f"Follow-up scheduled on {fu_str} (in {diff_days} day(s)).",
                                reason=f"Follow-up approaching on {fu_str}. Prepare talking points ahead of time.",
                                job_id=j.id,
                                job_title=j.title,
                                company=j.company,
                                match_score=j.match_score,
                                readiness_score=j.application_readiness_score,
                                resume_score=j.resume_alignment_score,
                                lifecycle_status=st,
                                due_date=fu_str,
                            )
                        )
                except Exception as e:
                    logger.debug("Error parsing follow_up_date for job %s: %s", j.id, e)

            # Case 2: Application Neglect Detection (APPLIED with no follow-up scheduled)
            elif st == "APPLIED":
                # Check applied_at age
                applied_days = None
                if j.applied_at:
                    try:
                        app_str = str(j.applied_at).split("T")[0].split(" ")[0].strip()
                        app_d = date.fromisoformat(app_str)
                        applied_days = (today_d - app_d).days
                    except Exception:
                        pass

                if applied_days is not None and applied_days >= 14:
                    actions.append(
                        AgentAction(
                            id=f"act_neglect_long_{j.id}",
                            action_type=AgentActionType.UPDATE_APPLICATION,
                            priority=AgentActionPriority.HIGH,
                            title=f"Needs Attention: Check Application for {j.company}",
                            description=f"Applied {applied_days} days ago with no follow-up scheduled or recent update.",
                            reason=f"Application has been active for {applied_days} days without scheduled touchpoints. Review listing status or schedule a follow-up.",
                            job_id=j.id,
                            job_title=j.title,
                            company=j.company,
                            match_score=j.match_score,
                            readiness_score=j.application_readiness_score,
                            resume_score=j.resume_alignment_score,
                            lifecycle_status=st,
                            checklist=[
                                "Check employer portal or email for status changes",
                                "Schedule a follow-up or update status if closed",
                            ],
                        )
                    )
                elif applied_days is not None and applied_days >= 5:
                    actions.append(
                        AgentAction(
                            id=f"act_neglect_sched_{j.id}",
                            action_type=AgentActionType.FOLLOW_UP,
                            priority=AgentActionPriority.HIGH,
                            title=f"Needs Attention: Schedule Follow-up for {j.company}",
                            description=f"Applied {applied_days} days ago with no follow-up scheduled.",
                            reason=f"Applied on {app_str} ({applied_days} days ago). Reaching out 5–7 days post-application is standard practice.",
                            job_id=j.id,
                            job_title=j.title,
                            company=j.company,
                            match_score=j.match_score,
                            readiness_score=j.application_readiness_score,
                            resume_score=j.resume_alignment_score,
                            lifecycle_status=st,
                            checklist=[
                                "Draft brief status inquiry",
                                "Select a target follow-up date in the tracker",
                            ],
                        )
                    )

        return actions

    def _generate_interview_actions(self, jobs: List[Job], today_str: str) -> List[AgentAction]:
        """Generate preparation actions for upcoming and scheduled interviews."""
        actions: List[AgentAction] = []
        today_d = date.fromisoformat(today_str)

        for j in jobs:
            st = j.status.value if hasattr(j.status, "value") else str(j.status)
            int_st = str(getattr(j.interview_status, "value", j.interview_status) or "").upper()
            has_interview = (st == "INTERVIEW") or (int_st in ("SCHEDULED", "RESCHEDULED")) or (j.interview_date is not None and str(j.interview_date).strip() != "")

            if not has_interview:
                continue

            diff_days = None
            date_str = None
            if j.interview_date:
                try:
                    date_str = str(j.interview_date).split("T")[0].split(" ")[0].strip()
                    i_d = date.fromisoformat(date_str)
                    diff_days = (i_d - today_d).days
                except Exception:
                    pass

            # Determine priority based on proximity
            is_imminent = (diff_days is not None and diff_days <= 3) or (diff_days is None and st == "INTERVIEW")
            priority = AgentActionPriority.URGENT if is_imminent else AgentActionPriority.HIGH

            # Generate preparation content using existing InterviewPreparationService
            prep_pkg = self.interview_service.generate_preparation_package(j)
            checklist = (prep_pkg.checklist or [])[:6]
            skills = (prep_pkg.missing_skills or [])[:4]

            stage_text = f" ({j.interview_stage})" if j.interview_stage else ""
            timing_text = f"scheduled on {date_str}" if date_str else "scheduled"

            actions.append(
                AgentAction(
                    id=f"act_interview_{j.id}",
                    action_type=AgentActionType.PREPARE_INTERVIEW,
                    priority=priority,
                    title=f"Prepare Interview: {j.company}{stage_text}",
                    description=f"Interview {timing_text} for {j.title}. Review core technical topics and project stories.",
                    reason=f"Interview {timing_text}. Rehearsing technical topics and STAR stories ensures optimal confidence.",
                    job_id=j.id,
                    job_title=j.title,
                    company=j.company,
                    match_score=j.match_score,
                    readiness_score=j.application_readiness_score,
                    resume_score=j.resume_alignment_score,
                    lifecycle_status=st,
                    due_date=date_str,
                    skills_to_emphasize=skills,
                    checklist=checklist,
                    metadata={"prep_status": str(getattr(j, "interview_preparation_status", None) or getattr(j, "interview_prep_status", None) or "NOT_STARTED")},
                )
            )

        return actions

    def _generate_application_and_prep_actions(self, jobs: List[Job]) -> List[AgentAction]:
        """Generate deterministic resume prep, manual application, and review actions."""
        actions: List[AgentAction] = []
        excluded_statuses = {"APPLIED", "INTERVIEW", "OFFER", "REJECTED", "NOT_INTERESTED"}

        for j in jobs:
            st = j.status.value if hasattr(j.status, "value") else str(j.status)
            if st in excluded_statuses:
                continue

            match = j.match_score or 0
            readiness = j.application_readiness_score or 0
            prio = j.application_priority.value if hasattr(j.application_priority, "value") else str(j.application_priority or "")
            prep_status = str(getattr(j.preparation_status, "value", j.preparation_status) or "").upper()

            # Analyze resume alignment & recommendations using existing ResumeIntelligenceService
            resume_analysis = self.resume_service.analyze(j)
            skills_to_emp = resume_analysis.skills_to_emphasize[:4]
            rec_proj = resume_analysis.recommended_project if isinstance(resume_analysis.recommended_project, str) else (resume_analysis.recommended_project.name if resume_analysis.recommended_project else None)

            # Action Tier 1: Ready to Apply manually (Preparation completed or ready)
            if prep_status == "READY" and readiness >= 65:
                act_prio = AgentActionPriority.URGENT if (prio == "URGENT" or match >= 85) else AgentActionPriority.HIGH
                actions.append(
                    AgentAction(
                        id=f"act_apply_{j.id}",
                        action_type=AgentActionType.APPLY_MANUALLY,
                        priority=act_prio,
                        title=f"Apply Manually: {j.company}",
                        description=f"Resume prep completed for {j.title} @ {j.company}. Ready for manual submission.",
                        reason=f"Application readiness is {readiness}/100 with Match {match}/100. Submit manually via company career portal.",
                        job_id=j.id,
                        job_title=j.title,
                        company=j.company,
                        match_score=match,
                        readiness_score=readiness,
                        resume_score=j.resume_alignment_score or resume_analysis.resume_alignment_score,
                        lifecycle_status=st,
                        skills_to_emphasize=skills_to_emp,
                        recommended_project=rec_proj,
                        checklist=[
                            f"Open job posting at {j.company}",
                            f"Emphasize keywords: {', '.join(skills_to_emp) if skills_to_emp else 'Core profile skills'}",
                            f"Highlight featured project: {rec_proj or 'Primary technical project'}",
                            "Submit manual application form directly on career portal",
                            "Record submission in tracker with date and notes",
                        ],
                    )
                )

            # Action Tier 2: High-value opportunity needing resume preparation
            elif (prio in ("URGENT", "HIGH") or match >= 75) and prep_status != "READY":
                act_prio = AgentActionPriority.URGENT if (prio == "URGENT" and match >= 85) else AgentActionPriority.HIGH
                actions.append(
                    AgentAction(
                        id=f"act_resume_{j.id}",
                        action_type=AgentActionType.PREPARE_RESUME,
                        priority=act_prio,
                        title=f"Prepare Resume: {j.company}",
                        description=f"Align resume for {j.title} ({match}% match, {readiness}% readiness).",
                        reason=f"High-quality posting. Tailoring resume keywords and selecting {rec_proj or 'relevant project'} maximizes application readiness.",
                        job_id=j.id,
                        job_title=j.title,
                        company=j.company,
                        match_score=match,
                        readiness_score=readiness,
                        resume_score=j.resume_alignment_score or resume_analysis.resume_alignment_score,
                        lifecycle_status=st,
                        skills_to_emphasize=skills_to_emp,
                        recommended_project=rec_proj,
                        checklist=[
                            f"Review missing keywords: {', '.join((getattr(resume_analysis, 'resume_missing_keywords', None) or getattr(resume_analysis, 'missing_keywords', []))[:4]) if (getattr(resume_analysis, 'resume_missing_keywords', None) or getattr(resume_analysis, 'missing_keywords', [])) else 'None'}",
                            f"Highlight primary project: {rec_proj or 'Primary project'}",
                            "Adjust resume bullet points to emphasize required frameworks",
                            "Mark preparation status as READY once verified",
                        ],
                    )
                )

            # Action Tier 3: Normal recommended matches
            elif match >= 60 and prio in ("NORMAL", "HIGH"):
                actions.append(
                    AgentAction(
                        id=f"act_review_{j.id}",
                        action_type=AgentActionType.REVIEW_JOB,
                        priority=AgentActionPriority.MEDIUM,
                        title=f"Review Match: {j.company}",
                        description=f"Review posting for {j.title} in {j.location}.",
                        reason=f"Deterministic match score is {match}/100. Evaluate requirements and shortlist if suitable.",
                        job_id=j.id,
                        job_title=j.title,
                        company=j.company,
                        match_score=match,
                        readiness_score=readiness,
                        resume_score=j.resume_alignment_score or resume_analysis.resume_alignment_score,
                        lifecycle_status=st,
                        skills_to_emphasize=skills_to_emp,
                        recommended_project=rec_proj,
                    )
                )

            # Action Tier 4: Lower-priority or developing match
            else:
                actions.append(
                    AgentAction(
                        id=f"act_review_low_{j.id}",
                        action_type=AgentActionType.REVIEW_JOB,
                        priority=AgentActionPriority.LOW,
                        title=f"Optional Review: {j.company}",
                        description=f"{j.title} ({match}% match).",
                        reason=f"Lower match score ({match}/100). Review if interested in expanding parameters.",
                        job_id=j.id,
                        job_title=j.title,
                        company=j.company,
                        match_score=match,
                        readiness_score=readiness,
                        resume_score=j.resume_alignment_score or resume_analysis.resume_alignment_score,
                        lifecycle_status=st,
                    )
                )

        return actions

    def _generate_system_and_search_actions(
        self,
        target_remaining: int,
        streak_days: int,
        search_report: Optional[Any],
    ) -> List[AgentAction]:
        """Generate high-level strategic actions for search intelligence and goal tracking."""
        actions: List[AgentAction] = []

        # Search Strategy review action
        if search_report and (search_report.recommendations or search_report.search_gaps):
            top_rec = search_report.recommendations[0].title if search_report.recommendations else "Search Intelligence"
            actions.append(
                AgentAction(
                    id="act_sys_search_strategy",
                    action_type=AgentActionType.REVIEW_SEARCH_STRATEGY,
                    priority=AgentActionPriority.MEDIUM,
                    title="Review Search Intelligence Strategy",
                    description="Inspect source allocations, top hiring corridors, and coverage gaps.",
                    reason=f"Intelligence recommendations available ({top_rec}). Optimizing search queries improves daily yield.",
                    metadata={"confidence": str(getattr(search_report, "data_confidence", "INSUFFICIENT_DATA"))},
                )
            )

        # Analytics & Target review action
        if target_remaining > 0:
            actions.append(
                AgentAction(
                    id="act_sys_analytics_target",
                    action_type=AgentActionType.REVIEW_ANALYTICS,
                    priority=AgentActionPriority.LOW,
                    title="Review Daily Target & Analytics Funnel",
                    description=f"{target_remaining} application(s) remaining today. Active streak: {streak_days} days.",
                    reason=f"Daily goal is {5} manual applications. Checking pipeline conversion maintains search consistency.",
                )
            )

        return actions

    # -------------------------------------------------------------------------
    # ORCHESTRATION RANKING ALGORITHM
    # -------------------------------------------------------------------------

    def _calculate_action_score(self, action: AgentAction, today_str: str) -> float:
        """Deterministic action-ranking algorithm.
        
        NOTE: This is an ORCHESTRATION SCORE only. It coordinates daily attention
        and does NOT replace match score or application readiness calculations.
        """
        score = 0.0

        # 1. Base Urgency & Action Category Weighting
        if action.action_type == AgentActionType.FOLLOW_UP:
            if action.due_date and action.due_date < today_str:
                score += 160.0  # Overdue follow-up is top priority
            elif action.due_date and action.due_date == today_str:
                score += 130.0  # Due today
            elif "Needs Attention" in action.title:
                score += 115.0  # Neglected application
            else:
                score += 65.0   # Upcoming follow-up
        elif action.action_type == AgentActionType.PREPARE_INTERVIEW:
            if action.due_date:
                try:
                    diff = (date.fromisoformat(action.due_date) - date.fromisoformat(today_str)).days
                    if diff <= 1:
                        score += 150.0  # Imminent interview
                    elif diff <= 3:
                        score += 125.0
                    else:
                        score += 90.0
                except Exception:
                    score += 95.0
            else:
                score += 95.0
        elif action.action_type == AgentActionType.APPLY_MANUALLY:
            score += 85.0
        elif action.action_type == AgentActionType.PREPARE_RESUME:
            score += 75.0
        elif action.action_type == AgentActionType.REVIEW_SEARCH_STRATEGY:
            score += 45.0
        elif action.action_type == AgentActionType.REVIEW_JOB:
            score += 40.0
        elif action.action_type == AgentActionType.UPDATE_APPLICATION:
            score += 105.0
        elif action.action_type == AgentActionType.REVIEW_ANALYTICS:
            score += 20.0
        else:
            score += 30.0

        # 2. Quality and Alignment Dimensions
        if action.match_score is not None:
            score += (action.match_score * 0.35)
        if action.readiness_score is not None:
            score += (action.readiness_score * 0.25)
        if action.resume_score is not None:
            score += (action.resume_score * 0.15)

        return round(score, 2)

    # -------------------------------------------------------------------------
    # DAILY PLAN & REPORT SYNTHESIS
    # -------------------------------------------------------------------------

    def get_daily_plan(self, as_of_date: Optional[str] = None) -> DailyJobPlan:
        """Generate a prioritized deterministic daily action plan from live database state."""
        today_str = as_of_date or date.today().isoformat()

        # Fetch current database jobs
        jobs: List[Job] = self.db.get_all_jobs() if self.db else []

        # Target & Streak metrics
        target_daily = 5
        applied_today = 0
        streak_days = 0

        if self.db:
            try:
                target_status = self.db.get_daily_target_status(target=target_daily)
                applied_today = target_status.get("applied_today", 0)
                streak_info = self.db.get_application_streak()
                streak_days = streak_info.get("current_streak", 0)
            except Exception as e:
                logger.debug("Error querying target/streak: %s", e)
        else:
            # Fallback counting from jobs directly
            applied_today = sum(
                1 for j in jobs
                if (j.status in (JobStatus.APPLIED, JobStatus.INTERVIEW, JobStatus.OFFER)
                    and j.applied_at and str(j.applied_at).startswith(today_str))
            )

        target_remaining = max(0, target_daily - applied_today)
        target_progress_pct = round((applied_today / target_daily) * 100.0, 1) if target_daily > 0 else 0.0

        # Get Search Intelligence
        search_report = None
        if self.search_intelligence_service:
            try:
                search_report = self.search_intelligence_service.get_search_intelligence_report()
            except Exception as e:
                logger.debug("Error getting search report: %s", e)

        # Generate action candidate pool
        all_candidate_actions: List[AgentAction] = []
        all_candidate_actions.extend(self._generate_follow_up_actions(jobs, today_str))
        all_candidate_actions.extend(self._generate_interview_actions(jobs, today_str))
        all_candidate_actions.extend(self._generate_application_and_prep_actions(jobs))
        all_candidate_actions.extend(
            self._generate_system_and_search_actions(target_remaining, streak_days, search_report)
        )

        # Apply in-memory state overrides if user completed/skipped actions
        for act in all_candidate_actions:
            if act.id in self._action_state_overrides:
                act.status = self._action_state_overrides[act.id]

        # Prioritize and sort actions deterministically
        def sort_key(act: AgentAction) -> Tuple[int, float]:
            prio_order = {
                AgentActionPriority.URGENT: 0,
                AgentActionPriority.HIGH: 1,
                AgentActionPriority.MEDIUM: 2,
                AgentActionPriority.LOW: 3,
            }
            score = self._calculate_action_score(act, today_str)
            return (prio_order.get(act.priority, 4), -score)

        sorted_actions = sorted(all_candidate_actions, key=sort_key)

        urgent_list = [a for a in sorted_actions if a.priority == AgentActionPriority.URGENT]
        high_list = [a for a in sorted_actions if a.priority == AgentActionPriority.HIGH]
        medium_list = [a for a in sorted_actions if a.priority == AgentActionPriority.MEDIUM]
        low_list = [a for a in sorted_actions if a.priority == AgentActionPriority.LOW]

        return DailyJobPlan(
            date=today_str,
            actions=sorted_actions,
            urgent_actions=urgent_list,
            high_actions=high_list,
            medium_actions=medium_list,
            low_actions=low_list,
            target_applied_today=applied_today,
            target_daily=target_daily,
            target_remaining=target_remaining,
            target_progress_pct=target_progress_pct,
            streak_days=streak_days,
        )

    def get_agent_report(self, as_of_date: Optional[str] = None) -> JobAgentReport:
        """Synthesize unified daily command center report."""
        today_str = as_of_date or date.today().isoformat()
        plan = self.get_daily_plan(as_of_date=today_str)
        jobs: List[Job] = self.db.get_all_jobs() if self.db else []

        # Metrics for JobAgentSummary
        jobs_found_today = sum(
            1 for j in jobs
            if j.date_found and str(j.date_found).startswith(today_str)
        )
        relevant_jobs = sum(1 for j in jobs if (j.match_score or 0) >= 60)
        recommended_jobs = sum(
            1 for j in jobs
            if (j.application_priority and (j.application_priority.value if hasattr(j.application_priority, "value") else str(j.application_priority)) in ("URGENT", "HIGH", "NORMAL"))
        )
        interviews_upcoming = sum(
            1 for j in jobs
            if (j.status == JobStatus.INTERVIEW or (j.interview_date is not None and str(j.interview_date).strip() != ""))
        )
        follow_ups_due = sum(
            1 for a in plan.actions
            if a.action_type == AgentActionType.FOLLOW_UP and a.priority in (AgentActionPriority.URGENT, AgentActionPriority.HIGH)
        )
        overdue_actions = sum(
            1 for a in plan.urgent_actions
            if "Overdue" in a.title or "overdue" in a.reason.lower()
        )

        summary = JobAgentSummary(
            jobs_found_today=jobs_found_today,
            relevant_jobs=relevant_jobs,
            recommended_jobs=recommended_jobs,
            applications_today=plan.target_applied_today,
            target_remaining=plan.target_remaining,
            interviews_upcoming=interviews_upcoming,
            follow_ups_due=follow_ups_due,
            overdue_actions=overdue_actions,
        )

        # Job Action Cards for Today's Applications (ready to apply)
        today_apps: List[JobAgentRecommendation] = []
        resume_preps: List[JobAgentRecommendation] = []

        unapplied_jobs = [
            j for j in jobs
            if j.status not in (JobStatus.APPLIED, JobStatus.INTERVIEW, JobStatus.OFFER, JobStatus.REJECTED, JobStatus.NOT_INTERESTED)
        ]

        for j in unapplied_jobs:
            if (j.match_score or 0) < 60:
                continue

            r_analysis = self.resume_service.analyze(j)
            skills = r_analysis.skills_to_emphasize[:4]
            proj_name = r_analysis.recommended_project if isinstance(r_analysis.recommended_project, str) else (r_analysis.recommended_project.name if r_analysis.recommended_project else None)
            prep_st = str(getattr(j.preparation_status, "value", j.preparation_status) or "").upper()

            rec = JobAgentRecommendation(
                job_id=j.id,
                title=j.title,
                company=j.company,
                location=j.location,
                match_score=j.match_score or 0,
                readiness_score=j.application_readiness_score or 0,
                resume_alignment_score=j.resume_alignment_score or r_analysis.resume_alignment_score,
                priority=AgentActionPriority.HIGH if (j.application_priority and (j.application_priority.value if hasattr(j.application_priority, "value") else str(j.application_priority)) in ("URGENT", "HIGH")) else AgentActionPriority.MEDIUM,
                next_action=AgentActionType.APPLY_MANUALLY if prep_st == "READY" else AgentActionType.PREPARE_RESUME,
                preparation_summary="Resume review completed" if prep_st == "READY" else "Resume alignment required",
                skills_to_emphasize=skills,
                recommended_project=proj_name,
                application_status="NOT YET APPLIED",
                url=j.url,
            )

            if prep_st == "READY":
                today_apps.append(rec)
            else:
                resume_preps.append(rec)

        # Sort today_apps and resume_preps
        today_apps.sort(key=lambda x: (-(x.readiness_score), -(x.match_score)))
        resume_preps.sort(key=lambda x: (-(x.match_score), -(x.readiness_score)))

        # Interview prep jobs
        interview_prep_jobs: List[Dict[str, Any]] = []
        for j in jobs:
            st = j.status.value if hasattr(j.status, "value") else str(j.status)
            if st == "INTERVIEW" or (j.interview_date is not None and str(j.interview_date).strip() != ""):
                pkg = self.interview_service.generate_preparation_package(j)
                interview_prep_jobs.append({
                    "job_id": j.id,
                    "title": j.title,
                    "company": j.company,
                    "interview_date": j.interview_date,
                    "stage": j.interview_stage or "Technical Screen",
                    "prep_status": str(getattr(j, "interview_preparation_status", None) or getattr(j, "interview_prep_status", None) or "NOT_STARTED"),
                    "topics": [t.skill for t in (pkg.technical_topics or [])[:3]],
                    "checklist": (pkg.checklist or [])[:5],
                })

        # Follow-ups summary list
        follow_ups_list: List[Dict[str, Any]] = []
        for a in plan.actions:
            if a.action_type == AgentActionType.FOLLOW_UP:
                follow_ups_list.append({
                    "action_id": a.id,
                    "priority": a.priority.value,
                    "company": a.company,
                    "job_title": a.job_title,
                    "due_date": a.due_date,
                    "title": a.title,
                    "reason": a.reason,
                    "job_id": a.job_id,
                })

        # Search focus from Phase 13 Search Intelligence
        search_focus_list: List[Dict[str, Any]] = []
        try:
            report_si = self.search_intelligence_service.get_search_intelligence_report()
            for r in report_si.recommendations[:4]:
                search_focus_list.append({
                    "category": r.category,
                    "title": r.title,
                    "recommendation": r.recommendation,
                    "priority": r.priority.value if hasattr(r.priority, "value") else str(r.priority),
                    "reason": r.reason,
                })
        except Exception as e:
            logger.debug("Error populating search focus: %s", e)

        return JobAgentReport(
            generated_at=datetime.now().isoformat(),
            summary=summary,
            plan=plan,
            today_applications=today_apps,
            resume_prep_jobs=resume_preps,
            interview_prep_jobs=interview_prep_jobs,
            follow_ups=follow_ups_list,
            search_focus=search_focus_list,
            safety_notices=SAFETY_NOTICES,
        )
