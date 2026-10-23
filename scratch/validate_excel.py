"""Validation: inspect the latest Excel export for Accenture job IDs, URLs, and sheet structure."""
import os
import glob
import openpyxl

exports_dir = "data/exports"
xlsx_files = sorted(glob.glob(os.path.join(exports_dir, "jobs_*.xlsx")))
if not xlsx_files:
    print("ERROR: No Excel exports found!")
    raise SystemExit(1)

latest = xlsx_files[-1]
print(f"Inspecting: {latest} ({os.path.getsize(latest)} bytes)")

wb = openpyxl.load_workbook(latest)
print(f"\nSheets ({len(wb.sheetnames)}): {wb.sheetnames}")

TARGET_SHEETS = ["Accenture", "Top Matches", "All Relevant Jobs", "New Matches"]

for sheet_name in TARGET_SHEETS:
    if sheet_name not in wb.sheetnames:
        print(f"\n[WARNING] Sheet '{sheet_name}' NOT found")
        continue

    ws = wb[sheet_name]
    data_rows = [r for r in ws.iter_rows(min_row=2, max_row=ws.max_row) if any(c.value for c in r)]
    print(f"\n=== Sheet: '{sheet_name}' — {len(data_rows)} data row(s) ===")

    headers = [str(c.value or "").strip() for c in ws[1]]

    for row in data_rows:
        vals = {h: c.value for h, c in zip(headers, row) if h}
        url_cell = next((c for h, c in zip(headers, row) if "url" in h.lower()), None)
        hyperlink = url_cell.hyperlink.target if url_cell and url_cell.hyperlink else None

        print(f"  Title          : {vals.get('Job Title') or vals.get('Title') or vals.get('Job ID')}")
        print(f"  Company        : {vals.get('Company')}")
        print(f"  Match Score    : {vals.get('Match Score')}")
        print(f"  Match Category : {vals.get('Match Category')}")
        print(f"  Location       : {vals.get('Location')}")
        print(f"  Source         : {vals.get('Source')}")

        # Find Job ID column
        job_id_val = vals.get("Job ID") or vals.get("Official Job ID") or vals.get("Requisition ID")
        print(f"  Job ID column  : {job_id_val!r}")

        url_val = vals.get("Job URL") or vals.get("URL")
        print(f"  URL cell value : {url_val}")
        print(f"  Hyperlink      : {hyperlink}")
        print()
