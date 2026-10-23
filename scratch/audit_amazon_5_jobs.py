import sqlite3
from app.services.filter import JobFilter, match_level_title, match_seniority_title
from app.config.settings import get_settings
from app.models import Job

settings = get_settings()
profile = settings.load_profile()
flt = JobFilter(profile=profile, max_required_min_years=1)

conn = sqlite3.connect("data/jobs.db")
amazon_ids = ['10572929', '10531567', '10551515', '10495277', '10528516']

for aid in amazon_ids:
    row = conn.execute("SELECT source_job_id, title, company, location, experience_required, description, url FROM jobs WHERE source_job_id = ? OR url LIKE ?", (aid, f"%{aid}%")).fetchone()
    if not row:
        print(f"Job {aid} not found")
        continue
    
    source_job_id, title, company, location, exp_req, desc, url = row
    job = Job(
        source="company_json",
        source_job_id=source_job_id,
        title=title,
        company=company,
        location=location,
        experience_required=exp_req,
        description=desc,
        url=url
    )
    
    from app.services.filter import parse_structured_experience_min, scan_description_experience
    # Run gate 1
    g1_min = parse_structured_experience_min(job.experience_required)
    
    # Run gate 2
    g2_min, g2_snippet = scan_description_experience(job.description)
    
    # Run full classify_job
    decision, dec_reason = flt.classify_job(job)
    
    # Check level title
    lvl = match_level_title(title)
    
    print("=" * 80)
    print(f"AMAZON JOB ID: {source_job_id}")
    print(f"Title: {title}")
    print(f"Level Marker: {lvl}")
    print(f"Gate 1 Input (experience_required): '{exp_req}'")
    import re
    snippets = [line.strip() for line in desc.split("\n") if re.search(r"\b\d+\+?\s*(?:to\s*\d+\s*)?years?", line, re.IGNORECASE)]
    print(f"Gate 2 Relevant Snippets in Description:\n  " + "\n  ".join(snippets))
    print(f"Gate 2 Output: min={g2_min}, snippet='{g2_snippet}'")
    print(f"Final Decision: {decision}")
    print(f"Final Decision Reason: {dec_reason}")

conn.close()
