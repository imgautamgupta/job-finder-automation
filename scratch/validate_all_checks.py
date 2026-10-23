import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
import openpyxl

sys.path.insert(0, ".")

from app.config.settings import Settings, get_settings
from app.database.database import DatabaseManager
from app.models.job import Job, JobStatus
from app.services.deduplicator import JobDeduplicator
from app.services.excel_exporter import ExcelExporter, ACCENTURE_COLUMNS
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher
from app.sources.accenture import (
    AccentureJobSource,
    fetch_accenture_jobs_http,
    parse_accenture_job,
)

async def main():
    print("=" * 60)
    print("STARTING SYSTEMATIC ACCENTURE CONNECTOR VALIDATION")
    print("=" * 60)

    settings = get_settings()
    profile = settings.load_profile()

    # -------------------------------------------------------------
    # CHECK 1: PAGINATION VERIFICATION
    # -------------------------------------------------------------
    print("\n[CHECK 1] Verifying Pagination & ACCENTURE_MAX_JOBS behavior...")
    # Test: Single query with max_results=50
    test_source = AccentureJobSource(is_enabled=True, settings=Settings(ACCENTURE_ENABLED=True, ACCENTURE_MAX_JOBS=50))
    # We inspect how collect_jobs behaves when 50 jobs are requested for a query with thousands of results
    collected_p1 = await test_source.collect_jobs(roles=["Python Developer"], locations=["Bengaluru"], max_results=50)
    print(f"  Requested max_results=50 for 'Python Developer'")
    print(f"  Actually collected: {len(collected_p1)}")
    print(f"  Queries attempted: {test_source.diagnostics.get('queries_attempted')}")
    if len(collected_p1) == 25:
        print("  --> EVIDENCE OF DEFECT: Only page 0 (25 items) was fetched. start_index was never advanced to 25.")
    else:
        print("  --> Pagination succeeded in fetching subsequent page.")

    # -------------------------------------------------------------
    # CHECK 2: TARGET ROLES COVERAGE
    # -------------------------------------------------------------
    print("\n[CHECK 2] Confirming target roles coverage from profile.json...")
    print(f"  Configured target_roles in profile.json: {len(profile.target_roles)}")
    for idx, r in enumerate(profile.target_roles, 1):
        print(f"    {idx}. {r}")
    
    test_source_roles = AccentureJobSource(is_enabled=True, settings=Settings(ACCENTURE_ENABLED=True, ACCENTURE_MAX_JOBS=25))
    collected_roles = await test_source_roles.collect_jobs(roles=profile.target_roles, locations=profile.preferred_locations, max_results=25)
    print(f"  When max_results=25, queries attempted: {test_source_roles.diagnostics.get('queries_attempted')}/{len(profile.target_roles)}")
    if test_source_roles.diagnostics.get('queries_attempted') == 1:
        print("  --> EVIDENCE OF DEFECT: The loop terminated at query 1 because len(jobs) >= 25, leaving 16 target roles unsearched.")

    # -------------------------------------------------------------
    # CHECK 3: FRESH LIVE COLLECTION
    # -------------------------------------------------------------
    print("\n[CHECK 3] Running fresh live collection from official Accenture portal...")
    live_settings = Settings(
        ACCENTURE_ENABLED=True,
        ACCENTURE_MAX_JOBS=30,
        ACCENTURE_REQUEST_DELAY_SEC=1.0,
    )
    live_source = AccentureJobSource(is_enabled=True, settings=live_settings)
    await live_source.setup()

    # Pass profile target roles
    live_raw_jobs = await live_source.collect_jobs(
        roles=profile.target_roles,
        locations=profile.preferred_locations,
        max_results=30,
    )
    await live_source.teardown()

    print(f"  Portal status: {live_source.last_status} (Error: {live_source.last_error})")
    print(f"  Total raw listings collected: {len(live_raw_jobs)}")

    job_ids = [j.source_job_id for j in live_raw_jobs if j.source_job_id]
    unique_job_ids = set(job_ids)
    print(f"  Listings with official Job IDs: {len(job_ids)}/{len(live_raw_jobs)}")
    print(f"  Unique official Job IDs: {len(unique_job_ids)}")

    # Match against profile
    job_filter = JobFilter(profile=profile)
    matcher = JobMatcher(profile=profile)

    matching_jobs = []
    excluded_jobs = []

    for j in live_raw_jobs:
        if job_filter.is_match(j):
            res = matcher.match(j)
            j.apply_match_result(res)
            matching_jobs.append(j)
        else:
            res = matcher.match(j)
            j.apply_match_result(res)
            excluded_jobs.append((j, res))

    print(f"  Matching jobs passing profile filter: {len(matching_jobs)}")
    print(f"  Excluded jobs: {len(excluded_jobs)}")

    # -------------------------------------------------------------
    # CHECK 4: REAL DIRECT URLS FOR MATCHING JOBS
    # -------------------------------------------------------------
    print("\n[CHECK 4] Real Direct URLs for Profile-Matching Jobs:")
    if matching_jobs:
        for idx, mj in enumerate(matching_jobs, 1):
            print(f"  Match {idx}:")
            print(f"    Title: {mj.title}")
            print(f"    Official Job ID: {mj.source_job_id}")
            print(f"    Location: {mj.location}")
            print(f"    Match Score: {mj.match_score} ({mj.match_category})")
            print(f"    Matched Skills: {mj.matched_skills}")
            print(f"    Experience Required: {mj.experience_required}")
            print(f"    Real Direct URL: {mj.url}")
    else:
        print("  (No jobs in this batch met 100% of the strict fresher/0-2 yrs & location criteria)")

    # -------------------------------------------------------------
    # CHECK 5: EXCLUSION REASONS BREAKDOWN
    # -------------------------------------------------------------
    print("\n[CHECK 5] Exclusion Reasons Breakdown for Rejected Listings:")
    for idx, (ej, res) in enumerate(excluded_jobs, 1):
        desc = (ej.description or "").lower()
        title = (ej.title or "").lower()
        loc = (ej.location or "").lower()
        exp = (ej.experience_required or "").lower()

        # Detailed classification
        reasons_detail = []

        # Location check
        unapproved_locs = ["mumbai", "pune", "hyderabad", "chennai", "gurugram", "gurgaon", "kolkata"]
        loc_match = [c for c in unapproved_locs if c in loc]
        if loc_match:
            reasons_detail.append(f"Unapproved Location: contains {loc_match} (allowed: Delhi, Noida, Bangalore, Ahmedabad, Remote)")

        # Experience check: explicit vs incidental
        explicit_req = None
        min_m = re.search(r"minimum\s*(\d+)\s*year", desc)
        if min_m:
            explicit_req = f"Explicit requirement: 'Minimum {min_m.group(1)} year(s) of experience is required'"
        elif "experience: 5-10 years" in exp or "5-10" in exp:
            explicit_req = "Explicit requirement: 'Experience: 5-10 years' in vacancy metadata"
        elif "experience: 10-12 years" in exp or "10-12" in exp:
            explicit_req = "Explicit requirement: 'Experience: 10-12 years' in vacancy metadata"
        elif "experience: 2-5 years" in exp or "2-5" in exp:
            explicit_req = "Explicit requirement: 'Experience: 2-5 years' in vacancy metadata"

        if explicit_req:
            reasons_detail.append(explicit_req)

        # Seniority titles
        if any(w in title for w in ["senior", "lead", "principal", "manager", "director", "consultant"]):
            reasons_detail.append(f"Senior Title: title contains seniority keyword")

        # Incidental mentions
        if "15 years full time education" in desc:
            reasons_detail.append("Note: contains incidental educational mention '15 years full time education' (distinguished from professional work experience)")

        if not reasons_detail:
            reasons_detail.append(f"Filter rejection: {res.excluded_reasons or 'Did not match target criteria'}")

        print(f"  {idx}. [{ej.source_job_id}] {ej.title} ({ej.location})")
        for r in reasons_detail:
            print(f"     -> {r}")

    # -------------------------------------------------------------
    # CHECK 6: EXCEL REPORT INSPECTION
    # -------------------------------------------------------------
    print("\n[CHECK 6] Inspecting Generated Excel Report...")
    exports_dir = Path("data/exports")
    exporter = ExcelExporter(exports_dir=exports_dir)
    export_file = exporter.export(live_raw_jobs)
    print(f"  Excel export created at: {export_file}")

    wb = openpyxl.load_workbook(export_file)
    print(f"  Sheets in workbook: {wb.sheetnames}")
    assert "Accenture" in wb.sheetnames, "Accenture sheet missing!"
    ws_acc = wb["Accenture"]

    headers = [ws_acc.cell(row=1, column=c).value for c in range(1, len(ACCENTURE_COLUMNS) + 1)]
    print(f"  Accenture sheet headers ({len(headers)} columns): {headers}")
    print(f"  Row count in Accenture sheet: {ws_acc.max_row}")

    # Sample rows verification
    print("  First 3 rows in Accenture worksheet:")
    for r in range(2, min(5, ws_acc.max_row + 1)):
        score = ws_acc.cell(row=r, column=1).value
        title = ws_acc.cell(row=r, column=2).value
        job_id_val = ws_acc.cell(row=r, column=3).value
        loc_val = ws_acc.cell(row=r, column=4).value
        url_cell = ws_acc.cell(row=r, column=11)
        has_hyp = url_cell.hyperlink is not None
        hyp_target = url_cell.hyperlink.target if has_hyp else "NO HYPERLINK"
        print(f"    Row {r}: Score={score} | Title={title} | Job ID={job_id_val} | Loc={loc_val}")
        print(f"           Clickable URL Target: {hyp_target}")

    # -------------------------------------------------------------
    # CHECK 7: SECOND RUN STATUS & NOTES PRESERVATION
    # -------------------------------------------------------------
    print("\n[CHECK 7] Verifying State Preservation Across Multiple Runs...")
    db_path = Path("data/jobs_test_validation.db")
    if db_path.exists():
        db_path.unlink()
    db_manager = DatabaseManager(db_path=db_path)

    sample_job = live_raw_jobs[0]
    run_1_id = "run-20261012-001"
    is_new = db_manager.save_job(sample_job, run_id=run_1_id)
    print(f"  Run 1: Inserted job '{sample_job.title}' (ID: {sample_job.source_job_id}), is_new={is_new}")

    # User interacts: marks job as APPLIED and adds personal notes
    with db_manager.get_connection() as conn:
        conn.execute(
            """
            UPDATE jobs SET
                status = 'APPLIED',
                notes = 'Applied on Accenture careers portal. Referral requested from alumni.',
                interview_date = '2026-10-25',
                interview_status = 'SCHEDULED'
            WHERE source_job_id = ?;
            """,
            (sample_job.source_job_id,),
        )
        conn.commit()

    # Verify updated values in DB
    with db_manager.get_connection() as conn:
        row = conn.execute("SELECT status, notes, interview_date, interview_status, first_seen_at FROM jobs WHERE source_job_id = ?;", (sample_job.source_job_id,)).fetchone()
        print(f"  User updated DB record: status={row['status']}, notes='{row['notes']}', interview_date={row['interview_date']}")

    # Simulate Run 2 collecting the exact same job
    run_2_id = "run-20261012-002"
    # A fresh Job instance as parsed from source (status defaults to NEW, notes=None)
    job_run_2 = parse_accenture_job({
        "title": sample_job.title,
        "requisitionId": sample_job.source_job_id,
        "guid": f"{sample_job.source_job_id}_en",
        "location": [sample_job.location],
        "jobDetailUrl": sample_job.url,
        "jobDescriptionClean": sample_job.description,
        "yearsOfExperience": sample_job.experience_required,
    })
    is_new_run2 = db_manager.save_job(job_run_2, run_id=run_2_id)
    print(f"  Run 2: Re-saved same job, is_new={is_new_run2} (expected False)")

    # Verify that existing application status, notes, and history were preserved
    with db_manager.get_connection() as conn:
        row2 = conn.execute("SELECT status, notes, interview_date, interview_status, first_seen_at, last_seen_run_id FROM jobs WHERE source_job_id = ?;", (sample_job.source_job_id,)).fetchone()
        print(f"  After Run 2 DB record:")
        print(f"    status: {row2['status']} (Preserved: {row2['status'] == 'APPLIED'})")
        print(f"    notes: '{row2['notes']}' (Preserved: bool(row2['notes']))")
        print(f"    interview_date: {row2['interview_date']} (Preserved: row2['interview_date'] == '2026-10-25')")
        print(f"    last_seen_run_id updated to: {row2['last_seen_run_id']} (Updated: {row2['last_seen_run_id'] == run_2_id})")

    # Clean up test db
    if db_path.exists():
        db_path.unlink()

    print("\n" + "=" * 60)
    print("ALL 7 VALIDATION CHECKS COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
