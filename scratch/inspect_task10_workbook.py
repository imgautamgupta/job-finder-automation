"""Inspection script for Task 10 Excel workbook validation."""

from collections import Counter
from pathlib import Path
import openpyxl

WORKBOOK_PATH = Path("data/exports/jobs_20261020_174634.xlsx")

def inspect_workbook():
    wb = openpyxl.load_workbook(WORKBOOK_PATH, data_only=True)
    print("=== SHEET ROW COUNTS ===")
    for sheetname in wb.sheetnames:
        sheet = wb[sheetname]
        print(f"Sheet '{sheetname}': {sheet.max_row} rows (including header)")

    all_jobs_sheet = wb["All Jobs"]
    headers = [cell.value for cell in all_jobs_sheet[1]]
    print("\nHeaders in All Jobs:", headers)

    company_idx = headers.index("Company")
    title_idx = headers.index("Job Title")
    job_id_idx = headers.index("Official Job ID")
    location_idx = headers.index("Location")
    decision_idx = headers.index("Decision")
    decision_reason_idx = headers.index("Decision Reason")
    url_idx = headers.index("Application URL")
    score_idx = headers.index("Match Score") if "Match Score" in headers else -1

    company_decision_counts = {}
    sample_urls = {}
    all_rows = []

    for row_num in range(2, all_jobs_sheet.max_row + 1):
        comp = all_jobs_sheet.cell(row=row_num, column=company_idx + 1).value
        title = all_jobs_sheet.cell(row=row_num, column=title_idx + 1).value
        job_id = all_jobs_sheet.cell(row=row_num, column=job_id_idx + 1).value
        loc = all_jobs_sheet.cell(row=row_num, column=location_idx + 1).value
        dec = all_jobs_sheet.cell(row=row_num, column=decision_idx + 1).value
        reason = all_jobs_sheet.cell(row=row_num, column=decision_reason_idx + 1).value
        url_cell = all_jobs_sheet.cell(row=row_num, column=url_idx + 1)
        url = url_cell.hyperlink.target if url_cell.hyperlink else url_cell.value
        score = all_jobs_sheet.cell(row=row_num, column=score_idx + 1).value if score_idx >= 0 else None

        if not comp:
            continue

        if comp not in company_decision_counts:
            company_decision_counts[comp] = Counter()
        company_decision_counts[comp][dec] += 1

        if comp not in sample_urls and url:
            sample_urls[comp] = (title, job_id, url)

        all_rows.append({
            "company": comp,
            "title": title,
            "job_id": job_id,
            "location": loc,
            "decision": dec,
            "reason": reason,
            "url": url,
            "score": score or 0,
        })

    print("\n=== PER-COMPANY DECISION COUNTS (All Jobs) ===")
    total_match = 0
    total_review = 0
    total_reject = 0

    for comp in sorted(company_decision_counts.keys()):
        counts = company_decision_counts[comp]
        m = counts.get("MATCH", 0)
        r = counts.get("REVIEW", 0)
        rej = counts.get("REJECT", 0)
        total = sum(counts.values())
        total_match += m
        total_review += r
        total_reject += rej
        print(f"{comp:15s}: Total={total:4d} | MATCH={m:2d} | REVIEW={r:3d} | REJECT={rej:4d}")

    print(f"\nGRAND TOTAL: Total={len(all_rows)} | MATCH={total_match} | REVIEW={total_review} | REJECT={total_reject}")

    print("\n=== SAMPLE URLS FOR SPOT-CHECK ===")
    for comp, (t, jid, u) in sample_urls.items():
        print(f"[{comp}] {t} (ID: {jid}) -> {u}")

    print("\n=== TOP 10 CLOSEST JOBS (Highest Match Score / REVIEW / REJECT Analysis) ===")
    # Sort by score descending
    sorted_rows = sorted(all_rows, key=lambda x: x["score"], reverse=True)
    for i, job in enumerate(sorted_rows[:15], 1):
        print(f"{i}. [{job['company']}] {job['title']} (Score: {job['score']}, Decision: {job['decision']})")
        print(f"   Reason: {job['reason']}")
        print(f"   URL: {job['url']}\n")

if __name__ == "__main__":
    inspect_workbook()
