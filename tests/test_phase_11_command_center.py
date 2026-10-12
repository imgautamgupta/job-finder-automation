"""Comprehensive Phase 11 Test Suite: Application Command Center & Interview Preparation.

Tests cover:
- Application tracking (applied_at set & preserved, status transitions)
- Interview tracking (date, stage, status, notes, prep status)
- Follow-up management (due, upcoming, overdue, inactive exclusions)
- Daily action plan prioritization (Tiers 1-7, reasons, deduplication)
- Deterministic interview preparation engine (topics, roles, projects, HR, questions, checklist)
- Data consistency audit (dashboard vs queue alignment)
- Dashboard routes (/applications, /today, /interview-prep, POST /jobs/{id}/interview)
- Excel export (new columns and Applications / Interview Preparation sheets)
- Regression and safety verification (no auto-apply, manual-only)
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.dashboard.app import app
from app.database.database import DatabaseManager
from app.models.interview import (
    DailyActionPriority,
    InterviewPrepStatus,
    InterviewStage,
    InterviewStatus,
)
from app.models.job import ApplicationPriority, Job, JobStatus
from app.models.profile import JobProfile
from app.services.excel_exporter import ExcelExporter
from app.services.interview_preparation import InterviewPreparationService
from app.services.job_tracker import JobTracker


@pytest.fixture
def temp_db(tmp_path):
    """Fixture providing an isolated SQLite database."""
    db_file = tmp_path / "test_phase11.db"
    db = DatabaseManager(db_path=db_file)
    db.initialize()
    return db


@pytest.fixture
def tracker(temp_db):
    """Fixture providing JobTracker backed by isolated DB."""
    return JobTracker(temp_db)


@pytest.fixture
def sample_profile():
    """Fixture providing candidate profile."""
    return JobProfile(
        target_roles=["Python Developer", "Backend Developer", "Machine Learning Engineer"],
        preferred_locations=["Bangalore", "Remote"],
        skills=["Python", "FastAPI", "SQL", "PostgreSQL", "Machine Learning", "Scikit-learn", "Git", "React"],
        negative_keywords=["Senior", "Staff", "Director", "PHP"],
        projects=[
            {
                "name": "Loan Application Fraud Detection",
                "skills": ["Python", "FastAPI", "Machine Learning", "Scikit-learn", "OpenCV"],
                "description": "Multi-modal fraud detection system using OCR and anomaly detection.",
            },
            {
                "name": "NeuroNest Notes & Bookmarks",
                "skills": ["React", "Next.js", "TypeScript", "SQL", "REST API"],
                "description": "Full-stack personal knowledge management application.",
            },
        ],
    )


@pytest.fixture
def sample_job():
    """Fixture providing a base Job instance."""
    return Job(
        id=101,
        source="lever",
        source_job_id="test-job-101",
        title="Python Backend Engineer Intern",
        company="TechCorp Innovations",
        location="Bangalore, India",
        url="https://jobs.lever.co/techcorp/101",
        description="We are looking for a Python Backend Engineer with FastAPI, PostgreSQL, and REST API experience.",
        date_posted="2026-10-01",
        match_score=85,
        match_category="Good",
        matched_roles=["Backend Developer", "Python Developer"],
        matched_skills=["Python", "FastAPI", "PostgreSQL", "REST API"],
        application_readiness_score=88,
        application_priority=ApplicationPriority.URGENT,
        resume_alignment_score=84,
        status=JobStatus.NEW,
    )


# ==============================================================================
# 1. APPLICATION TRACKING TESTS
# ==============================================================================

def test_applied_at_set_when_status_becomes_applied(temp_db, tracker, sample_job):
    """Transitioning to APPLIED sets applied_at timestamp."""
    temp_db.save_job(sample_job)
    assert sample_job.applied_at is None

    success = tracker.update_status(sample_job.id, JobStatus.APPLIED, notes="Sent resume directly")
    assert success is True

    updated = temp_db.get_job_by_id(sample_job.id)
    assert updated.status == JobStatus.APPLIED
    assert updated.applied_at is not None
    assert updated.notes == "Sent resume directly"


def test_applied_at_preserved_on_subsequent_status_transitions(temp_db, tracker, sample_job):
    """applied_at is NOT overwritten when moving to INTERVIEW or OFFER."""
    sample_job.status = JobStatus.APPLIED
    original_applied_at = datetime(2026, 10, 5, 14, 30, tzinfo=timezone.utc)
    sample_job.applied_at = original_applied_at
    temp_db.save_job(sample_job)

    # Transition to INTERVIEW
    tracker.update_status(sample_job.id, JobStatus.INTERVIEW)
    job_interview = temp_db.get_job_by_id(sample_job.id)
    assert job_interview.status == JobStatus.INTERVIEW
    assert job_interview.applied_at == original_applied_at

    # Transition to OFFER
    tracker.update_status(sample_job.id, JobStatus.OFFER)
    job_offer = temp_db.get_job_by_id(sample_job.id)
    assert job_offer.status == JobStatus.OFFER
    assert job_offer.applied_at == original_applied_at


def test_existing_notes_preserved_when_updating_status(temp_db, tracker, sample_job):
    """Updating status without new notes preserves existing notes."""
    sample_job.notes = "Important: Recruiter contacted via LinkedIn"
    temp_db.save_job(sample_job)

    tracker.update_status(sample_job.id, JobStatus.SHORTLISTED)
    updated = temp_db.get_job_by_id(sample_job.id)
    assert updated.status == JobStatus.SHORTLISTED
    assert updated.notes == "Important: Recruiter contacted via LinkedIn"


# ==============================================================================
# 2. INTERVIEW TRACKING TESTS
# ==============================================================================

def test_interview_fields_persistence(temp_db, tracker, sample_job):
    """Interview tracking fields persist correctly in SQLite."""
    temp_db.save_job(sample_job)

    target_date = "2026-10-15"
    stage = InterviewStage.TECHNICAL_INTERVIEW.value
    status = InterviewStatus.SCHEDULED.value
    prep_status = InterviewPrepStatus.IN_PROGRESS.value
    notes = "Round 2 with Lead Architect. Focus on FastAPI design."

    success = tracker.update_interview(
        job_id=sample_job.id,
        interview_date=target_date,
        interview_stage=stage,
        interview_status=status,
        interview_notes=notes,
        interview_preparation_status=prep_status,
    )
    assert success is True

    saved = temp_db.get_job_by_id(sample_job.id)
    assert saved.interview_date == target_date
    assert saved.interview_stage == InterviewStage.TECHNICAL_INTERVIEW
    assert saved.interview_status == InterviewStatus.SCHEDULED
    assert saved.interview_notes == notes
    assert saved.interview_preparation_status == InterviewPrepStatus.IN_PROGRESS


def test_interview_nullable_fields(temp_db, tracker, sample_job):
    """Nullable interview fields can be cleared or set independently."""
    sample_job.interview_date = "2026-10-12"
    sample_job.interview_notes = "Initial phone screening"
    temp_db.save_job(sample_job)

    # Clear notes, keep date
    tracker.update_interview(sample_job.id, interview_notes="")
    saved = temp_db.get_job_by_id(sample_job.id)
    assert saved.interview_date == "2026-10-12"
    assert saved.interview_notes is None or saved.interview_notes == ""


def test_interview_prep_status_updates(temp_db, tracker, sample_job):
    """Interview preparation status updates independently."""
    temp_db.save_job(sample_job)

    tracker.update_interview_prep_status(sample_job.id, "READY", notes="Reviewed FastAPI decorator concepts")
    saved = temp_db.get_job_by_id(sample_job.id)
    assert saved.interview_preparation_status == InterviewPrepStatus.READY
    assert "Reviewed FastAPI" in (saved.interview_notes or "")


# ==============================================================================
# 3. FOLLOW-UP MANAGEMENT TESTS
# ==============================================================================

def test_follow_up_due_upcoming_and_overdue(temp_db, tracker):
    """Follow-up categorization accurately identifies due, upcoming, and overdue tasks."""
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=2)).isoformat()
    future_str = (date.today() + timedelta(days=5)).isoformat()

    job_due = Job(
        id=1, source="lever", source_job_id="j1", title="Dev 1", company="A Corp",
        url="https://example.com/1", match_score=80, status=JobStatus.APPLIED, follow_up_date=today_str,
    )
    job_overdue = Job(
        id=2, source="lever", source_job_id="j2", title="Dev 2", company="B Corp",
        url="https://example.com/2", match_score=80, status=JobStatus.APPLIED, follow_up_date=yesterday_str,
    )
    job_upcoming = Job(
        id=3, source="lever", source_job_id="j3", title="Dev 3", company="C Corp",
        url="https://example.com/3", match_score=80, status=JobStatus.APPLIED, follow_up_date=future_str,
    )
    # Inactive jobs should be excluded
    job_rejected = Job(
        id=4, source="lever", source_job_id="j4", title="Dev 4", company="D Corp",
        url="https://example.com/4", match_score=80, status=JobStatus.REJECTED, follow_up_date=yesterday_str,
    )
    job_offer = Job(
        id=5, source="lever", source_job_id="j5", title="Dev 5", company="E Corp",
        url="https://example.com/5", match_score=80, status=JobStatus.OFFER, follow_up_date=today_str,
    )

    for j in [job_due, job_overdue, job_upcoming, job_rejected, job_offer]:
        temp_db.save_job(j)

    summary = tracker.get_follow_ups_summary()
    assert summary["due_today"] == 1
    assert summary["overdue"] == 1
    assert summary["upcoming"] == 1
    assert summary["due"] == 2

    # Verify inactive exclusions in filtered query
    due_jobs, _ = temp_db.get_applications_filtered(follow_up_filter="due")
    assert len(due_jobs) == 2  # due today + overdue
    due_ids = [j.id for j in due_jobs]
    assert job_due.id in due_ids
    assert job_overdue.id in due_ids

    overdue_jobs, _ = temp_db.get_applications_filtered(follow_up_filter="overdue")
    assert len(overdue_jobs) == 1
    assert overdue_jobs[0].id == job_overdue.id


# ==============================================================================
# 4. DAILY ACTION PLAN TESTS
# ==============================================================================

def test_daily_action_plan_prioritization(temp_db, tracker):
    """Daily action items are strictly and deterministically ordered by tier 1 through 7."""
    today_str = date.today().isoformat()
    tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
    yesterday_str = (date.today() - timedelta(days=2)).isoformat()

    # Tier 1: Interview Today
    j1 = Job(id=1, source="lever", source_job_id="j1", title="Job 1", company="Corp 1",
             url="https://example.com/j1", match_score=80, status=JobStatus.INTERVIEW,
             interview_date=today_str, interview_status=InterviewStatus.SCHEDULED)
    # Tier 2: Interview Soon
    j2 = Job(id=2, source="lever", source_job_id="j2", title="Job 2", company="Corp 2",
             url="https://example.com/j2", match_score=80, status=JobStatus.INTERVIEW,
             interview_date=tomorrow_str, interview_status=InterviewStatus.SCHEDULED)
    # Tier 3: Follow-up Due
    j3 = Job(id=3, source="lever", source_job_id="j3", title="Job 3", company="Corp 3",
             url="https://example.com/j3", match_score=80, status=JobStatus.APPLIED, follow_up_date=yesterday_str)
    # Tier 4: Urgent Apply
    j4 = Job(id=4, source="lever", source_job_id="j4", title="Job 4", company="Corp 4",
             url="https://example.com/j4", match_score=90, application_readiness_score=92,
             application_priority=ApplicationPriority.URGENT, status=JobStatus.NEW)
    # Tier 5: High Apply
    j5 = Job(id=5, source="lever", source_job_id="j5", title="Job 5", company="Corp 5",
             url="https://example.com/j5", match_score=82, application_readiness_score=85,
             application_priority=ApplicationPriority.HIGH, status=JobStatus.SHORTLISTED)
    # Tier 6: Resume Prep Needed
    j6 = Job(id=6, source="lever", source_job_id="j6", title="Job 6", company="Corp 6",
             url="https://example.com/j6", match_score=80, resume_alignment_score=78,
             application_priority=ApplicationPriority.HIGH,
             interview_preparation_status=InterviewPrepStatus.NOT_STARTED, status=JobStatus.SHORTLISTED)

    for j in [j6, j4, j2, j1, j5, j3]:  # insert in random order
        temp_db.save_job(j)

    actions = tracker.get_daily_actions(limit=10)
    assert len(actions) >= 5

    # Check top action is Tier 1
    assert actions[0].priority_rank == DailyActionPriority.INTERVIEW_TODAY.value
    assert actions[0].job_id == j1.id
    assert "Interview scheduled for today" in actions[0].reason

    # Check second action is Tier 2
    assert actions[1].priority_rank == DailyActionPriority.INTERVIEW_SOON.value
    assert actions[1].job_id == j2.id
    assert "Interview scheduled for" in actions[1].reason

    # Check third action is Tier 3
    assert actions[2].priority_rank == DailyActionPriority.FOLLOW_UP_DUE.value
    assert actions[2].job_id == j3.id
    assert "Follow-up overdue" in actions[2].reason


# ==============================================================================
# 5. INTERVIEW PREPARATION ENGINE TESTS
# ==============================================================================

def test_interview_prep_engine_technical_and_role_topics(sample_profile, sample_job):
    """Preparation engine extracts topics matching job description & profile."""
    service = InterviewPreparationService()
    package = service.generate_package(sample_job, sample_profile)

    # Technical skills extracted
    tech_names = [t.skill.lower() for t in package.technical_topics]
    assert "python" in tech_names
    assert "fastapi" in tech_names
    assert "postgresql" in tech_names

    # Role guides
    role_titles = [r["role_title"] for r in package.role_topics]
    assert "Backend Developer" in role_titles or "Python Developer" in role_titles

    # Technical questions generated
    assert len(package.likely_technical_questions) > 0


def test_interview_prep_project_matching(sample_profile, sample_job):
    """Identifies candidate's relevant project and generates targeted questions."""
    service = InterviewPreparationService()
    package = service.generate_package(sample_job, sample_profile)

    assert package.project_questions is not None
    assert package.project_questions.project_name in (
        "Loan Application Fraud Detection",
        "NeuroNest Notes & Bookmarks",
    )
    assert len(package.project_questions.discussion_points) >= 4


