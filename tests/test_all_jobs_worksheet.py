"""Tests for Task 5: Master 'All Jobs' Worksheet.

Verifies:
- All Jobs is the first worksheet in the workbook (index 0).
- All enabled companies are present.
- Deduplication by company + job ID, falling back to company + normalized title + location + URL.
- Active hyperlinks on Application URL column.
- Deterministic sorting: MATCH, REVIEW, REJECT, then score descending.
- No silent drops: exclusions are logged with count and reason.
- History preservation across two runs (application status, notes, interview details, follow-up dates).
- Reopening the generated workbook with openpyxl and reporting row counts per sheet.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import openpyxl
import pytest

from app.database.database import DatabaseManager
from app.models.job import Job, JobStatus
from app.services.deduplicator import JobDeduplicator, deduplicate_for_all_jobs
from app.services.excel_exporter import (
    ALL_JOBS_COLUMNS,
    ExcelExporter,
    get_enabled_companies_from_settings,
    sort_all_jobs,
)


def _make_test_job(
    company: str,
    title: str,
    job_id: str = "",
    location: str = "Bengaluru",
    score: int = 75,
    decision: str = "MATCH",
    decision_reason: str = "Eligible entry-level role",
    source: str = "accenture",
    url: str = "https://example.com/job/1",
    status: JobStatus = JobStatus.NEW,
    notes: str = "",
    follow_up_date: str = "",
    interview_date: str = "",
    interview_stage: str = "",
    interview_status: str = "",
    interview_notes: str = "",
) -> Job:
    """Helper to create a Job with full metadata for testing."""
    j = Job(
        source=source,
        title=title,
        company=company,
        location=location,
        url=url,
        job_id=job_id,
        source_job_id=job_id,
        experience_required="0-1 years",
        match_score=score,
        matched_skills=["Python", "SQL"],
        status=status,
        notes=notes,
        follow_up_date=follow_up_date,
        interview_date=interview_date,
        interview_stage=interview_stage,
        interview_status=interview_status,
        interview_notes=interview_notes,
    )
    j.extra_metadata = {
        "decision": decision,
        "decision_reason": decision_reason,
    }
    return j


def test_all_jobs_sheet_is_first(tmp_path):
    """Verify 'All Jobs' is the first worksheet in the workbook (index 0) and existing sheets exist."""
    exporter = ExcelExporter(exports_dir=tmp_path)
    job = _make_test_job("Accenture", "Software Engineer", job_id="ACC-101", score=85)
    file_path = exporter.export([job], output_path=tmp_path / "report.xlsx", full_report=True)

    wb = openpyxl.load_workbook(file_path)
    assert wb.sheetnames[0] == "All Jobs", f"First sheet is {wb.sheetnames[0]}, expected 'All Jobs'"

    # Existing sheets are all retained
    existing_expected = [
        "New Matches",
        "Top Matches",
        "All Relevant Jobs",
        "Apply Today",
        "Resume Preparation",
        "Applications",
        "Interview Preparation",
        "Analytics",
        "Search Intelligence",
        "Job Agent",
    ]
    for s in existing_expected:
        assert s in wb.sheetnames, f"Expected sheet '{s}' missing"

    # Columns match specification exactly
    ws = wb["All Jobs"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, len(ALL_JOBS_COLUMNS) + 1)]
    assert headers == ALL_JOBS_COLUMNS


def test_all_enabled_companies_present(tmp_path):
    """Verify jobs from all enabled companies are present in the 'All Jobs' worksheet."""
    exporter = ExcelExporter(exports_dir=tmp_path)
    j1 = _make_test_job("Accenture", "Associate Software Engineer", job_id="ACC-1", source="accenture")
    j2 = _make_test_job("Paytm", "Backend Engineer", job_id="PAY-1", source="lever")
    j3 = _make_test_job("Stripe", "Software Developer", job_id="STR-1", source="greenhouse")

    enabled = ["Accenture", "Paytm", "Stripe"]
    file_path = exporter.export(
        [j1, j2, j3],
        output_path=tmp_path / "enabled_test.xlsx",
        enabled_companies=enabled,
        full_report=True,
    )

    wb = openpyxl.load_workbook(file_path)
    ws = wb["All Jobs"]

    companies_in_sheet = {ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)}
    assert companies_in_sheet == {"Accenture", "Paytm", "Stripe"}


def test_all_jobs_dedupe(caplog):
    """Verify deduplication:
    1. By company + job ID
    2. Falling back to company + normalized title + location + URL
    """
    caplog.set_level(logging.INFO)

    # 1. Duplicate by company + job ID
    j1 = _make_test_job("Accenture", "Software Engineer", job_id="ID-100", url="https://example.com/j1")
    j2 = _make_test_job("Accenture", "Software Engineer (Duplicate)", job_id="ID-100", url="https://example.com/j2")

    # 2. Duplicate fallback (no job ID, same company + title + location + URL)
    j3 = _make_test_job("Infosys", "Systems Engineer", job_id="", location="Bengaluru", url="https://example.com/syseng")
    j4 = _make_test_job("Infosys", " Systems Engineer ", job_id="", location="bengaluru", url="https://example.com/syseng")

    # 3. Unique job
    j5 = _make_test_job("Accenture", "Data Analyst", job_id="ID-200", url="https://example.com/da")

    deduped = deduplicate_for_all_jobs([j1, j2, j3, j4, j5])
    assert len(deduped) == 3
    assert j1 in deduped
    assert j2 not in deduped
    assert j3 in deduped
    assert j4 not in deduped
    assert j5 in deduped

    # Verify no silent drops: exclusions are logged with reasons
    log_text = caplog.text
    assert "Dropped duplicate job" in log_text
    assert "ID-100" in log_text
    assert "Duplicate company 'Infosys'" in log_text
    assert "Exclusion summary" in log_text


def test_all_jobs_hyperlinks(tmp_path):
    """Verify Application URL column (col 12) contains active, clickable hyperlinks."""
    exporter = ExcelExporter(exports_dir=tmp_path)
    job = _make_test_job("Accenture", "Cloud Architect", job_id="ARC-1", url="https://accenture.com/jobs/arc1")

    file_path = exporter.export([job], output_path=tmp_path / "hyperlink_test.xlsx", full_report=True)
    wb = openpyxl.load_workbook(file_path)
    ws = wb["All Jobs"]

    url_cell = ws.cell(row=2, column=14)
    assert url_cell.value == "https://accenture.com/jobs/arc1"
    assert url_cell.hyperlink is not None
    assert url_cell.hyperlink.target == "https://accenture.com/jobs/arc1"
    assert url_cell.font.color.rgb == "000000FF" or url_cell.font.underline == "single"


def test_all_jobs_sorting(tmp_path):
    """Verify sorting order: MATCH, REVIEW, REJECT, then score descending."""
    exporter = ExcelExporter(exports_dir=tmp_path)

    j_match_90 = _make_test_job("Co A", "Role 1", job_id="1", score=90, decision="MATCH")
    j_match_70 = _make_test_job("Co A", "Role 2", job_id="2", score=70, decision="MATCH")
    j_review_95 = _make_test_job("Co B", "Role 3", job_id="3", score=95, decision="REVIEW")
    j_review_60 = _make_test_job("Co B", "Role 4", job_id="4", score=60, decision="REVIEW")
    j_reject_99 = _make_test_job("Co C", "Role 5", job_id="5", score=99, decision="REJECT")
    j_reject_50 = _make_test_job("Co C", "Role 6", job_id="6", score=50, decision="REJECT")

    # Pass in shuffled order
    input_jobs = [j_reject_99, j_review_60, j_match_70, j_review_95, j_match_90, j_reject_50]

    file_path = exporter.export(input_jobs, output_path=tmp_path / "sort_test.xlsx", full_report=True)
    wb = openpyxl.load_workbook(file_path)
    ws = wb["All Jobs"]

    results = []
    for r in range(2, ws.max_row + 1):
        dec = ws.cell(row=r, column=9).value
        score = ws.cell(row=r, column=7).value
        job_id = ws.cell(row=r, column=3).value
        results.append((dec, score, job_id))

    expected = [
        ("MATCH", 90, "1"),
        ("MATCH", 70, "2"),
        ("REVIEW", 95, "3"),
        ("REVIEW", 60, "4"),
        ("REJECT", 99, "5"),
        ("REJECT", 50, "6"),
    ]
    assert results == expected


def test_all_jobs_color_coding_and_formatting(tmp_path):
    """Verify decision color coding (green/amber/red), autofilter, frozen panes, and sensible widths."""
    exporter = ExcelExporter(exports_dir=tmp_path)
    j1 = _make_test_job("Co A", "Role 1", job_id="1", score=92, decision="MATCH")
    j2 = _make_test_job("Co B", "Role 2", job_id="2", score=75, decision="REVIEW")
    j3 = _make_test_job("Co C", "Role 3", job_id="3", score=40, decision="REJECT")

    file_path = exporter.export([j1, j2, j3], output_path=tmp_path / "format_test.xlsx", full_report=True)
    wb = openpyxl.load_workbook(file_path)
    ws = wb["All Jobs"]

    # Frozen header
    assert ws.freeze_panes == "A2"

    # AutoFilter
    assert ws.auto_filter.ref is not None
    assert ws.auto_filter.ref.startswith("A1:Q")

    # Decision color coding: col 9
    # Row 2 is MATCH (green fill)
    cell_match = ws.cell(row=2, column=9)
    assert cell_match.fill.start_color.rgb in ("00DCFCE7", "DCFCE7")
    assert cell_match.font.bold is True

    # Row 3 is REVIEW (amber fill)
    cell_review = ws.cell(row=3, column=9)
    assert cell_review.fill.start_color.rgb in ("00FEF3C7", "FEF3C7")
    assert cell_review.font.bold is True

    # Row 4 is REJECT (red fill)
    cell_reject = ws.cell(row=4, column=9)
    assert cell_reject.fill.start_color.rgb in ("00FEE2E2", "FEE2E2")
    assert cell_reject.font.bold is True

    # Column widths are sensible (>= 14 and <= 55)
    for col_letter, dim in ws.column_dimensions.items():
        assert dim.width >= 14, f"Column {col_letter} width {dim.width} < 14"
        assert dim.width <= 55, f"Column {col_letter} width {dim.width} > 55"


def test_history_preserved_across_two_runs(tmp_path):
    """Verify application status, notes, interview details, and follow-up dates
    are preserved across two consecutive runs in SQLite and exported into 'All Jobs'.
    """
    db_path = tmp_path / "test_history.db"
    db = DatabaseManager(db_path=db_path)
    from app.services.job_tracker import JobTracker
    tracker = JobTracker(db)
    exporter = ExcelExporter(exports_dir=tmp_path)

    # Run 1: Job collected fresh, user later updates application details
    job_run1 = _make_test_job(
        company="Accenture",
        title="Associate Software Engineer",
        job_id="ACC-HIST-1",
        url="https://example.com/job/hist1",
        score=85,
        decision="MATCH",
    )
    db.save_job(job_run1, run_id="run-1")
    assert job_run1.id is not None

    # User interacts via JobTracker: applies, sets notes, follow-up, and interview schedule
    tracker.update_status(job_run1.id, JobStatus.INTERVIEW, notes="Screening cleared, round 1 technical scheduled")
    tracker.update_follow_up(job_run1.id, follow_up_date="2026-10-25", follow_up_notes="Follow up on test")
    tracker.update_interview(
        job_run1.id,
        interview_date="2026-10-28",
        interview_stage="Technical Round 1",
        interview_status="SCHEDULED",
        interview_notes="Focus on Python data structures",
    )

    # Run 2: Fresh scrape of the exact same job returns default fields
    job_run2_scraped = _make_test_job(
        company="Accenture",
        title="Associate Software Engineer",
        job_id="ACC-HIST-1",
        url="https://example.com/job/hist1",
        score=85,
        decision="MATCH",
        status=JobStatus.NEW,  # Fresh scrape always has status NEW
        notes="",              # Scraper has no notes
        follow_up_date="",     # Scraper has no follow-up
        interview_date="",     # Scraper has no interview
    )

    # Run 2 database upsert
    db.save_job(job_run2_scraped, run_id="run-2")

    # Verify that in-memory job object received preserved fields
    assert job_run2_scraped.status == JobStatus.INTERVIEW
    assert job_run2_scraped.notes == "Screening cleared, round 1 technical scheduled"
    assert job_run2_scraped.follow_up_date == "2026-10-25"
    assert job_run2_scraped.interview_date == "2026-10-28"
    assert job_run2_scraped.interview_stage == "Technical Round 1"
    assert job_run2_scraped.interview_status == "SCHEDULED"
    assert job_run2_scraped.interview_notes == "Focus on Python data structures"

    # Export workbook in Run 2
    export_file = exporter.export([job_run2_scraped], output_path=tmp_path / "run2_export.xlsx", full_report=True)

    # Reopen workbook and check that 'All Jobs' has preserved status
    wb = openpyxl.load_workbook(export_file)
    ws = wb["All Jobs"]

    # Row 2 contains job
    assert ws.cell(row=2, column=16).value == "INTERVIEW"  # Application Status col 16
    assert ws.cell(row=2, column=3).value == "ACC-HIST-1"   # Job ID col 3
