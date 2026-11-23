"""Tests for Task 12: Simple Workbook (My Jobs single-sheet output, tracking sync, full report flag)."""

import os
from datetime import datetime
from pathlib import Path
import openpyxl
import pytest

from app.database.database import DatabaseManager
from app.models.job import Job, JobStatus
from app.services.excel_exporter import ExcelExporter, sync_excel_tracking_to_db


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_jobs.db"
    return DatabaseManager(db_path=str(db_file))


@pytest.fixture
def sample_jobs():
    j1 = Job(
        source="test",
        title="Frontend Engineer",
        company="TechCorp",
        location="Bengaluru, India",
        url="https://techcorp.com/job1",
        source_job_id="TC-101",
        description="React and TypeScript",
        experience_required="2+ years",
        posted_date="2026-10-10",
        decision="MATCH",
        match_score=92,
        decision_reason="Strong tech stack match; 2 yrs exp",
        run_id="run-1",
        date_found="2026-10-20",
    )
    j2 = Job(
        source="test",
        title="Fullstack Developer",
        company="StartupX",
        location="Bengaluru, India",
        url="https://startupx.com/job2",
        source_job_id="SX-202",
        description="Python and React",
        experience_required="Not Specified",
        posted_date="2026-10-12",
        decision="REVIEW",
        match_score=85,
        decision_reason="experience not stated",
        run_id="run-1",
        date_found="2026-10-20",
    )
    j3 = Job(
        source="test",
        title="Staff Architect",
        company="BigCo",
        location="Bengaluru, India",
        url="https://bigco.com/job3",
        source_job_id="BC-303",
        description="System design 15+ years",
        experience_required="15+ years",
        posted_date="2026-10-15",
        decision="REJECT",
        match_score=40,
        decision_reason="requires 15+ years (max 4)",
        run_id="run-1",
        date_found="2026-10-20",
    )
    j4 = Job(
        source="test",
        title="Junior Developer",
        company="AlphaCorp",
        location="Bengaluru, India",
        url="https://alphacorp.com/job4",
        source_job_id="AC-404",
        description="Entry level role",
        experience_required="0-1 years",
        posted_date="2026-10-18",
        decision="MATCH",
        match_score=78,
        decision_reason="Entry level title",
        run_id="run-1",
        date_found="2026-10-20",
    )
    return [j1, j2, j3, j4]


def test_single_sheet_default_and_filtering(tmp_path, temp_db, sample_jobs):
    """Default export must produce only one worksheet 'My Jobs' containing only MATCH and REVIEW."""
    exporter = ExcelExporter()
    out_file = tmp_path / "My_Jobs_test.xlsx"
    exporter.export(sample_jobs, output_path=out_file, db_manager=temp_db)

    wb = openpyxl.load_workbook(out_file)
    assert wb.sheetnames == ["My Jobs"], f"Expected only ['My Jobs'], got {wb.sheetnames}"

    ws = wb["My Jobs"]
    # Header is row 1
    # sample_jobs has 2 MATCH (TC-101, AC-404) and 1 REVIEW (SX-202), BC-303 is REJECT
    # Total data rows should be 3 (rows 2, 3, 4)
    rows = list(ws.iter_rows(values_only=True))
    assert len(rows) == 4  # 1 header + 3 jobs

    header = rows[0]
    expected_header = (
        "Decision", "New?", "Company", "Job Title", "Location", "Country", "Experience",
        "Why", "Apply Link", "Posted", "Job ID", "Date Found",
        "Application Status", "Follow-up Date", "Notes"
    )
    assert header == expected_header

    # Verify REJECT is not included
    job_ids = [r[10] for r in rows[1:]]
    assert "BC-303" not in job_ids
    assert "TC-101" in job_ids
    assert "SX-202" in job_ids
    assert "AC-404" in job_ids


def test_my_jobs_ordering(tmp_path, temp_db, sample_jobs):
    """Order must be: MATCH first (by score desc, newest first), then REVIEW."""
    exporter = ExcelExporter()
    out_file = tmp_path / "My_Jobs_order.xlsx"
    exporter.export(sample_jobs, output_path=out_file, db_manager=temp_db)

    wb = openpyxl.load_workbook(out_file)
    ws = wb["My Jobs"]
    rows = list(ws.iter_rows(values_only=True))[1:]

    # Row 1: TC-101 (MATCH, score 92)
    # Row 2: AC-404 (MATCH, score 78)
    # Row 3: SX-202 (REVIEW, score 85)
    assert rows[0][0] == "MATCH"
    assert rows[0][10] == "TC-101"

    assert rows[1][0] == "MATCH"
    assert rows[1][10] == "AC-404"

    assert rows[2][0] == "REVIEW"
    assert rows[2][10] == "SX-202"


