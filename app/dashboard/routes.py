"""Route definitions for Job Review Dashboard."""

from datetime import datetime
import math
from typing import Optional
from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config.settings import get_settings
from app.database.database import DatabaseManager
from app.models.interview import InterviewPrepStatus, InterviewStage, InterviewStatus
from app.models.job import JobStatus
from app.services.interview_preparation import InterviewPreparationService
from app.services.job_tracker import JobTracker

router = APIRouter()


def get_db() -> DatabaseManager:
    """Dependency / helper to get database manager instance."""
    settings = get_settings()
    return DatabaseManager(db_path=settings.DATABASE_PATH)


def get_tracker() -> JobTracker:
    """Dependency / helper to get JobTracker instance."""
    return JobTracker(get_db())


def get_interview_service() -> InterviewPreparationService:
    """Dependency / helper to get InterviewPreparationService instance."""
    return InterviewPreparationService()


@router.get("/", response_class=RedirectResponse)
async def root():
    """Redirect root path to main dashboard."""
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    """Render main dashboard with summary statistics, high priority jobs, and recent pipeline runs."""
    from app.dashboard.app import templates
    settings = get_settings()
    db = get_db()
    tracker = get_tracker()

    counts = db.get_dashboard_counts()
    top_jobs, _ = db.get_jobs_filtered(min_score=80, per_page=10, sort_by="match_score", order="desc")
    recent_runs = db.get_recent_pipeline_runs(limit=5)
    source_health = db.get_source_health()
    upcoming_follow_ups = tracker.get_upcoming_follow_ups(limit=5)
    apply_today_preview, _ = db.get_jobs_filtered(
        exclude_inactive=True,
        sort_by="priority",
        order="asc",
        per_page=5,
    )

    daily_target = getattr(settings, "DAILY_APPLICATION_TARGET", 5)
    applied_today = counts.get("applied_today", 0)
    remaining_today = max(0, daily_target - applied_today)
    daily_actions = tracker.get_daily_actions(limit=5)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "counts": counts,
            "top_jobs": top_jobs,
            "recent_runs": recent_runs,
            "source_health": source_health,
            "upcoming_follow_ups": upcoming_follow_ups,
            "apply_today_preview": apply_today_preview,
            "daily_actions": daily_actions,
            "daily_target": daily_target,
            "remaining_today": remaining_today,
            "active_tab": "dashboard",
        },
    )


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_list_view(
    request: Request,
    score: Optional[str] = Query(None, description="Minimum match score filter"),
    status_filter: Optional[str] = Query(None, alias="status", description="Status filter"),
    source: Optional[str] = Query(None, description="Source filter"),
    company: Optional[str] = Query(None, description="Company filter"),
    location: Optional[str] = Query(None, description="Location filter"),
    search: Optional[str] = Query(None, description="Full-text search"),
    first_seen_days: Optional[str] = Query(None, description="Filter jobs first seen in last N days"),
    sort_by: str = Query("match_score", description="Sort column"),
    order: str = Query("desc", description="Sort order asc/desc"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    view_title: str = Query("All Jobs", description="Custom title for filtered view"),
):
    """Render filterable, sortable, paginated jobs table."""
    from app.dashboard.app import templates
    db = get_db()

    # Parse numeric filters safely
    min_score_val = None
    if score and score.strip() and score.strip().lower() != "all":
        try:
            min_score_val = int(score.replace("+", "").strip())
        except ValueError:
            min_score_val = None

    days_val = None
    if first_seen_days is not None and first_seen_days.strip() != "":
        try:
            days_val = int(first_seen_days)
        except ValueError:
            days_val = None

    jobs, total_count = db.get_jobs_filtered(
        min_score=min_score_val,
        status=status_filter,
        source=source,
        location=location,
        company=company,
        search=search,
        first_seen_days=days_val,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
    )

    total_pages = max(1, math.ceil(total_count / per_page))

    distinct_sources = db.get_distinct_sources()
    distinct_companies = db.get_distinct_companies()
    all_statuses = [s.value for s in JobStatus]

    # Determine active tab for navigation
    active_tab = "jobs"
    if status_filter == "SHORTLISTED":
        active_tab = "shortlisted"
    elif status_filter == "APPLIED":
        active_tab = "applied"
    elif status_filter == "INTERVIEW":
        active_tab = "interviews"
    elif status_filter == "OFFER":
        active_tab = "offers"
    elif days_val is not None:
        active_tab = "new-matches"

    return templates.TemplateResponse(
        request=request,
        name="jobs.html",
        context={
            "jobs": jobs,
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "score": score or "all",
            "status": status_filter or "all",
            "source": source or "all",
            "company": company or "",
            "location": location or "",
            "search": search or "",
            "first_seen_days": first_seen_days or "",
            "sort_by": sort_by,
            "order": order,
            "distinct_sources": distinct_sources,
            "distinct_companies": distinct_companies,
            "all_statuses": all_statuses,
            "view_title": view_title,
            "active_tab": active_tab,
        },
    )


@router.get("/new-matches", response_class=HTMLResponse)
async def new_matches_view(
    request: Request,
    days: str = Query("0", description="0 for today, 3 for 3 days, 7 for 7 days"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """Quick view of newly discovered jobs."""
    days_label = "Today" if days == "0" else f"Last {days} Days"
    return await jobs_list_view(
        request=request,
        score=None,
        status_filter=None,
        source=None,
        company=None,
        location=None,
        search=None,
        first_seen_days=days,
        sort_by="first_seen_at",
        order="desc",
        page=page,
        per_page=per_page,
        view_title=f"New Matches ({days_label})",
    )


@router.get("/shortlisted", response_class=HTMLResponse)
async def shortlisted_view(request: Request, page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=100)):
    """Filtered view of shortlisted opportunities."""
    return await jobs_list_view(
        request=request,
        score=None,
        status_filter="SHORTLISTED",
        source=None,
        company=None,
        location=None,
        search=None,
        first_seen_days=None,
        sort_by="match_score",
        order="desc",
        page=page,
        per_page=per_page,
        view_title="Shortlisted Jobs",
    )


@router.get("/applied", response_class=HTMLResponse)
async def applied_view(request: Request, page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=100)):
    """Filtered view of applied jobs."""
    return await jobs_list_view(
        request=request,
        score=None,
        status_filter="APPLIED",
        source=None,
        company=None,
        location=None,
        search=None,
        first_seen_days=None,
        sort_by="last_seen_at",
        order="desc",
        page=page,
        per_page=per_page,
        view_title="Applied Jobs",
    )


@router.get("/interviews", response_class=HTMLResponse)
async def interviews_view(request: Request, page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=100)):
    """Filtered view of jobs in interview stage."""
    return await jobs_list_view(
        request=request,
        score=None,
        status_filter="INTERVIEW",
        source=None,
        company=None,
        location=None,
        search=None,
        first_seen_days=None,
        sort_by="last_seen_at",
        order="desc",
        page=page,
        per_page=per_page,
        view_title="Interviews",
    )


