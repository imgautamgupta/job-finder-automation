"""Detailed verification of data preservation between pre-run backup and current state."""

from pathlib import Path
import sqlite3
import openpyxl

root = Path(__file__).resolve().parent.parent
db_path = root / "data" / "jobs.db"
bak_db_path = root / "data" / "backups" / "jobs_backup_pre_phase2_2.db"
excel_path = root / "data" / "exports" / "My_Jobs_latest.xlsx"
bak_excel_path = root / "data" / "exports" / "My_Jobs_latest_backup_pre_phase2_2.xlsx"

conn_cur = sqlite3.connect(db_path)
conn_cur.row_factory = sqlite3.Row
cur_c = conn_cur.cursor()

conn_bak = sqlite3.connect(bak_db_path)
conn_bak.row_factory = sqlite3.Row
cur_b = conn_bak.cursor()

# 1. Compare all jobs in backup to current DB
cur_b.execute("SELECT id, source_job_id, fingerprint, company, title, status, notes, applied_at, interview_stage, interview_notes FROM jobs")
bak_jobs = {row["fingerprint"]: dict(row) for row in cur_b.fetchall()}

cur_c.execute("SELECT id, source_job_id, fingerprint, company, title, status, notes, applied_at, interview_stage, interview_notes FROM jobs")
cur_jobs = {row["fingerprint"]: dict(row) for row in cur_c.fetchall()}

print("=" * 80)
print("DATA PRESERVATION VERIFICATION")
print("=" * 80)

# Check all backup jobs exist in current DB
missing_jobs = []
tracking_altered = []

for fp, b_job in bak_jobs.items():
    if fp not in cur_jobs:
        missing_jobs.append(b_job)
    else:
        c_job = cur_jobs[fp]
        # Compare tracking fields
        if b_job["status"] != c_job["status"]:
            tracking_altered.append({"fp": fp, "field": "status", "bak": b_job["status"], "cur": c_job["status"]})
        if b_job["notes"] != c_job["notes"]:
            tracking_altered.append({"fp": fp, "field": "notes", "bak": b_job["notes"], "cur": c_job["notes"]})
        if b_job["applied_at"] != c_job["applied_at"]:
            tracking_altered.append({"fp": fp, "field": "applied_at", "bak": b_job["applied_at"], "cur": c_job["applied_at"]})
        if b_job["interview_stage"] != c_job["interview_stage"]:
            tracking_altered.append({"fp": fp, "field": "interview_stage", "bak": b_job["interview_stage"], "cur": c_job["interview_stage"]})

print(f"Total jobs in backup DB: {len(bak_jobs)}")
print(f"Total jobs in current DB: {len(cur_jobs)}")
print(f"Pre-existing jobs missing from current DB: {len(missing_jobs)}")
print(f"Pre-existing jobs with modified tracking fields: {len(tracking_altered)}")

# Status breakdown comparison
cur_b.execute("SELECT status, count(*) FROM jobs GROUP BY status")
print(f"\nBackup DB status breakdown: {dict(cur_b.fetchall())}")

cur_c.execute("SELECT status, count(*) FROM jobs GROUP BY status")
print(f"Current DB status breakdown: {dict(cur_c.fetchall())}")

# User notes comparison
cur_b.execute("SELECT count(*) FROM jobs WHERE notes IS NOT NULL AND notes != ''")
print(f"Backup DB records with user notes: {cur_b.fetchone()[0]}")
cur_c.execute("SELECT count(*) FROM jobs WHERE notes IS NOT NULL AND notes != ''")
print(f"Current DB records with user notes: {cur_c.fetchone()[0]}")

# 2. Excel comparison
wb_bak = openpyxl.load_workbook(bak_excel_path)
wb_cur = openpyxl.load_workbook(excel_path)

print(f"\nExcel Comparison:")
print(f"  Backup Excel sheets: {wb_bak.sheetnames}")
print(f"  Current Excel sheets: {wb_cur.sheetnames}")

all_bak_ws = wb_bak["All Jobs"]
all_cur_ws = wb_cur["All Jobs"]
print(f"  Backup 'All Jobs' rows: {all_bak_ws.max_row - 1}")
print(f"  Current 'All Jobs' rows: {all_cur_ws.max_row - 1}")

top_bak_ws = wb_bak["Top Matches"]
top_cur_ws = wb_cur["Top Matches"]
print(f"  Backup 'Top Matches' rows: {top_bak_ws.max_row - 1}")
print(f"  Current 'Top Matches' rows: {top_cur_ws.max_row - 1}")

