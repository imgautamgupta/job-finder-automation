"""Database migration manager for applying and rolling back versioned schema changes (Phase 3B)."""

import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Union

from app.database.migrations import m001_multiuser_tables

logger = logging.getLogger(__name__)

# Registry of available migrations ordered by version number
MIGRATIONS = [
    m001_multiuser_tables,
]


class MigrationManager:
    """Manages transactional migration execution, tracking, and rollbacks for SQLite."""

    def __init__(self, db_path: Union[str, Path], settings: Optional[Any] = None):
        self.db_path = Path(db_path)
        self.settings = settings

    def _get_connection(self) -> sqlite3.Connection:
        """Create a dedicated connection with foreign key enforcement and timeout."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        return conn

    def ensure_schema_migrations_table(self, conn: sqlite3.Connection) -> None:
        """Ensure the version tracking table exists."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    def get_applied_versions(self, conn: sqlite3.Connection) -> List[int]:
        """Return sorted list of applied migration versions."""
        self.ensure_schema_migrations_table(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
        return [row["version"] for row in cursor.fetchall()]

    def apply_all(self) -> List[Dict[str, Any]]:
        """Apply all pending migrations inside atomic transactions.

        Returns:
            List of execution results for newly applied migrations.
        """
        results = []
        conn = self._get_connection()
        try:
            self.ensure_schema_migrations_table(conn)
            applied = set(self.get_applied_versions(conn))

            for mod in sorted(MIGRATIONS, key=lambda m: m.VERSION):
                if mod.VERSION in applied:
                    logger.debug(f"Migration {mod.VERSION} ({mod.NAME}) already applied. Skipping.")
                    continue

                logger.info(f"Applying migration {mod.VERSION} ({mod.NAME})...")
                # Atomic transaction per migration
                conn.execute("BEGIN IMMEDIATE;")
                try:
                    res = mod.up(conn, self.settings)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name) VALUES (?, ?);",
                        (mod.VERSION, mod.NAME),
                    )
                    conn.commit()
                    logger.info(f"Successfully applied migration {mod.VERSION} ({mod.NAME}).")
                    results.append(res)
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Failed to apply migration {mod.VERSION} ({mod.NAME}): {e}")
                    raise RuntimeError(f"Migration {mod.VERSION} ({mod.NAME}) failed: {e}") from e
        finally:
            conn.close()

        return results

    def rollback(self, target_version: int = 0) -> List[Dict[str, Any]]:
        """Rollback applied migrations down to target_version (exclusive).

        Returns:
            List of rolled-back migration details.
        """
        results = []
        conn = self._get_connection()
        try:
            self.ensure_schema_migrations_table(conn)
            applied = self.get_applied_versions(conn)

            # Sort descending for safe reverse-dependency teardown
            to_rollback = [v for v in sorted(applied, reverse=True) if v > target_version]

            migration_map = {m.VERSION: m for m in MIGRATIONS}

            for v in to_rollback:
                mod = migration_map.get(v)
                if not mod:
                    raise RuntimeError(f"Cannot rollback unknown migration version: {v}")

                logger.warning(f"Rolling back migration {v} ({mod.NAME})...")
                conn.execute("BEGIN IMMEDIATE;")
                try:
                    mod.down(conn)
                    conn.execute("DELETE FROM schema_migrations WHERE version = ?;", (v,))
                    conn.commit()
                    logger.info(f"Successfully rolled back migration {v} ({mod.NAME}).")
                    results.append({"version": v, "name": mod.NAME, "action": "ROLLED_BACK"})
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Failed to rollback migration {v} ({mod.NAME}): {e}")
                    raise RuntimeError(f"Rollback {v} ({mod.NAME}) failed: {e}") from e
        finally:
            conn.close()

        return results

    def get_status(self) -> Dict[str, Any]:
        """Inspect the current migration status and table statistics."""
        conn = self._get_connection()
        try:
            self.ensure_schema_migrations_table(conn)
            applied_versions = self.get_applied_versions(conn)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row["name"] for row in cursor.fetchall()]

            cursor.execute("SELECT COUNT(*) FROM jobs;")
            jobs_count = cursor.fetchone()[0]

            return {
                "applied_versions": applied_versions,
                "all_available_versions": [m.VERSION for m in MIGRATIONS],
                "pending_versions": [m.VERSION for m in MIGRATIONS if m.VERSION not in applied_versions],
                "tables": tables,
                "jobs_count": jobs_count,
            }
        finally:
            conn.close()

