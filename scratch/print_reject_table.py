import openpyxl
import glob
from collections import defaultdict

latest = sorted(glob.glob("data/exports/jobs_*.xlsx"))[-1]
wb = openpyxl.load_workbook(latest)
ws = wb["All Jobs"]
headers = [c.value for c in ws[1]]
comp_idx = headers.index("Company")
dec_idx = headers.index("Decision")
reason_idx = headers.index("Decision Reason")
exp_idx = headers.index("Experience Requirement")

categories = ["Location", "Seniority Title", "Experience Gate 1", "Experience Gate 2", "Other"]
counts = defaultdict(lambda: {cat: 0 for cat in categories})

for r in range(2, ws.max_row + 1):
    comp = str(ws.cell(r, comp_idx + 1).value or "Unknown").strip()
    dec = str(ws.cell(r, dec_idx + 1).value or "").strip()
    reason = str(ws.cell(r, reason_idx + 1).value or "").strip()
    exp = ws.cell(r, exp_idx + 1).value
    if dec != "REJECT":
        continue

    reason_lower = reason.lower()
    if "location" in reason_lower or "remote" in reason_lower:
        cat = "Location"
    elif "senior/negative keyword" in reason_lower or "senior marker" in reason_lower:
        cat = "Seniority Title"
    elif "requires" in reason_lower:
        if exp and any(ch.isdigit() for ch in str(exp)):
            cat = "Experience Gate 1"
        else:
            cat = "Experience Gate 2"
    else:
        cat = "Other"

    counts[comp][cat] += 1

print(f"{'Company':<15} | {'Location':<10} | {'Seniority Title':<16} | {'Exp Gate 1':<12} | {'Exp Gate 2':<12} | {'Other':<8} | {'Total REJECT':<12}")
print("-" * 95)
totals = defaultdict(int)
for comp in sorted(counts.keys()):
    c = counts[comp]
    tot = sum(c.values())
    for k, v in c.items():
        totals[k] += v
    totals["Total"] += tot
    print(f"{comp:<15} | {c['Location']:<10} | {c['Seniority Title']:<16} | {c['Experience Gate 1']:<12} | {c['Experience Gate 2']:<12} | {c['Other']:<8} | {tot:<12}")

print("-" * 95)
print(f"{'TOTAL':<15} | {totals['Location']:<10} | {totals['Seniority Title']:<16} | {totals['Experience Gate 1']:<12} | {totals['Experience Gate 2']:<12} | {totals['Other']:<8} | {totals['Total']:<12}")
