"""Safe URL verification on a representative sample of all 40 target companies."""

import asyncio
import json
from pathlib import Path
import re
import urllib.parse
import openpyxl
import httpx

root = Path(__file__).resolve().parent.parent
excel_path = root / "data" / "exports" / "My_Jobs_latest.xlsx"

wb = openpyxl.load_workbook(excel_path)
ws = wb["All Jobs"]

# Group jobs by company
company_samples = {}
for r in range(2, ws.max_row + 1):
    comp = str(ws.cell(row=r, column=1).value or "").strip()
    title = str(ws.cell(row=r, column=2).value or "").strip()
    job_id = str(ws.cell(row=r, column=3).value or "").strip()
    url = str(ws.cell(row=r, column=14).value or "").strip()
    
    if comp not in company_samples:
        company_samples[comp] = []
    if len(company_samples[comp]) < 2:
        company_samples[comp].append({"title": title, "job_id": job_id, "url": url})

print(f"Sampled {sum(len(v) for v in company_samples.values())} URLs across {len(company_samples)} companies.")

# Domain regex patterns for official domains
OFFICIAL_DOMAINS = [
    r"accenture\.com",
    r"turbohire\.co", r"flipkartcareers\.com",
    r"smartrecruiters\.com", r"soprasteria\.(in|com)",
    r"myworkdayjobs\.com", r"workday\.com", r"hp\.com", r"adobe\.com", r"intel\.com",
    r"nvidia\.com", r"salesforce\.com", r"walmart\.com", r"mastercard\.com", r"visa\.com", r"paypal\.com",
    r"oraclecloud\.com", r"oracle\.com", r"dell\.com", r"hexaware\.com", r"zensar\.com", r"eclerx\.com",
    r"successfactors\.com", r"capgemini\.com", r"wipro\.com", r"hcltech\.com", r"birlasoft\.com", r"mastek\.com",
    r"greenhouse\.io", r"careerpuck\.com", r"stripe\.com", r"cloudflare\.com", r"databricks\.com",
    r"elastic\.co", r"canonical\.com", r"mongodb\.com", r"brex\.com", r"gitlab\.com", r"affirm\.com",
    r"lyft\.com", r"scale\.com", r"pinterestcareers\.com", r"redditinc\.com", r"figma\.com",
    r"twilio\.com", r"instacart\.careers", r"airtable\.com",
]

INACTIVE_PATTERNS = [
    r"no longer available",
    r"job has expired",
    r"requisition has been closed",
    r"this position has been filled",
    r"job not found",
    r"page not found",
    r"404 not found",
]

async def check_url(client: httpx.AsyncClient, item: dict, comp: str) -> dict:
    url = item["url"]
    title = item["title"]
    
    res = {
        "company": comp,
        "title": title,
        "url": url,
        "domain_valid": False,
        "opened": False,
        "http_status": None,
        "confirmed_active": False,
        "note": "",
    }
    
    # 1. Domain format
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        res["domain_valid"] = any(re.search(pat, netloc) for pat in OFFICIAL_DOMAINS)
    except Exception as e:
        res["note"] = f"Invalid URL structure: {e}"
        return res
        
    if not res["domain_valid"]:
        res["note"] = f"Unrecognized domain: {netloc}"
        return res

    # 2. HTTP Request (safe GET with headers)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    try:
        resp = await client.get(url, headers=headers, timeout=12.0)
        res["http_status"] = resp.status_code
        if resp.status_code in (200, 301, 302, 303, 307, 308):
            res["opened"] = True
            
            # Check for inactive job phrases
            text_lower = resp.text.lower()
            is_inactive = any(re.search(pat, text_lower) for pat in INACTIVE_PATTERNS)
            if not is_inactive and len(resp.text) > 200:
                res["confirmed_active"] = True
                res["note"] = f"HTTP {resp.status_code} OK (active posting page)"
            else:
                res["note"] = f"HTTP {resp.status_code} (inactive/closed notice detected)"
        elif resp.status_code == 403:
            # Cloudflare / Bot detection on direct browser page
            res["opened"] = False
            res["note"] = f"HTTP 403 (WAF/Cloudflare bot challenge on direct browser URL)"
        else:
            res["note"] = f"HTTP {resp.status_code}"
    except httpx.TimeoutException:
        res["note"] = "Timeout (>=12s)"
    except Exception as e:
        res["note"] = f"Network/SSL error: {str(e)[:50]}"
        
    return res

async def main():
    results = []
    # Test 1 sample per company (40 companies) to be polite and avoid hammering
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for comp, items in sorted(company_samples.items()):
            first_item = items[0]
            r = await check_url(client, first_item, comp)
            results.append(r)
            print(f"[{'PASS' if r['opened'] else 'WARN'}] {comp:<25} | Domain: {r['domain_valid']} | Opened: {r['opened']} | Status: {r['http_status']} | Note: {r['note']}")
            await asyncio.sleep(0.5)

    # Summary
    domain_valid_count = sum(1 for r in results if r["domain_valid"])
    opened_count = sum(1 for r in results if r["opened"])
    active_count = sum(1 for r in results if r["confirmed_active"])
    unverified_count = sum(1 for r in results if not r["opened"])

    print("\n" + "=" * 80)
    print("URL VALIDATION SUMMARY (1 sample per company across 40 companies):")
    print(f"  Total companies sampled: {len(results)}")
    print(f"  Domain-valid URLs: {domain_valid_count} / {len(results)} ({domain_valid_count/len(results)*100:.1f}%)")
    print(f"  Successfully opened job pages: {opened_count} / {len(results)} ({opened_count/len(results)*100:.1f}%)")
    print(f"  Confirmed active postings: {active_count} / {len(results)} ({active_count/len(results)*100:.1f}%)")
    print(f"  Links that could not be verified (bot challenges/WAF): {unverified_count} / {len(results)}")
    print("=" * 80)

    # Save to json for report
    out_file = root / "reports" / "url_audit_sample_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total_sampled": len(results),
                "domain_valid": domain_valid_count,
                "opened": opened_count,
                "confirmed_active": active_count,
                "unverified": unverified_count,
            },
            "results": results,
        }, f, indent=2)
    print(f"Saved audit results to {out_file}")

if __name__ == "__main__":
    asyncio.run(main())

