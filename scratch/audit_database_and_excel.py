"""Phase 2.3 — Audit Script for Database, Excel, Links, and Backups."""

import json
import os
from pathlib import Path
import re
import sqlite3
import openpyxl
import httpx

root = Path(__file__).resolve().parent.parent
db_path = root / "data" / "jobs.db"
bak_path = root / "data" / "backups" / "jobs_backup_pre_phase2_2.db"
excel_path = root / "data" / "exports" / "My_Jobs_latest.xlsx"
bak_excel_path = root / "data" / "exports" / "My_Jobs_latest_backup_pre_phase2_2.xlsx"

print("=" * 80)
print("1. SQLITE DATABASE RECONCILIATION AUDIT")
print("=" * 80)

# Connect to current DB
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1.1 Tables in current DB
tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables in current DB: {tables}")
for t in tables:
    count = cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    print(f"  Table '{t}' row count: {count}")

# 1.2 Tables in backup DB
conn_bak = sqlite3.connect(bak_path)
conn_bak.row_factory = sqlite3.Row
cur_bak = conn_bak.cursor()

tables_bak = [row[0] for row in cur_bak.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"\nTables in backup DB: {tables_bak}")
for t in tables_bak:
    count = cur_bak.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    print(f"  Backup table '{t}' row count: {count}")

# 1.3 Row count and unique job IDs in current DB
cur.execute("SELECT count(*) FROM jobs")
total_current_jobs = cur.fetchone()[0]

cur.execute("SELECT count(DISTINCT id) FROM jobs")
distinct_pk_ids = cur.fetchone()[0]

cur.execute("SELECT count(DISTINCT job_id) FROM jobs")
distinct_job_ids = cur.fetchone()[0]

cur.execute("SELECT count(DISTINCT fingerprint) FROM jobs")
distinct_fingerprints = cur.fetchone()[0]

print(f"\nCurrent 'jobs' table metrics:")
print(f"  Total rows: {total_current_jobs}")
print(f"  Distinct primary key (id): {distinct_pk_ids}")
print(f"  Distinct job_id: {distinct_job_ids}")
print(f"  Distinct fingerprint: {distinct_fingerprints}")

# Check status distribution
cur.execute("SELECT status, count(*) FROM jobs GROUP BY status")
status_dist = dict(cur.fetchall())
print(f"  Status distribution in current DB: {status_dist}")

# In backup DB
cur_bak.execute("SELECT count(*) FROM jobs")
total_bak_jobs = cur_bak.fetchone()[0]
cur_bak.execute("SELECT count(DISTINCT job_id) FROM jobs")
distinct_bak_job_ids = cur_bak.fetchone()[0]
cur_bak.execute("SELECT status, count(*) FROM jobs GROUP BY status")
bak_status_dist = dict(cur_bak.fetchall())
print(f"\nBackup 'jobs' table metrics:")
print(f"  Total rows: {total_bak_jobs}")
print(f"  Distinct job_id: {distinct_bak_job_ids}")
print(f"  Status distribution in backup DB: {bak_status_dist}")

# 1.4 Reconcile the discrepancy:
# Where did 4,948 -> 6,349 come from?
# Difference = 6,349 - 4,948 = 1,401 jobs.
# Let's inspect pipeline_runs or created_at in jobs table!
cur.execute("SELECT last_seen_run_id, count(*) FROM jobs GROUP BY last_seen_run_id")
run_id_dist = cur.fetchall()
print(f"\nBreakdown by last_seen_run_id:")
for r in run_id_dist:
    print(f"  Run ID '{r[0]}': {r[1]} jobs")

# Find jobs that were added between backup and current
cur_bak.execute("SELECT id, job_id, fingerprint FROM jobs")
bak_fingerprints = set(row["fingerprint"] for row in cur_bak.fetchall() if row["fingerprint"])
bak_ids = set(row["id"] for row in cur_bak.fetchall())

cur.execute("SELECT id, job_id, fingerprint, company, created_at, last_seen_run_id FROM jobs")
new_jobs = []
for row in cur.fetchall():
    if row["fingerprint"] not in bak_fingerprints:
        new_jobs.append(dict(row))

print(f"\nTotal new jobs in current DB not in backup: {len(new_jobs)}")
# Breakdown of new jobs by company
new_by_comp = {}
for j in new_jobs:
    c = j["company"]
    new_by_comp[c] = new_by_comp.get(c, 0) + 1
print(f"New jobs added per company since backup:")
for c, cnt in sorted(new_by_comp.items()):
    print(f"  {c}: {cnt}")