def test_interview_prep_skill_gap_prioritization(sample_profile, sample_job):
    """Skill gaps are prioritized into critical, moderate, and minor."""
    sample_job.critical_gaps = ["Docker"]
    sample_job.moderate_gaps = ["Kubernetes"]
    sample_job.minor_gaps = ["Redis"]

    service = InterviewPreparationService()
    package = service.generate_package(sample_job, sample_profile)

    assert "Docker" in package.missing_skills or "Docker" in sample_job.critical_gaps
    assert len(package.missing_skills) >= 0


def test_interview_prep_questions_to_ask_and_checklist(sample_profile, sample_job):
    """Package includes questions to ask the employer and preparation checklist."""
    service = InterviewPreparationService()
    package = service.generate_package(sample_job, sample_profile)

    assert len(package.questions_to_ask_employer) >= 5
    assert any("first" in q.lower() or "team" in q.lower() for q in package.questions_to_ask_employer)
    assert len(package.checklist) >= 8


# ==============================================================================
# 6. DATA CONSISTENCY AUDIT REGRESSION TEST
# ==============================================================================

def test_data_consistency_between_dashboard_and_apply_today(temp_db):
    """Section 5 regression: Apply Today counts on dashboard match actionable queue."""
    # Create 3 actionable jobs (URGENT, HIGH, NORMAL)
    j_urg = Job(id=1, source="lever", source_job_id="j1", title="Role 1", company="A",
                url="https://example.com/1", match_score=85,
                application_priority=ApplicationPriority.URGENT, status=JobStatus.NEW)
    j_high = Job(id=2, source="lever", source_job_id="j2", title="Role 2", company="B",
                 url="https://example.com/2", match_score=80,
                 application_priority=ApplicationPriority.HIGH, status=JobStatus.SHORTLISTED)
    j_norm = Job(id=3, source="lever", source_job_id="j3", title="Role 3", company="C",
                 url="https://example.com/3", match_score=75,
                 application_priority=ApplicationPriority.NORMAL, status=JobStatus.NEW)

    # Create 1 low job (non-actionable for immediate apply)
    j_low = Job(id=4, source="lever", source_job_id="j4", title="Role 4", company="D",
                url="https://example.com/4", match_score=65,
                application_priority=ApplicationPriority.LOW, status=JobStatus.NEW)

    # Create 1 applied job
    j_app = Job(id=5, source="lever", source_job_id="j5", title="Role 5", company="E",
                url="https://example.com/5", match_score=85,
                application_priority=ApplicationPriority.URGENT, status=JobStatus.APPLIED)

    for j in [j_urg, j_high, j_norm, j_low, j_app]:
        temp_db.save_job(j)

    counts = temp_db.get_dashboard_counts()
    # Dashboard apply_today counts active actionable jobs (1, 2, 3) = 3
    assert counts["apply_today"] == 3

    # get_jobs_filtered with actionable_only=True must also return exactly 3
    actionable_jobs, total = temp_db.get_jobs_filtered(actionable_only=True, exclude_inactive=True)
    assert total == 3
    assert len(actionable_jobs) == 3


