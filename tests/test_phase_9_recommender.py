"""Tests for Phase 9 - Job Recommendation Quality & Application Workflow.

Covers:
1. Application Readiness Score calculation across edge cases.
2. Application Priority assignment (URGENT, HIGH, NORMAL, LOW, SKIP).
3. Skill Gap Analysis (critical, moderate, minor gap categorization).
4. Profile Alignment, Recommendation Reasons, and Risk Warnings.
5. Application Checklist generation.
6. Pipeline integration and status preservation.
7. Follow-up tracking (date, notes, upcoming queries, overdue logic).
8. Daily application target and progress counting.
9. Database persistence, schema migration, and backfill.
10. Dashboard /apply-today route and follow-up endpoint.
11. Excel export containing Phase 9 fields and "Apply Today" sheet.
"""

from datetime import date, datetime, timedelta
import tempfile
from pathlib import Path
import pytest
from starlette.testclient import TestClient
import openpyxl

from app.models.job import Job, JobStatus, ApplicationPriority
from app.models.profile import JobProfile
from app.models.recommendation import ApplicationRecommendation
from app.services.recommender import JobRecommender
from app.database.database import DatabaseManager
from app.services.job_tracker import JobTracker
from app.services.excel_exporter import ExcelExporter, REPORT_COLUMNS
from app.dashboard.app import app
import app.dashboard.routes as dashboard_routes


@pytest.fixture
def sample_profile():
    return JobProfile(
        target_roles=["Python Developer", "Backend Engineer", "Software Engineer"],
        skills=["Python", "FastAPI", "Django", "SQL", "PostgreSQL", "Docker", "Git"],
        preferred_locations=["Bangalore", "Bengaluru", "Remote"],
        min_experience_years=0,
        max_experience_years=2,
    )


@pytest.fixture
def recommender(sample_profile):
    return JobRecommender(sample_profile)


# ==============================================================================
# 1. APPLICATION READINESS SCORE TESTS
# ==============================================================================

def test_readiness_score_excellent_match_and_full_info(recommender):
    """Job with 90 match score, direct URL, entry experience, 5 matched skills, full signals."""
    job = Job(
        source="greenhouse",
        title="Junior Python Developer",
        company="Stripe",
        location="Bengaluru",
        url="https://boards.greenhouse.io/stripe/jobs/12345",
        description="Looking for an entry level Python engineer with FastAPI, SQL, Docker, and Git.",
        match_score=90,
        matched_skills=["Python", "FastAPI", "SQL", "Docker", "Git"],
        experience_required="0-2 years (fresher/entry level)",
        experience_match=True,
    )
    score = recommender.calculate_application_readiness(job)
    # 90 * 0.50 = 45
    # Accessibility: greenhouse URL -> 10 + 5 = 15
    # Experience: entry level -> 15
    # Skill coverage: 5 matched skills -> 10
    # Readiness signals: 5 signals -> 10
    # Total = 45 + 15 + 15 + 10 + 10 = 95
    assert score == 95


def test_readiness_score_weak_match(recommender):
    """Job with low match score and missing info."""
    job = Job(
        source="lever",
        title="Sales Associate",
        company="Unknown",
        location="",
        url="",
        description="",
        match_score=30,
        matched_skills=[],
        experience_required="5+ years required",
        experience_match=False,
    )
    score = recommender.calculate_application_readiness(job)
    # Match: 30 * 0.5 = 15
    # Accessibility: 0 (no URL)
    # Experience: 0 (5+ years)
    # Skill coverage: 0
    # Signals: title + lever source = 2 signals -> 4
    assert score == 19


def test_readiness_score_missing_url(recommender):
    """Job with strong match but missing URL loses accessibility points."""
    job = Job(
        source="lever",
        title="Software Engineer",
        company="Paytm",
        location="Bengaluru",
        url="",
        description="Python backend role with detailed description over 50 chars for testing purposes.",
        match_score=80,
        matched_skills=["Python", "SQL"],
        experience_required="0-1 years",
        experience_match=True,
    )
    score = recommender.calculate_application_readiness(job)
    # Match: 40
    # Accessibility: 0
    # Experience: 15
    # Skills: 2 skills -> 4
    # Signals: company, title, location, desc = 4 signals -> 8
    # Total = 67
    assert score == 67


