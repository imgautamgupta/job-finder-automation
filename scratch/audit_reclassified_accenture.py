import sys
sys.path.insert(0, ".")
import sqlite3
import json
import openpyxl
from app.config.settings import get_settings
from app.services.filter import JobFilter
from app.models.job import Job

settings = get_settings()
profile = settings.load_profile()
job_filter = JobFilter(profile=profile)

conn = sqlite3.connect("data/jobs.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get all Accenture jobs from DB
cursor.execute("SELECT id, title, source_job_id, location, experience_required, raw_metadata FROM jobs WHERE source='accenture';")
rows = cursor.fetchall()

print(f"Total Accenture jobs in DB: {len(rows)}")

# For every job in DB, run classify_job with the updated filter and see decision and reason
reclassified = []
for r in rows:
    meta = json.loads(r["raw_metadata"]) if r["raw_metadata"] else {}
    job = Job(
        id=r["id"],
        title=r["title"],
        company="Accenture",
        source="accenture",
        source_job_id=r["source_job_id"],
        location=r["location"],
        experience_required=r["experience_required"],
        url="",
        extra_metadata=meta,
    )
    decision, reason = job_filter.classify_job(job)
    
    # Update DB if different
    prev_decision = meta.get("decision", "NONE")
    prev_reason = meta.get("decision_reason", "")
    
    meta["decision"] = decision
    meta["decision_reason"] = reason
    cursor.execute("UPDATE jobs SET raw_metadata = ? WHERE id = ?", (json.dumps(meta), r["id"]))
    
    reclassified.append({
        "id": r["id"],
        "source_job_id": r["source_job_id"],
        "title": r["title"],
        "location": r["location"],
        "exp": r["experience_required"],
        "prev_decision": prev_decision,
        "prev_reason": prev_reason,
        "new_decision": decision,
        "new_reason": reason,
    })

conn.commit()

# Filter for jobs that were previously 2+ year jobs (e.g. 2-5 years)
prev_2yr_jobs = [j for j in reclassified if j["exp"] and "2" in j["exp"] and "5-10" not in j["exp"] and "10-12" not in j["exp"]]

print("\n========================================================")
print(f"PREVIOUSLY 2+ YEAR ACCENTURE JOBS NOW CLASSIFIED REJECT ({len(prev_2yr_jobs)} jobs):")
print("========================================================")
for j in prev_2yr_jobs:
    print(f"ID {j['id']:2d} | Requisition: {j['source_job_id']:22s} | Title: {j['title']:30s} | Exp: {j['exp']:9s} | Location: {j['location']}")
    print(f"       Previous: [{j['prev_decision']}] {j['prev_reason']}")
    print(f"       Now:      [{j['new_decision']}] Reason: \"{j['new_reason']}\"")
    print()

# Check newest Excel workbook Accenture sheet
wb = openpyxl.load_workbook("data/exports/jobs_20261019_200942.xlsx")
ws = wb["Accenture"]
print(f"\nNewest Excel 'Accenture' Sheet Rows: {ws.max_row} (Header + {ws.max_row - 1} data rows)")
headers = [c.value for c in ws[1]]
dec_idx = headers.index("Decision") if "Decision" in headers else -1
title_idx = headers.index("Job Title") if "Job Title" in headers else -1
id_idx = headers.index("Official Job ID") if "Official Job ID" in headers else -1
exp_idx = headers.index("Experience Requirement") if "Experience Requirement" in headers else -1

print(f"Columns in Accenture sheet: {headers}")

# Check distribution of decisions in newest Accenture sheet
dec_counts = {}
for row in ws.iter_rows(min_row=2, values_only=True):
    d = row[dec_idx] if dec_idx >= 0 else None
    dec_counts[d] = dec_counts.get(d, 0) + 1
print(f"Decision distribution in export Accenture sheet: {dec_counts}")
