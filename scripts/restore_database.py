"""Safe, validated SQLite database restore tool."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import get_settings


def validate_candidate_backup(backup_path: Path) -> tuple[bool, int, str]:
    """Validate that candidate backup is a valid SQLite DB with jobs table.

    Returns:
        Tuple of (is_valid: bool, job_count: int, reason: str)
    """
    if not backup_path.exists():
        return False, 0, f"File does not exist: {backup_path}"

    if backup_path.stat().st_size == 0:
        return False, 0, f"File is empty: {backup_path}"

    try:
        with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA quick_check;")
            qc = cur.fetchone()
            if not qc or qc[0] != "ok":
                return False, 0, f"PRAGMA quick_check failed: {qc}"

            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {r[0] for r in cur.fetchall()}
            if "jobs" not in tables:
                return False, 0, "Missing required 'jobs' table"

            cur.execute("SELECT COUNT(*) FROM jobs;")
            cnt = cur.fetchone()[0]
            return True, cnt, "Valid SQLite database"
    except Exception as exc:
        return False, 0, f"Failed opening candidate backup: {exc}"


def create_pre_restore_safety_backup(live_db: Path, backup_dir: Path) -> Path:
    """Create a protective safety backup of the active database before restoring.

    Returns:
        Path to the safety backup file.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safety_file = backup_dir / f"pre_restore_safety_{timestamp}.db"

    if live_db.exists():
        src_conn = sqlite3.connect(f"file:{live_db}?mode=ro", uri=True)
        dst_conn = sqlite3.connect(str(safety_file))
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
    return safety_file


def restore_database(
    backup_path: Path,
    target_db: Optional[Path] = None,
    allow_external: bool = False,
    auto_confirmed: bool = False,
    safety_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Restore target database from backup_path with verification and safety backups.

    Returns:
        Dict with status, restored_jobs, and safety_backup path.
    """
    settings = get_settings()
    target_path = (target_db or settings.DATABASE_PATH).resolve()
    candidate_path = Path(backup_path).resolve()
    backups_dir = (safety_dir or settings.BACKUPS_DIR).resolve()

    # 1. Path safety check: ensure candidate is inside backups_dir or explicitly allowed
    if not allow_external and backups_dir not in candidate_path.parents and candidate_path.parent != backups_dir:
        raise ValueError(
            f"Candidate backup '{candidate_path}' is outside designated backups directory '{backups_dir}'. "
            f"Pass --allow-external to override."
        )

    # 2. Validate candidate backup
    is_valid, backup_job_count, reason = validate_candidate_backup(candidate_path)
    if not is_valid:
        raise ValueError(f"Candidate backup failed validation: {reason}")

    # 3. Check current live database
    current_jobs = 0
    if target_path.exists():
        try:
            with sqlite3.connect(f"file:{target_path}?mode=ro", uri=True) as cur_conn:
                cur = cur_conn.cursor()
                cur.execute("SELECT COUNT(*) FROM jobs;")
                current_jobs = cur.fetchone()[0]
        except Exception:
            current_jobs = -1

    # 4. Require explicit user confirmation if not auto_confirmed
    if not auto_confirmed:
        print("==================================================")
        print("DATABASE RESTORE WARNING")
        print("==================================================")
        print(f"Target Database:  {target_path} (current jobs: {current_jobs})")
        print(f"Restore Source:   {candidate_path} (restore jobs: {backup_job_count})")
        print("==================================================")
        response = input("To proceed, type 'RESTORE' exactly: ").strip()
        if response != "RESTORE":
            raise PermissionError("Database restore cancelled: confirmation token did not match 'RESTORE'.")

    # 5. Create safety backup of current live DB before touching it
    safety_backup = create_pre_restore_safety_backup(target_path, backups_dir)

    # 6. Perform atomic restore using SQLite backup API
    src_conn = sqlite3.connect(f"file:{candidate_path}?mode=ro", uri=True)
    dst_conn = sqlite3.connect(str(target_path))
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    # 7. Validate restored database
    with sqlite3.connect(f"file:{target_path}?mode=ro", uri=True) as verify_conn:
        v_cur = verify_conn.cursor()
        v_cur.execute("SELECT COUNT(*) FROM jobs;")
        final_jobs = v_cur.fetchone()[0]

    if final_jobs != backup_job_count:
        raise RuntimeError(f"Restored job count ({final_jobs}) does not match source ({backup_job_count})!")

    return {
        "status": "PASS",
        "target_db": str(target_path),
        "source_backup": str(candidate_path),
        "safety_backup": str(safety_backup),
        "restored_jobs": final_jobs,
        "previous_jobs": current_jobs,
    }


def main():
    parser = argparse.ArgumentParser(description="Restore SQLite database from a verified backup file.")
    parser.add_argument("backup_file", type=Path, help="Path to backup file (e.g. data/backups/jobs_YYYYMMDD_HHMMSS.db).")
    parser.add_argument("--target", type=Path, default=None, help="Target database path (default: active jobs.db).")
    parser.add_argument("--confirm", choices=["RESTORE"], default=None, help="Explicit confirmation token for automation.")
    parser.add_argument("--yes", action="store_true", help="Bypass interactive confirmation prompt.")
    parser.add_argument("--allow-external", action="store_true", help="Allow restore from files outside data/backups.")
    args = parser.parse_args()

    auto_confirmed = (args.confirm == "RESTORE") or args.yes

    try:
        res = restore_database(
            backup_path=args.backup_file,
            target_db=args.target,
            allow_external=args.allow_external,
            auto_confirmed=auto_confirmed,
        )
        print("==================================================")
        print("SQLite Database Restore Successful")
        print("==================================================")
        print(f"Restored to:    {res['target_db']}")
        print(f"From backup:    {res['source_backup']}")
        print(f"Safety backup:  {res['safety_backup']}")
        print(f"Restored jobs:  {res['restored_jobs']}")
        print("==================================================")
        sys.exit(0)
    except Exception as exc:
        print(f"[ERROR] Restore failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
