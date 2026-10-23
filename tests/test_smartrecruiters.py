"""Unit tests for SmartRecruiters career portal source connector.

Verifies:
- Config-driven company configuration.
- Every job extracts: company, title, job ID, location, posting date, direct apply URL.
- Independent failure isolation.
- Offline collection using saved sample JSON files (labelled as samples).
"""

import asyncio
import json
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from app.sources.smartrecruiters import SmartRecruitersJobSource

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"


def test_smartrecruiters_config_driven():
    """Verify company configuration can be customized via config."""
    source = SmartRecruitersJobSource(companies=["customco", "testcorp"])
    assert source.configured_companies == ["customco", "testcorp"]


def test_smartrecruiters_sample_parsing():
    """Test parsing saved sample SmartRecruiters response with all required fields."""
    sample_file = SAMPLES_DIR / "smartrecruiters_sample.json"
    with open(sample_file, "r", encoding="utf-8") as f:
        sample_data = json.load(f)

    source = SmartRecruitersJobSource(is_enabled=True, companies=["samplecompany"])

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_data

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        jobs = asyncio.run(source.collect_jobs(roles=["Software Engineer"], locations=["Bengaluru"], max_results=10))

    assert len(jobs) == 2
    j1 = jobs[0]
    assert j1.company == "Samplecompany"
    assert j1.title == "Software Engineer - Backend"
    assert j1.job_id == "743999999999001"
    assert "Bengaluru" in j1.location
    assert j1.date_posted == "2026-03-15T10:00:00.000Z"
    assert j1.url == "https://jobs.smartrecruiters.com/samplecompany/743999999999001"


def test_smartrecruiters_independent_failure():
    """Test that failure of one company doesn't crash others."""
    sample_file = SAMPLES_DIR / "smartrecruiters_sample.json"
    with open(sample_file, "r", encoding="utf-8") as f:
        sample_data = json.load(f)

    source = SmartRecruitersJobSource(is_enabled=True, companies=["goodco", "badco"])

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_data

    async def mock_get(url, *args, **kwargs):
        if "goodco" in str(url):
            return mock_resp
        raise Exception("SmartRecruiters API Timeout")

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        jobs = asyncio.run(source.collect_jobs(roles=["Software"], locations=["India"], max_results=10))

    assert len(jobs) == 2
    assert source.diagnostics["by_company"]["goodco"]["status"] == "COMPLETED"
    assert source.diagnostics["by_company"]["badco"]["status"] == "FAILED"
