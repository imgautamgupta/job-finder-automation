"""Main orchestration entry point for Job Finder Automation (Phase 7A)."""

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import uuid

# Ensure project root is in sys.path when run directly
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.config.settings import get_settings
from app.database.database import DatabaseManager
from app.services.collector import JobCollector
from app.services.deduplicator import JobDeduplicator
from app.services.excel_exporter import ExcelExporter
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher
from app.services.recommender import JobRecommender
from app.services.resume_intelligence import ResumeIntelligenceService
from app.services.resume_parser import ResumeParser
from app.sources.greenhouse import GreenhouseJobSource
from app.sources.lever import LeverJobSource
from app.sources.linkedin import LinkedInJobSource
from app.sources.naukri import NaukriJobSource
from app.utils.lock import JobFinderLock, cleanup_old_logs


def setup_logging(log_level: str = "INFO") -> None:
    """Configure console logging format."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def run_pipeline() -> None:
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

    # 4. Initialize Source Connectors
    linkedin_source = LinkedInJobSource(is_enabled=True)
    naukri_source = NaukriJobSource(is_enabled=settings.NAUKRI_ENABLED, settings=settings)
    lever_source = LeverJobSource(is_enabled=settings.LEVER_ENABLED, settings=settings)
    greenhouse_source = GreenhouseJobSource(is_enabled=settings.GREENHOUSE_ENABLED, settings=settings)

    collector = JobCollector(sources=[linkedin_source, naukri_source, lever_source, greenhouse_source])
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
            elif s_status == "BLOCKED":
                logger.warning("[SOURCE] %s: blocked (%s)", src_name.capitalize(), s_err)
            elif s_status == "DISABLED":
                logger.debug("[SOURCE] %s: disabled", src_name.capitalize())
            else:
                logger.warning("[SOURCE] %s: status=%s (error=%s, collected=%d)", src_name.capitalize(), s_status, s_err, s_coll)

        # Step 2: Filter Jobs by User Preferences
        logger.info("[FILTER] Filtering jobs against profile preferences...")
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

        logger.info(
            "[DB] Database upsert finished: new=%d, duplicates=%d",
            new_jobs_count,
            duplicate_jobs_count,
        )

        # Step 6: Generate Styled Excel Export
        logger.info("[EXCEL] Exporting jobs to Excel report...")
        export_file = exporter.export(batch_jobs, current_run_id=run_id)
        logger.info("[EXCEL] Report generated at: %s", export_file)

        # Step 7: Lever & Greenhouse In-Depth Diagnostics
        if lever_source.is_enabled and lever_source.diagnostics.get("collected", 0) > 0:
            diag_report = lever_source.format_diagnostics(
                filtered_jobs=filtered_jobs,
                scored_jobs=batch_jobs,
            )
            logger.info("==================================================")
            logger.info("\n%s", diag_report)

        if greenhouse_source.is_enabled and greenhouse_source.diagnostics.get("collected", 0) > 0:
            gh_diag_report = greenhouse_source.format_diagnostics(
                filtered_jobs=filtered_jobs,
                scored_jobs=batch_jobs,
            )
            logger.info("==================================================")
            logger.info("\n%s", gh_diag_report)

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
                if s.get("status") in ("BLOCKED", "UNAVAILABLE", "ERROR")
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
            print_daily_summary(
                run_id=run_id,
                source_results=collector.get_source_results(),
                raw_count=len(raw_jobs),
                new_count=new_jobs_count,
                duplicate_count=duplicate_jobs_count,
                relevant_count=relevant_count,
                strong_count=strong_count,
                excellent_count=excellent_count,
                run_status=run_status,
                export_file=str(export_file) if export_file else "None",
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
) -> None:
    """Print the human-readable Daily Summary block."""
    lines = [
        "==================================================",
        "DAILY JOB FINDER SUMMARY",
        "==================================================",
        "",
        f"Run ID: {run_id}",
        "",
        "Sources:",
    ]

    for name, s_info in source_results.items():
        status = s_info.get("status", "UNKNOWN")
        coll = s_info.get("collected", 0)
        err = s_info.get("error")
        cap_name = name.capitalize()

        if status == "COMPLETED":
            lines.append(f"  {cap_name:<12}: {coll} collected")
        elif status == "BLOCKED":
            lines.append(f"  {cap_name:<12}: BLOCKED ({err or 'Access Denied'})")
        elif status == "DISABLED":
            lines.append(f"  {cap_name:<12}: DISABLED")
        elif status == "UNAVAILABLE":
            lines.append(f"  {cap_name:<12}: UNAVAILABLE ({err})")
        else:
            lines.append(f"  {cap_name:<12}: {status} ({err or f'{coll} collected'})")

    lines.extend([
        "",
        "Jobs:",
        f"  Collected   : {raw_count}",
        f"  New         : {new_count}",
        f"  Duplicates  : {duplicate_count}",
        f"  Relevant    : {relevant_count}",
        f"  Strong      : {strong_count}",
        f"  Excellent   : {excellent_count}",
        "",
        "Status:",
        f"  Run         : {run_status}",
        "",
        "Excel:",
        f"  {export_file}",
        "==================================================",
    ])

    print("\n" + "\n".join(lines))


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

    try:
        asyncio.run(run_pipeline())
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
