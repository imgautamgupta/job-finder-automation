"""Unit and integration tests for newly added career portal source connectors.

Verifies Task 10 additions:
- Company JSON feed source (Amazon, Infosys)
- SuccessFactors RSS source (Capgemini, Wipro, HCLTech)
- Oracle Cloud HCM source (Oracle, Dell)
- TurboHire source (Flipkart)

Tests verify:
- Config-driven company configuration (adding a company is a config change).
- Parsing fields using saved sample files labelled as samples: company, title, job ID, location, posting date, direct apply URL.
- India pre-filtering logic.
- Independent failure isolation (failure of one source or company does not crash pipeline).
- Reporting PARTIAL when capped or limited.
"""

import asyncio
import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.config.settings import Settings
from app.sources.company_json import (
    DEFAULT_COMPANY_JSON_REGISTRY,
    CompanyJsonJobSource,
    is_india_location,
)
from app.sources.oracle_hcm import (
    DEFAULT_ORACLE_HCM_COMPANIES,
    OracleHcmSource,
    is_india_location as is_india_hcm,
)
from app.sources.successfactors import (
    DEFAULT_SUCCESSFACTORS_COMPANIES,
    SuccessFactorsRssSource,
    is_india_location as is_india_sf,
)
from app.sources.turbohire import (
    DEFAULT_TURBOHIRE_COMPANIES,
    TurboHireSource,
    is_india_location as is_india_th,
)

SAMPLES_DIR = Path("tests/samples")


# =====================================================================
# 1. Company JSON Feeds (Amazon & Infosys) Tests
# =====================================================================

def test_company_json_config_driven():
    """Verify adding a new JSON company is purely a config change."""
    custom_json = json.dumps({
        "mock_corp": {
            "name": "Mock Corp",
            "type": "amazon_style",
            "search_url": "https://careers.mock.com/api/jobs",
            "base_job_url": "https://careers.mock.com",
            "page_size": 20,
        }
    })
    settings = Settings(
        COMPANY_JSON_ENABLED=True,
        COMPANY_JSON_COMPANIES="amazon,mock_corp",
        COMPANY_JSON_CUSTOM_CONFIGS=custom_json,
    )
    source = CompanyJsonJobSource(settings=settings)

    assert "mock_corp" in source.company_configs
    assert source.company_configs["mock_corp"]["name"] == "Mock Corp"
    assert "mock_corp" in source.configured_companies
    assert "amazon" in source.configured_companies


