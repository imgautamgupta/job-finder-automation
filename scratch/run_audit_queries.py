import sqlite3
import json

conn = sqlite3.connect("data/jobs.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("--- Tables ---")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for t in tables:
    name = t['name']
    cursor.execute(f"SELECT COUNT(*) FROM {name}")
    cnt = cursor.fetchone()[0]
    print(f"Table: {name}, count: {cnt}")

print("\n--- Columns in jobs ---")
cursor.execute("PRAGMA table_info(jobs);")
cols = [col['name'] for col in cursor.fetchall()]
print(cols)

# Query SQLite for total jobs by decision and by source.
# Where is decision stored? In extra_metadata JSON or a column?
# Let's inspect a few rows from jobs.
print("\n--- Sample row from jobs ---")
cursor.execute("SELECT * FROM jobs LIMIT 1;")
row = cursor.fetchone()
if row:
    d = dict(row)
    print("source:", d.get("source"))
    print("extra_metadata:", d.get("extra_metadata"))

# Let's see all unique sources
print("\n--- Jobs by source ---")
cursor.execute("SELECT source, COUNT(*) as count FROM jobs GROUP BY source ORDER BY count DESC;")
for r in cursor.fetchall():
    print(f"Source: {r['source']}, Count: {r['count']}")

# Check decisions
# In extra_metadata, decision might be JSON: {"decision": "..."}
cursor.execute("SELECT id, title, company, source, match_score, raw_metadata FROM jobs;")
rows = cursor.fetchall()
decision_counts = {}
decision_by_source = {}
accenture_jobs = []

for r in rows:
    meta = {}
    if r["raw_metadata"]:
        try:
            meta = json.loads(r["raw_metadata"])
        except Exception:
            pass
    dec = meta.get("decision", "NONE")
    decision_counts[dec] = decision_counts.get(dec, 0) + 1
    
    src = r["source"] or "Unknown"
    if src not in decision_by_source:
        decision_by_source[src] = {}
    decision_by_source[src][dec] = decision_by_source[src].get(dec, 0) + 1
    
    if (src and src.lower() == "accenture") or (r["company"] and "accenture" in r["company"].lower()):
        accenture_jobs.append({
            "id": r["id"],
            "title": r["title"],
            "match_score": r["match_score"],
            "meta": meta
        })

print("\n--- Jobs by decision (from extra_metadata) ---")
for dec, cnt in decision_counts.items():
    print(f"Decision: {dec}, Count: {cnt}")

print("\n--- Jobs by source and decision ---")
for src, decs in decision_by_source.items():
    print(f"Source: {src}: {decs}")

print(f"\n--- Total Accenture jobs found in DB: {len(accenture_jobs)} ---")
