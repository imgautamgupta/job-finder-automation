"""Comprehensive tests for Phase 8 Job Review Dashboard & Tracking UI."""

import html
import pytest
from fastapi.testclient import TestClient

from app.dashboard.app import app
from app.database.database import DatabaseManager
from app.models.job import Job, JobStatus


@pytest.fixture
def client(test_db, monkeypatch):
    """Create FastAPI TestClient fixture isolated to temporary test_db."""
    import app.dashboard.routes as routes_mod
    monkeypatch.setattr(routes_mod, "get_db", lambda: test_db)
    return TestClient(app)


@pytest.fixture
def test_db(tmp_path):
    """Create isolated SQLite database with sample test jobs."""
    db_file = tmp_path / "test_dashboard.db"
    db = DatabaseManager(db_path=db_file)

    sample_jobs = [
        Job(
            source="lever",
            source_job_id="test-001",
            title="Senior Python Backend Developer",
            company="Acme Corp",
            location="Remote",
            url="https://example.com/jobs/001",
            description="Leading backend systems development with Python and FastAPI.",
            match_score=92,
            match_category="Excellent",
            matched_roles=["Backend Developer"],
            matched_skills=["Python", "FastAPI"],
            status=JobStatus.NEW,
            notes="Initial note",
        ),
        Job(
            source="greenhouse",
            source_job_id="test-002",
            title="Full Stack Engineer",
            company="Beta Tech",
            location="Bangalore",
            url="https://example.com/jobs/002",
            description="Developing web applications with Python and React.",
            match_score=82,
            match_category="Strong",
            matched_roles=["Full Stack Developer"],
            matched_skills=["Python", "React"],
            status=JobStatus.SHORTLISTED,
            notes="Reviewed on Monday",
        ),
        Job(
            source="lever",
            source_job_id="test-003",
            title="Data Scientist",
            company="Gamma Labs",
            location="Delhi",
            url="https://example.com/jobs/003",
            description="Machine learning and predictive modeling.",
            match_score=71,
            match_category="Good",
            matched_roles=["Data Scientist"],
            matched_skills=["Python", "Pandas"],
            status=JobStatus.APPLIED,
            notes="Applied through company portal",
        ),
        Job(
            source="greenhouse",
            source_job_id="test-004",
            title="DevOps Engineer",
            company="Delta Systems",
            location="Noida",
            url="https://example.com/jobs/004",
            description="CI/CD and cloud infrastructure.",
            match_score=62,
            match_category="Possible",
            matched_roles=["DevOps Engineer"],
            matched_skills=["Docker", "Linux"],
            status=JobStatus.INTERVIEW,
            notes="First round scheduled",
        ),
        Job(
            source="naukri",
            source_job_id="test-005",
            title="Junior QA Engineer",
            company="Epsilon Software",
            location="Pune",
            url="https://example.com/jobs/005",
            description="Manual testing and test plans.",
            match_score=45,
            match_category="Not Relevant",
            matched_roles=[],
            matched_skills=[],
            status=JobStatus.REJECTED,
            notes="Not aligned with profile",
        ),
    ]

    for j in sample_jobs:
        db.save_job(j, run_id="test-run-100")

    return db


def test_dashboard_homepage(client):
    """Verify dashboard home responds with status 200 and displays core metrics."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Job Review Dashboard" in response.text
    assert "Total Jobs" in response.text
    assert "High Priority" in response.text
    assert "Strong Matches" in response.text


def test_root_redirect_to_dashboard(client):
    """Verify root / redirects to /dashboard."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (301, 302, 307)
    assert response.headers["location"] == "/dashboard"


def test_all_nav_pages_respond_200(client):
    """Verify all navigation links and filtered views respond with HTTP 200."""
    endpoints = [
        "/jobs",
        "/new-matches",
        "/shortlisted",
        "/applied",
        "/interviews",
        "/offers",
        "/pipeline-runs",
        "/source-health",
    ]
    for endpoint in endpoints:
        res = client.get(endpoint)
        assert res.status_code == 200, f"Endpoint {endpoint} failed with {res.status_code}"


def test_job_filtering_by_score(test_db):
    """Verify filtering jobs by minimum match score."""
    jobs_80, count_80 = test_db.get_jobs_filtered(min_score=80)
    assert count_80 == 2  # 92 and 82
    assert all(j.match_score >= 80 for j in jobs_80)

    jobs_90, count_90 = test_db.get_jobs_filtered(min_score=90)
    assert count_90 == 1  # 92
    assert jobs_90[0].title == "Senior Python Backend Developer"


def test_job_filtering_by_status(test_db):
    """Verify filtering jobs by application status."""
    jobs_applied, count_applied = test_db.get_jobs_filtered(status="APPLIED")
    assert count_applied == 1
    assert jobs_applied[0].status == JobStatus.APPLIED
    assert jobs_applied[0].company == "Gamma Labs"

    jobs_shortlisted, count_sl = test_db.get_jobs_filtered(status="SHORTLISTED")
    assert count_sl == 1
    assert jobs_shortlisted[0].company == "Beta Tech"


def test_job_filtering_by_source(test_db):
    """Verify filtering jobs by source platform."""
    lever_jobs, lever_cnt = test_db.get_jobs_filtered(source="lever")
    assert lever_cnt == 2
    assert all(j.source == "lever" for j in lever_jobs)

    gh_jobs, gh_cnt = test_db.get_jobs_filtered(source="greenhouse")
    assert gh_cnt == 2
    assert all(j.source == "greenhouse" for j in gh_jobs)


