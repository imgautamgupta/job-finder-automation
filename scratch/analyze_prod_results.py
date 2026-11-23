import json
import sqlite3
from pathlib import Path

root = Path(__file__).resolve().parent.parent

# Read json
with open(root / "reports" / "prod_collection_data.json", encoding="utf-8") as f:
    data = json.load(f)

# Connect to DB
conn = sqlite3.connect(root / "data" / "jobs.db")
c = conn.cursor()

c.execute("SELECT count(*) FROM jobs")
total_db_jobs = c.fetchone()[0]

c.execute("SELECT count(DISTINCT company) FROM jobs")
unique_db_companies = c.fetchone()[0]

cols = [col[1] for col in c.execute("PRAGMA table_info(jobs)").fetchall()]
print(f"Jobs columns: {cols}")

tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables in DB: {tables}")

c.execute("SELECT count(*) FROM jobs WHERE status NOT IN ('not_applied', 'discovered', 'active') OR notes IS NOT NULL OR applied_at IS NOT NULL")
tracked_jobs = c.fetchone()[0]
backup_db = root / "data" / "backups" / "jobs_backup_pre_phase2_2.db"
conn_bak = sqlite3.connect(backup_db)
c_bak = conn_bak.cursor()
c_bak.execute("SELECT count(*) FROM jobs")
total_bak_jobs = c_bak.fetchone()[0]

print(f"Database Verification:")
print(f"  Pre-run jobs in backup: {total_bak_jobs}")
print(f"  Current jobs in jobs.db: {total_db_jobs} (+{total_db_jobs - total_bak_jobs} new jobs)")
print(f"  Unique companies in jobs.db: {unique_db_companies}")
print(f"  Tracked application records preserved: {tracked_jobs}")

# Company breakdown analysis
comp_stats = data["company_stats"]
active_vacancies = 0
zero_vacancies = 0
total_raw = 0
total_parsed = 0
total_unique = 0

print("\nCompany-wise Breakdown:")
for cid, info in comp_stats.items():
    raw = info["raw_records"]
    total_raw += raw
    total_parsed += info["parsed_jobs"]
    total_unique += info["unique_jobs"]
    if raw > 0:
        active_vacancies += 1
    else:
        zero_vacancies += 1
    print(f"  {info['name']:<25} | ATS: {info['ats_platform']:<15} | Raw: {raw:<4} | Unique: {info['unique_jobs']:<4} | Valid URLs: {info['valid_app_urls']:<4} | Status: {info['health_status']}")

print(f"\nSummary:")
print(f"  Total companies audited: {len(comp_stats)}")
print(f"  Companies with active vacancies: {active_vacancies}")
print(f"  Companies with 0 current vacancies: {zero_vacancies}")
print(f"  Total raw collected: {total_raw}")
print(f"  Total parsed: {total_parsed}")
print(f"  Total unique: {total_unique}")
