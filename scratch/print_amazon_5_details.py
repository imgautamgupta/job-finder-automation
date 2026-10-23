import sqlite3
from app.services.filter import parse_structured_experience_min, scan_description_experience, match_level_title

conn = sqlite3.connect("data/jobs.db")
amazon_ids = ['10572929', '10531567', '10551515', '10495277', '10528516']

for aid in amazon_ids:
    row = conn.execute("SELECT source_job_id, title, company, location, experience_required, description, url FROM jobs WHERE source_job_id = ? OR url LIKE ?", (aid, f"%{aid}%")).fetchone()
    if not row:
        print(f"Job {aid} not found")
        continue
    source_job_id, title, company, location, exp_req, desc, url = row
    
    g1_min = parse_structured_experience_min(exp_req)
    g2_min, g2_snippet = scan_description_experience(desc)
    lvl = match_level_title(title)
    
    print("=" * 80)
    print(f"AMAZON ID: {source_job_id}")
    print(f"Title: {title}")
    print(f"Level Marker Detected: {lvl}")
    print(f"\n[Gate 1: Structured Experience Field]")
    print(f"  Raw input: {repr(exp_req)}")
    print(f"  Parsed minimum: {g1_min}")
    print(f"\n[Gate 2: Job Description]")
    print(f"  Total characters: {len(desc)}")
    print(f"  Gate 2 Parsed minimum: {g2_min}")
    print(f"  Gate 2 Matched snippet: {repr(g2_snippet)}")
    print(f"\n[Description Content]:")
    print(desc)
    print("=" * 80)

conn.close()
