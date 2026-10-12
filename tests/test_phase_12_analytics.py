"""Comprehensive unit and integration tests for Phase 12 Application Analytics & Optimization."""

import os
from datetime import date, datetime, timedelta
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.database.database import DatabaseManager
from app.models.job import ApplicationPriority, Job, JobStatus
from app.models.profile import JobProfile
from app.services.analytics import AnalyticsService
from app.services.excel_exporter import ExcelExporter
from app.dashboard.app import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture providing an isolated SQLite database."""
    db_file = tmp_path / "test_analytics.db"
    db = DatabaseManager(str(db_file))
    db.initialize()
    return db


@pytest.fixture
def sample_profile():
    """Fixture providing a mock candidate profile."""
    return JobProfile(
        target_roles=[
            "Python Developer",
            "Backend Developer",
            "Software Engineer",
            "Full Stack Developer",
            "ML Engineer",
            "SDE Intern",
        ],
        preferred_locations=[
            "Bangalore",
            "Bengaluru",
            "Delhi",
            "Noida",
            "Remote",
            "India",
        ],
        skills=["Python", "FastAPI", "React", "SQL", "Machine Learning", "Git"],
    )


def _create_mock_job(
    title: str = "Backend Developer",
    company: str = "Acme Corp",
    location: str = "Bangalore, India",
    source: str = "greenhouse",
    match_score: int = 85,
    readiness_score: int = 80,
    resume_score: int = 75,
    priority: ApplicationPriority = ApplicationPriority.HIGH,
    status: JobStatus = JobStatus.NEW,
    applied_at: datetime = None,
    interview_date: str = None,
    interview_status: str = "NOT_SCHEDULED",
    easy_apply: bool = False,
    skills: list = None,
) -> Job:
    """Helper to instantiate mock Job objects with specified properties."""
    return Job(
        title=title,
        company=company,
        location=location,
        source=source,
        url=f"https://example.com/job/{datetime.now().timestamp()}_{title.replace(' ', '_')}",
        description=f"Job for {title} with skills {skills or ['Python']}",
        easy_apply=easy_apply,
        match_score=match_score,
        application_readiness_score=readiness_score,
        resume_alignment_score=resume_score,
        application_priority=priority,
        status=status,
        applied_at=applied_at,
        interview_date=interview_date,
        interview_status=interview_status,
        matched_roles=[title],
        matched_skills=skills or ["Python", "FastAPI"],
        matched_locations=["Bangalore"],
    )


def test_funnel_and_conversions_calculation(temp_db, sample_profile):
    """Test core funnel metric counts and percentage calculations."""
    today_dt = datetime.now()
    # 1. Job Relevant + Applied
    j1 = _create_mock_job(
        title="Backend Developer",
        match_score=85,
        priority=ApplicationPriority.HIGH,
        status=JobStatus.APPLIED,
        applied_at=today_dt,
    )
    # 2. Job Relevant + Interview
    j2 = _create_mock_job(
        title="Python Developer",
        match_score=90,
        priority=ApplicationPriority.URGENT,
        status=JobStatus.INTERVIEW,
        applied_at=today_dt - timedelta(days=2),
        interview_date=date.today().isoformat(),
        interview_status="SCHEDULED",
    )
    # 3. Job Relevant + Offer
    j3 = _create_mock_job(
        title="Software Engineer",
        match_score=80,
        priority=ApplicationPriority.HIGH,
        status=JobStatus.OFFER,
        applied_at=today_dt - timedelta(days=5),
    )
    # 4. Job Relevant + Unapplied
    j4 = _create_mock_job(
        title="Full Stack Developer",
        match_score=70,
        priority=ApplicationPriority.NORMAL,
        status=JobStatus.NEW,
    )
    # 5. Job Not Relevant (< 60)
    j5 = _create_mock_job(
        title="Senior Director",
        match_score=40,
        priority=ApplicationPriority.SKIP,
        status=JobStatus.NEW,
    )

    for j in [j1, j2, j3, j4, j5]:
        temp_db.save_job(j)

    service = AnalyticsService(temp_db, sample_profile)
    report = service.get_report(period="all")

    # Funnel checks
    assert report.funnel.jobs_found == 5
    assert report.funnel.relevant == 4  # j1, j2, j3, j4
    assert report.funnel.recommended == 4  # j1, j2, j3, j4
    assert report.funnel.applied == 3  # j1, j2, j3 (APPLIED, INTERVIEW, OFFER)
    assert report.funnel.interview == 1  # j2
    assert report.funnel.offer == 1  # j3

    # Conversions
    # Application Rate: 3 / 4 * 100 = 75.0%
    assert report.conversion_rates.application_rate == 75.0
    # Recommendation to App Rate: 3 / 4 * 100 = 75.0%
    assert report.conversion_rates.recommendation_to_app_rate == 75.0
    # Interview Rate: 1 / 3 * 100 = 33.3%
    assert report.conversion_rates.interview_rate == 33.3
    # Offer Rate: 1 / 3 * 100 = 33.3%
    assert report.conversion_rates.offer_rate == 33.3
    # Interview to Offer Rate: 1 / 1 * 100 = 100.0%
    assert report.conversion_rates.interview_to_offer_rate == 100.0


def test_zero_denominator_safe_handling(temp_db, sample_profile):
    """Verify that zero denominators safely produce None without division errors."""
    service = AnalyticsService(temp_db, sample_profile)
    report = service.get_report(period="all")

    assert report.funnel.jobs_found == 0
    assert report.conversion_rates.application_rate is None
    assert report.conversion_rates.recommendation_to_app_rate is None
    assert report.conversion_rates.interview_rate is None
    assert report.conversion_rates.offer_rate is None
    assert report.conversion_rates.interview_to_offer_rate is None


def test_source_quality_score_formula(temp_db, sample_profile):
    """Test deterministic source quality score formula and small sample protection."""
    service = AnalyticsService(temp_db, sample_profile)

    # 1. Under 5 jobs -> Insufficient data
    score, label = service.compute_source_quality_score(
        jobs_found=4, relevant=4, recommended=4, applied=2, interview=1, offer=0
    )
    assert score is None
    assert label == "Insufficient data"

    # 2. 10 jobs with high relevance & conversion -> Strong Quality
    # rel = 8/10 (80%), rec = 7/10 (70%), app = 4/8 (50%), int = 2/4 (50%)
    # score = (80*0.4) + (70*0.25) + (50*0.2) + (50*0.15) = 32 + 17.5 + 10 + 7.5 = 67.0
    score, label = service.compute_source_quality_score(
        jobs_found=10, relevant=8, recommended=7, applied=4, interview=2, offer=1
    )
    assert score == 67.0
    assert label == "Moderate Quality"

    # 3. Near perfect conversion -> Strong Quality (>= 75.0)
    score_top, label_top = service.compute_source_quality_score(
        jobs_found=10, relevant=10, recommended=10, applied=10, interview=8, offer=3
    )
    assert score_top >= 75.0
    assert label_top == "Strong Quality"


def test_source_analytics_grouping(temp_db, sample_profile):
    """Verify source connector metrics aggregation."""
    for i in range(6):
        temp_db.save_job(
            _create_mock_job(
                source="lever",
                match_score=80 if i < 4 else 50,
                status=JobStatus.APPLIED if i == 0 else JobStatus.NEW,
            )
        )
    temp_db.save_job(
        _create_mock_job(
            source="greenhouse",
            match_score=85,
            status=JobStatus.NEW,
        )
    )

    service = AnalyticsService(temp_db, sample_profile)
    report = service.get_report(period="all")

    lever_metric = next((s for s in report.sources if s.source == "lever"), None)
    assert lever_metric is not None
    assert lever_metric.jobs_found == 6
    assert lever_metric.relevant == 4
    assert lever_metric.applied == 1
    assert lever_metric.quality_score is not None

    gh_metric = next((s for s in report.sources if s.source == "greenhouse"), None)
    assert gh_metric is not None
    assert gh_metric.jobs_found == 1
    assert gh_metric.quality_score is None  # < 5 jobs
    assert gh_metric.quality_label == "Insufficient data"


def test_role_and_location_analytics(temp_db, sample_profile):
    """Verify target role and location performance aggregation."""
    temp_db.save_job(_create_mock_job(title="Python Developer", location="Bangalore, India", status=JobStatus.APPLIED))
    temp_db.save_job(_create_mock_job(title="Backend Developer", location="Delhi, India", status=JobStatus.NEW))
    temp_db.save_job(_create_mock_job(title="SDE Intern", location="Remote", status=JobStatus.NEW))

    service = AnalyticsService(temp_db, sample_profile)
    report = service.get_report(period="all")

    py_role = next((r for r in report.roles if r.role_name == "Python Developer"), None)
    assert py_role is not None
    assert py_role.applied == 1

    blr_loc = next((l for l in report.locations if "Bangalore" in l.location_name), None)
    assert blr_loc is not None
    assert blr_loc.applied == 1


def test_score_buckets_analytics(temp_db, sample_profile):
    """Verify Match, Readiness, and Resume score bucket distributions."""
    temp_db.save_job(_create_mock_job(match_score=95, readiness_score=88, resume_score=92, status=JobStatus.APPLIED))
    temp_db.save_job(_create_mock_job(match_score=82, readiness_score=78, resume_score=68, status=JobStatus.NEW))
    temp_db.save_job(_create_mock_job(match_score=65, readiness_score=62, resume_score=55, status=JobStatus.NEW))
    temp_db.save_job(_create_mock_job(match_score=45, readiness_score=40, resume_score=35, status=JobStatus.NEW))

    service = AnalyticsService(temp_db, sample_profile)
    report = service.get_report(period="all")

    m_90 = next((b for b in report.match_buckets if "90–100" in b.bucket_label), None)
    assert m_90.jobs_count == 1
    assert m_90.applied == 1

    r_85 = next((b for b in report.readiness_buckets if "85–100" in b.bucket_label), None)
    assert r_85.jobs_count == 1

    res_80 = next((b for b in report.resume_buckets if "80–100" in b.bucket_label), None)
    assert res_80.jobs_count == 1


def test_easy_apply_and_skills_analytics(temp_db, sample_profile):
    """Test Easy Apply comparison and observed skill frequency."""
    temp_db.save_job(_create_mock_job(easy_apply=True, status=JobStatus.APPLIED, skills=["Python", "FastAPI"]))
    temp_db.save_job(_create_mock_job(easy_apply=False, status=JobStatus.APPLIED, skills=["Python", "React"]))

    service = AnalyticsService(temp_db, sample_profile)
    report = service.get_report(period="all")

    easy_metric = next((e for e in report.easy_apply if e.type_label == "Easy Apply"), None)
    assert easy_metric is not None
    assert easy_metric.applied == 1

    py_skill = next((s for s in report.skills if s.skill == "Python"), None)
    assert py_skill is not None
    assert py_skill.applied_count == 2


def test_daily_target_and_streak(temp_db, sample_profile):
    """Test daily application target tracking and streak calculation."""
    today_dt = datetime.now()
    # 2 applications today
    temp_db.save_job(_create_mock_job(status=JobStatus.APPLIED, applied_at=today_dt))
    temp_db.save_job(_create_mock_job(status=JobStatus.APPLIED, applied_at=today_dt))

    service = AnalyticsService(temp_db, sample_profile)
    report = service.get_report(period="all", daily_target=5)

    assert report.daily_target.target == 5
    assert report.daily_target.applied_today == 2
    assert report.daily_target.remaining == 3
    assert report.daily_target.achievement_percentage == 40.0
    assert report.streak.current_streak >= 1


def test_small_dataset_protection_and_insights(temp_db, sample_profile):
    """Test that small samples are appropriately flagged with limitation insights."""
    # Only 1 application
    temp_db.save_job(_create_mock_job(status=JobStatus.APPLIED, applied_at=datetime.now()))

    service = AnalyticsService(temp_db, sample_profile)
    report = service.get_report(period="all")

    assert report.is_small_sample is True
    limitation_insight = next((i for i in report.insights if i.category == "LIMITATION"), None)
    assert limitation_insight is not None
    assert "Limited Application Sample Size" in limitation_insight.title


def test_excel_analytics_sheet_export(temp_db, tmp_path):
    """Verify that export_jobs creates Sheet 8 'Analytics' with complete content."""
    job1 = _create_mock_job(match_score=85, status=JobStatus.APPLIED, applied_at=datetime.now())
    job2 = _create_mock_job(match_score=92, status=JobStatus.INTERVIEW, interview_status="SCHEDULED")
    temp_db.save_job(job1)
    temp_db.save_job(job2)

    jobs = temp_db.get_all_jobs()
    export_path = tmp_path / "test_analytics_export.xlsx"

    exporter = ExcelExporter()
    out = exporter.export(jobs=jobs, output_path=str(export_path))

    import openpyxl
    wb = openpyxl.load_workbook(out)

    assert "Analytics" in wb.sheetnames
    ws = wb["Analytics"]
    assert ws["A1"].value == "Pipeline Metric"
    assert ws["B1"].value == "Count / Value"
    assert ws["C1"].value == "Conversion / Yield"


def test_dashboard_analytics_route_http_200():
    """Verify GET /analytics returns 200 OK with rendered HTML."""
    client = TestClient(app)

    response = client.get("/analytics")
    assert response.status_code == 200
    assert "Application Analytics" in response.text
    assert "Application Funnel" in response.text
    assert "Daily Target Analysis" in response.text


def test_dashboard_routes_regression():
    """Verify all existing dashboard routes continue to return HTTP 200."""
    client = TestClient(app)

    endpoints = [
        "/dashboard",
        "/applications",
        "/today",
        "/apply-today",
        "/interview-prep",
        "/resume-preparation",
        "/jobs",
        "/pipeline-runs",
        "/source-health",
    ]
    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 200, f"Endpoint {ep} failed with status {resp.status_code}"


def test_period_and_date_filtering(temp_db, sample_profile):
    """Verify period filtering (today, 7d, 30d) and custom date ranges."""
    today_dt = datetime.now()
    j_today = _create_mock_job(title="Job Today", match_score=85, status=JobStatus.APPLIED, applied_at=today_dt)
    j_today.date_found = today_dt
    j_today.first_seen_at = today_dt

    j_old = _create_mock_job(title="Job Old", match_score=75, status=JobStatus.NEW)
    j_old.date_found = today_dt - timedelta(days=45)
    j_old.first_seen_at = today_dt - timedelta(days=45)

    temp_db.save_job(j_today)
    temp_db.save_job(j_old)

    service = AnalyticsService(temp_db, sample_profile)

    # 1. Period = today
    r_today = service.get_report(period="today")
    assert r_today.funnel.jobs_found == 1
    assert r_today.funnel.applied == 1

    # 2. Period = 7d
    r_7d = service.get_report(period="7d")
    assert r_7d.funnel.jobs_found == 1

    # 3. Period = all
    r_all = service.get_report(period="all")
    assert r_all.funnel.jobs_found == 2


def test_weekly_comparison_metrics(temp_db, sample_profile):
    """Verify weekly comparison captures current and previous week activity."""
    today_dt = datetime.now()
    j_cur = _create_mock_job(title="Cur Week", match_score=85, status=JobStatus.APPLIED, applied_at=today_dt)
    j_cur.date_found = today_dt
    j_cur.first_seen_at = today_dt

    j_prev = _create_mock_job(title="Prev Week", match_score=75, status=JobStatus.NEW)
    j_prev.date_found = today_dt - timedelta(days=10)
    j_prev.first_seen_at = today_dt - timedelta(days=10)

    temp_db.save_job(j_cur)
    temp_db.save_job(j_prev)

    service = AnalyticsService(temp_db, sample_profile)
    report = service.get_report(period="all")

    assert report.weekly is not None
    assert report.weekly.current_week_jobs == 1
    assert report.weekly.previous_week_jobs == 1


def test_streak_consecutive_days_and_resets(temp_db, sample_profile):
    """Verify application streak properly increments on consecutive days and resets on gaps."""
    today = date.today()
    d1 = datetime(today.year, today.month, today.day, 10, 0, 0)
    d2 = d1 - timedelta(days=1)
    d3 = d1 - timedelta(days=2)
    d_gap = d1 - timedelta(days=10)

    # 3 consecutive days + 1 older day
    j1 = _create_mock_job(status=JobStatus.APPLIED, applied_at=d1)
    j2 = _create_mock_job(status=JobStatus.APPLIED, applied_at=d2)
    j3 = _create_mock_job(status=JobStatus.APPLIED, applied_at=d3)
    j4 = _create_mock_job(status=JobStatus.APPLIED, applied_at=d_gap)

    for j in [j1, j2, j3, j4]:
        temp_db.save_job(j)

    streak = temp_db.get_application_streak()
    assert streak["current_streak"] == 3
    assert streak["longest_streak"] >= 3


def test_experience_fit_breakdown(temp_db, sample_profile):
    """Verify experience category breakdown."""
    j1 = _create_mock_job(title="Fresher SDE", match_score=80, status=JobStatus.APPLIED)
    j1.experience_required = "Fresher / 0 years"
    j2 = _create_mock_job(title="Junior Developer", match_score=75, status=JobStatus.NEW)
    j2.experience_required = "0-1 years"

    temp_db.save_job(j1)
    temp_db.save_job(j2)

    service = AnalyticsService(temp_db, sample_profile)
    report = service.get_report(period="all")

    assert len(report.experience) >= 2
    fresher = next((e for e in report.experience if "Fresher" in e.level_label), None)
    assert fresher is not None
    assert fresher.relevant == 1
    assert fresher.applied == 1


def test_analytics_route_filter_queries():
    """Verify GET /analytics handles query parameters smoothly."""
    client = TestClient(app)

    urls = [
        "/analytics?period=today",
        "/analytics?period=7d",
        "/analytics?period=30d",
        "/analytics?period=90d",
        "/analytics?period=all",
        "/analytics?source=greenhouse",
        "/analytics?role=Python",
        "/analytics?location=Bangalore",
    ]
    for u in urls:
        resp = client.get(u)
        assert resp.status_code == 200, f"Failed URL {u} with {resp.status_code}"