def test_hyperlinks_and_formatting(tmp_path, temp_db, sample_jobs):
    """Apply Link must have text 'Apply' and a clickable hyperlink. Green/amber fills, freeze panes, wrap text."""
    exporter = ExcelExporter()
    out_file = tmp_path / "My_Jobs_format.xlsx"
    exporter.export(sample_jobs, output_path=out_file, db_manager=temp_db)

    wb = openpyxl.load_workbook(out_file)
    ws = wb["My Jobs"]

    # Check freeze panes (D2 freezes row 1 and columns A, B, C)
    assert ws.freeze_panes == "D2"

    # Check row 2 (TC-101, MATCH)
    # Col 1: Decision = MATCH -> green fill (C6EFCE)
    cell_a2 = ws["A2"]
    assert cell_a2.value == "MATCH"
    assert cell_a2.fill.start_color.rgb in ("00D1FAE5", "D1FAE5", "00C6EFCE", "C6EFCE")

    # Col 9: Apply Link -> text "Apply", hyperlink target
    cell_i2 = ws["I2"]
    assert cell_i2.value == "Apply"
    assert cell_i2.hyperlink is not None
    assert cell_i2.hyperlink.target == "https://techcorp.com/job1"

    # Col 8 (Why) and Col 15 (Notes) have wrap_text = True
    assert ws["H2"].alignment.wrap_text is True
    assert ws["O2"].alignment.wrap_text is True

    # Check row 4 (SX-202, REVIEW) -> amber fill (FEF3C7 or FFEB9C)
    cell_a4 = ws["A4"]
    assert cell_a4.value == "REVIEW"
    assert cell_a4.fill.start_color.rgb in ("00FEF3C7", "FEF3C7", "00FFEB9C", "FFEB9C")


def test_data_validation_dropdown(tmp_path, temp_db, sample_jobs):
    """Application Status column must have a dropdown validation."""
    exporter = ExcelExporter()
    out_file = tmp_path / "My_Jobs_dv.xlsx"
    exporter.export(sample_jobs, output_path=out_file, db_manager=temp_db)

    wb = openpyxl.load_workbook(out_file)
    ws = wb["My Jobs"]

    validations = ws.data_validations.dataValidation
    assert len(validations) >= 1
    dv = validations[0]
    assert dv.type == "list"
    assert "Not applied" in dv.formula1
    assert "Applied" in dv.formula1
    assert "Interview" in dv.formula1
    assert "Offer" in dv.formula1
    assert "Rejected" in dv.formula1
    assert "Skipped" in dv.formula1


def test_new_flag(tmp_path, temp_db, sample_jobs):
    """Jobs first seen in current run get 'NEW', otherwise blank."""
    exporter = ExcelExporter()
    out_file = tmp_path / "My_Jobs_new.xlsx"
    # Provide current_run_id = 'run-1'. All sample_jobs have run_id='run-1'
    exporter.export(sample_jobs, output_path=out_file, db_manager=temp_db, current_run_id="run-1")

    wb = openpyxl.load_workbook(out_file)
    ws = wb["My Jobs"]
    rows = list(ws.iter_rows(values_only=True))[1:]
    for r in rows:
        assert r[1] == "NEW"  # Col 2 is New?

    # Now run for run-2 where only AC-404 is run-2
    sample_jobs[0].run_id = "run-1"
    sample_jobs[1].run_id = "run-1"
    sample_jobs[3].run_id = "run-2"
    exporter.export(sample_jobs, output_path=out_file, db_manager=temp_db, current_run_id="run-2")

    wb2 = openpyxl.load_workbook(out_file)
    ws2 = wb2["My Jobs"]
    rows2 = list(ws2.iter_rows(values_only=True))[1:]
    # rows2[0] is TC-101 (run-1) -> "" or None
    # rows2[1] is AC-404 (run-2) -> "NEW"
    # rows2[2] is SX-202 (run-1) -> "" or None
    assert not rows2[0][1]
    assert rows2[1][1] == "NEW"
    assert not rows2[2][1]


