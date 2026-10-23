import sqlite3
import pandas as pd
import openpyxl
from app.services.filter import JobFilter, match_level_title, match_seniority_title
from app.config.settings import get_settings
from app.models import Job

excel_path = r"data\exports\jobs_20261021_171418.xlsx"
wb = openpyxl.load_workbook(excel_path, data_only=True)

print("=== SHEET ROW COUNTS ===")
for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    print(f"Sheet: {sheet_name} -> {ws.max_row} rows (including header)")

# Read All Jobs sheet
df_all = pd.read_excel(excel_path, sheet_name="All Jobs")
print(f"\nTotal rows in 'All Jobs': {len(df_all)}")
print("Columns:", list(df_all.columns))

# Decision breakdown in All Jobs
if "Decision" in df_all.columns:
    print("\n=== DECISION BREAKDOWN IN ALL JOBS ===")
    print(df_all["Decision"].value_counts(dropna=False))

# Check Non-India Locations in All Jobs
print("\n=== NON-INDIA LOCATIONS IN ALL JOBS ===")
# Look at locations and check which ones don't match India
from app.sources.successfactors import INDIAN_LOCATIONS_REGEX
non_india_jobs = []
for idx, row in df_all.iterrows():
    loc = str(row.get("Location", ""))
    company = str(row.get("Company", ""))
    title = str(row.get("Job Title", ""))
    decision = str(row.get("Decision", ""))
    reason = str(row.get("Decision Reason", ""))
    if not INDIAN_LOCATIONS_REGEX.search(loc) and "india" not in loc.lower() and "remote" not in loc.lower():
        non_india_jobs.append({
            "company": company,
            "title": title,
            "location": loc,
            "decision": decision,
            "reason": reason
        })

print(f"Total non-India jobs found in All Jobs: {len(non_india_jobs)}")
for j in non_india_jobs[:10]:
    print(f"  [{j['company']}] '{j['title']}' | Loc: '{j['location']}' | Decision: {j['decision']} ({j['reason']})")

# Check REJECT Reason breakdown per company
print("\n=== REJECT REASON BREAKDOWN PER COMPANY ===")
df_rejects = df_all[df_all["Decision"] == "REJECT"].copy()
print(f"Total REJECT jobs: {len(df_rejects)}")

def categorize_reject_reason(row):
    r = str(row.get("Decision Reason", "")).lower()
    failing = str(row.get("All Failing Rules", "")).lower()
    combined = f"{r} {failing}"
    if "location" in combined:
        return "location"
    elif "level title" in combined:
        return "level title"
    elif "seniority title" in combined or "senior" in combined or "lead" in combined or "principal" in combined:
        return "seniority title"
    elif "gate 1" in combined:
        return "Gate 1"
    elif "gate 2" in combined or "requires" in combined:
        return "Gate 2"
    else:
        return "other"

df_rejects["reject_category"] = df_rejects.apply(categorize_reject_reason, axis=1)
pivot_rejects = pd.crosstab(df_rejects["Company"], df_rejects["reject_category"], margins=True)
print(pivot_rejects)

# Check REVIEW jobs
print("\n=== REVIEW JOBS AUDIT ===")
df_review = df_all[df_all["Decision"] == "REVIEW"]
print(f"Total REVIEW jobs: {len(df_review)}")
# Print all REVIEW jobs with title, company, link and reason
for idx, row in df_review.iterrows():
    print(f"  - [{row['Company']}] '{row['Job Title']}'")
    print(f"    Reason: {row['Decision Reason']}")
    print(f"    Link: {row.get('Application URL', '')}")

sr_in_review = []
for idx, row in df_review.iterrows():
    title = str(row.get("Job Title", ""))
    if match_seniority_title(title):
        sr_in_review.append((row["Company"], title))
print(f"\nSenior titles in REVIEW: {len(sr_in_review)}")
if sr_in_review:
    print("Found senior titles in review:", sr_in_review)

# Check MATCH jobs
print("\n=== MATCH JOBS AUDIT ===")
df_match = df_all[df_all["Decision"] == "MATCH"]
print(f"Total MATCH jobs: {len(df_match)}")
for idx, row in df_match.iterrows():
    print(f"  [{row['Company']}] '{row['Job Title']}' | Reason: {row['Decision Reason']} | URL: {row.get('Application URL', '')}")

# Check 5 Amazon Jobs
print("\n=== 5 AMAZON JOBS AUDIT ===")
conn = sqlite3.connect("data/jobs.db")
amazon_ids = ['10572929', '10531567', '10551515', '10495277', '10528516']
for aid in amazon_ids:
    row = conn.execute("SELECT source_job_id, title, company, location, experience_required, description, url FROM jobs WHERE source_job_id = ?", (aid,)).fetchone()
    if row:
        print(f"\nID: {row[0]}")
        print(f"Title: {row[1]}")
        print(f"Exp Req: {row[4]}")
        print(f"Desc snippet: {row[5][:300]}...")
    else:
        # Check by url or like
        row2 = conn.execute("SELECT source_job_id, title, company, location, experience_required, description, url FROM jobs WHERE url LIKE ?", (f"%{aid}%",)).fetchone()
        if row2:
            print(f"\nFound by URL ID: {row2[0]} (matched {aid})")
            print(f"Title: {row2[1]}")
            print(f"Exp Req: {row2[4]}")
            print(f"Desc snippet: {row2[5][:300]}...")
        else:
            print(f"ID {aid} not found in DB")
conn.close()
