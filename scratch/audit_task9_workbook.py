import openpyxl
from collections import Counter

wb_path = r'data\exports\jobs_20261020_165602.xlsx'
wb = openpyxl.load_workbook(wb_path, data_only=True)
print('Sheet names and max_row:')
for name in wb.sheetnames:
    ws = wb[name]
    print(f'  {name}: {ws.max_row} rows')

ws = wb['All Jobs']
headers = [cell.value for cell in ws[1]]

rows = []
for row in ws.iter_rows(min_row=2, values_only=True):
    rows.append(dict(zip(headers, row)))

print(f'\nTotal rows in All Jobs: {len(rows)}')

# By company and decision
by_comp_dec = {}
for r in rows:
    c = r.get('Company') or 'Unknown'
    d = r.get('Decision') or 'Unknown'
    if c not in by_comp_dec:
        by_comp_dec[c] = Counter()
    by_comp_dec[c][d] += 1

print('\nPer-company Decision breakdown:')
for c, counts in sorted(by_comp_dec.items()):
    match_c = counts.get('MATCH', 0)
    rev_c = counts.get('REVIEW', 0)
    rej_c = counts.get('REJECT', 0)
    tot = sum(counts.values())
    print(f'  {c:15}: MATCH={match_c:3}, REVIEW={rev_c:3}, REJECT={rej_c:3}, Total={tot:4}')

# Overall decision counts
overall_dec = Counter(r.get('Decision') for r in rows)
print('\nOverall Decision counts:', overall_dec)

# Top 10 closest REVIEW/REJECT jobs (by Match Score descending)
sorted_jobs = sorted(rows, key=lambda x: float(x.get('Match Score') or 0.0), reverse=True)
matches = [r for r in sorted_jobs if r.get('Decision') == 'MATCH']
reviews = [r for r in sorted_jobs if r.get('Decision') == 'REVIEW']
rejects = [r for r in sorted_jobs if r.get('Decision') == 'REJECT']

print(f'\nTotal MATCH: {len(matches)}')
print(f'Total REVIEW: {len(reviews)}')
print(f'Total REJECT: {len(rejects)}')

if len(matches) == 0:
    print('\nTop 10 closest non-MATCH jobs:')
    candidates = sorted(reviews + rejects, key=lambda x: float(x.get('Match Score') or 0.0), reverse=True)
    for i, r in enumerate(candidates[:15], 1):
        print(f'{i}. [{r.get("Company")}] {r.get("Job Title")} (ID: {r.get("Official Job ID")})')
        print(f'   Score: {r.get("Match Score")}, Decision: {r.get("Decision")}')
        print(f'   Reason: {r.get("Decision Reason")}')
        print(f'   Exp Req: {r.get("Experience Requirement")}')
        print()
else:
    print('\nMATCH jobs:')
    for i, r in enumerate(matches, 1):
        print(f'{i}. [{r.get("Company")}] {r.get("Job Title")} (Score: {r.get("Match Score")}) - {r.get("Decision Reason")}')

    print('\nTop 10 closest REVIEW / REJECT jobs:')
    candidates = sorted(reviews + rejects, key=lambda x: float(x.get('Match Score') or 0.0), reverse=True)
    for i, r in enumerate(candidates[:10], 1):
        print(f'{i}. [{r.get("Company")}] {r.get("Job Title")} (ID: {r.get("Official Job ID")})')
        print(f'   Score: {r.get("Match Score")}, Decision: {r.get("Decision")}')
        print(f'   Reason: {r.get("Decision Reason")}')
        print(f'   Exp Req: {r.get("Experience Requirement")}')
        print()
