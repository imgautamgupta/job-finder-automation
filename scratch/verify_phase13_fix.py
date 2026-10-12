import sys
import os
sys.path.insert(0, os.path.abspath("."))

from app.database.database import DatabaseManager
from app.services.search_intelligence import SearchIntelligenceService

db = DatabaseManager('data/jobs.db')
jobs = db.get_all_jobs_raw()
print(f"Total jobs in DB: {len(jobs)}")
for j in jobs:
    if j['id'] in (1, 7):
        print(f"Job {j['id']}: {j['title']} @ {j['company']}, status={j['status']}, applied_at={j['applied_at']}")

svc = SearchIntelligenceService(db=db)
report = svc.get_search_intelligence_report()
print(f"Search Intelligence total_jobs: {report.total_jobs}")
print(f"Search Intelligence applied_jobs: {report.applied_jobs}")

assert len(jobs) == 7, f"Expected 7 jobs, got {len(jobs)}"
assert report.total_jobs == 7, f"Expected 7 total_jobs in report, got {report.total_jobs}"
assert report.applied_jobs == 1, f"Expected 1 applied_jobs in report, got {report.applied_jobs}"

job1 = next(j for j in jobs if j['id'] == 1)
job7 = next(j for j in jobs if j['id'] == 7)

assert job1['status'] == "NEW", f"Job 1 status should be NEW, got {job1['status']}"
assert job7['status'] == "APPLIED", f"Job 7 status should be APPLIED, got {job7['status']}"

print("ALL PHASE 13 FIX VALIDATION CHECKS PASSED PERFECTLY!")
