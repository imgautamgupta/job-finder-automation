"""Lightweight environment, configuration, and runtime readiness validator."""

import os
import sys
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config.settings import Settings, get_settings
from app.models.profile import JobProfile


@dataclass
class ValidationCheck:
    """Record representing the result of an environment or system check."""

    name: str
    category: str
    passed: bool
    is_warning: bool
    message: str
    remediation: Optional[str] = None

    @property
    def status_label(self) -> str:
        """Return human-readable status badge."""
        if self.passed:
            return "PASS"
        if self.is_warning:
            return "WARN"
        return "FAIL"


class EnvironmentValidator:
    """Validates local environment, configuration, directories, and runtime dependencies."""

    REQUIRED_PACKAGES = [
        "pydantic",
        "pydantic_settings",
        "fastapi",
        "uvicorn",
        "openpyxl",
        "jinja2",
        "httpx",
        "playwright",
        "pandas",
    ]

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def check_python_version(self) -> ValidationCheck:
        """Verify Python runtime version is at least 3.10."""
        major, minor = sys.version_info[:2]
        if (major, minor) >= (3, 10):
            return ValidationCheck(
                name="Python Version",
                category="Runtime",
                passed=True,
                is_warning=False,
                message=f"Python {major}.{minor}.{sys.version_info.micro} satisfies minimum requirement (>= 3.10)",
            )
        return ValidationCheck(
            name="Python Version",
            category="Runtime",
            passed=False,
            is_warning=False,
            message=f"Python {major}.{minor} is below minimum requirement (>= 3.10)",
            remediation="Install Python 3.10 or higher from python.org",
        )

    def check_packages(self) -> list[ValidationCheck]:
        """Verify core required Python packages are installed and importable."""
        results = []
        for pkg in self.REQUIRED_PACKAGES:
            try:
                __import__(pkg)
                results.append(
                    ValidationCheck(
                        name=f"Package: {pkg}",
                        category="Dependencies",
                        passed=True,
                        is_warning=False,
                        message=f"Module '{pkg}' is available",
                    )
                )
            except ImportError:
                results.append(
                    ValidationCheck(
                        name=f"Package: {pkg}",
                        category="Dependencies",
                        passed=False,
                        is_warning=False,
                        message=f"Required package '{pkg}' is missing",
                        remediation=f"Run: pip install -r requirements.txt (do not run automatically)",
                    )
                )
        return results

    def _check_directory_writable(self, dir_path: Path, name: str) -> ValidationCheck:
        """Check if directory exists or can be created, and is writable."""
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            test_file = dir_path / f".write_test_{os.getpid()}.tmp"
            test_file.write_text("ok", encoding="utf-8")
            if test_file.exists():
                test_file.unlink()
            return ValidationCheck(
                name=f"Directory: {name}",
                category="Filesystem",
                passed=True,
                is_warning=False,
                message=f"Directory '{dir_path}' exists and is writable",
            )
        except Exception as err:
            return ValidationCheck(
                name=f"Directory: {name}",
                category="Filesystem",
                passed=False,
                is_warning=False,
                message=f"Directory '{dir_path}' write test failed: {err}",
                remediation=f"Ensure write permissions exist for '{dir_path}'",
            )

    def check_directories(self) -> list[ValidationCheck]:
        """Verify all essential data directories are accessible and writable."""
        dirs_to_check = [
            ("Data Root", self.settings.DATABASE_PATH.parent),
            ("Exports", self.settings.EXPORTS_DIR),
            ("Logs", self.settings.LOGS_DIR),
            ("Backups", self.settings.BACKUPS_DIR),
        ]
        return [self._check_directory_writable(path, name) for name, path in dirs_to_check]

    def check_profile(self) -> ValidationCheck:
        """Verify job search profile exists and parses cleanly."""
        profile_path = self.settings.PROFILE_PATH
        if not profile_path.is_absolute():
            profile_path = self.settings.PROJECT_ROOT / profile_path

        if not profile_path.exists():
            return ValidationCheck(
                name="Profile File",
                category="Configuration",
                passed=False,
                is_warning=True,
                message=f"Profile file '{profile_path}' does not exist (will use built-in defaults)",
                remediation=f"Create a personalized profile at '{profile_path}'",
            )

        try:
            profile = JobProfile.from_file(profile_path)
            num_roles = len(profile.target_roles)
            num_skills = len(profile.skills)
            return ValidationCheck(
                name="Profile File",
                category="Configuration",
                passed=True,
                is_warning=False,
                message=f"Profile valid: {num_roles} target roles, {num_skills} skills, {len(profile.preferred_locations)} locations",
            )
        except Exception as err:
            return ValidationCheck(
                name="Profile File",
                category="Configuration",
                passed=False,
                is_warning=False,
                message=f"Profile parsing error at '{profile_path}': {err}",
                remediation=f"Correct JSON formatting or schema in '{profile_path}'",
            )

    def check_database(self) -> ValidationCheck:
        """Verify SQLite database file is accessible, valid, and readable."""
        db_path = self.settings.DATABASE_PATH
        if not db_path.exists():
            # If not yet created, ensure parent directory is writable
            if db_path.parent.exists() and os.access(db_path.parent, os.W_OK):
                return ValidationCheck(
                    name="Database File",
                    category="Database",
                    passed=True,
                    is_warning=True,
                    message=f"Database '{db_path}' not yet created (parent directory is writable)",
                )
            return ValidationCheck(
                name="Database File",
                category="Database",
                passed=False,
                is_warning=False,
                message=f"Database directory '{db_path.parent}' is not writable",
                remediation="Ensure write permissions on data directory",
            )

        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = con.cursor()
            cur.execute("PRAGMA quick_check;")
            res = cur.fetchone()
            con.close()
            if res and res[0] == "ok":
                return ValidationCheck(
                    name="Database File",
                    category="Database",
                    passed=True,
                    is_warning=False,
                    message=f"SQLite database '{db_path}' is accessible and integrity check passed",
                )
            return ValidationCheck(
                name="Database File",
                category="Database",
                passed=False,
                is_warning=False,
                message=f"SQLite integrity check reported: {res}",
                remediation="Review database integrity or restore from a valid backup",
            )
        except Exception as err:
            return ValidationCheck(
                name="Database File",
                category="Database",
                passed=False,
                is_warning=False,
                message=f"Failed to open database '{db_path}': {err}",
                remediation="Check database permissions or corruption",
            )

    def validate_all(self) -> tuple[bool, list[ValidationCheck]]:
        """Run all environment validation checks.

        Returns:
            Tuple of (overall_healthy: bool, list of checks)
        """
        checks: list[ValidationCheck] = []
        checks.append(self.check_python_version())
        checks.extend(self.check_packages())
        checks.extend(self.check_directories())
        checks.append(self.check_profile())
        checks.append(self.check_database())

        # Overall healthy if no FAIL checks exist (warnings are allowed)
        has_failure = any(not c.passed and not c.is_warning for c in checks)
        return not has_failure, checks
