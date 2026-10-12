"""Safe, atomic SQLite database backup and retention tool."""

import argparse
from datetime import datetime, timedelta
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import get_settings


BACKUP_FILENAME_PATTERN = re.compile(r"^jobs_(\d{4}\d{2}\d{2})_(\d{2}\d{2}\d{2})\.db$")


def validate_backup(backup_path: Path, expected_jobs: int) -> tuple[bool, str]:
    """Validate that the backup file is a valid, readable SQLite DB with matching job count.

    Returns:
        Tuple of (is_valid: bool, reason: str)
    """
    if not backup_path.exists():
        return False, f"Backup file not found at {backup_path}"

    if backup_path.stat().st_size == 0:
        return False, f"Backup file {backup_path} is 0 bytes"

    try:
        with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA quick_check;")
            qc = cur.fetchone()
            if not qc or qc[0] != "ok":
                return False, f"PRAGMA quick_check failed: {qc}"

            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {r[0] for r in cur.fetchall()}
            if "jobs" not in tables:
                return False, "Backup database missing 'jobs' table"

            cur.execute("SELECT COUNT(*) FROM jobs;")
            backup_jobs = cur.fetchone()[0]

            if backup_jobs != expected_jobs:
                return False, f"Job count mismatch: source={expected_jobs}, backup={backup_jobs}"

            return True, f"Valid SQLite DB, {backup_jobs} jobs verified"
    except Exception as exc:
        return False, f"Database verification exception: {exc}"


def purge_expired_backups(backup_dir: Path, retention_days: int) -> tuple[int, int]:
    """Delete backups older than retention_days matching the strict filename pattern.

    Returns:
        Tuple of (retained_count, deleted_count)
    """
    cutoff = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0
    retained_count = 0

    backup_dir = backup_dir.resolve()
    if not backup_dir.exists():
        return 0, 0

    for file_path in backup_dir.iterdir():
        if not file_path.is_file():
            continue

        match = BACKUP_FILENAME_PATTERN.match(file_path.name)
        if not match:
            # Strictly ignore non-matching files (e.g. .gitkeep, arbitrary files)
            continue

        date_str, time_str = match.groups()
        try:
            file_dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
        except ValueError:
            retained_count += 1
            continue

        if file_dt < cutoff:
            try:
                file_path.unlink()
                deleted_count += 1
            except Exception as err:
                print(f"[WARN] Failed to delete expired backup {file_path.name}: {err}", file=sys.stderr)
                retained_count += 1
        else:
            retained_count += 1

    return retained_count, deleted_count


def backup_database(
    source_db: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
    retention_days: Optional[int] = None,
) -> dict[str, Any]:
    """Execute safe SQLite backup using the native sqlite3 backup API.

    Returns:
        Dict with status, backup_path, validation results, and retention counts.
    """
    settings = get_settings()
    src_path = (source_db or settings.DATABASE_PATH).resolve()
    dst_dir = (backup_dir or settings.BACKUPS_DIR).resolve()
    ret_days = retention_days if retention_days is not None else settings.DATABASE_BACKUP_RETENTION_DAYS

    if not src_path.exists():
        raise FileNotFoundError(f"Source database not found: {src_path}")

    dst_dir.mkdir(parents=True, exist_ok=True)

    # 1. Determine source job count
    with sqlite3.connect(f"file:{src_path}?mode=ro", uri=True) as src_conn:
        src_cur = src_conn.cursor()
        src_cur.execute("SELECT COUNT(*) FROM jobs;")
        source_job_count = src_cur.fetchone()[0]

    # 2. Generate timestamp and destination path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = dst_dir / f"jobs_{timestamp}.db"

    # Avoid rare collision
    counter = 1
    while backup_file.exists():
        backup_file = dst_dir / f"jobs_{timestamp}_{counter}.db"
        counter += 1

    # 3. Perform safe online SQLite backup
    src_conn = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    dst_conn = sqlite3.connect(str(backup_file))
    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=100)
    finally:
        dst_conn.close()
        src_conn.close()

    # 4. Immediate Validation
    is_valid, validation_msg = validate_backup(backup_file, source_job_count)
    if not is_valid:
        # If invalid, remove the corrupted backup file and raise
        if backup_file.exists():
            backup_file.unlink()
        raise RuntimeError(f"Backup validation failed: {validation_msg}")

    # 5. Backup Retention Cleanup
    retained_count, deleted_count = purge_expired_backups(dst_dir, ret_days)

    return {
        "status": "PASS",
        "source_db": str(src_path),
        "backup_path": str(backup_file),
        "source_jobs": source_job_count,
        "backup_jobs": source_job_count,
        "validation": "PASS",
        "validation_message": validation_msg,
        "retained_backups": retained_count,
        "deleted_backups": deleted_count,
        "retention_days": ret_days,
    }


def main():
    parser = argparse.ArgumentParser(description="Create a safe, verified local backup of the SQLite database.")
    parser.add_argument("--source", type=Path, default=None, help="Path to source database file.")
    parser.add_argument("--backup-dir", type=Path, default=None, help="Directory to store backups.")
    parser.add_argument("--retention-days", type=int, default=None, help="Days of backups to retain.")
    args = parser.parse_args()

    try:
        result = backup_database(
            source_db=args.source,
            backup_dir=args.backup_dir,
            retention_days=args.retention_days,
        )
        print("==================================================")
        print("SQLite Database Backup Successful")
        print("==================================================")
        print(f"Source:            {result['source_db']}")
        print(f"Backup:            {result['backup_path']}")
        print(f"Source jobs:       {result['source_jobs']}")
        print(f"Backup jobs:       {result['backup_jobs']}")
        print(f"Backup validation: {result['validation']} ({result['validation_message']})")
        print(f"Retention policy:  {result['retention_days']} days")
        print(f"Backups retained:  {result['retained_backups']}")
        print(f"Backups pruned:    {result['deleted_backups']}")
        print("==================================================")
        sys.exit(0)
    except Exception as exc:
        print(f"[ERROR] Backup failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
