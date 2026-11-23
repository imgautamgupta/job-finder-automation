import asyncio
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from app.sources.accenture import AccentureJobSource
from app.sources.workday import WorkdayJobSource
from app.sources.oracle_hcm import OracleHCMJobSource
from app.sources.successfactors import SuccessFactorsJobSource
from app.sources.smartrecruiters import SmartRecruitersJobSource
from app.sources.company_json import CompanyJsonJobSource
from app.sources.turbohire import TurboHireJobSource
from app.sources.greenhouse import GreenhouseJobSource

async def audit():
    print("=" * 80, flush=True)
    print("AUDITING 40 TARGET COMPANIES LIVE", flush=True)
    print("=" * 80, flush=True)

    summary = []

    # 1. Accenture
    print("\n--- Auditing Accenture ---", flush=True)
    src_acc = AccentureJobSource(is_enabled=True)
    jobs_acc = await src_acc.collect_jobs(roles=["Engineer", "Developer"], locations=["India"], max_results=10)
    print(f"Accenture: collected {len(jobs_acc)} jobs. Sample: {jobs_acc[0].title if jobs_acc else None} | URL: {jobs_acc[0].url if jobs_acc else None}", flush=True)
    summary.append({
        "company": "Accenture",
        "connector": "accenture",
        "collected": len(jobs_acc),
        "sample_title": jobs_acc[0].title if jobs_acc else None,
        "sample_url": jobs_acc[0].url if jobs_acc else None,
        "passed": len(jobs_acc) > 0 and bool(jobs_acc[0].url)
    })

    # 2. CompanyJson (Amazon, Infosys)
    print("\n--- Auditing CompanyJson (Amazon, Infosys) ---", flush=True)
    src_cj = CompanyJsonJobSource(is_enabled=True, companies=["amazon", "infosys"])
    jobs_cj = await src_cj.collect_jobs(roles=["Engineer", "Developer"], locations=["India"], max_results=10)
    for c in ["amazon", "infosys"]:
        c_jobs = [j for j in jobs_cj if c in j.company.lower() or c in (j.extra_metadata or {}).get("company_key", "")]
        c_name = "Amazon" if c == "amazon" else "Infosys"
        print(f"{c_name}: collected {len(c_jobs)} jobs. Sample: {c_jobs[0].title if c_jobs else None} | URL: {c_jobs[0].url if c_jobs else None}", flush=True)
        summary.append({
            "company": c_name,
            "connector": "company_json",
            "collected": len(c_jobs),
            "sample_title": c_jobs[0].title if c_jobs else None,
            "sample_url": c_jobs[0].url if c_jobs else None,
            "passed": len(c_jobs) > 0 and bool(c_jobs[0].url)
        })

    # 3. TurboHire (Flipkart)
    print("\n--- Auditing TurboHire (Flipkart) ---", flush=True)
    src_th = TurboHireJobSource(is_enabled=True, companies=["flipkart"])
    jobs_th = await src_th.collect_jobs(roles=["Engineer", "Developer"], locations=["India"], max_results=10)
    print(f"Flipkart: collected {len(jobs_th)} jobs. Sample: {jobs_th[0].title if jobs_th else None} | URL: {jobs_th[0].url if jobs_th else None}", flush=True)
    summary.append({
        "company": "Flipkart",
        "connector": "turbohire",
        "collected": len(jobs_th),
        "sample_title": jobs_th[0].title if jobs_th else None,
        "sample_url": jobs_th[0].url if jobs_th else None,
        "passed": len(jobs_th) > 0 and bool(jobs_th[0].url)
    })

    # 4. Workday (Adobe, Intel, NVIDIA, Salesforce, Walmart, Mastercard, Visa, PayPal, HP)
    wd_list = ["adobe", "intel", "nvidia", "salesforce", "walmart", "mastercard", "visa", "paypal", "hp"]
    print(f"\n--- Auditing Workday ({len(wd_list)} companies) ---", flush=True)
    src_wd = WorkdayJobSource(is_enabled=True, companies=wd_list)
    src_wd.request_delay_sec = 0.2
    jobs_wd = await src_wd.collect_jobs(roles=["Engineer", "Developer"], locations=["India"], max_results=10)
    for c in wd_list:
        diag = src_wd.diagnostics.get("by_company", {}).get(c, {})
        c_jobs = [j for j in jobs_wd if c in j.company.lower() or c in (j.extra_metadata or {}).get("company_key", "")]
        c_name = diag.get("name", c.capitalize())
        print(f"{c_name}: collected {len(c_jobs)} jobs. Sample: {c_jobs[0].title if c_jobs else None} | URL: {c_jobs[0].url if c_jobs else None}", flush=True)
        summary.append({
            "company": c_name,
            "connector": "workday",
            "collected": len(c_jobs),
            "sample_title": c_jobs[0].title if c_jobs else None,
            "sample_url": c_jobs[0].url if c_jobs else None,
            "passed": len(c_jobs) > 0 and bool(c_jobs[0].url)
        })

    # 5. Oracle HCM (Oracle, Dell, Hexaware, Zensar, eClerx, OFSS)
    oh_list = ["oracle", "dell", "hexaware", "zensar", "eclerx", "ofss"]
    print(f"\n--- Auditing Oracle HCM ({len(oh_list)} companies) ---", flush=True)
    src_oh = OracleHCMJobSource(is_enabled=True, companies=oh_list)
    src_oh.request_delay_sec = 0.2
    jobs_oh = await src_oh.collect_jobs(roles=["Engineer", "Developer"], locations=["India"], max_results=10)
    for c in oh_list:
        diag = src_oh.diagnostics.get("by_company", {}).get(c, {})
        c_jobs = [j for j in jobs_oh if c in j.company.lower() or c in (j.extra_metadata or {}).get("company_key", "")]
        c_name = diag.get("name", c.capitalize())
        print(f"{c_name}: collected {len(c_jobs)} jobs. Sample: {c_jobs[0].title if c_jobs else None} | URL: {c_jobs[0].url if c_jobs else None}", flush=True)
        summary.append({
            "company": c_name,
            "connector": "oracle_hcm",
            "collected": len(c_jobs),
            "sample_title": c_jobs[0].title if c_jobs else None,
            "sample_url": c_jobs[0].url if c_jobs else None,
            "passed": len(c_jobs) > 0 and bool(c_jobs[0].url)
        })

    # 6. SuccessFactors (Capgemini, Wipro, HCLTech, Deloitte India, Birlasoft, Mastek)
    sf_list = ["capgemini", "wipro", "hcltech", "deloitte_india", "birlasoft", "mastek"]
    print(f"\n--- Auditing SuccessFactors ({len(sf_list)} companies) ---", flush=True)
    src_sf = SuccessFactorsJobSource(is_enabled=True, companies=sf_list)
    src_sf.request_delay_sec = 0.2
    jobs_sf = await src_sf.collect_jobs(roles=["Engineer", "Developer"], locations=["India"], max_results=10)
    for c in sf_list:
        diag = src_sf.diagnostics.get("by_company", {}).get(c, {})
        c_jobs = [j for j in jobs_sf if c in j.company.lower() or c in (j.extra_metadata or {}).get("company_key", "")]
        c_name = diag.get("name", c.capitalize())
        print(f"{c_name}: collected {len(c_jobs)} jobs. Sample: {c_jobs[0].title if c_jobs else None} | URL: {c_jobs[0].url if c_jobs else None}", flush=True)
        summary.append({
            "company": c_name,
            "connector": "successfactors",
            "collected": len(c_jobs),
            "sample_title": c_jobs[0].title if c_jobs else None,
            "sample_url": c_jobs[0].url if c_jobs else None,
            "passed": len(c_jobs) > 0 and bool(c_jobs[0].url)
        })

    # 7. SmartRecruiters (Sopra Steria)
    print("\n--- Auditing SmartRecruiters (Sopra Steria) ---", flush=True)
    src_sr = SmartRecruitersJobSource(is_enabled=True, companies=["sopra_steria"])
    jobs_sr = await src_sr.collect_jobs(roles=["Engineer", "Developer"], locations=["India"], max_results=10)
    print(f"Sopra Steria: collected {len(jobs_sr)} jobs. Sample: {jobs_sr[0].title if jobs_sr else None} | URL: {jobs_sr[0].url if jobs_sr else None}", flush=True)
    summary.append({
        "company": "Sopra Steria",
        "connector": "smartrecruiters",
        "collected": len(jobs_sr),
        "sample_title": jobs_sr[0].title if jobs_sr else None,
        "sample_url": jobs_sr[0].url if jobs_sr else None,
        "passed": len(jobs_sr) > 0 and bool(jobs_sr[0].url)
    })

    # 8. Greenhouse (15 companies)
    gh_tokens = [
        "cloudflare", "stripe", "figma", "databricks", "elastic",
        "canonical", "gitlab", "reddit", "twilio", "mongodb",
        "brex", "affirm", "pinterest", "scaleai"
    ]
    print(f"\n--- Auditing Greenhouse ({len(gh_tokens)} companies) ---", flush=True)
    # Check each greenhouse company using GreenhouseJobSource or direct fetch
    from app.sources.greenhouse import fetch_greenhouse_postings_http, normalize_greenhouse_posting
    for token in gh_tokens:
        postings, err = fetch_greenhouse_postings_http(token)
        jobs_gh = []
        c_name = token.capitalize()
        for p in postings:
            j = normalize_greenhouse_posting(p, company_id=token, company_name=c_name)
            if j:
                jobs_gh.append(j)
        print(f"{c_name}: collected {len(jobs_gh)} jobs. Sample: {jobs_gh[0].title if jobs_gh else None} | URL: {jobs_gh[0].url if jobs_gh else None}", flush=True)
        summary.append({
            "company": c_name,
            "connector": "greenhouse",
            "collected": len(jobs_gh),
            "sample_title": jobs_gh[0].title if jobs_gh else None,
            "sample_url": jobs_gh[0].url if jobs_gh else None,
            "passed": len(jobs_gh) > 0 and bool(jobs_gh[0].url)
        })

    print("\n" + "=" * 80, flush=True)
    print(f"FINAL AUDIT SUMMARY: {len(summary)} COMPANIES TESTED", flush=True)
    print("=" * 80, flush=True)
    passed_cnt = sum(1 for s in summary if s["passed"])
    print(f"PASSED: {passed_cnt} / {len(summary)}", flush=True)
    for s in summary:
        status_str = "PASS" if s["passed"] else "FAIL"
        print(f"[{status_str}] {s['company']:<25} ({s['connector']:<15}): {s['collected']:>4} jobs | URL: {s['sample_url']}", flush=True)

if __name__ == "__main__":
    asyncio.run(audit())