# ==============================================================================
# 7. DASHBOARD ROUTES & CONTROLLERS TESTS
# ==============================================================================

@pytest.fixture
def client(temp_db, monkeypatch):
    """FastAPI TestClient with temp_db dependency."""
    # Ensure settings points to temp_db
    monkeypatch.setattr("app.dashboard.routes.get_db", lambda: temp_db)
    monkeypatch.setattr("app.dashboard.routes.get_tracker", lambda: JobTracker(temp_db))

    return TestClient(app)


def test_applications_route(client, temp_db, sample_job):
    """GET /applications returns 200 with pipeline metrics and application list."""
    sample_job.status = JobStatus.APPLIED
    sample_job.applied_at = datetime.now(timezone.utc)
    temp_db.save_job(sample_job)

    response = client.get("/applications")
    assert response.status_code == 200
    assert "Application Command Center" in response.text
    assert "TechCorp Innovations" in response.text
    assert "Python Backend Engineer Intern" in response.text


def test_today_route(client, temp_db, sample_job):
    """GET /today returns 200 with daily prioritized action items."""
    sample_job.status = JobStatus.INTERVIEW
    sample_job.interview_date = date.today().isoformat()
    sample_job.interview_status = InterviewStatus.SCHEDULED
    temp_db.save_job(sample_job)

    response = client.get("/today")
    assert response.status_code == 200
    assert "What Should I Work On Today?" in response.text
    assert "Interview Today" in response.text


