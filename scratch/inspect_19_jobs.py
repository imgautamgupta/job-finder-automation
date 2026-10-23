import sqlite3
import openpyxl
import re
from app.services.filter import scan_description_experience_min, NUM_WORDS_PATTERN, DASH_PATTERN, parse_num

wb = openpyxl.load_workbook('data/exports/jobs_20261020_121238.xlsx', data_only=True)
ws = wb['All Jobs']
headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]

jobs_19 = []
for r in range(2, ws.max_row + 1):
    row = {headers[c-1]: ws.cell(r, c).value for c in range(1, ws.max_column + 1)}
    if '30+' in str(row.get('Decision Reason', '')):
        jobs_19.append(row)

conn = sqlite3.connect('data/jobs.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

print(f"Total jobs with 'requires 30+ years': {len(jobs_19)}")

for idx, j in enumerate(jobs_19, start=1):
    job_id = j.get('Official Job ID')
    url = j.get('Application URL')
    title = j.get('Job Title')
    comp = j.get('Company')
    
    db_job = c.execute(
        'SELECT id, company, title, description, location, experience_required FROM jobs WHERE (source_job_id = ? OR url = ?) AND company = ?',
        (job_id, url, comp)
    ).fetchone()
    if not db_job:
        db_job = c.execute(
            'SELECT id, company, title, description, location, experience_required FROM jobs WHERE title = ? AND company = ?',
            (title, comp)
        ).fetchone()

    print(f"\n--- Job {idx}: [{comp}] {title} (ID: {job_id}) ---")
    if db_job and db_job['description']:
        desc = db_job['description']
        # Let's search for "30" in the description
        matches_30 = []
        for m in re.finditer(r".{0,50}(?:30|thirty).{0,50}", desc, re.IGNORECASE):
            matches_30.append(m.group(0).strip())
        print(f"Description length: {len(desc)}")
        print(f"Matches around '30' or 'thirty':")
        for m in matches_30:
            print(f"  -> {repr(m)}")
    else:
        print("Description: NOT FOUND or EMPTY in DB!")
