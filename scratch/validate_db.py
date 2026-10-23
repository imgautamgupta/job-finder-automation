"""Validation script: inspect DB for Accenture jobs, statuses, and pipeline run records."""
import sqlite3, json

db_path = "data/jobs.db"
con = sqlite3.connect(db_path)
cur = con.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print("Tables:", [r[0] for r in cur.fetchall()])

# All Accenture jobs with tracking fields
cur.execute(
    "SELECT source_job_id, title, url, status, notes, match_score, match_category, "
    "first_seen_at, last_seen_at, interview_stage, interview_status, interview_notes, follow_up_date "
    "FROM jobs WHERE source='accenture' ORDER BY match_score DESC"
)
rows = cur.fetchall()
print(f"\nAccenture jobs in DB: {len(rows)}")
for r in rows:
    print(f"  Official Job ID      : {r[0]}")
    print(f"  Title                : {r[1]}")
    print(f"  Application Status   : {r[3]}")
    print(f"  Notes                : {r[4]!r}")
    print(f"  Match Score          : {r[5]}  Category: {r[6]}")
    print(f"  First Seen           : {r[7]}")
    print(f"  Last Seen            : {r[8]}")
    print(f"  Interview Stage      : {r[9]}")
    print(f"  Interview Status     : {r[10]}")
    print(f"  Interview Notes      : {r[11]!r}")
    print(f"  Follow-up Date       : {r[12]}")
    print(f"  Direct URL           : {r[2]}")
    print()

cur.execute("SELECT COUNT(*) FROM pipeline_runs")
print("Total pipeline runs recorded:", cur.fetchone()[0])

cur.execute(
    "SELECT run_id, status, raw_collected, filtered, new_jobs, duplicate_jobs, source_results "
    "FROM pipeline_runs ORDER BY rowid DESC LIMIT 3"
)
runs = cur.fetchall()
print("\nLast 3 pipeline runs:")
for run in runs:
    print(f"  RUN: {run[0]}")
    print(f"    status={run[1]} | raw={run[2]} | filtered={run[3]} | new={run[4]} | dup={run[5]}")
    if run[6]:
        try:
            sr = json.loads(run[6])
            for src, info in sr.items():
                print(f"    source[{src}]: status={info.get('status')} collected={info.get('collected')}")
        except Exception:
            print(f"    source_results={run[6]}")
    print()

con.close()
