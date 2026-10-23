"""Reusable, config-driven Company JSON Feed Career Portal Source Connector.

Collects public job postings from verified enterprise JSON feeds:
- Amazon Jobs (https://www.amazon.jobs/en/search.json)
- Infosys Careers (https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/getCareerSearchJobs)

Safety & Compliance Rules:
- Uses ONLY publicly exposed candidate experience JSON endpoints.
- Does NOT require private credentials or API keys.
- Gracefully handles HTTP 401/403/404/429 and timeouts without crashing the pipeline.
- For large feeds (Amazon, Infosys), uses role-targeted queries instead of downloading everything.
- Reports total pages/available versus fetched, and reports PARTIAL if capped by per-run limits.
- Provides per-company health diagnostics and independent failure isolation.
"""

import asyncio
from datetime import datetime, timezone
import json
import html
import logging
import math
import re
from typing import Any, Dict, List, Optional
import urllib.parse

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


# Verified Company JSON feed registry
DEFAULT_COMPANY_JSON_REGISTRY: Dict[str, Dict[str, Any]] = {
    "amazon": {
        "name": "Amazon",
        "type": "amazon",
        "endpoint": "https://www.amazon.jobs/en/search.json",
        "base_url": "https://www.amazon.jobs",
        "country": "IND",
        "page_size": 50,
    },
    "infosys": {
        "name": "Infosys",
        "type": "infosys",
        "endpoint": "https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/getCareerSearchJobs",
        "base_apply_url": "https://career.infosys.com/jobdescription",
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


class CompanyJsonJobSource(BaseJobSource):
    """Reusable, config-driven source connector for direct enterprise JSON job feeds."""

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
            else getattr(self._settings, "COMPANY_JSON_ENABLED", True)
        )
        super().__init__(is_enabled=enabled_flag)

        self.max_jobs_per_company = getattr(self._settings, "COMPANY_JSON_MAX_JOBS_PER_COMPANY", 200)
        self.max_pages_per_query = getattr(self._settings, "COMPANY_JSON_MAX_PAGES_PER_QUERY", 5)
        self.request_delay_sec = getattr(self._settings, "COMPANY_JSON_REQUEST_DELAY_SEC", 1.0)

        # Build company registry from defaults + custom configs
        self.company_configs = dict(DEFAULT_COMPANY_JSON_REGISTRY)
        custom_json = getattr(self._settings, "COMPANY_JSON_CUSTOM_CONFIGS", "")
        if custom_json:
            try:
                custom_dict = json.loads(custom_json)
                self.company_configs.update(custom_dict)
            except Exception as e:
                logger.warning("Failed to parse COMPANY_JSON_CUSTOM_CONFIGS: %s", e)

        if companies:
            self.configured_companies = [c.strip().lower() for c in companies if c.strip()]
        else:
            raw_companies = getattr(self._settings, "COMPANY_JSON_COMPANIES", "")
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
        return "company_json"

    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Collect postings across configured JSON companies with independent failure isolation."""
        if not self.is_enabled:
            logger.info("Company JSON collection is disabled in configuration.")
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
                    logger.warning("[COMPANY_JSON] Unknown company key '%s'; skipping.", comp_key)
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
                logger.info("[COMPANY_JSON] Collecting JSON feed for: %s (%s)...", comp_name, comp_key)

                try:
                    feed_type = comp_config.get("type", "")
                    if feed_type == "amazon":
                        amazon_limit = getattr(self._settings, "AMAZON_MAX_JOBS", None) or getattr(self._settings, "COMPANY_JSON_AMAZON_MAX_JOBS", None)
                        actual_limit = int(amazon_limit) if amazon_limit is not None else comp_limit
                        comp_jobs = await self._collect_amazon_jobs(client, comp_config, comp_key, actual_limit)
                    elif feed_type == "infosys":
                        comp_jobs = await self._collect_infosys_jobs(client, comp_config, comp_key, comp_limit)
                    else:
                        raise ValueError(f"Unsupported company JSON feed type '{feed_type}'")

                    all_jobs.extend(comp_jobs)
                except Exception as comp_err:
                    logger.warning("[COMPANY_JSON] Independent failure for %s: %s", comp_name, comp_err)
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
        any_partial = any(
            c.get("status") in ("PARTIAL", "FAILED")
            for c in self.diagnostics["by_company"].values()
        )
        if any_partial:
            self.last_status = "PARTIAL"
            reasons = [
                f"{c['name']}: {c.get('error') or c.get('status')}"
                for c in self.diagnostics["by_company"].values()
                if c.get("status") in ("PARTIAL", "FAILED")
            ]
            self.last_error = "; ".join(reasons)
        else:
            self.last_status = "COMPLETED"
            self.last_error = None

        logger.info(
            "[COMPANY_JSON] Finished collection across %d companies. Total jobs: %d",
            len(self.configured_companies),
            len(all_jobs),
        )
        return all_jobs

    async def _collect_amazon_jobs(
        self,
        client: httpx.AsyncClient,
        comp_config: Dict[str, Any],
        comp_key: str,
        max_limit: int,
    ) -> List[Job]:
        """Collect Amazon jobs using role-targeted queries, backoff, and pagination."""
        comp_name = comp_config["name"]
        endpoint = comp_config["endpoint"]
        base_url = comp_config["base_url"]
        page_size = comp_config.get("page_size", 50)

        targeted_terms = [
            "intern", "internship", "graduate", "new grad", "trainee",
            "fresher", "entry level", "software dev engineer i", "sde i",
            "associate", "junior", "python", "backend", "software engineer",
            "full stack", "web developer", "ai engineer", "ml engineer",
        ]

        collected_jobs: List[Job] = []
        seen_job_ids = set()
        total_available = 0
        total_pages_exist = 0
        total_pages_fetched = 0
        req_error: Optional[str] = None

        # Warm up request to get baseline hits
        try:
            r_base = await client.get(
                f"{endpoint}?country=IND&facets[]=normalized_country_code%3A%3AIND&offset=0&result_limit=1",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if r_base.status_code == 200:
                total_available = r_base.json().get("hits", 0)
                total_pages_exist = math.ceil(total_available / page_size) if total_available else 0
        except Exception as e:
            logger.debug("[COMPANY_JSON] Amazon baseline hits probe notice: %s", e)

        for q_idx, term in enumerate(targeted_terms):
            if len(collected_jobs) >= max_limit:
                break
            if req_error:
                break

            offset = 0
            pages_for_this_query = 0

            while pages_for_this_query < self.max_pages_per_query and len(collected_jobs) < max_limit:
                params = {
                    "country": "IND",
                    "facets[]": "normalized_country_code::IND",
                    "base_query": term,
                    "offset": offset,
                    "result_limit": page_size,
                    "sort": "recent",
                }

                resp = None
                for attempt in range(3):
                    try:
                        resp = await client.get(endpoint, params=params, headers={"User-Agent": "Mozilla/5.0"})
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
                jobs = data.get("jobs", [])
                hits = data.get("hits", 0)
                if not jobs:
                    break

                total_pages_fetched += 1
                pages_for_this_query += 1

                for j in jobs:
                    if len(collected_jobs) >= max_limit:
                        break
                    job = self.parse_amazon_job(j, comp_config)
                    if not job:
                        continue
                    if job.job_id in seen_job_ids:
                        continue
                    seen_job_ids.add(job.job_id)
                    collected_jobs.append(job)

                offset += len(jobs)
                if offset >= hits:
                    break

                if self.request_delay_sec > 0:
                    await asyncio.sleep(self.request_delay_sec)

            if self.request_delay_sec > 0 and q_idx < len(targeted_terms) - 1:
                await asyncio.sleep(self.request_delay_sec)

        is_capped = (total_available > len(collected_jobs))
        status = "PARTIAL" if (is_capped or req_error) else "COMPLETED"
        note = (
            f"Role-targeted query capped by per-run limit ({total_pages_fetched} pages fetched out of {total_pages_exist} total available pages)"
            if is_capped
            else "Fetched all matching listings"
        )
        if req_error:
            note = f"{note}; error: {req_error}"

        gap = max(0, total_available - len(collected_jobs))

        self.diagnostics["by_company"][comp_key] = {
            "name": comp_name,
            "status": status,
            "available": total_available,
            "collected": len(collected_jobs),
            "gap": gap,
            "error": note,
            "pages_exist": total_pages_exist,
            "pages_fetched": total_pages_fetched,
        }
        self.diagnostics["total_collected"] += len(collected_jobs)
        self.diagnostics["valid_normalized"] += len(collected_jobs)

        logger.info(
            "[COMPANY_JSON] %s: total available: %d, fetched: %d, gap: %d (status: %s, note: %s)",
            comp_name, total_available, len(collected_jobs), gap, status, note
        )
        return collected_jobs

    async def _collect_infosys_jobs(
        self,
        client: httpx.AsyncClient,
        comp_config: Dict[str, Any],
        comp_key: str,
        max_limit: int,
    ) -> List[Job]:
        """Collect Infosys postings using the IntapGateway feed."""
        comp_name = comp_config["name"]
        endpoint = comp_config["endpoint"]
        base_apply_url = comp_config["base_apply_url"]

        collected_jobs: List[Job] = []
        seen_job_ids = set()
        total_available = 0
        req_error: Optional[str] = None

        url = f"{endpoint}?sourceId=1&searchText=India"

        resp = None
        for attempt in range(3):
            try:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
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

        if resp and resp.status_code == 200:
            raw_data = resp.json()
            if isinstance(raw_data, list):
                total_available = len(raw_data)

                # Prioritize targeted technical roles from the large feed
                target_keywords = re.compile(
                    r"\b(python|backend|developer|software|engineer|full\s*stack|web|ai|ml|data|intern|graduate|trainee|associate|fresher)\b",
                    re.IGNORECASE,
                )

                # First pass: technical role matches; second pass: remaining vacancies
                tech_postings = [p for p in raw_data if target_keywords.search(p.get("postingTitle") or "")]
                other_postings = [p for p in raw_data if not target_keywords.search(p.get("postingTitle") or "")]
                ordered_postings = tech_postings + other_postings

                for p in ordered_postings:
                    job = self.parse_infosys_job(p, comp_config)
                    if not job:
                        continue
                    if job.job_id in seen_job_ids:
                        continue
                    seen_job_ids.add(job.job_id)
                    collected_jobs.append(job)

        is_capped = (total_available > len(collected_jobs))
        status = "PARTIAL" if (is_capped or req_error) else "COMPLETED"
        note = (
            f"Feed capped by per-run limit: collected {len(collected_jobs)} of {total_available} total available jobs"
            if is_capped
            else "Fetched all available jobs"
        )
        if req_error:
            note = f"{note}; error: {req_error}"

        gap = max(0, total_available - len(collected_jobs))

        self.diagnostics["by_company"][comp_key] = {
            "name": comp_name,
            "status": status,
            "available": total_available,
            "collected": len(collected_jobs),
            "gap": gap,
            "error": note,
        }
        self.diagnostics["total_collected"] += len(collected_jobs)
        self.diagnostics["valid_normalized"] += len(collected_jobs)

        logger.info(
            "[COMPANY_JSON] %s: total available: %d, fetched: %d, gap: %d (status: %s, note: %s)",
            comp_name, total_available, len(collected_jobs), gap, status, note
        )
        return collected_jobs

    def parse_amazon_job(self, j: Dict[str, Any], comp_config: Dict[str, Any]) -> Optional[Job]:
        """Parse raw Amazon job JSON object into Job model instance with full qualifications."""
        comp_name = comp_config.get("name", "Amazon")
        base_url = comp_config.get("base_url", "https://www.amazon.jobs")
        job_id = str(j.get("id_icims") or j.get("id") or "").strip()
        title = (j.get("title") or "").strip()
        if not job_id or not title:
            return None

        job_path = j.get("job_path") or f"/en/jobs/{job_id}"
        apply_url = f"{base_url}{job_path}"
        loc_str = (j.get("location") or "India").strip()
        city = j.get("city")
        location = f"{city}, India" if city else loc_str
        posted_date = (j.get("posted_date") or "Unknown").strip()

        desc_raw = (j.get("description") or j.get("description_short") or "").strip()
        basic_qual_raw = (j.get("basic_qualifications") or "").strip()
        pref_qual_raw = (j.get("preferred_qualifications") or "").strip()

        desc_clean = clean_html(desc_raw)
        basic_clean = clean_html(basic_qual_raw)
        pref_clean = clean_html(pref_qual_raw)

        desc_parts = []
        if desc_clean:
            desc_parts.append(desc_clean)
        if basic_clean:
            desc_parts.append(f"Basic Qualifications:\n{basic_clean}")
        if pref_clean:
            desc_parts.append(f"Preferred Qualifications:\n{pref_clean}")
        full_description = "\n\n".join(desc_parts).strip() or f"{title} at {comp_name}. Location: {location}. Posted: {posted_date}."

        return Job(
            source=self.source_name,
            title=title,
            company=comp_name,
            location=location,
            url=apply_url,
            job_id=job_id,
            source_job_id=job_id,
            date_posted=posted_date,
            description=full_description,
            date_found=datetime.now(timezone.utc),
        )

    def parse_infosys_job(self, p: Dict[str, Any], comp_config: Dict[str, Any]) -> Optional[Job]:
        """Parse raw Infosys posting JSON object into Job model instance with full requirements."""
        comp_name = comp_config.get("name", "Infosys")
        base_apply_url = comp_config.get("base_apply_url", "https://career.infosys.com/jobdescription")
        ref_code = str(p.get("referenceCode") or p.get("requisitionId") or p.get("postingId") or "").strip()
        title = (p.get("postingTitle") or "").strip()
        if not ref_code or not title:
            return None

        raw_loc = (p.get("location") or "India").strip()
        location = f"{raw_loc.title()}, India" if not raw_loc.lower().endswith("india") else raw_loc.title()
        posted_date = (p.get("createdOn") or "Unknown").strip()
        min_exp = p.get("minExperienceLevel")
        max_exp = p.get("maxExperienceLevel")
        exp_req = f"{min_exp}-{max_exp} years" if min_exp is not None else None

        desc_parts = []
        desc_body = clean_html(p.get("postingDescription") or "")
        if desc_body:
            desc_parts.append(desc_body)
        tech_req = clean_html(p.get("technicalRequirement") or "")
        if tech_req:
            desc_parts.append(f"Technical Requirements:\n{tech_req}")
        roles = clean_html(p.get("rolesResponsibilities") or "")
        if roles:
            desc_parts.append(f"Roles and Responsibilities:\n{roles}")
        edu = clean_html(p.get("educationalRequirement") or "")
        if edu:
            desc_parts.append(f"Educational Requirements:\n{edu}")
        skills = clean_html(p.get("skills") or "")
        if skills:
            desc_parts.append(f"Skills: {skills}")

        full_desc = "\n\n".join(desc_parts).strip() or f"{title} at Infosys. Location: {location}."

        apply_url = f"{base_apply_url}?referenceCode={urllib.parse.quote(ref_code)}"

        return Job(
            source=self.source_name,
            title=title,
            company=comp_name,
            location=location,
            url=apply_url,
            job_id=ref_code,
            source_job_id=ref_code,
            experience_required=exp_req,
            date_posted=posted_date,
            description=full_desc,
            date_found=datetime.now(timezone.utc),
        )

    # Aliases for backward compatibility in unit tests
    _parse_amazon_job = parse_amazon_job
    _parse_infosys_job = parse_infosys_job

    def format_diagnostics(self) -> str:
        """Format detailed per-company diagnostic report for logs and summaries."""
        lines = ["Company JSON Feeds Diagnostics:"]
        lines.append(f"  Total collected: {self.diagnostics.get('total_collected', 0)}")
        lines.append(f"  Valid normalized: {self.diagnostics.get('valid_normalized', 0)}")
        lines.append("Company breakdown:")

        for comp_key, info in self.diagnostics.get("by_company", {}).items():
            name = info.get("name", comp_key)
            status = info.get("status", "UNKNOWN")
            coll = info.get("collected", 0)
            avail = info.get("available", 0)
            gap = info.get("gap", 0)
            err = info.get("error")
            lines.append(f"  - {name}: status={status}, collected={coll}, available={avail}, gap={gap}, note={err}")

        return "\n".join(lines)
