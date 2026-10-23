import openpyxl

wb = openpyxl.load_workbook('data/exports/jobs_20261019_233441.xlsx')
print('=== WORKBOOK SHEETS & ROW COUNTS ===')
for idx, name in enumerate(wb.sheetnames):
    ws = wb[name]
    print(f'Sheet {idx}: "{name}" -> {ws.max_row} rows (Data: {max(0, ws.max_row - 1)})')

print('\n=== ALL JOBS SAMPLE (COLUMNS & DECISIONS) ===')
ws_all = wb['All Jobs']
headers = [ws_all.cell(row=1, column=c).value for c in range(1, ws_all.max_column + 1)]
print('Headers:', headers)

decisions = {}
for r in range(2, ws_all.max_row + 1):
    dec = ws_all.cell(row=r, column=8).value
    decisions[dec] = decisions.get(dec, 0) + 1

print('Decision Breakdown:', decisions)

print('\n=== FIRST 3 JOBS IN ALL JOBS ===')
for r in range(2, min(5, ws_all.max_row + 1)):
    comp = ws_all.cell(row=r, column=1).value
    title = ws_all.cell(row=r, column=2).value
    job_id = ws_all.cell(row=r, column=3).value
    score = ws_all.cell(row=r, column=6).value
    dec = ws_all.cell(row=r, column=8).value
    reason = ws_all.cell(row=r, column=9).value
    url_cell = ws_all.cell(row=r, column=12)
    has_hyperlink = bool(url_cell.hyperlink)
    print(f'Row {r}: [{dec}] (Score: {score}) {comp} - {title} (ID: {job_id}) | Reason: {reason} | Hyperlink: {has_hyperlink}')
