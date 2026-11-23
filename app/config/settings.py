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
    MAX_RESULTS_PER_SOURCE: int = Field(default=1000, ge=1, le=5000)
    HEADLESS_BROWSER: bool = True
    BROWSER_TIMEOUT_MS: int = Field(default=30000, ge=1000, le=300000)

    # Scheduled Run Time
    DAILY_RUN_TIME: str = "08:00"

    # LinkedIn Job Source Configuration
    LINKEDIN_ENABLED: bool = False

    # Naukri Source Configuration
    NAUKRI_ENABLED: bool = False
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

    # Accenture Careers Source Configuration
    ACCENTURE_ENABLED: bool = False
    ACCENTURE_MAX_JOBS: int = Field(default=200, ge=1, le=5000)
    ACCENTURE_REQUEST_DELAY_SEC: float = Field(default=1.0, ge=0.0, le=60.0)
    ACCENTURE_COUNTRY: str = "India"
    ACCENTURE_COUNTRY_SITE: str = "in-en"
    ACCENTURE_SEARCH_ROLES: str = ""
    ACCENTURE_SORT_BY: str = "0"  # 0 = Relevance / Vector Search, 1 = Newest

    # Workday CXS Careers Configuration (Task 6)
    WORKDAY_ENABLED: bool = True
    WORKDAY_COMPANIES: str = "adobe,intel,nvidia,salesforce,walmart,mastercard,visa,paypal,hp"
    WORKDAY_MAX_JOBS_PER_COMPANY: int = Field(default=1000, ge=1, le=5000)
    WORKDAY_REQUEST_DELAY_SEC: float = Field(default=0.8, ge=0.0, le=60.0)
    WORKDAY_CUSTOM_CONFIGS: str = ""  # Optional JSON string for extra companies
    WORKDAY_FETCH_DETAILS: bool = False
    WORKDAY_DETAIL_DELAY_SEC: float = Field(default=0.5, ge=0.0, le=10.0)
    WORKDAY_MAX_DETAILS_PER_RUN: int = Field(default=50, ge=1, le=500)

    # SmartRecruiters Configuration (Task 6)
    SMARTRECRUITERS_ENABLED: bool = False
    SMARTRECRUITERS_COMPANIES: str = ""
    SMARTRECRUITERS_MAX_JOBS_PER_COMPANY: int = Field(default=25, ge=1, le=500)
    SMARTRECRUITERS_REQUEST_DELAY_SEC: float = Field(default=1.0, ge=0.0, le=60.0)

    # SuccessFactors RSS Source Configuration (Task 10: Capgemini, Wipro, HCLTech)
    SUCCESSFACTORS_ENABLED: bool = True
    SUCCESSFACTORS_COMPANIES: str = "capgemini,wipro,hcltech,deloitte_india,deloitte_srilanka,deloitte_mauritius"
    SUCCESSFACTORS_REQUEST_DELAY_SEC: float = Field(default=1.0, ge=0.0, le=60.0)
    SUCCESSFACTORS_CUSTOM_CONFIGS: str = ""
    SUCCESSFACTORS_MAX_JOBS_PER_COMPANY: int = Field(default=100, ge=1, le=500)

    # Oracle Cloud HCM Source Configuration (Task 10: Oracle, Dell)
    ORACLE_HCM_ENABLED: bool = True
    ORACLE_HCM_COMPANIES: str = "oracle,dell"
    ORACLE_HCM_REQUEST_DELAY_SEC: float = Field(default=1.0, ge=0.0, le=60.0)
    ORACLE_HCM_CUSTOM_CONFIGS: str = ""
    ORACLE_HCM_MAX_JOBS_PER_COMPANY: int = Field(default=100, ge=1, le=500)

    # Company JSON Feeds Source Configuration (Task 10: Amazon, Infosys)
    COMPANY_JSON_ENABLED: bool = True
    COMPANY_JSON_COMPANIES: str = "amazon,infosys"
    COMPANY_JSON_REQUEST_DELAY_SEC: float = Field(default=1.0, ge=0.0, le=60.0)
    COMPANY_JSON_MAX_PAGES_PER_QUERY: int = Field(default=5, ge=1, le=50)
    COMPANY_JSON_CUSTOM_CONFIGS: str = ""
    COMPANY_JSON_MAX_JOBS_PER_COMPANY: int = Field(default=1000, ge=1, le=5000)
    AMAZON_MAX_JOBS: int = Field(default=1000, ge=1, le=5000)

    # TurboHire Source Configuration (Task 10: Flipkart)
    TURBOHIRE_ENABLED: bool = True
    TURBOHIRE_COMPANIES: str = "flipkart"
    TURBOHIRE_REQUEST_DELAY_SEC: float = Field(default=1.0, ge=0.0, le=60.0)
    TURBOHIRE_CUSTOM_CONFIGS: str = ""
    TURBOHIRE_MAX_JOBS_PER_COMPANY: int = Field(default=100, ge=1, le=500)

    # Daily Application Goal (Phase 9)
    DAILY_APPLICATION_TARGET: int = Field(default=5, ge=1, le=100)

    # Backup Retention (Phase 15)
    DATABASE_BACKUP_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)

    # Resume Configuration (Phase 10)
    RESUME_PATH: Optional[str] = ""

    # Master switch for enabled sources / portals (Task 16)
    ENABLED_SOURCES: str = Field(
        default=(
            "accenture,workday,adobe,intel,nvidia,salesforce,walmart,mastercard,visa,paypal,hp,"
            "amazon,infosys,capgemini,wipro,hcltech,deloitte_india,deloitte_srilanka,deloitte_mauritius,"
            "oracle,dell,flipkart,turbohire,smartrecruiters,sopra_steria,oracle_hcm,hexaware,zensar,eclerx,ofss,"
            "birlasoft,mastek,greenhouse,stripe,cloudflare,databricks,elastic,canonical,mongodb,brex,gitlab,"
            "affirm,lyft,scaleai,pinterest,reddit,figma,twilio,instacart,airtable"
        ),
        description="Single switch for enabled sources and career portals (comma-separated).",
    )
    SOURCE_TIMEOUT_SEC: float = Field(
        default=300.0,
        ge=5.0,
        le=600.0,
        description="Per-source time limit in seconds so slow sources cannot stall the run.",
    )

    # Experience Double Filter Configuration (Task 2)
    MAX_REQUIRED_MIN_YEARS: int = Field(default=1, ge=0, le=50)

    # Experience MATCH/REVIEW thresholds (Task 15)
    MATCH_MAX_YEARS: int = Field(default=2, ge=0, le=50)
    REVIEW_MAX_YEARS: int = Field(default=3, ge=0, le=50)

    # Full Multi-Sheet Report Flag (Task 12)
    FULL_REPORT: bool = False

    # Multi-User Initial Account Configuration (Phase 3B)
    INITIAL_USER_EMAIL: str = Field(
        default="admin@jobfinder.local",
        description="Email address for the initial designated owner account during migration",
    )
    INITIAL_USER_NAME: str = Field(
        default="Primary Candidate",
        description="Display name for the initial designated owner account",
    )
    INITIAL_USER_PASSWORD_HASH: Optional[str] = Field(
        default=None,
        description="Pre-computed password hash for the initial user account; if omitted, a secure token is generated",
    )

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

    @property
    def enabled_sources_list(self) -> list[str]:
        """Return parsed, lowercase list of enabled source/portal keys."""
        if not self.ENABLED_SOURCES:
            return []
        if isinstance(self.ENABLED_SOURCES, list):
            return [str(s).strip().lower() for s in self.ENABLED_SOURCES if str(s).strip()]
        return [s.strip().lower() for s in str(self.ENABLED_SOURCES).split(",") if s.strip()]

    @property
    def accenture_search_roles_list(self) -> list[str]:
        """Return parsed, whitespace-stripped list of Accenture search role keywords if configured."""
        if not self.ACCENTURE_SEARCH_ROLES:
            return []
        return [r.strip() for r in self.ACCENTURE_SEARCH_ROLES.split(",") if r.strip()]

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
