import sqlite3
import json

conn = sqlite3.connect("data/jobs.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT id, title, source_job_id, experience_required, match_score, raw_metadata FROM jobs WHERE source='accenture';")
rows = cursor.fetchall()

print(f"Total Accenture rows in DB: {len(rows)}")

matched_jobs = []

for r in rows:
    meta = json.loads(r["raw_metadata"]) if r["raw_metadata"] else {}
    exp = r["experience_required"] or meta.get("experience_required") or ""
    dec = meta.get("decision", "NONE")
    reason = meta.get("decision_reason") or meta.get("reason") or ""
    
    # Check if job shows "2+ years" or "2-5 years" or similar 2+ year pattern
    # The prompt asks: "which Accenture jobs show '2+ years' yet are not REJECT. Quote the decision reason for each."
    # Let's check both:
    # 1. Any job with "2" in experience requirement that is not REJECT
    # 2. Any job with "2+" or "2-5" or intermediate experience that is not REJECT
    if dec != "REJECT":
        matched_jobs.append({
            "id": r["id"],
            "title": r["title"],
            "source_job_id": r["source_job_id"],
            "experience_required": exp,
            "decision": dec,
            "decision_reason": reason,
            "match_score": r["match_score"],
            "meta": meta
        })

print(f"\nTotal Accenture jobs that are NOT REJECT: {len(matched_jobs)}")
for j in matched_jobs:
    print(f"ID={j['id']} | JobID={j['source_job_id']} | Title='{j['title']}' | Exp='{j['experience_required']}' | Dec={j['decision']} | Score={j['match_score']}")
    print(f"  Decision Reason: '{j['decision_reason']}'")
    print(f"  Eligibility: '{j['meta'].get('eligibility')}'")
    print()

# Also check if any REJECT jobs have "2-5 years" or "2+ years"
rejected_2yr = []
for r in rows:
    meta = json.loads(r["raw_metadata"]) if r["raw_metadata"] else {}
    exp = r["experience_required"] or meta.get("experience_required") or ""
    dec = meta.get("decision", "NONE")
    reason = meta.get("decision_reason") or meta.get("reason") or ""
    if dec == "REJECT" and ("2" in exp):
        rejected_2yr.append({
            "id": r["id"],
            "title": r["title"],
            "source_job_id": r["source_job_id"],
            "exp": exp,
            "reason": reason
        })

print(f"\nTotal Accenture REJECT jobs with '2' in exp: {len(rejected_2yr)}")
for j in rejected_2yr[:10]:
    print(f"  ID={j['id']} | Title='{j['title']}' | Exp='{j['exp']}' | Reason='{j['reason']}'")
