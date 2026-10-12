"""Application configuration module using pydantic-settings."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.models.profile import JobProfile, SearchPreferences


class Settings(BaseSettings):
    """Global application settings with validated bounds and types."""

    # Project Root Directory
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

    # Environment & Logging
    APP_ENV: str = "development"
    LOG_LEVEL: str = Field(default="INFO")

    # Paths (relative to PROJECT_ROOT by default)
    DATABASE_PATH: Path = PROJECT_ROOT / "data" / "jobs.db"
    EXPORTS_DIR: Path = PROJECT_ROOT / "data" / "exports"
    LOGS_DIR: Path = PROJECT_ROOT / "data" / "logs"
    BACKUPS_DIR: Path = PROJECT_ROOT / "data" / "backups"
    LOCK_FILE: Path = PROJECT_ROOT / "data" / "job_finder.lock"
    PROFILE_PATH: Path = PROJECT_ROOT / "data" / "profile.json"

    # Scraping & Source Defaults
    MAX_RESULTS_PER_SOURCE: int = Field(default=25, ge=1, le=500)
    HEADLESS_BROWSER: bool = True
    BROWSER_TIMEOUT_MS: int = Field(default=30000, ge=1000, le=300000)

    # Scheduled Run Time
    DAILY_RUN_TIME: str = "08:00"

    # Naukri Source Configuration
    NAUKRI_ENABLED: bool = True
    NAUKRI_MAX_PAGES: int = Field(default=1, ge=1, le=50)
    NAUKRI_MAX_JOBS: int = Field(default=10, ge=1, le=200)
    NAUKRI_REQUEST_DELAY_SEC: float = Field(default=2.0, ge=0.0, le=60.0)

    # Lever Public Postings Configuration
    LEVER_ENABLED: bool = False
    LEVER_COMPANIES: str = ""
    LEVER_MAX_JOBS_PER_COMPANY: int = Field(default=25, ge=1, le=500)
    LEVER_REQUEST_DELAY_SEC: float = Field(default=1.0, ge=0.0, le=60.0)

    # Greenhouse Public Job Board Configuration
    GREENHOUSE_ENABLED: bool = False
    GREENHOUSE_COMPANIES: str = ""
    GREENHOUSE_MAX_JOBS_PER_COMPANY: int = Field(default=25, ge=1, le=500)
    GREENHOUSE_REQUEST_DELAY_SEC: float = Field(default=1.0, ge=0.0, le=60.0)

    # Daily Application Goal (Phase 9)
    DAILY_APPLICATION_TARGET: int = Field(default=5, ge=1, le=100)

    # Backup Retention (Phase 15)
    DATABASE_BACKUP_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)

    # Resume Configuration (Phase 10)
    RESUME_PATH: Optional[str] = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate and normalize logging level."""
        cleaned = v.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if cleaned not in allowed:
            raise ValueError(f"Invalid LOG_LEVEL '{v}'. Allowed values: {sorted(allowed)}")
        return cleaned

    @field_validator("DAILY_RUN_TIME")
    @classmethod
    def validate_daily_run_time(cls, v: str) -> str:
        """Validate format of DAILY_RUN_TIME (HH:MM)."""
        cleaned = v.strip()
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", cleaned):
            raise ValueError(f"DAILY_RUN_TIME must be in 24-hour 'HH:MM' format, got '{v}'")
        return cleaned

    @property
    def lever_company_list(self) -> list[str]:
        """Return parsed, whitespace-stripped list of Lever company identifiers."""
        if not self.LEVER_COMPANIES:
            return []
        return [c.strip() for c in self.LEVER_COMPANIES.split(",") if c.strip()]

    @property
    def greenhouse_company_list(self) -> list[str]:
        """Return parsed, whitespace-stripped list of Greenhouse board identifiers."""
        if not self.GREENHOUSE_COMPANIES:
            return []
        return [c.strip() for c in self.GREENHOUSE_COMPANIES.split(",") if c.strip()]

    def load_profile(self) -> JobProfile:
        """Load and validate the job search preferences profile from disk.

        Returns:
            Validated JobProfile instance. If the file does not exist,
            returns a default JobProfile.
        """
        target_path = self.PROFILE_PATH
        if not target_path.is_absolute():
            target_path = self.PROJECT_ROOT / target_path

        if not target_path.exists():
            return JobProfile()

        return JobProfile.from_file(target_path)

    def safe_dict(self) -> dict:
        """Return sanitized dictionary representation without exposing sensitive details."""
        d = self.model_dump()
        # Ensure path representations are clean strings
        for k, v in d.items():
            if isinstance(v, Path):
                d[k] = str(v)
        return d


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of Settings."""
    return Settings()
