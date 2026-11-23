import asyncio
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

import httpx
from datetime import datetime, timezone

from app.config.company_registry import TARGET_40_COMPANIES
from app.sources.accenture import AccentureJobSource
from app.sources.workday import WorkdayJobSource
from app.sources.oracle_hcm import OracleHCMJobSource
from app.sources.successfactors import SuccessFactorsJobSource
from app.sources.smartrecruiters import SmartRecruitersJobSource
from app.sources.turbohire import TurboHireJobSource
from app.sources.greenhouse import fetch_greenhouse_postings_http, parse_greenhouse_posting

async def test_all_40():
    print("=" * 100, flush=True)
    print("TESTING EXACT 40 TARGET WORKING COMPANIES LIVE", flush=True)
    print("=" * 100, flush=True)

    results = []

    # 1. Accenture
    print("Testing 1/40: Accenture...", flush=True)
    try:
        src_acc = AccentureJobSource(is_enabled=True)
        jobs_acc = await src_acc.collect_jobs(roles=["Engineer"], locations=["India"], max_results=5)
    except Exception as e:
        print(f"  Accenture error: {e}", flush=True)
        jobs_acc = []
    # If transient timeout, retry once
    if not jobs_acc:
        try:
            print("  Retrying Accenture with fresh client...", flush=True)
            jobs_acc = await src_acc.collect_jobs(roles=["Engineer"], locations=["India"], max_results=5)
        except Exception as e:
            print(f"  Accenture retry error: {e}", flush=True)
    results.append({
        "id": "accenture",
        "name": "Accenture",
        "connector": "accenture",
        "count": len(jobs_acc),
        "title": jobs_acc[0].title if jobs_acc else None,
        "url": jobs_acc[0].url if jobs_acc else None,
        "location": jobs_acc[0].location if jobs_acc else None,
    })

    # 2. Flipkart
    print("Testing 2/40: Flipkart...", flush=True)
    try:
        src_th = TurboHireJobSource(is_enabled=True, companies=["flipkart"])
        jobs_th = await src_th.collect_jobs(roles=["Engineer"], locations=["India"], max_results=5)
    except Exception as e:
        print(f"  Flipkart error: {e}", flush=True)
        jobs_th = []
    if not jobs_th:
        try:
            print("  Retrying Flipkart...", flush=True)
            jobs_th = await src_th.collect_jobs(roles=["Engineer"], locations=["India"], max_results=5)
        except Exception as e:
            print(f"  Flipkart retry error: {e}", flush=True)
    results.append({
        "id": "flipkart",
        "name": "Flipkart",
        "connector": "turbohire",
        "count": len(jobs_th),
        "title": jobs_th[0].title if jobs_th else None,
        "url": jobs_th[0].url if jobs_th else None,
        "location": jobs_th[0].location if jobs_th else None,
    })

    # 3. Sopra Steria
    print("Testing 3/40: Sopra Steria...", flush=True)
    try:
        src_sr = SmartRecruitersJobSource(is_enabled=True, companies=["sopra_steria"])
        jobs_sr = await src_sr.collect_jobs(roles=["Engineer"], locations=["India"], max_results=5)
    except Exception as e:
        print(f"  Sopra Steria error: {e}", flush=True)
        jobs_sr = []
    results.append({
        "id": "sopra_steria",
        "name": "Sopra Steria",
        "connector": "smartrecruiters",
        "count": len(jobs_sr),
        "title": jobs_sr[0].title if jobs_sr else None,
        "url": jobs_sr[0].url if jobs_sr else None,
        "location": jobs_sr[0].location if jobs_sr else None,
    })

    # 4-12. Workday (9)
    wd_comps = [
        ("adobe", "Adobe"),
        ("intel", "Intel"),
        ("nvidia", "NVIDIA"),
        ("salesforce", "Salesforce"),
        ("walmart", "Walmart Global Tech"),
        ("mastercard", "Mastercard"),
        ("visa", "Visa"),
        ("paypal", "PayPal"),
        ("hp", "HP"),
    ]
    for cid, cname in wd_comps:
        idx = len(results) + 1
        print(f"Testing {idx}/40: {cname} (Workday)...", flush=True)
        try:
            src = WorkdayJobSource(is_enabled=True, companies=[cid])
            src.request_delay_sec = 0.1
            jobs = await src.collect_jobs(roles=["Engineer"], locations=["India"], max_results=5)
        except Exception as e:
            print(f"  {cname} error: {e}", flush=True)
            jobs = []
        results.append({
            "id": cid,
            "name": cname,
            "connector": "workday",
            "count": len(jobs),
            "title": jobs[0].title if jobs else None,
            "url": jobs[0].url if jobs else None,
            "location": jobs[0].location if jobs else None,
        })

    # 13-18. Oracle Cloud HCM (6)
    oh_comps = [
        ("oracle", "Oracle"),
        ("dell", "Dell Technologies"),
        ("hexaware", "Hexaware Technologies"),
        ("zensar", "Zensar Technologies"),
        ("eclerx", "eClerx"),
        ("ofss", "Oracle Financial Services Software"),
    ]
    for cid, cname in oh_comps:
        idx = len(results) + 1
        print(f"Testing {idx}/40: {cname} (Oracle HCM)...", flush=True)
        try:
            src = OracleHCMJobSource(is_enabled=True, companies=[cid])
            src.request_delay_sec = 0.1
            jobs = await src.collect_jobs(roles=["Engineer"], locations=["India"], max_results=5)
        except Exception as e:
            print(f"  {cname} error: {e}", flush=True)
            jobs = []
        results.append({
            "id": cid,
            "name": cname,
            "connector": "oracle_hcm",
            "count": len(jobs),
            "title": jobs[0].title if jobs else None,
            "url": jobs[0].url if jobs else None,
            "location": jobs[0].location if jobs else None,
        })

    # 19-23. SuccessFactors (5)
    sf_comps = [
        ("capgemini", "Capgemini"),
        ("wipro", "Wipro"),
        ("hcltech", "HCLTech"),
        ("birlasoft", "Birlasoft"),
        ("mastek", "Mastek"),
    ]
    for cid, cname in sf_comps:
        idx = len(results) + 1
        print(f"Testing {idx}/40: {cname} (SuccessFactors)...", flush=True)
        try:
            src = SuccessFactorsJobSource(is_enabled=True, companies=[cid])
            src.request_delay_sec = 0.1
            jobs = await src.collect_jobs(roles=["Engineer"], locations=["India"], max_results=5)
        except Exception as e:
            print(f"  {cname} error: {e}", flush=True)
            jobs = []
        results.append({
            "id": cid,
            "name": cname,
            "connector": "successfactors",
            "count": len(jobs),
            "title": jobs[0].title if jobs else None,
            "url": jobs[0].url if jobs else None,
            "location": jobs[0].location if jobs else None,
        })

    # 24-40. Greenhouse (17)
    gh_comps = [
        ("stripe", "Stripe"),
        ("cloudflare", "Cloudflare"),
        ("databricks", "Databricks"),
        ("elastic", "Elastic"),
        ("canonical", "Canonical"),
        ("mongodb", "MongoDB"),
        ("brex", "Brex"),
        ("gitlab", "GitLab"),
        ("affirm", "Affirm"),
        ("lyft", "Lyft"),
        ("scaleai", "Scale AI"),
        ("pinterest", "Pinterest"),
        ("reddit", "Reddit"),
        ("figma", "Figma"),
        ("twilio", "Twilio"),
        ("instacart", "Instacart"),
        ("airtable", "Airtable"),
    ]
    for cid, cname in gh_comps:
        idx = len(results) + 1
        print(f"Testing {idx}/40: {cname} (Greenhouse)...", flush=True)
        try:
            postings = fetch_greenhouse_postings_http(cid)
            jobs = []
            for p in postings:
                j = parse_greenhouse_posting(p, company_id=cid)
                if j:
                    j.company = cname
                    jobs.append(j)
                    if len(jobs) >= 5:
                        break
        except Exception as e:
            print(f"  {cname} error: {e}", flush=True)
            jobs = []
        results.append({
            "id": cid,
            "name": cname,
            "connector": "greenhouse",
            "count": len(jobs),
            "title": jobs[0].title if jobs else None,
            "url": jobs[0].url if jobs else None,
            "location": jobs[0].location if jobs else None,
        })

    print("\n" + "=" * 100, flush=True)
    print(f"FINAL AUDIT RESULTS: {len(results)} TARGET COMPANIES", flush=True)
    print("=" * 100, flush=True)

    passed_count = 0
    for i, r in enumerate(results, 1):
        is_pass = r["count"] > 0 and bool(r["url"]) and bool(r["title"])
        if is_pass:
            passed_count += 1
        status_tag = "PASS" if is_pass else "FAIL"
        print(f"{i:2d}. [{status_tag}] {r['name']:<28} ({r['connector']:<15}): {r['count']} jobs | Sample: '{r['title']}' | Loc: '{r['location']}' | URL: {r['url']}", flush=True)

    print("-" * 100, flush=True)
    print(f"TOTAL WORKING COMPANIES: {passed_count} / {len(results)}", flush=True)

if __name__ == "__main__":
    asyncio.run(test_all_40())