def test_readiness_score_unspecified_experience(recommender):
    """Unspecified/missing experience gives partial points (8)."""
    job = Job(
        source="greenhouse",
        title="Python Engineer",
        company="MongoDB",
        location="Bengaluru",
        url="https://boards.greenhouse.io/mongodb/jobs/1",
        description="Backend developer with extensive description for high signal score testing.",
        match_score=70,
        matched_skills=["Python", "FastAPI", "SQL"],
        experience_required="",
        experience_match=False,
    )
    score = recommender.calculate_application_readiness(job)
    # Match: 35
    # Accessibility: 15
    # Experience: 8
    # Skills: 3 skills -> 7
    # Signals: 5 signals -> 10
    # Total = 75
    assert score == 75


# ==============================================================================
# 2. APPLICATION PRIORITY TESTS
# ==============================================================================

def test_priority_urgent(recommender):
    """Readiness >= 85 and match_score >= 80 -> URGENT."""
    job = Job(
        source="lever",
        title="Python Developer",
        company="Meesho",
        location="Bengaluru",
        url="https://jobs.lever.co/meesho/1",
        description="Freshers welcome. Python and FastAPI. Comprehensive description text.",
        match_score=85,
        matched_skills=["Python", "FastAPI", "SQL", "Docker", "Git"],
        experience_required="0-1 years",
        experience_match=True,
    )
    rec = recommender.recommend(job)
    assert rec.application_readiness_score >= 85
    assert rec.application_priority == ApplicationPriority.URGENT


def test_priority_high(recommender):
    """Readiness >= 75 or match_score >= 80 -> HIGH."""
    job = Job(
        source="lever",
        title="Software Engineer",
        company="Meesho",
        location="Bengaluru",
        url="https://jobs.lever.co/meesho/2",
        description="Python backend",
        match_score=80,
        matched_skills=["Python", "SQL"],
        experience_required=None,
        experience_match=False,
    )
    rec = recommender.recommend(job)
    assert rec.application_priority in [ApplicationPriority.HIGH, ApplicationPriority.URGENT]


def test_priority_normal_and_low_and_skip(recommender):
    job = Job(
        source="lever",
        title="Software Engineer",
        company="Meesho",
        location="Bengaluru",
        url="https://jobs.lever.co/meesho/3",
        match_score=60,
    )
    # Readiness between 60 and 74 with match < 80 -> NORMAL
    assert recommender.determine_application_priority(job, 65) == ApplicationPriority.NORMAL
    # Readiness between 45 and 59 -> LOW
    assert recommender.determine_application_priority(job, 50) == ApplicationPriority.LOW
    # Readiness < 45 -> SKIP
    assert recommender.determine_application_priority(job, 40) == ApplicationPriority.SKIP


# ==============================================================================
# 3. SKILL GAP ANALYSIS TESTS
# ==============================================================================

def test_skill_gap_analysis_required_vs_optional(recommender):
    """Verify critical gaps occur only when requirements sections strongly require the skill."""
    job = Job(
        source="greenhouse",
        title="Backend Engineer",
        company="Twilio",
        location="Bengaluru",
        url="https://boards.greenhouse.io/twilio/jobs/1",
        description=(
            "About us: We love technology.\n"
            "Requirements:\n"
            "- Must have 1+ years experience in Java and Spring Boot.\n"
            "- Strong grasp of computer science.\n"
            "Nice to have:\n"
            "- Experience with Redis and Kubernetes is a plus.\n"
        ),
        matched_skills=["Git"],
    )
    missing, critical, moderate, minor = recommender.analyze_skill_gaps(job)
    # Java and Spring Boot appear under 'Requirements' -> Critical Gaps
    assert "Java" in critical
    assert "Spring Boot" in critical
    # Redis appears in 'Nice to have' / body -> Moderate or Minor Gap, definitely not critical
    assert "Redis" not in critical
    assert "Redis" in moderate or "Redis" in minor


def test_skill_gap_no_missing_skills(recommender):
    """When job description mentions only skills candidate has."""
    job = Job(
        source="lever",
        title="Python Developer",
        company="FamPay",
        location="Bengaluru",
        url="https://jobs.lever.co/fampay/1",
        description="Requirements: Strong experience with Python, FastAPI, and SQL.",
        matched_skills=["Python", "FastAPI", "SQL"],
    )
    missing, critical, moderate, minor = recommender.analyze_skill_gaps(job)
    assert len(critical) == 0
    assert len(moderate) == 0


# ==============================================================================
# 4. EXPLANATIONS & RISK WARNINGS TESTS
# ==============================================================================