def test_empty_results_message(tmp_path, temp_db):
    """If there are 0 MATCH/REVIEW jobs, write sheet with one row 'No matching jobs this run'."""
    exporter = ExcelExporter()
    out_file = tmp_path / "My_Jobs_empty.xlsx"
    exporter.export([], output_path=out_file, db_manager=temp_db)

    wb = openpyxl.load_workbook(out_file)
    assert wb.sheetnames == ["My Jobs"]
    ws = wb["My Jobs"]
    rows = list(ws.iter_rows(values_only=True))
    assert len(rows) == 2
    assert rows[1][0] == "No matching jobs this run"


def test_tracking_sync_from_excel_to_db(tmp_path, temp_db, sample_jobs):
    """Edits typed into Excel (Status, Follow-up, Notes) are read back at run start and saved to DB."""
    # 1. Save jobs to DB
    for j in sample_jobs:
        temp_db.save_job(j, run_id="run-1")

    exporter = ExcelExporter()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    excel_path = export_dir / "My_Jobs_20261020_120000.xlsx"
    exporter.export(sample_jobs, output_path=excel_path, db_manager=temp_db)

    # 2. Simulate user typing into Excel:
    # Update TC-101: Status -> "Applied", Follow-up -> "2026-10-27", Notes -> "Referral submitted"
    wb = openpyxl.load_workbook(excel_path)
    ws = wb["My Jobs"]
    # Find TC-101 row
    tc_row = None
    for row_idx in range(2, ws.max_row + 1):
        if ws.cell(row=row_idx, column=11).value == "TC-101":
            tc_row = row_idx
            break
    assert tc_row is not None

    ws.cell(row=tc_row, column=13, value="Applied")
    ws.cell(row=tc_row, column=14, value="2026-10-27")
    ws.cell(row=tc_row, column=15, value="Referral submitted")
    wb.save(excel_path)

    # 3. Call sync_excel_tracking_to_db
    updated_count = sync_excel_tracking_to_db(temp_db, export_dir)
    assert updated_count == 1

    # Verify DB state
    db_job = temp_db.get_job_by_source_id("TC-101")
    assert db_job is not None
    assert db_job.status == JobStatus.APPLIED
    assert db_job.follow_up_date == "2026-10-27"
    assert db_job.notes == "Referral submitted"


def test_applied_job_stays_in_my_jobs_even_if_not_matching(tmp_path, temp_db, sample_jobs):
    """A job that is no longer MATCH/REVIEW but has status != 'Not applied' must still appear in My Jobs."""
    for j in sample_jobs:
        temp_db.save_job(j, run_id="run-1")

    # Mark BC-303 (Staff Architect, REJECT) as APPLIED in DB
    temp_db.update_job_tracking(
        company="BigCo",
        source_job_id="BC-303",
        status=JobStatus.APPLIED,
        notes="Applied directly via company portal",
    )

    exporter = ExcelExporter()
    out_file = tmp_path / "My_Jobs_tracked.xlsx"
    # Export current run jobs (sample_jobs, where BC-303 has decision REJECT)
    exporter.export(sample_jobs, output_path=out_file, db_manager=temp_db)

    wb = openpyxl.load_workbook(out_file)
    ws = wb["My Jobs"]
    rows = list(ws.iter_rows(values_only=True))[1:]
    job_ids = [r[10] for r in rows]

    # BC-303 must appear because it is tracked (APPLIED)
    assert "BC-303" in job_ids
    # Find BC-303 row
    bc_row = next(r for r in rows if r[10] == "BC-303")
    assert bc_row[12] == "Applied"
    assert bc_row[14] == "Applied directly via company portal"


def test_full_report_produces_all_old_sheets(tmp_path, temp_db, sample_jobs):
    """When full_report=True, legacy multi-sheet report is generated."""
    exporter = ExcelExporter()
    out_file = tmp_path / "jobs_full_test.xlsx"
    exporter.export(sample_jobs, output_path=out_file, db_manager=temp_db, full_report=True)

    wb = openpyxl.load_workbook(out_file)
    # Check that legacy sheets exist
    assert "All Jobs" in wb.sheetnames
    assert "Top Matches" in wb.sheetnames
    assert "Analytics" in wb.sheetnames
    assert "Search Intelligence" in wb.sheetnames
    assert "Job Agent" in wb.sheetnames
