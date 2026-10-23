import sqlite3
import openpyxl

# Check excel

print("\n--- LATEST EXCEL WORKBOOK ---")
import glob
files = sorted(glob.glob("data/exports/jobs_*.xlsx"))
if files:
    latest = files[-1]
    print(f"File: {latest}")
    wb = openpyxl.load_workbook(latest)
    ws = wb["All Jobs"]
    headers = [cell.value for cell in ws[1]]
    job_id_idx = headers.index("Official Job ID")
    title_idx = headers.index("Job Title")
    comp_idx = headers.index("Company")
    dec_idx = headers.index("Decision")
    reason_idx = headers.index("Decision Reason")
    for r in range(2, ws.max_row + 1):
        jid = str(ws.cell(r, job_id_idx + 1).value)
        if jid in ('R0138315', 'REF089412W'):
            print(f"{ws.cell(r, comp_idx + 1).value} | {jid} | {ws.cell(r, title_idx + 1).value} | {ws.cell(r, dec_idx + 1).value} | {ws.cell(r, reason_idx + 1).value}")
