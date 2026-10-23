import sqlite3
import json

conn = sqlite3.connect("data/jobs.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT id, job_id, title, source_job_id, experience_required, match_score, raw_metadata FROM jobs WHERE source='accenture';")
rows = cursor.fetchall()

print(f"Total Accenture rows: {len(rows)}")
for r in rows:
    meta = json.loads(r["raw_metadata"]) if r["raw_metadata"] else {}
    dec = meta.get("decision", "NONE")
    reason = meta.get("reason") or meta.get("decision_reason") or meta.get("eligibility_reason") or ""
    if dec != "REJECT":
        print(f"ID={r['id']} | JobID={r['job_id']} | SourceJobID={r['source_job_id']} | Title={r['title']} | Exp={r['experience_required']} | Score={r['match_score']} | Dec={dec} | Reason={reason}")

print("\n--- Check all unique decisions in Accenture jobs ---")
decs = {}
for r in rows:
    meta = json.loads(r["raw_metadata"]) if r["raw_metadata"] else {}
    d = meta.get("decision", "NONE")
    decs[d] = decs.get(d, 0) + 1
print(decs)

print("\n--- Check sample REJECT reasons in Accenture ---")
reject_reasons = {}
for r in rows:
    meta = json.loads(r["raw_metadata"]) if r["raw_metadata"] else {}
    if meta.get("decision") == "REJECT":
        reason = meta.get("reason") or meta.get("decision_reason") or "UNKNOWN"
        reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
for k, v in reject_reasons.items():
    print(f"Count: {v} | Reason: {k}")
