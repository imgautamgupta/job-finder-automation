"""Main orchestration entry point for Job Finder Automation (Phase 7A)."""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

# Ensure project root is in sys.path when run directly
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.config.settings import get_settings
from app.config.company_registry import get_company_registry, IntegrationStatus
from app.database.database import DatabaseManager
from app.services.collector import JobCollector
from app.services.deduplicator import JobDeduplicator
from app.services.excel_exporter import ExcelExporter, derive_country
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher
from app.services.recommender import JobRecommender
from app.services.resume_intelligence import ResumeIntelligenceService
from app.services.resume_parser import ResumeParser
from app.sources.accenture import AccentureJobSource
from app.sources.company_json import CompanyJsonJobSource
from app.sources.greenhouse import GreenhouseJobSource
from app.sources.lever import LeverJobSource
from app.sources.linkedin import LinkedInJobSource
from app.sources.naukri import NaukriJobSource
from app.sources.oracle_hcm import OracleHCMJobSource
from app.sources.smartrecruiters import SmartRecruitersJobSource
from app.sources.successfactors import SuccessFactorsJobSource
from app.sources.turbohire import TurboHireJobSource
from app.sources.workday import WorkdayJobSource
from app.utils.lock import JobFinderLock, cleanup_old_logs


def setup_logging(log_level: str = "INFO") -> None:
    """Configure console logging format."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def resolve_source_connectors(
    settings: Any,
    sources_override: Optional[str] = None,
) -> tuple[list[Any], list[str]]:
    """Determine enabled source connectors and company portal configurations based on ENABLED_SOURCES or CLI override."""
    if sources_override:
        enabled_tokens = [s.strip().lower() for s in sources_override.split(",") if s.strip()]
    else:
        enabled_tokens = settings.enabled_sources_list

    token_set = set(enabled_tokens)
    logger = logging.getLogger("job_finder_automation")
    logger.info("[CONFIG] Active source tokens for this run: %s", sorted(token_set))

    # All verified Workday companies
    all_workday = ["adobe", "intel", "nvidia", "salesforce", "walmart", "mastercard", "visa", "paypal", "hp"]
    # All verified CompanyJson companies
    all_company_json = ["amazon", "infosys"]
    # All verified SuccessFactors companies (including Birlasoft, Mastek)
    all_successfactors = [
        "capgemini", "wipro", "hcltech",
        "birlasoft", "mastek"
    ]
    # All verified Oracle HCM companies (including Hexaware, Zensar, eClerx, OFSS)
    all_oracle_hcm = ["oracle", "dell", "hexaware", "zensar", "eclerx", "ofss"]
    # All verified SmartRecruiters companies (including Sopra Steria)
    all_smartrecruiters = ["sopra_steria"]
    # All verified TurboHire companies
    all_turbohire = ["flipkart"]
    # All verified Greenhouse companies (17 top tech employers)
    all_greenhouse = [
        "stripe", "cloudflare", "databricks", "elastic", "canonical",
        "mongodb", "brex", "gitlab", "affirm", "lyft", "scaleai",
        "pinterest", "reddit", "figma", "twilio", "instacart", "airtable"
    ]

    # 1. Accenture
    accenture_enabled = "accenture" in token_set

    # 2. Workday
    if "workday" in token_set:
        workday_comps = list(all_workday)
        workday_enabled = True
    else:
        workday_comps = [c for c in all_workday if c in token_set]
        workday_enabled = len(workday_comps) > 0

    # 3. CompanyJson (Amazon, Infosys)
    if "company_json" in token_set:
        cj_comps = list(all_company_json)
        cj_enabled = True
    else:
        cj_comps = [c for c in all_company_json if c in token_set]
        cj_enabled = len(cj_comps) > 0

    # 4. SuccessFactors (Capgemini, Wipro, HCLTech, Deloitte, Birlasoft, Mastek)
    if "successfactors" in token_set:
        sf_comps = list(all_successfactors)
        sf_enabled = True
    else:
        sf_comps = []
        for c in all_successfactors:
            if c in token_set:
                sf_comps.append(c)
        if any("deloitte" in t for t in token_set):
            for d in ["deloitte_india", "deloitte_srilanka", "deloitte_mauritius"]:
                if d in token_set or "deloitte" in token_set:
                    sf_comps.append(d)
        sf_enabled = len(sf_comps) > 0

    # 5. Oracle HCM (Oracle, Dell, Hexaware, Zensar, eClerx, OFSS)
    if "oracle_hcm" in token_set:
        oh_comps = list(all_oracle_hcm)
        oh_enabled = True
    else:
        oh_comps = [c for c in all_oracle_hcm if c in token_set]
        oh_enabled = len(oh_comps) > 0

    # 6. TurboHire (Flipkart)
    turbohire_enabled = "turbohire" in token_set or "flipkart" in token_set
    th_comps = ["flipkart"] if turbohire_enabled else []

    # 7. SmartRecruiters (Sopra Steria)
    if "smartrecruiters" in token_set:
        sr_comps = list(all_smartrecruiters)
        smartrecruiters_enabled = True
    else:
        sr_comps = [c for c in all_smartrecruiters if c in token_set or c.replace("_", "") in token_set]
        smartrecruiters_enabled = len(sr_comps) > 0 or (
            "smartrecruiters" in token_set and getattr(settings, "SMARTRECRUITERS_ENABLED", False)
        )

    # 8. Greenhouse
    if "greenhouse" in token_set:
        gh_comps = list(all_greenhouse)
        greenhouse_enabled = True
    else:
        gh_comps = [c for c in all_greenhouse if c in token_set]
        greenhouse_enabled = len(gh_comps) > 0 or (
            "greenhouse" in token_set and getattr(settings, "GREENHOUSE_ENABLED", False)
        )

    # 9. Unverified / platform sources (always disabled unless explicitly enabled in config and tokens)
    linkedin_enabled = "linkedin" in token_set and getattr(settings, "LINKEDIN_ENABLED", False)
    naukri_enabled = "naukri" in token_set and getattr(settings, "NAUKRI_ENABLED", False)
    lever_enabled = "lever" in token_set and getattr(settings, "LEVER_ENABLED", False)

    sources = [
        AccentureJobSource(is_enabled=accenture_enabled, settings=settings),
        WorkdayJobSource(is_enabled=workday_enabled, settings=settings, companies=workday_comps),
        CompanyJsonJobSource(is_enabled=cj_enabled, settings=settings, companies=cj_comps),
        SuccessFactorsJobSource(is_enabled=sf_enabled, settings=settings, companies=sf_comps),
        OracleHCMJobSource(is_enabled=oh_enabled, settings=settings, companies=oh_comps),
        TurboHireJobSource(is_enabled=turbohire_enabled, settings=settings, companies=th_comps),
        LinkedInJobSource(is_enabled=linkedin_enabled, settings=settings),
        NaukriJobSource(is_enabled=naukri_enabled, settings=settings),
        LeverJobSource(is_enabled=lever_enabled, settings=settings),
        GreenhouseJobSource(is_enabled=greenhouse_enabled, settings=settings, companies=gh_comps if gh_comps else None),
        SmartRecruitersJobSource(is_enabled=smartrecruiters_enabled, settings=settings, companies=sr_comps if sr_comps else None),
    ]

    active_tokens = list(token_set)
    return sources, active_tokens


async def run_pipeline(full_report: bool = False, sources_override: Optional[str] = None) -> None:
    """Execute the end-to-end job discovery, filtering, deduplication, and export pipeline."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    logger = logging.getLogger("job_finder_automation")

    # 1. Unique Run Identifier
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    run_started_at = datetime.now(timezone.utc)

    logger.info("==================================================")
    logger.info("   Starting Job Finder Automation Pipeline        ")
    logger.info("==================================================")
    logger.info("[RUN] Started: %s", run_id)
    logger.info("[ENV] Project root: %s", project_root)
    logger.info("[ENV] Python executable: %s", sys.executable)

    # 2. Acquire Process Lock to prevent overlapping runs
    lock = JobFinderLock(lock_path=settings.LOCK_FILE)
    if not lock.acquire(run_id=run_id):
        logger.error(
            "[LOCK] Execution aborted: Another instance of Job Finder is already running. "
            "Lock file: %s",
            settings.LOCK_FILE,
        )
        sys.exit(3)

    # 3. Initialize Database & Run Record
    db_manager = DatabaseManager(db_path=settings.DATABASE_PATH)

    # Synchronize User Tracking Edits from Excel into SQLite (Task 12)
    try:
        from app.services.excel_exporter import sync_excel_tracking_to_db
        synced_count = sync_excel_tracking_to_db(db_manager, settings.EXPORTS_DIR)
        if synced_count > 0:
            logger.info("[TRACKING] Synchronized %d user tracking updates from Excel to SQLite", synced_count)
    except Exception as sync_err:
        logger.warning("[TRACKING] Error synchronizing tracking edits from Excel: %s", sync_err)

    # 4. Load User Profile Preferences
    profile = settings.load_profile()
    logger.info("Loaded profile from: %s", settings.PROFILE_PATH)
    logger.info("Target Roles: %s", ", ".join(profile.target_roles) or "None specified")
    logger.info("Locations: %s", ", ".join(profile.preferred_locations) or "None specified")
    logger.info(
        "Preferences: Remote Allowed=%s, Internships Allowed=%s, Freshers Allowed=%s",
        profile.preferences.remote_allowed,
        profile.preferences.internship_allowed,
        profile.preferences.fresher_allowed,
    )
    logger.info("Skills loaded: %d | Excluded keywords: %d", len(profile.skills), len(profile.negative_keywords))

    # 4. Initialize Source Connectors (Task 16 Single Switch ENABLED_SOURCES / CLI Override)
    sources, active_tokens = resolve_source_connectors(settings, sources_override=sources_override)
    collector = JobCollector(
        sources=sources,
        source_timeout_sec=settings.SOURCE_TIMEOUT_SEC,
    )
    logger.info("Active Sources: %s", ", ".join(collector.registered_sources))


    db_manager.create_pipeline_run(
        run_id=run_id,
        started_at=run_started_at,
        status="RUNNING",
        sources_attempted=collector.registered_sources,
    )

    # 5. Initialize Pipeline Services
    job_filter = JobFilter(profile=profile)
    matcher = JobMatcher(profile=profile)
    recommender = JobRecommender(profile=profile)
    resume_parser = ResumeParser()
    resumes_map = resume_parser.load_resumes(getattr(settings, "RESUME_PATH", ""))
    resume_intel = ResumeIntelligenceService(profile=profile, resume_profiles=resumes_map)
    deduplicator = JobDeduplicator(db_manager=db_manager)
    exporter = ExcelExporter(exports_dir=settings.EXPORTS_DIR)

    raw_jobs = []
    filtered_jobs = []
    batch_jobs = []
    new_jobs_count = 0
    duplicate_jobs_count = 0
    export_file = None
    run_status = "COMPLETED"

    try:
        # Step 1: Collect Jobs across sources
        logger.info("[SOURCE] Starting multi-source collection...")
        raw_jobs = await collector.collect_all(
            roles=profile.target_roles,
            locations=profile.preferred_locations,
            max_results_per_source=settings.MAX_RESULTS_PER_SOURCE,
        )
        logger.info("[SOURCE] Aggregated raw listings collected: %d", len(raw_jobs))

        # Log source-level results
        source_results = collector.get_source_results()
        for src_name, s_info in source_results.items():
            s_status = s_info.get("status", "UNKNOWN")
            s_coll = s_info.get("collected", 0)
            s_err = s_info.get("error")
            if s_status == "COMPLETED":
                logger.info("[SOURCE] %s: collected=%d", src_name.capitalize(), s_coll)
            elif s_status == "PARTIAL":
                logger.warning("[SOURCE] %s: PARTIAL (collected=%d, error=%s)", src_name.capitalize(), s_coll, s_err)
            elif s_status == "BLOCKED":
                logger.warning("[SOURCE] %s: blocked (%s)", src_name.capitalize(), s_err)
            elif s_status == "DISABLED":
                logger.debug("[SOURCE] %s: disabled", src_name.capitalize())
            else:
                logger.warning("[SOURCE] %s: status=%s (error=%s, collected=%d)", src_name.capitalize(), s_status, s_err, s_coll)

        # Step 2: Filter Jobs by User Preferences and Classify
        logger.info("[FILTER] Filtering jobs against profile preferences...")
        registry = get_company_registry()
        for src_name, s_info in source_results.items():
            by_comp = (s_info.get("diagnostics") or {}).get("by_company", {})
            if by_comp:
                for c_key, c_info in by_comp.items():
                    c_id = c_key.lower().replace(" ", "_")
                    c_coll = c_info.get("collected", 0)
                    c_st = c_info.get("status", "COMPLETED")
                    c_err = c_info.get("error")
                    registry.update_health(
                        company_id=c_id,
                        status=c_st,
                        jobs_retrieved=c_coll,
                        error=c_err,
                    )
            elif src_name.lower() == "accenture":
                c_coll = s_info.get("collected", 0)
                c_st = s_info.get("status", "COMPLETED")
                c_err = s_info.get("error")
                registry.update_health(
                    company_id="accenture",
                    status=c_st,
                    jobs_retrieved=c_coll,
                    error=c_err,
                )

        for job in raw_jobs:
            job_filter.classify_job(job)

        filtered_jobs = job_filter.filter_jobs(raw_jobs)
        logger.info("[FILTER] %d jobs passed preference filters.", len(filtered_jobs))

        # Step 3: Deterministic Scoring & Matching
        logger.info("[MATCH] Calculating match scores and categories...")
        scored_jobs = []
        for job in filtered_jobs:
            match_res = matcher.match(job)
            job.apply_match_result(match_res)
            # Step 3B: Deterministic Application Readiness & Workflow (Phase 9)
            rec_res = recommender.recommend(job)
            job.apply_recommendation_result(rec_res)
            # Step 3C: Deterministic Resume Intelligence & Preparation (Phase 10)
            if (job.match_score or 0) >= 60:
                prep_res = resume_intel.analyze(job)
                job.apply_resume_preparation(prep_res)
            scored_jobs.append(job)
        # Sort from highest to lowest score
        scored_jobs.sort(key=lambda j: j.match_score or 0, reverse=True)
        logger.info("[MATCH] Scored, recommended, and prepared %d candidate listings.", len(scored_jobs))

        # Step 4: In-Batch Deduplication
        batch_jobs = deduplicator.deduplicate_batch(scored_jobs)
        logger.info("[DEDUP] %d unique listings in current run batch.", len(batch_jobs))

        # Prepare and score all collected raw jobs (MATCH, REVIEW, REJECT) for the master 'All Jobs' worksheet
        for j in raw_jobs:
            if not (j.extra_metadata or {}).get("decision"):
                job_filter.classify_job(j)
            if j.match_score is None:
                match_res = matcher.match(j)
                j.apply_match_result(match_res)

        deduped_all_jobs = deduplicator.deduplicate_for_all_jobs(raw_jobs)
        logger.info("[DEDUP] %d unique listings in master 'All Jobs' collection.", len(deduped_all_jobs))

        # Prepare and score all collected Accenture jobs for the dedicated Accenture worksheet
        accenture_raw_jobs = [j for j in raw_jobs if j.source.lower() == "accenture"]
        deduped_accenture_jobs = deduplicator.deduplicate_batch(accenture_raw_jobs)

        # Step 5: Persist & Upsert Jobs in SQLite with Run ID
        logger.info("[DB] Persisting batch to SQLite (run_id=%s)...", run_id)
        for job in batch_jobs:
            is_new = db_manager.save_job(job, run_id=run_id)
            if is_new:
                job._is_new_in_run = True
                new_jobs_count += 1
            else:
                job._is_new_in_run = False
                duplicate_jobs_count += 1

        # Also persist/refresh tracking state on all unique jobs in master All Jobs collection
        for job in deduped_all_jobs:
            db_manager.save_job(job, run_id=run_id)

        logger.info(
            "[DB] Database upsert finished: new=%d, duplicates=%d",
            new_jobs_count,
            duplicate_jobs_count,
        )

        # Step 6: Generate Styled Excel Export
        logger.info("[EXCEL] Exporting jobs to Excel report...")
        use_full_report = full_report or settings.FULL_REPORT
        export_file = exporter.export(
            batch_jobs,
            current_run_id=run_id,
            full_report=use_full_report,
            db_manager=db_manager,
            accenture_jobs=deduped_accenture_jobs if deduped_accenture_jobs else None,
            all_jobs=deduped_all_jobs,
            enabled_sources=active_tokens,
        )
        logger.info("[EXCEL] Report generated at: %s", export_file)

        # Step 7: Connector In-Depth Diagnostics
        for s in sources:
            if getattr(s, "is_enabled", False):
                diag = getattr(s, "diagnostics", {})
                coll = diag.get("total_collected") or diag.get("collected") or 0
                if coll > 0 and hasattr(s, "format_diagnostics"):
                    try:
                        if s.source_name in ("lever", "greenhouse", "accenture"):
                            diag_report = s.format_diagnostics(filtered_jobs=filtered_jobs, scored_jobs=batch_jobs)
                        else:
                            diag_report = s.format_diagnostics()
                        logger.info("==================================================")
                        logger.info("\n%s", diag_report)
                    except Exception as diag_err:
                        logger.debug("Could not format diagnostics for %s: %s", s.source_name, diag_err)

        # Step 8: Overall Run Status
        if collector.has_source_warnings():
            run_status = "COMPLETED_WITH_SOURCE_WARNINGS"
            logger.warning("[RUN] Completed with warnings (some sources blocked or unavailable)")
        else:
            run_status = "COMPLETED"
            logger.info("[RUN] Completed successfully without errors")

    except Exception as exc:
        run_status = "FAILED"
        logger.exception("[RUN] Fatal internal pipeline failure: %s", exc)
        raise exc
    finally:
        # Step 9: Update SQLite Pipeline Run Record
        if db_manager is not None:
            completed_at = datetime.now(timezone.utc)
            relevant_count = sum(1 for j in batch_jobs if (j.match_score or 0) >= 60)
            strong_count = sum(1 for j in batch_jobs if (j.match_score or 0) >= 80)
            excellent_count = sum(1 for j in batch_jobs if (j.match_score or 0) >= 90)

            err_cnt = sum(
                1 for s in collector.get_source_results().values()
                if s.get("status") in ("BLOCKED", "UNAVAILABLE", "ERROR", "PARTIAL", "FAILED")
            )

            db_manager.update_pipeline_run(
                run_id=run_id,
                completed_at=completed_at,
                status=run_status,
                raw_collected=len(raw_jobs),
                normalized=len(raw_jobs),
                filtered=len(filtered_jobs),
                relevant=relevant_count,
                strong=strong_count,
                excellent=excellent_count,
                new_jobs=new_jobs_count,
                duplicate_jobs=duplicate_jobs_count,
                error_count=err_cnt,
                notes=f"Export: {export_file}" if export_file else None,
                source_results=json.dumps(collector.get_source_results()) if collector else None,
            )

            # Step 10: Print Daily Summary
            total_duration_sec = (completed_at - run_started_at).total_seconds()
            print_daily_summary(
                run_id=run_id,
                source_results=collector.get_source_results(),
                raw_count=len(deduped_all_jobs),
                new_count=new_jobs_count,
                duplicate_count=duplicate_jobs_count,
                relevant_count=relevant_count,
                strong_count=strong_count,
                excellent_count=excellent_count,
                run_status=run_status,
                export_file=str(export_file) if export_file else "None",
                all_jobs=deduped_all_jobs,
                raw_jobs=raw_jobs,
                total_runtime_sec=total_duration_sec,
                db_manager=db_manager,
            )

        # Step 11: Log Retention Cleanup (keep latest 30 days)
        try:
            cleanup_old_logs(logs_dir=settings.LOGS_DIR, retention_days=30)
        except Exception as cl_err:
            logger.debug("[CLEANUP] Log cleanup notice: %s", cl_err)

        # Step 12: Release Process Lock
        lock.release()