@router.get("/offers", response_class=HTMLResponse)
async def offers_view(request: Request, page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=100)):
    """Filtered view of received offers."""
    return await jobs_list_view(
        request=request,
        score=None,
        status_filter="OFFER",
        source=None,
        company=None,
        location=None,
        search=None,
        first_seen_days=None,
        sort_by="last_seen_at",
        order="desc",
        page=page,
        per_page=per_page,
        view_title="Job Offers",
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail_view(request: Request, job_id: int):
    """Render comprehensive job detail view."""
    from app.dashboard.app import templates
    tracker = get_tracker()
    job = tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found.")

    all_statuses = [s.value for s in JobStatus]
    referrer = request.headers.get("referer", "/jobs")

    return templates.TemplateResponse(
        request=request,
        name="job_detail.html",
        context={
            "job": job,
            "all_statuses": all_statuses,
            "referrer": referrer,
            "active_tab": "jobs",
        },
    )


@router.post("/jobs/{job_id}/status")
async def update_job_status_endpoint(
    job_id: int,
    new_status: str = Form(..., alias="status"),
    notes: Optional[str] = Form(None),
    redirect_to: Optional[str] = Form(None),
):
    """Update job application status via JobTracker service."""
    tracker = get_tracker()
    try:
        success = tracker.update_status(job_id=job_id, status=new_status, notes=notes)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    if not success:
        raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")

    target_url = redirect_to or f"/jobs/{job_id}"
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/jobs/{job_id}/notes")
async def update_job_notes_endpoint(
    job_id: int,
    notes: str = Form(...),
    redirect_to: Optional[str] = Form(None),
):
    """Update persistent user notes via JobTracker service."""
    tracker = get_tracker()
    success = tracker.update_notes(job_id=job_id, notes=notes)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")

    target_url = redirect_to or f"/jobs/{job_id}"
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/pipeline-runs", response_class=HTMLResponse)
async def pipeline_runs_view(request: Request, limit: int = Query(25, ge=1, le=100)):
    """Render historical execution runs from pipeline_runs table."""
    from app.dashboard.app import templates
    db = get_db()
    runs = db.get_recent_pipeline_runs(limit=limit)

    return templates.TemplateResponse(
        request=request,
        name="pipeline_runs.html",
        context={
            "runs": runs,
            "active_tab": "pipeline-runs",
        },
    )


@router.get("/source-health", response_class=HTMLResponse)
async def source_health_view(request: Request):
    """Render real-time status and health metrics across job sources."""
    from app.dashboard.app import templates
    db = get_db()
    health_data = db.get_source_health()

    return templates.TemplateResponse(
        request=request,
        name="source_health.html",
        context={
            "source_health": health_data,
            "active_tab": "source-health",
        },
    )


@router.get("/apply-today", response_class=HTMLResponse)
async def apply_today_view(
    request: Request,
    priority: Optional[str] = Query(None, description="Application priority filter"),
    min_readiness: Optional[str] = Query(None, description="Minimum readiness score"),
    status_filter: Optional[str] = Query(None, alias="status", description="Status filter"),
    sort_by: str = Query("priority", description="Sort column"),
    order: str = Query("asc", description="Sort order"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """Render high-priority actionable jobs in the Apply Today queue (Phase 9)."""
    from app.dashboard.app import templates
    db = get_db()

    min_r_val = None
    if min_readiness and min_readiness.strip() and min_readiness.strip().lower() not in ("any", "all"):
        try:
            min_r_val = int(min_readiness.replace("+", "").strip())
        except ValueError:
            min_r_val = None

    prio_val = None
    if priority and priority.strip() and priority.strip().lower() not in ("any", "all"):
        prio_val = priority.strip().upper()

    # By default, exclude inactive statuses (APPLIED, REJECTED, etc.) unless an explicit status was chosen
    exclude_inactive = not bool(status_filter and status_filter.strip().upper() != "ALL")
    actionable_only = bool(prio_val is None and (not status_filter or status_filter.strip().upper() == "ALL"))

    jobs, total_count = db.get_jobs_filtered(
        priority=prio_val,
        min_readiness=min_r_val,
        status=status_filter,
        actionable_only=actionable_only,
        exclude_inactive=exclude_inactive,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
    )

    total_pages = max(1, math.ceil(total_count / per_page))
    all_statuses = [s.value for s in JobStatus]

    return templates.TemplateResponse(
        request=request,
        name="apply_today.html",
        context={
            "jobs": jobs,
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "priority": priority or "all",
            "min_readiness": min_readiness or "any",
            "status": status_filter or "all",
            "sort_by": sort_by,
            "order": order,
            "all_statuses": all_statuses,
            "active_tab": "apply-today",
        },
    )


@router.post("/jobs/{job_id}/follow-up")
async def update_job_follow_up_endpoint(
    job_id: int,
    follow_up_date: Optional[str] = Form(None),
    follow_up_notes: Optional[str] = Form(None),
    redirect_to: Optional[str] = Form(None),
):
    """Update follow-up due date and notes via JobTracker service."""
    tracker = get_tracker()
    success = tracker.update_follow_up(
        job_id=job_id,
        follow_up_date=follow_up_date.strip() if follow_up_date else None,
        follow_up_notes=follow_up_notes.strip() if follow_up_notes else None,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")

    target_url = redirect_to or f"/jobs/{job_id}"
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/resume-preparation", response_class=HTMLResponse)
async def resume_preparation_view(
    request: Request,
    priority: Optional[str] = Query(None, description="Priority filter"),
    min_alignment: Optional[str] = Query(None, description="Minimum resume alignment score"),
    prep_status: Optional[str] = Query(None, description="Preparation status filter"),
    sort_by: str = Query("resume_alignment", description="Sort column"),
    order: str = Query("desc", description="Sort order"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """Render jobs worth preparing for (Phase 10 Resume Intelligence)."""
    from app.dashboard.app import templates
    db = get_db()

    min_align_val = None
    if min_alignment and min_alignment.strip() and min_alignment.strip().lower() not in ("any", "all"):
        try:
            min_align_val = int(min_alignment.replace("+", "").strip())
        except ValueError:
            min_align_val = None

    prio_val = None
    prep_prio_only = False
    if priority and priority.strip() and priority.strip().lower() not in ("any", "all"):
        prio_val = priority.strip().upper()
    else:
        # Default criteria: application_priority IN ('URGENT', 'HIGH')
        prep_prio_only = True

    prep_status_val = None
    if prep_status and prep_status.strip() and prep_status.strip().lower() not in ("any", "all"):
        prep_status_val = prep_status.strip().upper()

    jobs, total_count = db.get_jobs_filtered(
        priority=prio_val,
        min_resume_alignment=min_align_val,
        preparation_status=prep_status_val,
        prep_priority_only=prep_prio_only,
        exclude_inactive=True,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
    )

    total_pages = max(1, math.ceil(total_count / per_page))
    counts = db.get_dashboard_counts()

    return templates.TemplateResponse(
        request=request,
        name="resume_preparation.html",
        context={
            "jobs": jobs,
            "total_count": total_count,
            "ready_to_apply_count": counts.get("prep_ready_to_apply", 0),
            "urgent_high_count": counts.get("prep_urgent_high", 0),
            "avg_alignment": counts.get("avg_resume_alignment", 0.0),
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "priority": priority or "all",
            "min_alignment": min_alignment or "any",
            "prep_status": prep_status or "all",
            "sort_by": sort_by,
            "order": order,
            "active_tab": "resume-preparation",
        },
    )


@router.post("/jobs/{job_id}/preparation")
async def update_job_preparation_endpoint(
    job_id: int,
    preparation_status: str = Form(..., alias="preparation_status"),
    preparation_notes: Optional[str] = Form(None),
    redirect_to: Optional[str] = Form(None),
):
    """Update Phase 10 preparation status and notes via JobTracker service."""
    tracker = get_tracker()
    success = tracker.update_preparation_status(
        job_id=job_id,
        status=preparation_status.strip().upper(),
        notes=preparation_notes.strip() if preparation_notes else None,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")

    target_url = redirect_to or f"/jobs/{job_id}"
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/applications", response_class=HTMLResponse)
async def applications_view(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status", description="Status filter"),
    priority: Optional[str] = Query(None, description="Application priority filter"),
    score: Optional[str] = Query(None, description="Minimum match score filter"),
    min_readiness: Optional[str] = Query(None, description="Minimum readiness score"),
    company: Optional[str] = Query(None, description="Company filter"),
    role: Optional[str] = Query(None, description="Role filter"),
    location: Optional[str] = Query(None, description="Location filter"),
    source: Optional[str] = Query(None, description="Source filter"),
    search: Optional[str] = Query(None, description="Search term"),
    follow_up_filter: Optional[str] = Query(None, description="Follow-up status filter"),
    interview_filter: Optional[str] = Query(None, description="Interview status filter"),
    sort_by: str = Query("applied_at", description="Sort column"),
    order: str = Query("desc", description="Sort order"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """Render Application Command Center with pipeline funnel metrics and filterable applications."""
    from app.dashboard.app import templates
    db = get_db()
    tracker = get_tracker()

    min_score_val = None
    if score and score.strip() and score.strip().lower() not in ("all", "any"):
        try:
            min_score_val = int(score.replace("+", "").strip())
        except ValueError:
            min_score_val = None

    min_r_val = None
    if min_readiness and min_readiness.strip() and min_readiness.strip().lower() not in ("all", "any"):
        try:
            min_r_val = int(min_readiness.replace("+", "").strip())
        except ValueError:
            min_r_val = None

    prio_val = None
    if priority and priority.strip() and priority.strip().lower() not in ("all", "any"):
        prio_val = priority.strip().upper()

    jobs, total_count = db.get_applications_filtered(
        status=status_filter,
        priority=prio_val,
        min_score=min_score_val,
        min_readiness=min_r_val,
        company=company,
        role=role,
        location=location,
        source=source,
        search=search,
        follow_up_filter=follow_up_filter,
        interview_filter=interview_filter,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
    )

    total_pages = max(1, math.ceil(total_count / per_page))
    pipeline_counts = db.get_applications_pipeline_counts()
    follow_ups_summary = tracker.get_follow_ups_summary()
    counts = db.get_dashboard_counts()

    return templates.TemplateResponse(
        request=request,
        name="applications.html",
        context={
            "jobs": jobs,
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "pipeline": pipeline_counts,
            "pipeline_counts": pipeline_counts,
            "follow_ups_summary": follow_ups_summary,
            "interviews_active_count": counts.get("interviews_active", 0),
            "status": status_filter or "all",
            "priority": priority or "all",
            "score": score or "all",
            "min_readiness": min_readiness or "any",
            "company": company or "",
            "role": role or "",
            "location": location or "",
            "source": source or "all",
            "search": search or "",
            "follow_up_filter": follow_up_filter or "all",
            "interview_filter": interview_filter or "all",
            "sort_by": sort_by,
            "order": order,
            "active_tab": "applications",
        },
    )


@router.get("/today", response_class=HTMLResponse)
async def today_view(request: Request):
    """Render 'What Should I Work On Today?' prioritized action plan."""
    from app.dashboard.app import templates
    db = get_db()
    tracker = get_tracker()

    daily_actions = tracker.get_daily_actions(limit=30)
    follow_ups_summary = tracker.get_follow_ups_summary()
    counts = db.get_dashboard_counts()
    today_iso = datetime.now().strftime("%A, %B %d, %Y")

    return templates.TemplateResponse(
        request=request,
        name="today.html",
        context={
            "actions": daily_actions,
            "follow_ups_summary": follow_ups_summary,
            "counts": counts,
            "today_date": today_iso,
            "active_tab": "today",
        },
    )


@router.get("/interview-prep", response_class=HTMLResponse)
async def interview_prep_view(
    request: Request,
    job_id: Optional[int] = Query(None, description="Job ID to prepare for"),
):
    """Render deterministic interview preparation workspace."""
    from app.dashboard.app import templates
    settings = get_settings()
    db = get_db()
    prep_service = get_interview_service()

    profile = settings.load_profile()

    eligible_jobs, _ = db.get_jobs_filtered(
        min_score=60,
        exclude_inactive=False,
        sort_by="match_score",
        order="desc",
        per_page=100,
    )

    selected_job = None
    if job_id:
        selected_job = db.get_job_by_id(job_id)

    if not selected_job:
        for j in eligible_jobs:
            if (j.status.value if hasattr(j.status, "value") else str(j.status)) == "INTERVIEW":
                selected_job = j
                break
        if not selected_job:
            for j in eligible_jobs:
                if (j.status.value if hasattr(j.status, "value") else str(j.status)) == "APPLIED":
                    selected_job = j
                    break
        if not selected_job and eligible_jobs:
            selected_job = eligible_jobs[0]

    package = None
    if selected_job:
        package = prep_service.generate_package(selected_job, profile)

    counts = db.get_dashboard_counts()

    return templates.TemplateResponse(
        request=request,
        name="interview_prep.html",
        context={
            "job": selected_job,
            "package": package,
            "eligible_jobs": eligible_jobs,
            "counts": counts,
            "active_tab": "interview-prep",
        },
    )


@router.post("/jobs/{job_id}/interview")
async def update_job_interview_endpoint(
    job_id: int,
    interview_date: Optional[str] = Form(None),
    interview_stage: Optional[str] = Form(None),
    interview_status: Optional[str] = Form(None),
    interview_notes: Optional[str] = Form(None),
    interview_preparation_status: Optional[str] = Form(None),
    redirect_to: Optional[str] = Form(None),
):
    """Update interview date, stage, status, notes, and preparation status via JobTracker."""
    tracker = get_tracker()
    success = tracker.update_interview(
        job_id=job_id,
        interview_date=interview_date.strip() if interview_date and interview_date.strip() else None,
        interview_stage=interview_stage.strip() if interview_stage and interview_stage.strip() else None,
        interview_status=interview_status.strip().upper() if interview_status and interview_status.strip() else None,
        interview_notes=interview_notes.strip() if interview_notes and interview_notes.strip() else None,
        interview_preparation_status=interview_preparation_status.strip().upper() if interview_preparation_status and interview_preparation_status.strip() else None,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")

    target_url = redirect_to or f"/jobs/{job_id}"
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/jobs/{job_id}/interview-prep-status")
async def update_job_interview_prep_status_endpoint(
    job_id: int,
    status: str = Form(..., alias="status"),
    notes: Optional[str] = Form(None),
    redirect_to: Optional[str] = Form(None),
):
    """Update interview preparation status and notes via JobTracker."""
    tracker = get_tracker()
    success = tracker.update_interview_prep_status(
        job_id=job_id,
        status=status.strip().upper(),
        notes=notes.strip() if notes and notes.strip() else None,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")

    target_url = redirect_to or f"/interview-prep?job_id={job_id}"
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/analytics", response_class=HTMLResponse)
async def get_analytics_page(
    request: Request,
    period: str = Query("all"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
):
    """Application Analytics & Strategy Optimization Dashboard (Phase 12)."""
    from app.dashboard.app import templates
    tracker = get_tracker()
    db = get_db()
    report = tracker.get_analytics_report(
        period=period,
        start_date=start_date,
        end_date=end_date,
        source=source,
        role=role,
        location=location,
    )
    counts = db.get_dashboard_counts()

    return templates.TemplateResponse(
        request=request,
        name="analytics.html",
        context={
            "report": report,
            "period": period,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "source": source or "",
            "role": role or "",
            "location": location or "",
            "counts": counts,
            "active_tab": "analytics",
        },
    )


@router.get("/search-intelligence", response_class=HTMLResponse)
async def get_search_intelligence_page(request: Request):
    """Job Search Intelligence & Source Optimization Dashboard (Phase 13)."""
    from app.dashboard.app import templates
    from app.services.search_intelligence import SearchIntelligenceService

    db = get_db()
    service = SearchIntelligenceService(db=db)
    report = service.get_search_intelligence_report()
    counts = db.get_dashboard_counts()

    return templates.TemplateResponse(
        request=request,
        name="search_intelligence.html",
        context={
            "report": report,
            "counts": counts,
            "active_tab": "search-intelligence",
        },
    )


@router.get("/job-agent", response_class=HTMLResponse)
async def job_agent_view(request: Request):
    """Personal Job Agent command center (Phase 14)."""
    from app.dashboard.app import templates
    from app.services.job_agent import JobAgentService

    db = get_db()
    service = JobAgentService(db=db)
    report = service.get_agent_report()
    counts = db.get_dashboard_counts()

    return templates.TemplateResponse(
        request=request,
        name="job_agent.html",
        context={
            "report": report,
            "plan": report.plan,
            "summary": report.summary,
            "counts": counts,
            "today_applications": report.today_applications,
            "resume_prep_jobs": report.resume_prep_jobs,
            "interview_prep_jobs": report.interview_prep_jobs,
            "follow_ups": report.follow_ups,
            "search_focus": report.search_focus,
            "safety_notices": report.safety_notices,
            "active_tab": "job-agent",
        },
    )


@router.post("/job-agent/action")
async def job_agent_action_update(
    action_id: str = Form(...),
    action_status: str = Form(...),
):
    """Update status of an action without altering job lifecycle state."""
    from app.models.job_agent import AgentActionStatus
    from app.services.job_agent import JobAgentService

    service = JobAgentService(db=get_db())
    try:
        status_enum = AgentActionStatus(action_status.upper())
        service.mark_action_status(action_id, status_enum)
    except Exception as e:
        pass

    return RedirectResponse(url="/job-agent", status_code=status.HTTP_303_SEE_OTHER)