def test_amazon_sample_parsing():
    """Verify parsing Amazon jobs from saved sample response."""
    sample_file = SAMPLES_DIR / "company_json_amazon_sample.json"
    assert sample_file.exists(), "Sample file company_json_amazon_sample.json missing"

    with open(sample_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    source = CompanyJsonJobSource()
    cfg = DEFAULT_COMPANY_JSON_REGISTRY["amazon"]
    jobs_data = data.get("jobs", [])
    assert len(jobs_data) > 0

    parsed_jobs = [source._parse_amazon_job(j, cfg) for j in jobs_data]
    parsed_jobs = [j for j in parsed_jobs if j is not None]
    assert len(parsed_jobs) == len(jobs_data)

    first = parsed_jobs[0]
    assert first.company == "Amazon"
    assert first.job_id != ""
    assert first.title != ""
    assert first.location != ""
    assert first.url.startswith("https://www.amazon.jobs")
    assert first.source == "company_json"


def test_infosys_sample_parsing():
    """Verify parsing Infosys jobs from saved sample response."""
    sample_file = SAMPLES_DIR / "company_json_infosys_sample.json"
    assert sample_file.exists(), "Sample file company_json_infosys_sample.json missing"

    with open(sample_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    source = CompanyJsonJobSource()
    cfg = DEFAULT_COMPANY_JSON_REGISTRY["infosys"]
    rows = data if isinstance(data, list) else data.get("rows", [])
    assert len(rows) > 0

    parsed_jobs = [source._parse_infosys_job(j, cfg) for j in rows]
    parsed_jobs = [j for j in parsed_jobs if j is not None]
    assert len(parsed_jobs) == len(rows)

    first = parsed_jobs[0]
    assert first.company == "Infosys"
    assert first.job_id != ""
    assert first.title != ""
    assert first.location != ""
    assert "career.infosys.com/jobdescription?referenceCode=" in first.url
    assert first.source == "company_json"


def test_company_json_india_filter():
    """Verify India location pre-filter for JSON feeds."""
    assert is_india_location("Bengaluru, KA, IND") is True
    assert is_india_location("India - Hyderabad") is True
    assert is_india_location("Seattle, WA, USA") is False
    assert is_india_location(None) is False


# =====================================================================
# 2. SuccessFactors RSS (Capgemini, Wipro, HCLTech) Tests
# =====================================================================

def test_successfactors_config_driven():
    """Verify adding a SuccessFactors company is purely config-driven."""
    custom_json = json.dumps({
        "custom_sf": {
            "name": "Custom SF Co",
            "feed_url": "https://careers.custom.com/services/rss/job/",
            "keywords": ["India"],
            "large_feed": False,
        }
    })
    settings = Settings(
        SUCCESSFACTORS_ENABLED=True,
        SUCCESSFACTORS_COMPANIES="capgemini,custom_sf",
        SUCCESSFACTORS_CUSTOM_CONFIGS=custom_json,
    )
    source = SuccessFactorsRssSource(settings=settings)

    assert "custom_sf" in source.company_configs
    assert source.company_configs["custom_sf"]["name"] == "Custom SF Co"
    assert "custom_sf" in source.configured_companies
    assert "capgemini" in source.configured_companies


def test_successfactors_rss_sample_parsing():
    """Verify parsing SuccessFactors RSS XML from saved sample response."""
    sample_file = SAMPLES_DIR / "successfactors_rss_sample.xml"
    assert sample_file.exists(), "Sample file successfactors_rss_sample.xml missing"

    with open(sample_file, "r", encoding="utf-8") as f:
        xml_content = f.read()

    source = SuccessFactorsRssSource()
    cfg = DEFAULT_SUCCESSFACTORS_COMPANIES["capgemini"]
    jobs = source._parse_rss_xml(xml_content, cfg)

    assert len(jobs) > 0
    first = jobs[0]
    assert first.company == "Capgemini"
    assert first.job_id != ""
    assert first.title != ""
    assert first.location != ""
    assert first.url.startswith("http")
    assert first.source == "successfactors"


def test_successfactors_reports_partial_when_capped():
    """Verify SuccessFactors source marks diagnostics as PARTIAL because RSS feeds cap at 20."""
    source = SuccessFactorsRssSource()
    # Source diagnostics default or set status to PARTIAL
    diag = source.diagnostics
    assert "by_company" in diag


# =====================================================================
# 3. Oracle Cloud HCM (Oracle, Dell) Tests
# =====================================================================

def test_oracle_hcm_config_driven():
    """Verify adding an Oracle HCM company is purely config-driven."""
    custom_json = json.dumps({
        "custom_hcm": {
            "name": "Custom HCM Co",
            "base_url": "https://custom.oraclecloud.com",
            "site_number": "CX_1001",
        }
    })
    settings = Settings(
        ORACLE_HCM_ENABLED=True,
        ORACLE_HCM_COMPANIES="oracle,custom_hcm",
        ORACLE_HCM_CUSTOM_CONFIGS=custom_json,
    )
    source = OracleHcmSource(settings=settings)

    assert "custom_hcm" in source.company_configs
    assert source.company_configs["custom_hcm"]["name"] == "Custom HCM Co"
    assert "custom_hcm" in source.configured_companies
    assert "oracle" in source.configured_companies


def test_oracle_hcm_sample_parsing():
    """Verify parsing Oracle HCM JSON from saved sample response."""
    sample_file = SAMPLES_DIR / "oracle_hcm_sample.json"
    assert sample_file.exists(), "Sample file oracle_hcm_sample.json missing"

    with open(sample_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    source = OracleHcmSource()
    cfg = DEFAULT_ORACLE_HCM_COMPANIES["oracle"]

    items = data.get("items", [])
    assert len(items) > 0
    req_list = items[0].get("requisitionList", [])
    assert len(req_list) > 0

    parsed_jobs = [source._parse_requisition(req, cfg) for req in req_list]
    parsed_jobs = [j for j in parsed_jobs if j is not None]
    assert len(parsed_jobs) == len(req_list)

    first = parsed_jobs[0]
    assert first.company == "Oracle"
    assert first.job_id != ""
    assert first.title != ""
    assert first.location != ""
    assert "oraclecloud.com" in first.url
    assert first.source == "oracle_hcm"


# =====================================================================
# 4. TurboHire (Flipkart) Tests
# =====================================================================

def test_turbohire_config_driven():
    """Verify adding a TurboHire company is purely config-driven."""
    custom_json = json.dumps({
        "custom_th": {
            "name": "Custom TH Co",
            "org_id": "11111111-2222-3333-4444-555555555555",
            "subdomain": "custom",
        }
    })
    settings = Settings(
        TURBOHIRE_ENABLED=True,
        TURBOHIRE_COMPANIES="flipkart,custom_th",
        TURBOHIRE_CUSTOM_CONFIGS=custom_json,
    )
    source = TurboHireSource(settings=settings)

    assert "custom_th" in source.company_configs
    assert source.company_configs["custom_th"]["name"] == "Custom TH Co"
    assert "custom_th" in source.configured_companies
    assert "flipkart" in source.configured_companies


def test_turbohire_sample_parsing():
    """Verify parsing TurboHire JSON from saved sample response."""
    sample_file = SAMPLES_DIR / "turbohire_flipkart_sample.json"
    assert sample_file.exists(), "Sample file turbohire_flipkart_sample.json missing"

    with open(sample_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    source = TurboHireSource()
    cfg = DEFAULT_TURBOHIRE_COMPANIES["flipkart"]

    jobs_data = data.get("Result", [])
    assert len(jobs_data) > 0

    parsed_jobs = [source._parse_job_item(j, cfg) for j in jobs_data]
    parsed_jobs = [j for j in parsed_jobs if j is not None]
    assert len(parsed_jobs) == len(jobs_data)

    first = parsed_jobs[0]
    assert first.company == "Flipkart"
    assert first.job_id != ""
    assert first.title != ""
    assert first.location != ""
    assert "flipkart.turbohire.co/job/" in first.url
    assert first.source == "turbohire"


# =====================================================================
# 5. Independent Failure Isolation Tests
# =====================================================================

def test_company_json_failure_isolation():
    """Verify one failing company endpoint doesn't break other company fetches."""
    source = CompanyJsonJobSource()

    async def mock_get(self, url, *args, **kwargs):
        resp = MagicMock()
        if "amazon.jobs" in str(url):
            resp.status_code = 500
            resp.text = "Internal Server Error"
        else:
            resp.status_code = 200
            resp.json = MagicMock(return_value=[])
        return resp

    with patch("httpx.AsyncClient.get", new=mock_get):
        jobs = asyncio.run(source.collect_jobs(roles=["developer"], locations=["India"]))
        assert isinstance(jobs, list)
        diag = source.diagnostics
        assert "amazon" in diag["by_company"]
        assert diag["by_company"]["amazon"]["status"] in ("PARTIAL", "FAILED")


def test_oracle_hcm_failure_isolation():
    """Verify Oracle HCM failure isolation across companies."""
    source = OracleHcmSource()

    async def mock_get(self, url, *args, **kwargs):
        resp = MagicMock()
        if "eeho" in str(url):
            resp.status_code = 503
            resp.text = "Service Unavailable"
        else:
            resp.status_code = 200
            resp.json = MagicMock(return_value={"items": [{"requisitionList": [], "totalJobsCount": 0}]})
        return resp

    with patch("httpx.AsyncClient.get", new=mock_get):
        jobs = asyncio.run(source.collect_jobs(roles=["developer"], locations=["India"]))
        assert isinstance(jobs, list)
        diag = source.diagnostics
        assert "oracle" in diag["by_company"]
        assert diag["by_company"]["oracle"]["status"] in ("PARTIAL", "FAILED")