def print_daily_summary(
    run_id: str,
    source_results: dict,
    raw_count: int,
    new_count: int,
    duplicate_count: int,
    relevant_count: int,
    strong_count: int,
    excellent_count: int,
    run_status: str,
    export_file: str,
    all_jobs: Optional[list] = None,
    raw_jobs: Optional[list] = None,
    total_runtime_sec: Optional[float] = None,
    db_manager: Optional[Any] = None,
) -> None:
    """Print the human-readable Daily Summary block."""
    lines = [
        "==================================================",
        "DAILY JOB FINDER SUMMARY",
        "==================================================",
        "",
        f"Run ID: {run_id}",
    ]

    # Calculate My Jobs row count from workbook if available
    my_jobs_row_count = 0
    if export_file and Path(export_file).exists():
        try:
            import openpyxl
            wb = openpyxl.load_workbook(export_file, read_only=True)
            target_sheet = "My Jobs" if "My Jobs" in wb.sheetnames else wb.sheetnames[0]
            ws = wb[target_sheet]
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) > 1:
                # check if row 2 is empty placeholder
                if rows[1][0] and "No matching jobs" in str(rows[1][0]):
                    my_jobs_row_count = 0
                else:
                    my_jobs_row_count = len(rows) - 1
            wb.close()
        except Exception:
            my_jobs_row_count = relevant_count

    # Breakdown Tables: Company, Source, and Country (Task 12, 14 & 16)
    if all_jobs:
        # 1. Company Breakdown
        company_stats: Dict[str, Dict[str, int]] = {}
        # 2. Source Breakdown
        source_stats: Dict[str, Dict[str, int]] = {}
        # 3. Country Breakdown
        country_stats: Dict[str, Dict[str, int]] = {}

        for j in all_jobs:
            comp = j.company or "Unknown"
            src = (j.source or "Unknown").capitalize()
            ctry = derive_country(j.location)

            if comp not in company_stats:
                company_stats[comp] = {"collected": 0, "MATCH": 0, "REVIEW": 0, "REJECT": 0}
            if src not in source_stats:
                source_stats[src] = {"collected": 0, "MATCH": 0, "REVIEW": 0, "REJECT": 0}
            if ctry not in country_stats:
                country_stats[ctry] = {"collected": 0, "MATCH": 0, "REVIEW": 0, "REJECT": 0}

            company_stats[comp]["collected"] += 1
            source_stats[src]["collected"] += 1
            country_stats[ctry]["collected"] += 1

            dec = str((j.extra_metadata or {}).get("decision") or getattr(j, "decision", "REJECT")).upper()
            if dec in ("MATCH", "REVIEW"):
                company_stats[comp][dec] += 1
                source_stats[src][dec] += 1
                country_stats[ctry][dec] += 1
            else:
                company_stats[comp]["REJECT"] += 1
                source_stats[src]["REJECT"] += 1
                country_stats[ctry]["REJECT"] += 1

        lines.extend([
            "",
            "Company Breakdown:",
            f"  {'Company':<24} {'Collected':>9} {'MATCH':>7} {'REVIEW':>8} {'REJECT':>8}",
            "  " + "-" * 60,
        ])
        tot_c = tot_m = tot_rv = tot_rj = 0
        for comp in sorted(company_stats.keys()):
            cs = company_stats[comp]
            tot_c += cs["collected"]
            tot_m += cs["MATCH"]
            tot_rv += cs["REVIEW"]
            tot_rj += cs["REJECT"]
            lines.append(f"  {comp:<24} {cs['collected']:>9} {cs['MATCH']:>7} {cs['REVIEW']:>8} {cs['REJECT']:>8}")
        lines.extend([
            "  " + "-" * 60,
            f"  {'Total':<24} {tot_c:>9} {tot_m:>7} {tot_rv:>8} {tot_rj:>8}",
        ])

        # Source Breakdown Table (Task 14)
        lines.extend([
            "",
            "Source Breakdown:",
            f"  {'Source':<20} {'Collected':>9} {'MATCH':>7} {'REVIEW':>8} {'REJECT':>8}",
            "  " + "-" * 56,
        ])
        s_tot_c = s_tot_m = s_tot_rv = s_tot_rj = 0
        for src in sorted(source_stats.keys()):
            ss = source_stats[src]
            s_tot_c += ss["collected"]
            s_tot_m += ss["MATCH"]
            s_tot_rv += ss["REVIEW"]
            s_tot_rj += ss["REJECT"]
            lines.append(f"  {src:<20} {ss['collected']:>9} {ss['MATCH']:>7} {ss['REVIEW']:>8} {ss['REJECT']:>8}")
        lines.extend([
            "  " + "-" * 56,
            f"  {'Total':<20} {s_tot_c:>9} {s_tot_m:>7} {s_tot_rv:>8} {s_tot_rj:>8}",
        ])

        # Country Breakdown Table
        lines.extend([
            "",
            "Country Breakdown:",
            f"  {'Country':<18} {'Collected':>9} {'MATCH':>7} {'REVIEW':>8} {'REJECT':>8}",
            "  " + "-" * 54,
        ])
        c_tot_c = c_tot_m = c_tot_rv = c_tot_rj = 0
        for ctry in sorted(country_stats.keys()):
            cs = country_stats[ctry]
            c_tot_c += cs["collected"]
            c_tot_m += cs["MATCH"]
            c_tot_rv += cs["REVIEW"]
            c_tot_rj += cs["REJECT"]
            lines.append(f"  {ctry:<18} {cs['collected']:>9} {cs['MATCH']:>7} {cs['REVIEW']:>8} {cs['REJECT']:>8}")
        lines.extend([
            "  " + "-" * 54,
            f"  {'Total':<18} {c_tot_c:>9} {c_tot_m:>7} {c_tot_rv:>8} {c_tot_rj:>8}",
        ])

    # Per-Source Performance Summary (Task 16 Table)
    lines.extend([
        "",
        "Per-Source Performance Summary:",
        f"  {'Source / Portal':<26} {'Status':<11} {'Available':>9} {'Fetched':>8} {'MATCH':>7} {'REVIEW':>8} {'REJECT':>8} {'Runtime':>8}",
        "  " + "-" * 91,
    ])

    flagged_sources = []
    # Build unified view of portals
    for s_name, s_info in source_results.items():
        s_status = s_info.get("status", "UNKNOWN")
        s_avail = s_info.get("total_available", 0)
        s_coll = s_info.get("collected", 0)
        s_dur = f"{s_info.get('duration_sec', 0.0):.1f}s"
        s_err = s_info.get("error")

        # Check if source has sub-companies (workday, company_json, successfactors, oracle_hcm, turbohire)
        by_comp = (s_info.get("diagnostics") or {}).get("by_company", {})
        if by_comp:
            for c_key, c_info in sorted(by_comp.items(), key=lambda x: x[1].get("name", x[0])):
                c_name = c_info.get("name", c_key.capitalize())
                c_st = c_info.get("status", "COMPLETED")
                c_av = c_info.get("available", c_info.get("collected", 0))
                c_ft = c_info.get("collected", 0)
                c_er = c_info.get("error")
                c_stats = (company_stats.get(c_name) if all_jobs else None) or {"MATCH": 0, "REVIEW": 0, "REJECT": 0}
                lines.append(
                    f"  {c_name:<26} {c_st:<11} {c_av:>9} {c_ft:>8} {c_stats['MATCH']:>7} {c_stats['REVIEW']:>8} {c_stats['REJECT']:>8} {s_dur:>8}"
                )
                if c_st in ("FAILED", "BLOCKED") or c_ft == 0:
                    flagged_sources.append((c_name, c_st, c_er or "Returned 0 jobs"))
        else:
            c_name = s_name.capitalize()
            c_stats = (company_stats.get(c_name) if all_jobs else None) or (source_stats.get(c_name) if all_jobs else None) or {"MATCH": 0, "REVIEW": 0, "REJECT": 0}
            lines.append(
                f"  {c_name:<26} {s_status:<11} {s_avail:>9} {s_coll:>8} {c_stats['MATCH']:>7} {c_stats['REVIEW']:>8} {c_stats['REJECT']:>8} {s_dur:>8}"
            )
            if s_status in ("FAILED", "BLOCKED") or s_coll == 0:
                flagged_sources.append((c_name, s_status, s_err or "Returned 0 jobs"))

    lines.append("  " + "-" * 91)

    # Flagged sources section
    if flagged_sources:
        lines.extend([
            "",
            "Flagged Sources (0 Jobs or FAILED):",
        ])
        for f_name, f_st, f_reason in flagged_sources:
            lines.append(f"  - {f_name:<24}: [{f_st}] {f_reason}")

    lines.extend([
        "",
        "Jobs Summary:",
        f"  Collected   : {raw_count}",
        f"  New         : {new_count}",
        f"  Duplicates  : {duplicate_count}",
        f"  Relevant    : {relevant_count}",
        f"  Strong      : {strong_count}",
        f"  Excellent   : {excellent_count}",
        "",
        "Pipeline Status:",
        f"  Run Status  : {run_status}",
        f"  Total Time  : {f'{total_runtime_sec:.1f}s' if total_runtime_sec is not None else 'N/A'}",
        "",
        "Workbook Output:",
        f"  Path        : {export_file}",
        f"  My Jobs Rows: {my_jobs_row_count}",
    ])

    if "My_Jobs" in str(export_file):
        latest_file = str(Path(export_file).parent / "My_Jobs_latest.xlsx")
        lines.append(f"  Latest Link : {latest_file}")

    registry = get_company_registry()
    lines.extend([
        "",
        registry.format_health_summary(),
    ])

    lines.append("==================================================")

    output_str = "\n" + "\n".join(lines)
    logger = logging.getLogger("job_finder_automation")
    logger.info(output_str)
    print(output_str)


