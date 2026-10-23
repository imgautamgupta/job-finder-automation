import openpyxl
from collections import Counter

wb = openpyxl.load_workbook('data/exports/jobs_20261019_235034.xlsx', data_only=True)
ws = wb['All Jobs']

headers = [cell.value for cell in ws[1]]
co_idx = headers.index('Company')
dec_idx = headers.index('Decision')

counts = {}
for row in ws.iter_rows(min_row=2, values_only=True):
    co = row[co_idx]
    dec = row[dec_idx]
    if co not in counts:
        counts[co] = Counter()
    counts[co][dec] += 1

print(f"{'Company':<15} | {'Fetched':<8} | {'MATCH':<6} | {'REVIEW':<7} | {'REJECT':<7}")
print("-" * 55)
for co, dec_counts in sorted(counts.items()):
    total = sum(dec_counts.values())
    match_cnt = dec_counts.get("MATCH", 0)
    review_cnt = dec_counts.get("REVIEW", 0)
    reject_cnt = dec_counts.get("REJECT", 0)
    print(f"{co:<15} | {total:<8} | {match_cnt:<6} | {review_cnt:<7} | {reject_cnt:<7}")
