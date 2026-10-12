"""Process lock management and log cleanup utilities for reliable daily automation."""

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


class ActiveRunLockError(Exception):
    """Raised when another pipeline execution is currently active."""
    pass


def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is currently active.

    On Windows, queries the process handle via kernel32.
    On POSIX systems, probes via os.kill(pid, 0).
    """
    if pid <= 0:
        return False

    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(handle)
            # STILL_ACTIVE is 259
            return exit_code.value == 259
        except Exception as exc:
            logger.debug("Windows process check failed for PID %d: %s", pid, exc)
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


class JobFinderLock:
    """Lightweight, Windows-safe file lock preventing simultaneous pipeline runs."""

    def __init__(
        self,
        lock_path: Union[str, Path] = "data/job_finder.lock",
        max_stale_hours: float = 4.0,
        run_id: Optional[str] = None,
    ):
        self.lock_path = Path(lock_path)
        self.max_stale_hours = max_stale_hours
        self.run_id = run_id
        self._acquired = False

    def acquire(self, run_id: Optional[str] = None) -> bool:
        """Attempt to acquire the process lock.

        Returns:
            True if acquired, False if another active run is in progress.
        """
        active_run_id = run_id or self.run_id
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        if self.lock_path.exists():
            try:
                content = self.lock_path.read_text(encoding="utf-8").strip()
                lock_data: Dict[str, Any] = json.loads(content) if content else {}
            except Exception as read_err:
                logger.warning("Could not parse existing lock file: %s. Treating as stale.", read_err)
                lock_data = {}

            existing_pid = lock_data.get("pid")
            started_at_str = lock_data.get("started_at")
            existing_run_id = lock_data.get("run_id", "unknown")

            is_stale = False
            if not existing_pid or not is_process_running(int(existing_pid)):
                logger.info("[LOCK] Process PID %s is no longer active. Stale lock cleared.", existing_pid)
                is_stale = True
            elif started_at_str:
                try:
                    started_dt = datetime.fromisoformat(started_at_str)
                    age_hours = (datetime.now(timezone.utc) - started_dt).total_seconds() / 3600.0
                    if age_hours > self.max_stale_hours:
                        logger.warning(
                            "[LOCK] Lock file has exceeded max age of %.1fh (age: %.1fh). Clearing stale lock.",
                            self.max_stale_hours,
                            age_hours,
                        )
                        is_stale = True
                except Exception:
                    is_stale = True

            if not is_stale:
                logger.warning(
                    "[LOCK] Active pipeline execution already in progress (PID: %s, Run ID: %s, Started: %s).",
                    existing_pid,
                    existing_run_id,
                    started_at_str,
                )
                return False

            # Remove stale lock file
            try:
                self.lock_path.unlink(missing_ok=True)
            except Exception as del_err:
                logger.warning("Error deleting stale lock: %s", del_err)

        # Write fresh lock info
        lock_payload = {
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "run_id": active_run_id or "",
        }
        try:
            self.lock_path.write_text(json.dumps(lock_payload, indent=2), encoding="utf-8")
            self._acquired = True
            logger.debug("[LOCK] Lock acquired for PID %d (run_id=%s)", os.getpid(), active_run_id)
            return True
        except Exception as write_err:
            logger.error("[LOCK] Failed to write lock file: %s", write_err)
            return False

    def release(self) -> None:
        """Release and remove the lock file if owned by this process."""
        if self.lock_path.exists():
            try:
                content = self.lock_path.read_text(encoding="utf-8").strip()
                lock_data = json.loads(content) if content else {}
                lock_pid = lock_data.get("pid")
                # Only unlink if this process owns the lock or if file is unparseable/empty
                if lock_pid is None or lock_pid == os.getpid():
                    self.lock_path.unlink(missing_ok=True)
                    logger.debug("[LOCK] Lock released for PID %d", os.getpid())
                else:
                    logger.warning(
                        "[LOCK] Refusing to release lock owned by PID %s (current PID: %s)",
                        lock_pid,
                        os.getpid(),
                    )
            except Exception as exc:
                logger.warning("[LOCK] Error releasing lock: %s", exc)
        self._acquired = False

    def __enter__(self) -> "JobFinderLock":
        if not self.acquire():
            raise ActiveRunLockError("Another pipeline execution is already in progress.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


def cleanup_old_logs(logs_dir: Union[str, Path] = "data/logs", retention_days: int = 30) -> int:
    """Remove log files in logs_dir older than retention_days.

    Does not modify database data or Excel exports.

    Args:
        logs_dir: Path to directory containing logs.
        retention_days: Number of days to retain logs (default 30).

    Returns:
        Number of expired log files deleted.
    """
    path = Path(logs_dir).resolve()
    if not path.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0

    for log_file in path.glob("*.log"):
        if not log_file.is_file():
            continue

        # Prevent directory traversal
        try:
            if path not in log_file.resolve().parents:
                continue
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            if mtime < cutoff:
                log_file.unlink()
                deleted_count += 1
                logger.info("[CLEANUP] Deleted expired log file: %s", log_file.name)
        except Exception as exc:
            logger.warning("[CLEANUP] Could not remove log file %s: %s", log_file, exc)

    return deleted_count