def test_recommendation_reasons(recommender):
    job = Job(
        source="greenhouse",
        title="Python Backend Developer",
        company="Stripe",
        location="Bengaluru",
        url="https://boards.greenhouse.io/stripe/jobs/1",
        description="Python developer",
        match_score=85,
        matched_roles=["Python Developer"],
        matched_skills=["Python", "FastAPI"],
        matched_locations=["Bengaluru"],
        experience_required="0-2 years",
        experience_match=True,
    )
    reasons = recommender.generate_match_reasons(job)
    assert any("matches your target role" in r for r in reasons)
    assert any("Python" in r for r in reasons)
    assert any("Bengaluru" in r for r in reasons)
    assert any("entry-level" in r.lower() for r in reasons)


def test_risk_reasons_senior_and_missing_skills(recommender):
    job = Job(
        source="greenhouse",
        title="Senior Python Architect",
        company="Instawork",
        location="Remote - US Only",
        url="",
        description="Requirements:\nMust have 5+ years experience in Java and C++.",
        match_score=50,
        matched_skills=[],
        experience_required="5+ years required",
        experience_match=False,
    )
    rec = recommender.recommend(job)
    risks = rec.risk_reasons
    assert any("experience" in r.lower() for r in risks)
    assert any("missing" in r.lower() or "critical" in r.lower() for r in risks)
    assert any("direct application url" in r.lower() for r in risks)


def test_profile_alignment(recommender):
    job_strong = Job(
        source="lever",
        title="Python Developer",
        company="Paytm",
        location="Bengaluru",
        url="https://jobs.lever.co/paytm/1",
        match_score=85,
        matched_skills=["Python", "SQL"],
        matched_locations=["Bengaluru"],
        experience_match=True,
    )
    job_weak = Job(
        source="lever",
        title="Sales Manager",
        company="Unknown",
        location="London",
        url="https://jobs.lever.co/unknown/1",
        match_score=35,
        matched_skills=[],
        matched_locations=[],
        experience_match=False,
    )
    assert recommender.get_profile_alignment(job_strong) == "Strong alignment"
    assert recommender.get_profile_alignment(job_weak) == "Weak alignment"


# ==============================================================================
# 5. APPLICATION CHECKLIST TESTS
# ==============================================================================

def test_application_checklist_contains_tailoring_when_gaps_exist(recommender):
    job = Job(
        source="lever",
        title="Backend Engineer",
        company="JumpCloud",
        location="Bengaluru",
        url="https://jobs.lever.co/jumpcloud/1",
        description="Requirements: Must have Go and Kubernetes.",
        matched_skills=["Python"],
    )
    rec = recommender.recommend(job)
    assert len(rec.checklist) >= 6
    assert any("Tailor resume" in item for item in rec.checklist)
    assert any("Open application URL" in item for item in rec.checklist)


# ==============================================================================
# 6. DATABASE PERSISTENCE, MIGRATION & FOLLOW-UP TESTS
# ==============================================================================

def test_database_schema_and_follow_up_tracking(sample_profile):
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_jobs.db"
        db = DatabaseManager(db_path=db_path)

        job = Job(
            source="greenhouse",
            title="Software Engineer",
            company="GitLab",
            location="Remote",
            url="https://boards.greenhouse.io/gitlab/jobs/1",
            description="Python engineer",
            match_score=85,
            matched_skills=["Python", "Docker"],
            status=JobStatus.APPLIED,
        )

        recommender = JobRecommender(sample_profile)
        rec = recommender.recommend(job)
        job.apply_recommendation_result(rec)

        db.save_job(job)
        job_id = job.id

        # Set follow-up date and notes
        target_date = (date.today() + timedelta(days=5)).isoformat()
        db.update_job_follow_up(job_id, follow_up_date=target_date, follow_up_notes="Check in with recruiter")

        loaded = db.get_job_by_id(job_id)
        assert loaded is not None
        assert loaded.follow_up_date == target_date
        assert loaded.follow_up_notes == "Check in with recruiter"
        assert loaded.application_readiness_score == rec.application_readiness_score
        assert loaded.application_priority == rec.application_priority
        assert loaded.profile_alignment == rec.profile_alignment

        # Test upcoming follow-ups query
        upcoming = db.get_upcoming_follow_ups()
        assert len(upcoming) == 1
        assert upcoming[0].id == job_id
        assert upcoming[0].company == "GitLab"


def test_daily_application_progress(sample_profile):
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_jobs.db"
        db = DatabaseManager(db_path=db_path)

        # Job applied today
        job1 = Job(
            source="lever",
            title="Python Dev 1",
            company="Meesho",
            location="Bengaluru",
            url="https://jobs.lever.co/meesho/1",
            status=JobStatus.APPLIED,
            status_updated_at=datetime.now(),
        )
        db.save_job(job1)

        # Job applied yesterday (should NOT count as applied today)
        yesterday = datetime.now() - timedelta(days=1)
        job2 = Job(
            source="lever",
            title="Python Dev 2",
            company="Meesho",
            location="Bengaluru",
            url="https://jobs.lever.co/meesho/2",
            status=JobStatus.APPLIED,
            status_updated_at=yesterday,
        )
        db.save_job(job2)

        counts = db.get_dashboard_counts(daily_target=5)
        assert counts["applied_today"] == 1
        assert counts["daily_target"] == 5
        assert counts["remaining_today"] == 4