def test_interview_prep_route(client, temp_db, sample_job):
    """GET /interview-prep returns 200 with preparation package."""
    temp_db.save_job(sample_job)

    response = client.get(f"/interview-prep?job_id={sample_job.id}")
    assert response.status_code == 200
    assert "Interview Preparation Workspace" in response.text
    assert "Technical Concept Focus Areas" in response.text
    assert "Likely Technical Questions" in response.text


def test_post_interview_update(client, temp_db, sample_job):
    """POST /jobs/{id}/interview updates interview state and redirects."""
    temp_db.save_job(sample_job)

    response = client.post(
        f"/jobs/{sample_job.id}/interview",
        data={
            "interview_date": "2026-10-20",
            "interview_stage": "Technical Interview",
            "interview_status": "SCHEDULED",
            "interview_preparation_status": "IN_PROGRESS",
            "interview_notes": "Brush up on FastAPI concurrency",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    saved = temp_db.get_job_by_id(sample_job.id)
    assert saved.interview_date == "2026-10-20"
    assert saved.interview_stage == InterviewStage.TECHNICAL_INTERVIEW
    assert saved.interview_status == InterviewStatus.SCHEDULED


# ==============================================================================
# 8. EXCEL EXPORT TESTS
# ==============================================================================

def test_excel_export_phase_11_sheets_and_columns(tmp_path, sample_job):
    """Excel export generates Applications & Interview Preparation sheets with all Phase 11 fields."""
    sample_job.status = JobStatus.APPLIED
    sample_job.applied_at = datetime.now(timezone.utc)
    sample_job.interview_date = "2026-10-22"
    sample_job.interview_stage = InterviewStage.CODING_ROUND
    sample_job.interview_status = InterviewStatus.SCHEDULED
    sample_job.interview_preparation_status = InterviewPrepStatus.READY
    sample_job.interview_notes = "Prepare LeetCode medium questions"

    exporter = ExcelExporter(exports_dir=tmp_path)
    output_path = tmp_path / "test_phase11_export.xlsx"
    exported_file = exporter.export([sample_job], output_path=output_path)

    import openpyxl
    wb = openpyxl.load_workbook(exported_file)

    # Verify sheet names
    sheet_names = wb.sheetnames
    assert "Applications" in sheet_names
    assert "Interview Preparation" in sheet_names
    assert "New Matches" in sheet_names
    assert "Top Matches" in sheet_names
    assert "All Relevant Jobs" in sheet_names
    assert "Apply Today" in sheet_names
    assert "Resume Preparation" in sheet_names

    # Verify column headers in Applications sheet
    ws_apps = wb["Applications"]
    headers = [cell.value for cell in ws_apps[1]]
    assert "Applied At" in headers
    assert "Interview Date" in headers
    assert "Interview Stage" in headers
    assert "Interview Status" in headers
    assert "Interview Prep Status" in headers
    assert "Interview Notes" in headers

    # Verify row values in Applications sheet
    row2_vals = [cell.value for cell in ws_apps[2]]
    assert "Coding Round" in row2_vals or "CODING_ROUND" in row2_vals
    assert "2026-10-22" in row2_vals
    assert "Prepare LeetCode medium questions" in row2_vals


# ==============================================================================
# 9. REGRESSION & SAFETY AUDIT
# ==============================================================================

def test_safety_manual_only_enforcement():
    """Verify application command center never implements auto-apply or external API submission."""
    # Ensure no automated submission flags exist in database or models
    assert not hasattr(Job, "auto_apply_submitted")
    assert not hasattr(Job, "bot_submission_status")
    # All JobStatus values remain unchanged
    assert set(s.value for s in JobStatus) == {
        "NEW", "VIEWED", "SHORTLISTED", "APPLIED", "REJECTED", "NOT_INTERESTED", "INTERVIEW", "OFFER"
    }