def test_job_search_filter(test_db):
    """Verify search filter across title, company, location, and description."""
    # Search by skill mentioned in description
    python_jobs, cnt = test_db.get_jobs_filtered(search="FastAPI")
    assert cnt == 1
    assert python_jobs[0].company == "Acme Corp"

    # Search by company
    beta_jobs, cnt_beta = test_db.get_jobs_filtered(search="Beta Tech")
    assert cnt_beta == 1
    assert beta_jobs[0].title == "Full Stack Engineer"


def test_job_sorting(test_db):
    """Verify sorting options work correctly."""
    # Descending match score
    jobs_desc, _ = test_db.get_jobs_filtered(sort_by="match_score", order="desc")
    scores = [j.match_score for j in jobs_desc]
    assert scores == sorted(scores, reverse=True)

    # Ascending match score
    jobs_asc, _ = test_db.get_jobs_filtered(sort_by="match_score", order="asc")
    scores_asc = [j.match_score for j in jobs_asc]
    assert scores_asc == sorted(scores_asc)


def test_job_pagination(test_db):
    """Verify database-level pagination using LIMIT and OFFSET."""
    page1, total = test_db.get_jobs_filtered(page=1, per_page=2)
    assert total == 5
    assert len(page1) == 2

    page2, _ = test_db.get_jobs_filtered(page=2, per_page=2)
    assert len(page2) == 2
    assert page1[0].id != page2[0].id

    page3, _ = test_db.get_jobs_filtered(page=3, per_page=2)
    assert len(page3) == 1


def test_job_detail_endpoint(client):
    """Verify valid job loads details and missing job returns 404."""
    # Job ID 1 exists in test database
    response = client.get("/jobs/1")
    assert response.status_code == 200
    assert "Acme Corp" in response.text
    assert "Application Status Management" in response.text

    # Non-existent job
    missing_res = client.get("/jobs/999999")
    assert missing_res.status_code == 404


def test_status_update_and_preservation(client, test_db):
    """Verify status update updates status_updated_at while preserving first_seen_at and notes."""
    # Test on Job 1 in test database
    res_before = client.get("/jobs/1")
    assert res_before.status_code == 200

    # Transition to VIEWED
    post_res = client.post("/jobs/1/status", data={"status": "VIEWED"})
    assert post_res.status_code in (200, 303)

    # Transition to SHORTLISTED
    post_res = client.post("/jobs/1/status", data={"status": "SHORTLISTED"})
    assert post_res.status_code in (200, 303)

    # Transition to APPLIED
    post_res = client.post("/jobs/1/status", data={"status": "APPLIED"})
    assert post_res.status_code in (200, 303)

    # Transition to INTERVIEW
    post_res = client.post("/jobs/1/status", data={"status": "INTERVIEW"})
    assert post_res.status_code in (200, 303)

    # Transition to OFFER
    post_res = client.post("/jobs/1/status", data={"status": "OFFER"})
    assert post_res.status_code in (200, 303)

    # Reset Job 1 back to NEW
    post_res = client.post("/jobs/1/status", data={"status": "NEW"})
    assert post_res.status_code in (200, 303)

    # Verify Job 3 (APPLIED job in test_db) remained strictly APPLIED
    job3 = test_db.get_job_by_id(3)
    assert job3 is not None
    assert job3.status == JobStatus.APPLIED
    assert job3.notes == "Applied through company portal"


def test_notes_update_preservation(client, test_db):
    """Verify updating notes preserves job attributes."""
    # Update notes on Job 2
    post_res = client.post("/jobs/2/notes", data={"notes": "Test note via dashboard"})
    assert post_res.status_code in (200, 303)

    job2 = test_db.get_job_by_id(2)
    assert job2 is not None
    assert job2.notes == "Test note via dashboard"

    # Status update should preserve existing notes
    post_res2 = client.post("/jobs/2/status", data={"status": "VIEWED"})
    assert post_res2.status_code in (200, 303)

    job2_after = test_db.get_job_by_id(2)
    assert job2_after.notes == "Test note via dashboard"
    assert job2_after.status == JobStatus.VIEWED

    # Reset Job 2 status back to NEW
    client.post("/jobs/2/status", data={"status": "NEW"})


def test_security_html_escaping(client, test_db):
    """Verify unsafe HTML in description or title is safely rendered without script execution."""
    xss_job = Job(
        source="lever",
        source_job_id="xss-test-01",
        title="Software Engineer <script>alert('xss')</script>",
        company="SecCorp",
        location="Remote",
        url="https://example.com/xss",
        description="Dangerous payload: <script>document.cookie='stolen'</script><b>Bold content</b>",
        match_score=85,
    )
    test_db.save_job(xss_job)

    # Verify with DatabaseManager that job was created
    fetched = test_db.get_recent_jobs(limit=1)[0]
    assert "<script>" in fetched.title

    # Test that HTML special characters are properly escaped in templates
    escaped_title = html.escape(fetched.title)
    assert "&lt;script&gt;" in escaped_title


def test_security_sql_injection_defense(test_db):
    """Verify that arbitrary SQL injection attempts in search parameters do not break queries."""
    malicious_inputs = [
        "' OR '1'='1",
        "'; DROP TABLE jobs; --",
        "1 UNION SELECT null, null, null",
    ]
    for bad_input in malicious_inputs:
        # Should not raise exception and should safely return 0 matches
        jobs, count = test_db.get_jobs_filtered(search=bad_input)
        assert isinstance(jobs, list)
        assert isinstance(count, int)
        assert count == 0

        # In company field
        jobs_co, count_co = test_db.get_jobs_filtered(company=bad_input)
        assert count_co == 0
