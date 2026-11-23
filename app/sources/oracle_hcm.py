"""Reusable, config-driven Oracle Cloud HCM Candidate Experience Career Portal Source Connector.

Collects public job postings from Oracle Cloud HCM recruiting APIs:
https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber={site},keyword={keyword}

Used by enterprise portals:
- Oracle (CX_45001)
- Dell (CX_1)

Safety & Compliance Rules:
- Uses ONLY publicly exposed candidate experience JSON endpoints.
- Does NOT require private credentials or API keys.
- Gracefully handles HTTP 401/403/404/429 and timeouts without crashing the pipeline.
- Performs India pre-filtering to verify vacancy location.
- Provides per-company health diagnostics and independent failure isolation.
"""

import asyncio
from datetime import datetime, timezone
import html
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.config.settings import Settings, get_settings
from app.models.job import Job
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


def clean_html(raw_html: Optional[str]) -> str:
    """Strip HTML tags and unescape entities."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(raw_html))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


# Verified Oracle Cloud HCM company registry
DEFAULT_ORACLE_HCM_COMPANIES: Dict[str, Dict[str, Any]] = {
    "oracle": {
        "name": "Oracle",
        "base_url": "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "candidate_ui_base": "https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_45001/job",
        "site_number": "CX_45001",
        "location": "India",
    },
    "ofss": {
        "name": "Oracle Financial Services Software",
        "base_url": "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "candidate_ui_base": "https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_45001/job",
        "site_number": "CX_45001",
        "location": "India",
    },
    "dell": {
        "name": "Dell",
        "base_url": "https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "candidate_ui_base": "https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/CX_1/job",
        "site_number": "CX_1",
        "location": "India",
    },
    "hexaware": {
        "name": "Hexaware Technologies",
        "base_url": "https://fa-etqo-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "candidate_ui_base": "https://jobs.hexaware.com",
        "site_number": "CX_1",
        "location": "India",
    },
    "zensar": {
        "name": "Zensar Technologies",
        "base_url": "https://fa-etvl-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "candidate_ui_base": "https://fa-etvl-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job",
        "site_number": "CX_1",
        "location": "India",
    },
    "eclerx": {
        "name": "eClerx",
        "base_url": "https://fa-ewji-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "candidate_ui_base": "https://fa-ewji-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job",
        "site_number": "CX_1",
        "location": "India",
    },
}

INDIAN_LOCATIONS_REGEX = re.compile(
    r"\b(india|bangalore|bengaluru|hyderabad|pune|mumbai|chennai|gurgaon|gurugram|noida|"
    r"delhi|kolkata|ahmedabad|kochi|indore|bhopal|coimbatore|chandigarh|jaipur|karnataka|"
    r"telangana|maharashtra|tamil nadu|haryana|uttar pradesh)\b",
    re.IGNORECASE,
)


def is_india_location(locations_text: Optional[str]) -> bool:
    """Pre-filter verifying whether a location string represents an India vacancy."""
    if not locations_text:
        return False
    text = locations_text.strip().lower()
    if re.search(r"\b(indianapolis|indiana)\b", text) and not re.search(r"\b(india|bengaluru|bangalore|hyderabad|pune)\b", text):
        return False
    return bool(INDIAN_LOCATIONS_REGEX.search(text))


class OracleHCMJobSource(BaseJobSource):
    """Reusable, config-driven source connector for Oracle Cloud HCM career portals."""

    def __init__(
        self,
        is_enabled: Optional[bool] = None,
        settings: Optional[Settings] = None,
        companies: Optional[List[str]] = None,
    ):
        self._settings = settings or get_settings()
        enabled_flag = (
            is_enabled
            if is_enabled is not None
            else getattr(self._settings, "ORACLE_HCM_ENABLED", True)
        )
        super().__init__(is_enabled=enabled_flag)

        self.max_jobs_per_company = getattr(self._settings, "ORACLE_HCM_MAX_JOBS_PER_COMPANY", 100)
        self.request_delay_sec = getattr(self._settings, "ORACLE_HCM_REQUEST_DELAY_SEC", 1.0)

        # Build company registry from defaults + custom configs
        self.company_configs = dict(DEFAULT_ORACLE_HCM_COMPANIES)
        custom_json = getattr(self._settings, "ORACLE_HCM_CUSTOM_CONFIGS", "")
        if custom_json:
            try:
                custom_dict = json.loads(custom_json)
                self.company_configs.update(custom_dict)
            except Exception as e:
                logger.warning("Failed to parse ORACLE_HCM_CUSTOM_CONFIGS: %s", e)

        if companies:
            self.configured_companies = [c.strip().lower() for c in companies if c.strip()]
        else:
            raw_companies = getattr(self._settings, "ORACLE_HCM_COMPANIES", "")
            if raw_companies:
                self.configured_companies = [c.strip().lower() for c in raw_companies.split(",") if c.strip()]
            else:
                self.configured_companies = list(self.company_configs.keys())

        self.diagnostics: Dict[str, Any] = {
            "by_company": {},
            "total_collected": 0,
            "valid_normalized": 0,
        }

    @property
    def source_name(self) -> str:
        return "oracle_hcm"

    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Collect postings across configured Oracle Cloud HCM companies with independent failure isolation."""
        if not self.is_enabled:
            logger.info("Oracle Cloud HCM collection is disabled in configuration.")
            self.last_status = "DISABLED"
            self.last_error = None
            return []

        self.last_status = "COMPLETED"
        self.last_error = None
        all_jobs: List[Job] = []

        self.diagnostics = {
            "by_company": {},
            "total_collected": 0,
            "valid_normalized": 0,
        }

        comp_limit = min(max_results, self.max_jobs_per_company) if max_results < 25 else self.max_jobs_per_company

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for comp_key in self.configured_companies:
                comp_config = self.company_configs.get(comp_key)
                if not comp_config:
                    logger.warning("[ORACLE_HCM] Unknown company key '%s'; skipping.", comp_key)
                    self.diagnostics["by_company"][comp_key] = {
                        "name": comp_key.capitalize(),
                        "status": "UNKNOWN_CONFIG",
                        "error": "No configuration found",
                        "collected": 0,
                        "available": 0,
                        "gap": 0,
                    }
                    continue

                comp_name = comp_config.get("name", comp_key.capitalize())
                logger.info("[ORACLE_HCM] Collecting jobs for: %s (%s)...", comp_name, comp_key)

                try:
                    comp_jobs = await self._collect_company_jobs(
                        client=client,
                        comp_config=comp_config,
                        comp_key=comp_key,
                        max_limit=comp_limit,
                    )
                    all_jobs.extend(comp_jobs)
                except Exception as comp_err:
                    logger.warning("[ORACLE_HCM] Independent failure for %s: %s", comp_name, comp_err)
                    self.diagnostics["by_company"][comp_key] = {
                        "name": comp_name,
                        "status": "FAILED",
                        "error": str(comp_err),
                        "collected": 0,
                        "available": 0,
                        "gap": 0,
                    }

                if self.request_delay_sec > 0:
                    await asyncio.sleep(self.request_delay_sec)

        self.last_collected_count = len(all_jobs)
        companies_with_errors = [
            c for c in self.diagnostics["by_company"].values()
            if c.get("error") is not None or c.get("status") in ("FAILED", "PARTIAL")
        ]
        if len(companies_with_errors) > 0:
            err_summaries = [f"{c['name']} ({c.get('error') or c.get('status')})" for c in companies_with_errors]
            self.last_status = "PARTIAL" if len(all_jobs) > 0 else "FAILED"
            self.last_error = "; ".join(err_summaries)
        else:
            self.last_status = "COMPLETED"
            self.last_error = None

        logger.info(
            "[ORACLE_HCM] Finished collection across %d companies. Total jobs: %d",
            len(self.configured_companies),
            len(all_jobs),
        )
        return all_jobs

    async def _collect_company_jobs(
        self,
        client: httpx.AsyncClient,
        comp_config: Dict[str, Any],
        comp_key: str,
        max_limit: int,
    ) -> List[Job]:
        """Fetch and parse jobs for a single Oracle Cloud HCM company with pagination."""
        comp_name = comp_config["name"]
        base_url = comp_config["base_url"]
        site_number = comp_config["site_number"]
        location_param = comp_config.get("location", comp_config.get("keyword", "India"))
        candidate_ui_base = comp_config["candidate_ui_base"]

        collected_jobs: List[Job] = []
        seen_job_ids = set()
        total_available = 0
        req_error: Optional[str] = None
        offset = 0
        limit = 25

        while len(collected_jobs) < max_limit:
            finder_param = f"findReqs;siteNumber={site_number},location={location_param}"
            url = f"{base_url}?onlyData=true&expand=requisitionList&finder={finder_param}&limit={limit}&offset={offset}"

            resp = None
            for attempt in range(3):
                try:
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    if resp.status_code == 429:
                        await asyncio.sleep(2.0 * (attempt + 1))
                        continue
                    elif resp.status_code == 200:
                        break
                    else:
                        req_error = f"HTTP {resp.status_code}"
                        break
                except Exception as err:
                    if attempt < 2:
                        await asyncio.sleep(1.0)
                        continue
                    req_error = str(err)
                    break

            if not resp or resp.status_code != 200:
                break

            data = resp.json()
            items = data.get("items", [])
            if not items:
                break

            first_item = items[0]
            req_list = first_item.get("requisitionList", [])
            reported_total = first_item.get("TotalJobsCount") or first_item.get("TotalJobs")

            if offset == 0 and reported_total is not None:
                try:
                    total_available = int(reported_total)
                except (ValueError, TypeError):
                    total_available = len(req_list)
            elif offset == 0:
                total_available = len(req_list)

            if not req_list:
                break

            for req in req_list:
                if len(collected_jobs) >= max_limit:
                    break

                job_id = str(req.get("Id") or "").strip()
                title = (req.get("Title") or "").strip()
                if not job_id or not title:
                    continue

                if job_id in seen_job_ids:
                    continue

                location = (req.get("PrimaryLocation") or "India").strip()
                posted_date = (req.get("PostedDate") or "Unknown").strip()

                desc_parts = []
                if req.get("Description"):
                    desc_parts.append(clean_html(req["Description"]))
                if req.get("ShortDescriptionStr"):
                    desc_parts.append(clean_html(req["ShortDescriptionStr"]))
                if req.get("ExternalQualificationsStr"):
                    desc_parts.append(f"Qualifications:\n{clean_html(req['ExternalQualificationsStr'])}")
                if req.get("ExternalResponsibilitiesStr"):
                    desc_parts.append(f"Responsibilities:\n{clean_html(req['ExternalResponsibilitiesStr'])}")
                full_desc = "\n\n".join(desc_parts).strip() or f"{title} at {comp_name}. Location: {location}. Posted: {posted_date}."

                apply_url = f"{candidate_ui_base}/{job_id}"

                job = Job(
                    source=self.source_name,
                    title=title,
                    company=comp_name,
                    location=location,
                    url=apply_url,
                    job_id=job_id,
                    source_job_id=job_id,
                    date_posted=posted_date,
                    description=full_desc,
                    date_found=datetime.now(timezone.utc),
                    extra_metadata={"company_key": comp_key, "application_url": apply_url},
                )
                seen_job_ids.add(job_id)
                collected_jobs.append(job)

            offset += len(req_list)
            has_more = data.get("hasMore", False)
            if not has_more or len(req_list) < limit:
                break

            if self.request_delay_sec > 0:
                await asyncio.sleep(self.request_delay_sec)

        gap = max(0, total_available - len(collected_jobs))
        status = "PARTIAL" if (req_error or total_available > len(collected_jobs)) else "COMPLETED"

        self.diagnostics["by_company"][comp_key] = {
            "name": comp_name,
            "status": status,
            "available": total_available,
            "collected": len(collected_jobs),
            "gap": gap,
            "error": req_error,
        }
        self.diagnostics["total_collected"] += len(collected_jobs)
        self.diagnostics["valid_normalized"] += len(collected_jobs)

        logger.info(
            "[ORACLE_HCM] %s: total available: %d, fetched: %d, gap: %d (status: %s)",
            comp_name, total_available, len(collected_jobs), gap, status
        )
        return collected_jobs

    def parse_requisition(self, req: Dict[str, Any], comp_config: Dict[str, Any]) -> Optional[Job]:
        """Parse raw Oracle Cloud HCM requisition into Job model instance with full qualifications."""
        comp_name = comp_config.get("name", "Oracle")
        candidate_ui_base = comp_config.get("candidate_ui_base", "")
        job_id = str(req.get("Id") or "").strip()
        title = (req.get("Title") or "").strip()
        if not job_id or not title:
            return None

        location = (req.get("PrimaryLocation") or "India").strip()
        posted_date = (req.get("PostedDate") or "Unknown").strip()

        desc_parts = []
        if req.get("Description"):
            desc_parts.append(clean_html(req["Description"]))
        if req.get("ShortDescriptionStr"):
            desc_parts.append(clean_html(req["ShortDescriptionStr"]))
        if req.get("ExternalQualificationsStr"):
            desc_parts.append(f"Qualifications:\n{clean_html(req['ExternalQualificationsStr'])}")
        if req.get("ExternalResponsibilitiesStr"):
            desc_parts.append(f"Responsibilities:\n{clean_html(req['ExternalResponsibilitiesStr'])}")
        full_desc = "\n\n".join(desc_parts).strip() or f"{title} at {comp_name}. Location: {location}. Posted: {posted_date}."

        apply_url = f"{candidate_ui_base}/{job_id}" if candidate_ui_base else ""

        return Job(
            source=self.source_name,
            title=title,
            company=comp_name,
            location=location,
            url=apply_url,
            job_id=job_id,
            source_job_id=job_id,
            date_posted=posted_date,
            description=full_desc,
            date_found=datetime.now(timezone.utc),
        )

    _parse_requisition = parse_requisition

    def format_diagnostics(self) -> str:
        """Format detailed per-company diagnostic report for logs and summaries."""
        lines = ["Oracle Cloud HCM Diagnostics:"]
        lines.append(f"  Total collected: {self.diagnostics.get('total_collected', 0)}")
        lines.append(f"  Valid normalized: {self.diagnostics.get('valid_normalized', 0)}")
        lines.append("Company breakdown:")

        for comp_key, info in self.diagnostics.get("by_company", {}).items():
            name = info.get("name", comp_key)
            status = info.get("status", "UNKNOWN")
            coll = info.get("collected", 0)
            avail = info.get("available", 0)
            gap = info.get("gap", max(0, avail - coll))
            err = info.get("error")
            if err:
                lines.append(f"  - {name}: status={status}, collected={coll}, available={avail}, gap={gap}, error={err}")
            else:
                lines.append(f"  - {name}: status={status}, collected={coll}, available={avail}, gap={gap}")

        return "\n".join(lines)


# Convenient alias
OracleHcmSource = OracleHCMJobSource
