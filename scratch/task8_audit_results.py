import openpyxl
from collections import defaultdict
import glob

files = sorted(glob.glob("data/exports/jobs_*.xlsx"))
latest_file = files[-1]
print(f"Auditing latest workbook: {latest_file}")

wb = openpyxl.load_workbook(latest_file)
ws = wb["All Jobs"]

headers = [cell.value for cell in ws[1]]
print("Headers:", headers)
comp_idx = headers.index("Company")
jid_idx = headers.index("Official Job ID")
title_idx = headers.index("Job Title")
dec_idx = headers.index("Decision")
reason_idx = headers.index("Decision Reason")
exp_idx = headers.index("Experience Requirement")
loc_idx = headers.index("Location")

print("\n--- TARGET JOBS VERIFICATION ---")
target_ids = {"R0138315", "REF089412W"}
found_targets = {}

for r in range(2, ws.max_row + 1):
    jid = str(ws.cell(r, jid_idx + 1).value or "").strip()
    if jid in target_ids:
        comp = ws.cell(r, comp_idx + 1).value
        title = ws.cell(r, title_idx + 1).value
        dec = ws.cell(r, dec_idx + 1).value
        reason = ws.cell(r, reason_idx + 1).value
        found_targets[jid] = (comp, title, dec, reason)
        print(f"Company: {comp} | Job ID: {jid} | Title: {title}")
        print(f"  Decision: {dec} | Reason: {reason}")

print("\n--- REJECT REASONS AUDIT ---")
# Categories: location, seniority title, experience gate 1, experience gate 2, other
# Per company

categories = ["Location", "Seniority Title", "Experience Gate 1", "Experience Gate 2", "Other"]
company_counts = defaultdict(lambda: {cat: 0 for cat in categories})
total_counts = {cat: 0 for cat in categories}
non_reject_counts = defaultdict(lambda: {"MATCH": 0, "REVIEW": 0})
reason_examples = defaultdict(lambda: defaultdict(list))

for r in range(2, ws.max_row + 1):
    comp = str(ws.cell(r, comp_idx + 1).value or "Unknown").strip()
    dec = str(ws.cell(r, dec_idx + 1).value or "").strip()
    reason = str(ws.cell(r, reason_idx + 1).value or "").strip()
    
    if dec != "REJECT":
        non_reject_counts[comp][dec] += 1
        continue
    
    # Classify reason into category
    reason_lower = reason.lower()
    
    if "location" in reason_lower or "remote" in reason_lower:
        cat = "Location"
    elif "senior" in reason_lower or "lead" in reason_lower or "title" in reason_lower:
        cat = "Seniority Title"
    elif "requires" in reason_lower and ("gate 1" in reason_lower or ws.cell(r, exp_idx + 1).value):
        # Check if structured experience field was populated or gate 1
        exp_val = ws.cell(r, exp_idx + 1).value
        if exp_val and any(ch.isdigit() for ch in str(exp_val)):
            cat = "Experience Gate 1"
        else:
            cat = "Experience Gate 2"
    elif "requires" in reason_lower:
        cat = "Experience Gate 2"
    else:
        cat = "Other"
        
    company_counts[comp][cat] += 1
    total_counts[cat] += 1
    if len(reason_examples[comp][cat]) < 3:
        reason_examples[comp][cat].append(reason)

print(f"{'Company':<15} | {'Location':<10} | {'Seniority Title':<16} | {'Exp Gate 1':<12} | {'Exp Gate 2':<12} | {'Other':<8} | {'Total REJECT':<12}")
print("-" * 95)
grand_total_reject = 0
for comp in sorted(company_counts.keys()):
    counts = company_counts[comp]
    tot = sum(counts.values())
    grand_total_reject += tot
    print(f"{comp:<15} | {counts['Location']:<10} | {counts['Seniority Title']:<16} | {counts['Experience Gate 1']:<12} | {counts['Experience Gate 2']:<12} | {counts['Other']:<8} | {tot:<12}")

print("-" * 95)
print(f"{'TOTAL':<15} | {total_counts['Location']:<10} | {total_counts['Seniority Title']:<16} | {total_counts['Experience Gate 1']:<12} | {total_counts['Experience Gate 2']:<12} | {total_counts['Other']:<8} | {grand_total_reject:<12}")

print("\n--- Non-REJECT decisions ---")
for comp, d in sorted(non_reject_counts.items()):
    print(f"{comp}: MATCH={d['MATCH']}, REVIEW={d['REVIEW']}")
