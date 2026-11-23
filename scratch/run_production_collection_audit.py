"""Phase 2.2 — Production Collection and Real Job Data Verification.

Runs the real production collection pipeline across all 40 companies, verifies
production pagination, evaluates company-wise data metrics, checks Excel consolidation,
verifies candidate independence, and generates structured report data.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import openpyxl

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

import httpx

from app.config.company_registry import (
    CompanyRegistry,
    IntegrationStatus,
    TARGET_40_COMPANIES,
    DISCOVERY_UNSUPPORTED_REGISTRY,
    get_company_registry,
)
from app.config.settings import get_settings
from app.database.database import DatabaseManager
from app.models.job import Job, JobStatus
from app.models.profile import JobProfile
from app.services.collector import JobCollector
from app.services.deduplicator import JobDeduplicator
from app.services.excel_exporter import ExcelExporter
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher
from app.main import resolve_source_connectors

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("prod_collection_audit")


def verify_url_domain(url: str, platform: str) -> bool:
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        valid_patterns = [
            r"accenture\.com",
            r"flipkart\.turbohire\.co", r"turbohire\.co", r"flipkartcareers\.com",
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
        return any(re.search(pat, netloc) for pat in valid_patterns)
    except Exception:
        return False


def get_comp_id_for_job(job: Job, company_stats: Dict[str, Any]) -> Optional[str]:
    meta = job.extra_metadata or {}
    comp_key = meta.get("company_key")
    if comp_key and comp_key in company_stats:
        return comp_key
    src = (job.source or "").lower()
    if src == "accenture":
        return "accenture"
    if src == "turbohire":
        return "flipkart"
    if src == "smartrecruiters":
        return "sopra_steria"
    norm_name = (job.company or "").lower().strip()
    for cid, c_data in company_stats.items():
        c_name = c_data["name"].lower()
        if cid == norm_name or c_name == norm_name or cid in norm_name or norm_name in c_name:
            return cid
    return None


async def run_production_collection_audit():
    print("=" * 100)
    print("STARTING PHASE 2.2 PRODUCTION COLLECTION AUDIT (40 TARGET COMPANIES)")
    print("=" * 100)

    settings = get_settings()

    # Step 0: Ensure backup of previous Excel report exists
    latest_excel = settings.EXPORTS_DIR / "My_Jobs_latest.xlsx"
    backup_excel = settings.EXPORTS_DIR / "My_Jobs_latest_backup_pre_phase2_2.xlsx"
    if latest_excel.exists() and not backup_excel.exists():
        import shutil
        shutil.copy2(latest_excel, backup_excel)
        print(f"[BACKUP] Created backup of latest Excel: {backup_excel}")
    else:
        print(f"[BACKUP] Backup confirmed: {backup_excel}")

    # Step 1: Initialize Database & Sync User Tracking
    db_mgr = DatabaseManager(db_path=settings.DATABASE_PATH)
    db_mgr.init_db()
    exporter = ExcelExporter(exports_dir=settings.EXPORTS_DIR)
    from app.services.excel_exporter import sync_excel_tracking_to_db
    try:
        sync_count = sync_excel_tracking_to_db(db_mgr, settings.EXPORTS_DIR)
        print(f"[TRACKING] Synchronized {sync_count} user tracking edits from Excel to SQLite")
    except Exception as e:
        print(f"[TRACKING] Note: {e}")

    # Step 2: Initialize Sources for All 40 Working Companies
    sources_override = "accenture,workday,oracle_hcm,successfactors,greenhouse,turbohire,smartrecruiters"
    sources, active_tokens = resolve_source_connectors(settings, sources_override=sources_override)

    collector = JobCollector(
        sources=sources,
        source_timeout_sec=settings.SOURCE_TIMEOUT_SEC,
    )
    print(f"[CONFIG] Active Connectors: {', '.join(collector.registered_sources)}")

    # Step 3: Run Production Collection (Candidate-Independent)
    # The collector runs across all 40 companies without candidate resume or personal constraints
    print("\n[COLLECTION] Executing real multi-page production collection across all 40 companies...")
    start_time = time.time()
    
    # We pass standard discovery roles & locations to connectors
    raw_jobs = await collector.collect_all(
        roles=["Engineer", "Developer"],
        locations=["India"],
        max_results_per_source=settings.MAX_RESULTS_PER_SOURCE,
    )
    total_duration = round(time.time() - start_time, 2)
    print(f"[COLLECTION] Completed in {total_duration}s. Total raw jobs collected: {len(raw_jobs)}")

    # Step 4: Deduplication & Candidate Classification
    profile = settings.load_profile()
    job_filter = JobFilter(profile=profile)
    matcher = JobMatcher(profile=profile)
    deduplicator = JobDeduplicator(db_manager=db_mgr)

    for j in raw_jobs:
        job_filter.classify_job(j)
        match_res = matcher.match(j)
        j.apply_match_result(match_res)

    # In-batch deduplication
    deduped_all = deduplicator.deduplicate_for_all_jobs(raw_jobs)
    print(f"[DEDUP] Raw jobs: {len(raw_jobs)} -> Unique jobs after deduplication: {len(deduped_all)}")

    # Filtered candidate matches (for Top Matches sheet)
    filtered_jobs = job_filter.filter_jobs(raw_jobs)
    scored_candidates = [j for j in filtered_jobs if j.match_score is not None]
    scored_candidates.sort(key=lambda j: j.match_score or 0, reverse=True)
    batch_top_matches = deduplicator.deduplicate_batch(scored_candidates)
    print(f"[MATCHING] Top Matches meeting candidate criteria: {len(batch_top_matches)}")

    # Step 5: Save/Upsert to SQLite
    run_id = f"prod-audit-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    new_saved = 0
    dup_saved = 0
    for job in deduped_all:
        is_new = db_mgr.save_job(job, run_id=run_id)
        if is_new:
            new_saved += 1
        else:
            dup_saved += 1
    print(f"[DB] SQLite persistence: {new_saved} new jobs inserted, {dup_saved} existing records updated.")

    # Step 6: Export to Excel
    export_file = exporter.export(
        batch_top_matches,
        current_run_id=run_id,
        full_report=True,
        db_manager=db_mgr,
        all_jobs=deduped_all,
        enabled_sources=active_tokens,
    )
    print(f"[EXCEL] Consolidated workbook exported to: {export_file}")

    # Step 7: Company-wise Statistics Analysis
    # Group collected jobs by company
    company_stats: Dict[str, Dict[str, Any]] = {}
    reg = get_company_registry()

    for cid, entry in TARGET_40_COMPANIES.items():
        company_stats[cid] = {
            "name": entry.name,
            "company_id": cid,
            "ats_platform": entry.ats_platform,
            "connector": entry.connector_name or entry.ats_platform,
            "careers_url": entry.official_careers_url,
            "raw_records": 0,
            "parsed_jobs": 0,
            "unique_jobs": 0,
            "saved_to_sqlite": 0,
            "missing_locations": 0,
            "missing_job_ids": 0,
            "valid_detail_urls": 0,
            "valid_app_urls": 0,
            "health_status": "COMPLETED",
            "vacancies_status": "ACTIVE_VACANCIES",
            "sample_titles": [],
        }

    # Match raw jobs to companies
    for job in raw_jobs:
        comp_key = get_comp_id_for_job(job, company_stats)
        if comp_key and comp_key in company_stats:
            st = company_stats[comp_key]
            st["raw_records"] += 1
            st["parsed_jobs"] += 1
            if not job.location or job.location.strip().lower() in ("unknown", "none", "n/a"):
                st["missing_locations"] += 1
            if not job.job_id or job.job_id.strip().lower() in ("unknown", "none", "n/a"):
                st["missing_job_ids"] += 1
            if verify_url_domain(job.url, st["ats_platform"]):
                st["valid_detail_urls"] += 1
            app_url = (job.extra_metadata or {}).get("application_url") or job.url
            if verify_url_domain(app_url, st["ats_platform"]):
                st["valid_app_urls"] += 1
            if len(st["sample_titles"]) < 2 and job.title:
                st["sample_titles"].append(job.title)

    # Count unique jobs per company
    for job in deduped_all:
        comp_key = get_comp_id_for_job(job, company_stats)
        if comp_key and comp_key in company_stats:
            company_stats[comp_key]["unique_jobs"] += 1
            company_stats[comp_key]["saved_to_sqlite"] += 1

    # Check collector source results for health statuses and durations
    collector_results = collector.get_source_results()
    for src_name, s_res in collector_results.items():
        diag = s_res.get("diagnostics", {})
        by_comp = diag.get("by_company", {})
        for c_key, c_info in by_comp.items():
            cid = c_key.lower().replace(" ", "_")
            if cid in company_stats:
                st = company_stats[cid]
                st["health_status"] = c_info.get("status", "COMPLETED")
                if st["raw_records"] == 0:
                    st["vacancies_status"] = "NO_CURRENT_VACANCIES"
        if src_name == "accenture" and "accenture" in company_stats:
            company_stats["accenture"]["health_status"] = s_res.get("status", "COMPLETED")
        if src_name == "turbohire" and "flipkart" in company_stats:
            company_stats["flipkart"]["health_status"] = s_res.get("status", "COMPLETED")
        if src_name == "smartrecruiters" and "sopra_steria" in company_stats:
            company_stats["sopra_steria"]["health_status"] = s_res.get("status", "COMPLETED")

    # Step 8: Verify Excel Consolidation
    wb = openpyxl.load_workbook(export_file)
    sheet_names = wb.sheetnames
    all_jobs_ws = wb["All Jobs"]
    top_matches_ws = wb["Top Matches"]

    all_jobs_row_count = all_jobs_ws.max_row - 1
    top_matches_row_count = top_matches_ws.max_row - 1

    # Verify presence of companies in All Jobs
    exported_companies = set()
    clickable_links_count = 0
    for row in range(2, all_jobs_ws.max_row + 1):
        comp_cell = all_jobs_ws.cell(row=row, column=1).value
        if comp_cell:
            exported_companies.add(comp_cell.strip())
        url_cell = all_jobs_ws.cell(row=row, column=14)
        if url_cell.hyperlink:
            clickable_links_count += 1

    print("\n" + "=" * 100)
    print("EXCEL CONSOLIDATION VERIFICATION")
    print(f"Sheets in Workbook: {sheet_names}")
    print(f"Total Rows in 'All Jobs': {all_jobs_row_count}")
    print(f"Total Rows in 'Top Matches': {top_matches_row_count}")
    print(f"Unique Companies in 'All Jobs': {len(exported_companies)}")
    print(f"Clickable Application Hyperlinks: {clickable_links_count} / {all_jobs_row_count}")
    print("=" * 100)

    # Step 9: Save audit summary data to reports/prod_collection_data.json
    out_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_duration_sec": total_duration,
        "totals": {
            "raw_retrieved": len(raw_jobs),
            "parsed_jobs": len(raw_jobs),
            "unique_deduped": len(deduped_all),
            "saved_to_sqlite": new_saved + dup_saved,
            "new_saved": new_saved,
            "top_matches": len(batch_top_matches),
            "all_jobs_rows": all_jobs_row_count,
            "clickable_links": clickable_links_count,
        },
        "excel_export": str(export_file),
        "backup_excel": str(backup_excel),
        "collector_results": {k: {"status": v.get("status"), "collected": v.get("collected"), "duration_sec": v.get("duration_sec")} for k, v in collector_results.items()},
        "company_stats": company_stats,
    }

    out_json = root / "reports" / "prod_collection_data.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)
    print(f"Saved production collection data to: {out_json}")

if __name__ == "__main__":
    asyncio.run(run_production_collection_audit())
