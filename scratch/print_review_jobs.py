import openpyxl

wb_path = r'data\exports\jobs_20261020_165602.xlsx'
wb = openpyxl.load_workbook(wb_path, data_only=True)
ws = wb['All Jobs']
headers = [cell.value for cell in ws[1]]

rows = [dict(zip(headers, r)) for r in ws.iter_rows(min_row=2, values_only=True)]
reviews = [r for r in rows if r.get('Decision') == 'REVIEW']
print(f'Total REVIEW jobs: {len(reviews)}')
for i, r in enumerate(reviews, 1):
    print(f'{i}. [{r.get("Company")}] {r.get("Job Title")} (ID: {r.get("Official Job ID")})')
    print(f'   Score: {r.get("Match Score")}, Decision: {r.get("Decision")}')
    print(f'   Reason: {r.get("Decision Reason")}')
    print(f'   Exp Req: {r.get("Experience Requirement")}')
    print(f'   URL: {r.get("Application URL")}')
    print()