print("\n" + "=" * 80)
print("2. EXCEL WORKBOOK INTEGRITY AUDIT")
print("=" * 80)

wb = openpyxl.load_workbook(excel_path)
print(f"Sheets in {excel_path.name}: {wb.sheetnames}")
all_ws = wb["All Jobs"]
print(f"Dimensions of 'All Jobs': rows={all_ws.max_row}, cols={all_ws.max_column}")

# Read headers
headers = [all_ws.cell(row=1, column=col).value for col in range(1, all_ws.max_column + 1)]
print(f"Headers in 'All Jobs' ({len(headers)} columns):")
for idx, h in enumerate(headers, 1):
    print(f"  Col {idx}: {h}")

# Analyze rows
excel_rows = []
excel_companies = {}
excel_job_ids = set()
dup_job_ids = []
clickable_links = 0
missing_fields = {"company": 0, "title": 0, "location": 0, "country": 0, "url": 0}

for r in range(2, all_ws.max_row + 1):
    comp = all_ws.cell(row=r, column=1).value
    title = all_ws.cell(row=r, column=2).value
    job_id = all_ws.cell(row=r, column=3).value
    loc = all_ws.cell(row=r, column=4).value
    country = all_ws.cell(row=r, column=5).value
    exp = all_ws.cell(row=r, column=6).value
    status_val = all_ws.cell(row=r, column=16).value
    url_cell = all_ws.cell(row=r, column=14)
    url_val = url_cell.value
    
    if not comp: missing_fields["company"] += 1
    if not title: missing_fields["title"] += 1
    if not loc: missing_fields["location"] += 1
    if not country: missing_fields["country"] += 1
    if not url_val: missing_fields["url"] += 1
    
    if url_cell.hyperlink or (url_val and (str(url_val).startswith("http") or str(url_val).startswith("=HYPERLINK"))):
        clickable_links += 1
        
    comp_str = str(comp or "").strip()
    excel_companies[comp_str] = excel_companies.get(comp_str, 0) + 1
    
    if job_id and str(job_id).strip() not in ("None", "Unknown", ""):
        jid_str = f"{comp_str}:{str(job_id).strip()}"
        if jid_str in excel_job_ids:
            dup_job_ids.append((r, jid_str))
        else:
            excel_job_ids.add(jid_str)
            
    excel_rows.append({
        "row": r,
        "company": comp_str,
        "title": title,
        "job_id": job_id,
        "location": loc,
        "country": country,
        "url": url_val,
        "status": status_val,
    })

print(f"\nExcel Row Statistics:")
print(f"  Total data rows: {len(excel_rows)}")
print(f"  Total unique companies: {len(excel_companies)}")
print(f"  Missing essential fields: {missing_fields}")
print(f"  Clickable hyperlinks: {clickable_links} / {len(excel_rows)}")

print(f"\nCompany-wise Excel row counts:")
for c, cnt in sorted(excel_companies.items()):
    print(f"  {c:<30}: {cnt}")

# Check job_id values in DB
cur.execute("SELECT count(*) FROM jobs WHERE job_id IS NOT NULL AND job_id != ''")
non_empty_job_ids = cur.fetchone()[0]
cur.execute("SELECT count(DISTINCT job_id) FROM jobs WHERE job_id IS NOT NULL AND job_id != ''")
distinct_non_empty_job_ids = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM jobs WHERE source_job_id IS NOT NULL AND source_job_id != ''")
non_empty_source_job_ids = cur.fetchone()[0]
cur.execute("SELECT count(DISTINCT source_job_id) FROM jobs WHERE source_job_id IS NOT NULL AND source_job_id != ''")
distinct_non_empty_source_job_ids = cur.fetchone()[0]

print(f"\nJob ID Column Analysis in SQLite:")
print(f"  Non-empty job_id: {non_empty_job_ids} (distinct: {distinct_non_empty_job_ids})")
print(f"  Non-empty source_job_id: {non_empty_source_job_ids} (distinct: {distinct_non_empty_source_job_ids})")

cur.execute("SELECT job_id, source_job_id, company, title FROM jobs LIMIT 5")
for r in cur.fetchall():
    print(f"  Sample: job_id='{r['job_id']}', source_job_id='{r['source_job_id']}', company='{r['company']}', title='{r['title']}'")

print(f"\nExcel Duplicate Job IDs count: {len(dup_job_ids)}")
if dup_job_ids:
    print(f"  First 5 dups: {dup_job_ids[:5]}")