def run_health_check() -> int:
    """Execute system, configuration, and environment validation checks."""
    from app.services.env_validator import EnvironmentValidator
    from app.database.database import DatabaseManager

    settings = get_settings()
    validator = EnvironmentValidator(settings=settings)
    env_ok, env_checks = validator.validate_all()

    db = DatabaseManager(settings.DATABASE_PATH)
    db_health = db.check_database_health()

    task_runner_exists = (settings.PROJECT_ROOT / "scripts" / "run_daily_job_finder.bat").exists()

    checks_by_name = {c.name: c for c in env_checks}
    env_passed = all(c.passed for c in env_checks if c.category in ("Runtime", "Dependencies"))
    profile_passed = checks_by_name.get("Profile File", None) is not None and checks_by_name["Profile File"].passed
    exports_passed = any("Exports" in c.name and c.passed for c in env_checks)
    logs_passed = any("Logs" in c.name and c.passed for c in env_checks)
    backups_passed = any("Backups" in c.name and c.passed for c in env_checks)

    categories = [
        ("Environment", env_passed),
        ("Configuration", True),
        ("Database", db_health["is_healthy"]),
        ("Profile", profile_passed),
        ("Export Directory", exports_passed),
        ("Log Directory", logs_passed),
        ("Task Runner", task_runner_exists),
        ("Backup Directory", backups_passed),
    ]

    print("==================================================")
    print("Daily Job Finder Automation - System Health Status")
    print("==================================================")
    for cat_name, passed in categories:
        status_label = "PASS" if passed else "FAIL"
        print(f"{cat_name:<18}: {status_label}")

    overall_healthy = env_ok and db_health["is_healthy"] and task_runner_exists
    overall_status = "HEALTHY" if overall_healthy else "UNHEALTHY"
    print("--------------------------------------------------")
    print(f"Overall           : {overall_status}")
    print("==================================================")
    return 0 if overall_healthy else 1