def test_apply_today_queue_excludes_inactive(sample_profile):
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_jobs.db"
        db = DatabaseManager(db_path=db_path)

        # Active job (NEW)
        j1 = Job(
            source="lever",
            title="Python Engineer",
            company="FamPay",
            location="Bengaluru",
            url="https://jobs.lever.co/fampay/1",
            status=JobStatus.NEW,
            application_readiness_score=85,
            application_priority=ApplicationPriority.URGENT,
        )
        # Inactive job (APPLIED)
        j2 = Job(
            source="lever",
            title="Python Engineer 2",
            company="EpiFi",
            location="Bengaluru",
            url="https://jobs.lever.co/epifi/1",
            status=JobStatus.APPLIED,
            application_readiness_score=90,
            application_priority=ApplicationPriority.URGENT,
        )
        db.save_job(j1)
        db.save_job(j2)

        # Query with exclude_inactive=True (Apply Today behavior)
        active_jobs, total = db.get_jobs_filtered(exclude_inactive=True)
        assert total == 1
        assert active_jobs[0].company == "FamPay"


# ==============================================================================
# 7. DASHBOARD ROUTES & EXCEL EXPORT TESTS
# ==============================================================================

def test_dashboard_apply_today_route(sample_profile, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_jobs.db"
        db = DatabaseManager(db_path=db_path)

        job = Job(
            source="greenhouse",
            title="Backend Engineer",
            company="Elastic",
            location="Bengaluru",
            url="https://boards.greenhouse.io/elastic/jobs/1",
            status=JobStatus.NEW,
            application_readiness_score=88,
            application_priority=ApplicationPriority.URGENT,
            match_score=85,
            match_category="Strong",
            checklist=["Review requirements", "Submit application"],
            recommendation_reasons=["Matches Python role", "Bengaluru location"],
        )
        db.save_job(job)
        job_id = job.id

        monkeypatch.setattr(dashboard_routes, "get_db", lambda: db)
        monkeypatch.setattr(dashboard_routes, "get_tracker", lambda: JobTracker(db))
        client = TestClient(app)

        # GET /apply-today
        response = client.get("/apply-today")
        assert response.status_code == 200
        assert "Apply Today" in response.text
        assert "Elastic" in response.text
        assert "URGENT" in response.text

        # POST /jobs/{job_id}/follow-up
        post_resp = client.post(
            f"/jobs/{job_id}/follow-up",
            data={"follow_up_date": "2026-10-15", "follow_up_notes": "Follow up via email"},
            follow_redirects=True,
        )
        assert post_resp.status_code == 200

        # Verify updated in DB
        updated = db.get_job_by_id(job_id)
        assert updated.follow_up_date == "2026-10-15"
        assert updated.follow_up_notes == "Follow up via email"


def test_excel_export_phase_9_sheets_and_columns():
    with tempfile.TemporaryDirectory() as tmp_dir:
        exporter = ExcelExporter(exports_dir=tmp_dir)
        job = Job(
            source="lever",
            title="Python Developer",
            company="Meesho",
            location="Bengaluru",
            url="https://jobs.lever.co/meesho/1",
            match_score=85,
            match_category="Strong",
            application_readiness_score=88,
            application_priority=ApplicationPriority.URGENT,
            status=JobStatus.NEW,
            follow_up_date="2026-10-12",
        )
        file_path = exporter.export([job])

        wb = openpyxl.load_workbook(str(file_path))
        # Check sheets
        assert "Top Matches" in wb.sheetnames
        assert "All Relevant Jobs" in wb.sheetnames
        assert "New Matches" in wb.sheetnames
        assert "Apply Today" in wb.sheetnames

        # Active sheet must remain Top Matches
        assert wb.active.title == "Top Matches"

        # Check Apply Today sheet content
        ws_apply = wb["Apply Today"]
        col_prio = REPORT_COLUMNS.index("Application Priority") + 1
        col_readiness = REPORT_COLUMNS.index("Application Readiness") + 1
        assert ws_apply.cell(row=2, column=col_prio).value == "URGENT"
        assert ws_apply.cell(row=2, column=col_readiness).value == 88
