"""Tests for Phase 7B process lock, log cleanup, and runner helpers."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import pytest
import sys
import tempfile

from app.utils.lock import (
    ActiveRunLockError,
    JobFinderLock,
    cleanup_old_logs,
    is_process_running,
)


def test_is_process_running_current_pid():
    """Verify that current process PID is detected as running."""
    assert is_process_running(os.getpid()) is True


def test_is_process_running_invalid_pid():
    """Verify that an invalid PID is reported as not running."""
    assert is_process_running(-1) is False
    assert is_process_running(0) is False
    # Using an astronomically large PID unlikely to exist
    assert is_process_running(9999999) is False


def test_lock_acquire_and_release(tmp_path):
    """Verify standard lock acquisition and release lifecycle."""
    lock_file = tmp_path / "job_finder.lock"
    lock = JobFinderLock(lock_path=lock_file)

    assert not lock_file.exists()
    acquired = lock.acquire(run_id="test-run-001")
    assert acquired is True
    assert lock_file.exists()

    # Verify lock file content structure
    content = json.loads(lock_file.read_text(encoding="utf-8"))
    assert content["pid"] == os.getpid()
    assert content["run_id"] == "test-run-001"
    assert "started_at" in content

    # Release lock
    lock.release()
    assert not lock_file.exists()


def test_lock_prevents_simultaneous_run(tmp_path):
    """Verify that another lock cannot be acquired while an active process holds it."""
    lock_file = tmp_path / "job_finder.lock"
    lock1 = JobFinderLock(lock_path=lock_file)
    lock2 = JobFinderLock(lock_path=lock_file)

    assert lock1.acquire(run_id="run-1") is True
    # Attempting to acquire with active process PID should fail
    assert lock2.acquire(run_id="run-2") is False

    lock1.release()
    # Now lock2 should be able to acquire
    assert lock2.acquire(run_id="run-2") is True
    lock2.release()


def test_lock_context_manager(tmp_path):
    """Verify context manager handles acquisition and automatic release."""
    lock_file = tmp_path / "job_finder.lock"

    with JobFinderLock(lock_path=lock_file, run_id="ctx-test"):
        assert lock_file.exists()
        # Nested attempt should raise ActiveRunLockError
        with pytest.raises(ActiveRunLockError):
            with JobFinderLock(lock_path=lock_file):
                pass

    assert not lock_file.exists()


def test_stale_lock_recovered_when_pid_dead(tmp_path):
    """Verify stale lock from non-existent PID is automatically recovered."""
    lock_file = tmp_path / "job_finder.lock"
    dead_pid = 9999999  # Non-existent PID

    payload = {
        "pid": dead_pid,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "run_id": "dead-run",
    }
    lock_file.write_text(json.dumps(payload), encoding="utf-8")

    # A new runner should detect dead PID and acquire successfully
    lock = JobFinderLock(lock_path=lock_file)
    assert lock.acquire(run_id="recovered-run") is True

    # Verify lock was updated with current process
    content = json.loads(lock_file.read_text(encoding="utf-8"))
    assert content["pid"] == os.getpid()
    assert content["run_id"] == "recovered-run"
    lock.release()


def test_stale_lock_recovered_when_corrupted(tmp_path):
    """Verify malformed or corrupted lock file is safely treated as stale."""
    lock_file = tmp_path / "job_finder.lock"
    lock_file.write_text("CORRUPTED_NOT_JSON!!!", encoding="utf-8")

    lock = JobFinderLock(lock_path=lock_file)
    assert lock.acquire(run_id="corrupt-recovery") is True
    lock.release()


def test_cleanup_old_logs(tmp_path):
    """Verify that logs older than retention period are deleted while newer logs remain."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    # Create fresh log file
    fresh_log = logs_dir / "job_finder_20261007_120000.log"
    fresh_log.write_text("Fresh log entry")

    # Create old log file (40 days old)
    old_log = logs_dir / "job_finder_20260820_120000.log"
    old_log.write_text("Old log entry")
    old_time = (datetime.now() - timedelta(days=40)).timestamp()
    os.utime(old_log, (old_time, old_time))

    # Create a non-log file to ensure it's not touched
    other_file = logs_dir / "keep_me.txt"
    other_file.write_text("Do not delete")
    os.utime(other_file, (old_time, old_time))

    deleted = cleanup_old_logs(logs_dir=logs_dir, retention_days=30)

    assert deleted == 1
    assert not old_log.exists()
    assert fresh_log.exists()
    assert other_file.exists()


def test_cleanup_old_logs_nonexistent_dir(tmp_path):
    """Verify cleanup gracefully returns 0 if directory does not exist."""
    nonexistent = tmp_path / "does_not_exist"
    assert cleanup_old_logs(logs_dir=nonexistent, retention_days=30) == 0