def main() -> None:
    """CLI entrypoint."""
    if len(sys.argv) > 1 and sys.argv[1] in ("--health", "-health", "--status", "-status"):
        code = run_health_check()
        sys.exit(code)

    full_report_flag = any(arg in ("--full-report", "-full-report", "--full", "-full") for arg in sys.argv[1:])

    # Task 16: CLI option --sources / -s
    sources_override = None
    args = sys.argv[1:]
    for idx, arg in enumerate(args):
        if arg in ("--sources", "-s", "--source") and idx + 1 < len(args):
            sources_override = args[idx + 1]
        elif arg.startswith("--sources="):
            sources_override = arg.split("=", 1)[1]
        elif arg.startswith("-s="):
            sources_override = arg.split("=", 1)[1]
        elif arg.startswith("--source="):
            sources_override = arg.split("=", 1)[1]

    try:
        asyncio.run(run_pipeline(full_report=full_report_flag, sources_override=sources_override))
        sys.exit(0)
    except SystemExit as se:
        sys.exit(se.code if se.code is not None else 0)
    except KeyboardInterrupt:
        print("\nPipeline interrupted by user.")
        sys.exit(0)
    except Exception as exc:
        logger = logging.getLogger("job_finder_automation")
        logger.error("[MAIN] Pipeline failed with unhandled error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
