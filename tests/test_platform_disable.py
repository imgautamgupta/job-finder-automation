"""Tests for Task 3: Disabling job-portal/platform sources and keeping source-health clean."""

import asyncio
import json
from unittest.mock import patch

from app.config.settings import Settings
from app.database.database import DatabaseManager
from app.services.collector import JobCollector
from app.sources.linkedin import LinkedInJobSource
from app.sources.naukri import NaukriJobSource


def test_settings_platforms_disabled_by_default():
    """Verify that job portal / aggregator sources (LinkedIn, Naukri) are disabled by default."""
    settings = Settings()
    assert settings.LINKEDIN_ENABLED is False
    assert settings.NAUKRI_ENABLED is False


def test_linkedin_source_initialization_respects_config():
    """Verify LinkedInJobSource respects default and custom config."""
    # Default settings -> disabled
    src_default = LinkedInJobSource()
    assert src_default.is_enabled is False
    assert src_default.source_name == "linkedin"
    assert src_default.last_status == "DISABLED"

    # Explicit flag overrides config
    src_enabled = LinkedInJobSource(is_enabled=True)
    assert src_enabled.is_enabled is True
    assert src_enabled.last_status == "IDLE"

    # Custom settings overrides
    custom_settings = Settings(LINKEDIN_ENABLED=True)
    src_custom = LinkedInJobSource(settings=custom_settings)
    assert src_custom.is_enabled is True


def test_naukri_source_initialization_respects_config():
    """Verify NaukriJobSource respects default and custom config."""
    # Default settings -> disabled
    src_default = NaukriJobSource()
    assert src_default.is_enabled is False
    assert src_default.source_name == "naukri"
    assert src_default.last_status == "DISABLED"

    # Explicit flag overrides
    src_enabled = NaukriJobSource(is_enabled=True)
    assert src_enabled.is_enabled is True
    assert src_enabled.last_status == "IDLE"

    # Custom settings overrides
    custom_settings = Settings(NAUKRI_ENABLED=True)
    src_custom = NaukriJobSource(settings=custom_settings)
    assert src_custom.is_enabled is True


def test_job_collector_skips_disabled_platforms():
    """Verify JobCollector cleanly skips disabled job platforms without making network or browser calls."""
    linkedin = LinkedInJobSource(is_enabled=False)
    naukri = NaukriJobSource(is_enabled=False)

    collector = JobCollector(sources=[linkedin, naukri])
    results = asyncio.run(
        collector.collect_all(roles=["Python Developer"], locations=["Bangalore"])
    )

    assert results == []
    source_results = collector.get_source_results()
    assert source_results["linkedin"]["status"] == "DISABLED"
    assert source_results["linkedin"]["error"] is None
    assert source_results["linkedin"]["collected"] == 0
    assert source_results["naukri"]["status"] == "DISABLED"
    assert source_results["naukri"]["error"] is None
    assert source_results["naukri"]["collected"] == 0
    assert collector.has_source_warnings() is False


def test_source_health_cleans_errors_for_disabled_sources(tmp_path):
    """Verify get_source_health returns clean status (error='None') for disabled platforms even if older run had errors."""
    db_file = tmp_path / "test_jobs.db"
    db = DatabaseManager(db_path=db_file)

    # Simulate a pipeline run that previously recorded an error on naukri / linkedin
    poisoned_results = {
        "naukri": {"source": "naukri", "status": "BLOCKED", "collected": 0, "error": "HTTP 403 Forbidden"},
        "linkedin": {"source": "linkedin", "status": "ERROR", "collected": 0, "error": "Navigation Timeout"},
        "accenture": {"source": "accenture", "status": "COMPLETED", "collected": 45, "error": None},
    }
    db.create_pipeline_run(
        run_id="run-with-old-errors",
        sources_attempted=["naukri", "linkedin", "accenture"],
    )
    db.update_pipeline_run(
        run_id="run-with-old-errors",
        status="COMPLETED",
        source_results=json.dumps(poisoned_results),
    )

    # When sources are disabled in settings (default)
    with patch("app.config.settings.get_settings") as mock_settings:
        mock_settings.return_value = Settings(
            LINKEDIN_ENABLED=False,
            NAUKRI_ENABLED=False,
            ACCENTURE_ENABLED=True,
            LEVER_ENABLED=False,
            GREENHOUSE_ENABLED=False,
        )
        health = db.get_source_health()

    health_by_name = {h["source"].lower(): h for h in health}

    # Disabled platform errors must be cleanly suppressed to 'None'
    assert health_by_name["naukri"]["enabled"] is False
    assert health_by_name["naukri"]["status"] == "DISABLED"
    assert health_by_name["naukri"]["error"] == "None"
    assert health_by_name["naukri"]["collected"] == 0

    assert health_by_name["linkedin"]["enabled"] is False
    assert health_by_name["linkedin"]["status"] == "DISABLED"
    assert health_by_name["linkedin"]["error"] == "None"
    assert health_by_name["linkedin"]["collected"] == 0

    # Enabled career portal must retain its status and count
    assert health_by_name["accenture"]["enabled"] is True
    assert health_by_name["accenture"]["status"] == "COMPLETED"
    assert health_by_name["accenture"]["collected"] == 45
    assert health_by_name["accenture"]["error"] == "None"
