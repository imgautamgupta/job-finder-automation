"""Reusable, config-driven Workday CXS Career Portal Source Connector.

Collects public job postings from Workday CXS APIs used by enterprise career portals:
https://{host}/wday/cxs/{tenant}/{site}/jobs

Safety & Compliance Rules:
- Uses ONLY publicly exposed candidate experience JSON endpoints.
- Does NOT require private credentials or API keys.
- Does NOT bypass authentication, CAPTCHAs, or rate limits.
- Gracefully handles HTTP 401/403/404/429 and timeouts without crashing the pipeline.
- Performs India pre-filtering to avoid overseas listings while honoring all local openings.
- Provides per-company health diagnostics and independent failure isolation.
"""

import asyncio
from datetime import datetime, timezone
import html
import json
import logging
import re
from typing import Any, Dict, List, Optional, Union
import urllib.parse

import httpx

from app.config.settings import Settings, get_settings
from app.models.job import Job, normalize_url
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)

# Verified Workday CXS company registry with portal location facets for India (Task 9)
DEFAULT_WORKDAY_COMPANIES: Dict[str, Dict[str, Any]] = {
    "adobe": {
        "name": "Adobe",
        "host": "adobe.wd5.myworkdayjobs.com",
        "tenant": "adobe",
        "site": "external_experienced",
        "applied_facets": {
            "locationCountry": ["c4f78be1a8f14da0ab49ce1162348a5e"],  # India (Bengaluru, Noida, Gurgaon, Mumbai, Remote)
        },
    },
    "intel": {
        "name": "Intel",
        "host": "intel.wd1.myworkdayjobs.com",
        "tenant": "intel",
        "site": "External",
        "applied_facets": {
            "locations": [
                "1e4a4eb3adf101f44070f976bf8184cf",  # India, Bangalore
                "fabab36f05f51000ba74e9448dc20000",  # Virtual India
            ],
        },
    },
    "nvidia": {
        "name": "NVIDIA",
        "host": "nvidia.wd5.myworkdayjobs.com",
        "tenant": "nvidia",
        "site": "NVIDIAExternalCareerSite",
        "applied_facets": {
            "locationHierarchy1": ["2fcb99c455831013ea52b82135ba3266"],  # India (Bengaluru, Gurugram, Hyderabad, Mumbai, Pune, Remote)
        },
    },
    "salesforce": {
        "name": "Salesforce",
        "host": "salesforce.wd12.myworkdayjobs.com",
        "tenant": "salesforce",
        "site": "External_Career_Site",
        "applied_facets": {
            "CF_-_REC_-_LRV_-_Job_Posting_Anchor_-_Country_from_Job_Posting_Location_Extended": [
                "c4f78be1a8f14da0ab49ce1162348a5e"
            ],  # India (Bangalore, Gurgaon, Hyderabad, Mumbai, Pune, Chennai, Jaipur)
        },
    },
    "walmart": {
        "name": "Walmart",
        "host": "walmart.wd504.myworkdayjobs.com",
        "tenant": "walmart",
        "site": "WalmartExternal",
        "applied_facets": {
            "locationCountry": ["c4f78be1a8f14da0ab49ce1162348a5e"],  # India (Bangalore Home Offices, Chennai Home Offices)
        },
    },
    "mastercard": {
        "name": "Mastercard",
        "host": "mastercard.wd1.myworkdayjobs.com",
        "tenant": "mastercard",
        "site": "CorporateCareers",
        "applied_facets": {
            "locations": [
                "8eab563831bf10acbc722e4859721571",  # Pune, India
                "8eab563831bf10acb97b7fba5feff76e",  # Gurgaon, India
                "28905a74db1b10019f5bb16c36030000",  # Navi Mumbai, India
                "8eab563831bf10acb9d6f1103d78fa67",  # Hyderabad, India
                "85a5bdf4e1831035984400a2fb698c94",  # Vadodara, India
                "8eab563831bf10acb5d384310bb7d5ec",  # Bangalore, India
                "8eab563831bf10acbb7b5bf86d570af1",  # Mumbai, India
            ],
        },
    },
    "visa": {
        "name": "Visa",
        "host": "visa.wd5.myworkdayjobs.com",
        "tenant": "visa",
        "site": "visa",
        "applied_facets": {
            "locationCountry": ["c4f78be1a8f14da0ab49ce1162348a5e"],  # India (Bengaluru, Mumbai)
        },
    },
    "paypal": {
        "name": "PayPal",
        "host": "paypal.wd1.myworkdayjobs.com",
        "tenant": "paypal",
        "site": "jobs",
        "applied_facets": {
            "locations": [
                "bcdc9518960a0115db738aaa2d241899",  # Bangalore, Karnataka, India
                "bcdc9518960a01a46ac477aa2d240c99",  # Chennai, Tamil Nadu, India
            ],
        },
    },
    "hp": {
        "name": "HP",
        "host": "hp.wd5.myworkdayjobs.com",
        "tenant": "hp",
        "site": "ExternalCareerSite",
        "applied_facets": {},
        "location_scope": "all",
    },
}

INDIAN_LOCATIONS_REGEX = re.compile(
    r"\b(india|bangalore|bengaluru|hyderabad|pune|mumbai|chennai|gurgaon|gurugram|noida|"
    r"delhi|kolkata|ahmedabad|kochi|indore|bhopal|coimbatore|chandigarh|jaipur|karnataka|"
    r"telangana|maharashtra|tamil nadu|haryana|uttar pradesh)\b",
    re.IGNORECASE,
)

FALSE_POSITIVE_REGEX = re.compile(
    r"\b(indianapolis|indiana)\b",
    re.IGNORECASE,
)


def is_india_location(locations_text: Optional[str]) -> bool:
    """Pre-filter verifying whether a Workday locations string represents an India vacancy."""
    if not locations_text:
        return False
    text = locations_text.strip().lower()

    # Detect false positives like 'Indianapolis, IN'
    if FALSE_POSITIVE_REGEX.search(text) and not re.search(r"\b(india|bengaluru|bangalore|hyderabad|pune)\b", text):
        return False

    return bool(INDIAN_LOCATIONS_REGEX.search(text))


def extract_workday_job_id(posting: Dict[str, Any]) -> str:
    """Extract official job ID from bulletFields or externalPath."""
    bullet_fields = posting.get("bulletFields") or []
    if bullet_fields and str(bullet_fields[0]).strip():
        return str(bullet_fields[0]).strip()

    ext_path = posting.get("externalPath") or ""
    # Look for trailing pattern like _R169338 or _JR2024311
    m = re.search(r"[-_]([A-Za-z0-9]+)$", ext_path)
    if m:
        return m.group(1)

    return ""


def build_workday_direct_url(host: str, site: str, external_path: str) -> str:
    """Construct direct candidate-facing apply URL."""
    clean_host = host.strip()
    clean_site = site.strip()
    clean_path = external_path.strip()
    return f"https://{clean_host}/en-US/{clean_site}{clean_path}"


def clean_html_description(raw_content: Optional[str]) -> Optional[str]:
    """Safely convert HTML job description into clean plain text."""
    if not raw_content or not isinstance(raw_content, str):
        return None
    text = html.unescape(raw_content)
    text = re.sub(r"<(?:br|p|div|li|h[1-6]|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:strong|b|em|i|u|span|a|code)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def passes_title_location_prefilters(
    job: Union[Job, str],
    target_roles: Optional[List[str]] = None,
    target_locations: Optional[Union[List[str], str]] = None,
    location_scope: Optional[str] = None,
) -> bool:
    """Pre-filter verifying whether a Workday vacancy satisfies basic title and location criteria before detail fetch."""
    if isinstance(job, Job):
        title = job.title or ""
        loc = job.location or ""
    else:
        title = str(job or "")
        if isinstance(target_roles, str) and target_locations is None:
            loc = target_roles
            target_roles = None
        else:
            loc = str(target_locations or "") if isinstance(target_locations, str) else ""

    if location_scope != "all" and not is_india_location(loc):
        return False
    from app.services.filter import match_seniority_title

    # 1. Seniority exclusion
    if match_seniority_title(title):
        return False

    # 2b. Below-profile exclusion (intern/trainee/apprentice -> not relevant)
    # Note: This runs BEFORE detail fetch to save bandwidth
    from app.services.filter import match_below_profile_title
    if match_below_profile_title(title):
        return False

    # 2. Exclude levels >= 2 (e.g. "Software Engineer II", "Scientist IV")
    if re.search(r"\b(?:II|III|IV|V|VI)\b", title, re.IGNORECASE):
        return False

    # 3. Target role matching
    title_lower = title.lower()
    if target_roles:
        role_matched = False
        for role in target_roles:
            r_clean = role.strip().lower()
            if not r_clean:
                continue
            if re.search(r"\b" + re.escape(r_clean) + r"\b", title_lower):
                role_matched = True
                break
            tokens = [t for t in re.split(r"[\s\-_/]+", r_clean) if t]
            if len(tokens) > 1 and all(
                re.search(r"\b" + re.escape(t) + r"\b", title_lower) for t in tokens
            ):
                role_matched = True
                break
        if role_matched:
            return True

        # Check early career terms
        early_career = ["intern", "internship", "graduate", "fresher", "trainee", "associate", "entry level", "software", "developer", "engineer"]
        if any(re.search(r"\b" + re.escape(ec) + r"\b", title_lower) for ec in early_career):
            return True
        return False
    else:
        # Default software / tech keywords
        tech_kw = ["software", "developer", "engineer", "programmer", "python", "backend", "frontend", "full stack", "data", "ai", "ml", "intern", "trainee", "graduate", "analyst"]
        return any(re.search(r"\b" + re.escape(tk) + r"\b", title_lower) for tk in tech_kw)


class WorkdayJobSource(BaseJobSource):
    """Reusable, config-driven source connector for enterprise Workday CXS career portals."""

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
            else getattr(self._settings, "WORKDAY_ENABLED", True)
        )
        super().__init__(is_enabled=enabled_flag)

        self.max_jobs_per_company = getattr(self._settings, "WORKDAY_MAX_JOBS_PER_COMPANY", 25)
        self.request_delay_sec = getattr(self._settings, "WORKDAY_REQUEST_DELAY_SEC", 0.8)

        # Build company registry from defaults + custom configs
        self.company_configs = dict(DEFAULT_WORKDAY_COMPANIES)
        custom_json = getattr(self._settings, "WORKDAY_CUSTOM_CONFIGS", "")
        if custom_json:
            try:
                custom_dict = json.loads(custom_json)
                self.company_configs.update(custom_dict)
            except Exception as e:
                logger.warning("Failed to parse WORKDAY_CUSTOM_CONFIGS: %s", e)

        # Resolve configured company keys to query
        if companies:
            self.configured_companies = [c.strip().lower() for c in companies if c.strip()]
        else:
            raw_companies = getattr(self._settings, "WORKDAY_COMPANIES", "")
            if raw_companies:
                self.configured_companies = [c.strip().lower() for c in raw_companies.split(",") if c.strip()]
            else:
                self.configured_companies = list(self.company_configs.keys())

        self.fetch_details = getattr(self._settings, "WORKDAY_FETCH_DETAILS", True)
        self.detail_delay_sec = getattr(self._settings, "WORKDAY_DETAIL_DELAY_SEC", 0.5)
        self.max_details_per_run = getattr(self._settings, "WORKDAY_MAX_DETAILS_PER_RUN", 50)
        self.details_fetched_count = 0

        self.diagnostics: Dict[str, Any] = {
            "by_company": {},
            "total_collected": 0,
            "valid_normalized": 0,
            "missing_job_id": 0,
            "overseas_skipped": 0,
            "details_fetched": 0,
        }

    @property
    def source_name(self) -> str:
        return "workday"

    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Collect postings across all configured Workday companies with independent failure isolation.

        Args:
            roles: Target role titles.
            locations: Target locations.
            max_results: Maximum results limit per company.

        Returns:
            Aggregated list of collected, normalized Job instances.
        """
        if not self.is_enabled:
            logger.info("Workday collection is disabled in configuration.")
            self.last_status = "DISABLED"
            self.last_error = None
            return []

        self.last_status = "COMPLETED"
        self.last_error = None
        all_jobs: List[Job] = []
        self._current_collected = all_jobs

        # Reset diagnostics
        self.details_fetched_count = 0
        self.diagnostics = {
            "by_company": {},
            "total_collected": 0,
            "valid_normalized": 0,
            "missing_job_id": 0,
            "overseas_skipped": 0,
            "details_fetched": 0,
        }

        # Remove hidden 25 cap: respect WORKDAY_MAX_JOBS_PER_COMPANY or allow full pagination
        if max_results and max_results < 25:
            comp_max = max_results
        else:
            comp_max = self.max_jobs_per_company if (self.max_jobs_per_company and self.max_jobs_per_company > 25) else (max_results if max_results and max_results > 25 else 5000)

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for comp_key in self.configured_companies:
                comp_config = self.company_configs.get(comp_key)
                if not comp_config:
                    logger.warning("[WORKDAY] Unknown company key '%s'; skipping.", comp_key)
                    self.diagnostics["by_company"][comp_key] = {
                        "status": "UNKNOWN_CONFIG",
                        "error": "No configuration found",
                        "collected": 0,
                        "available": 0,
                        "gap": 0,
                    }
                    continue

                comp_name = comp_config.get("name", comp_key.capitalize())
                logger.info("[WORKDAY] Collecting jobs for company: %s (%s)...", comp_name, comp_key)

                try:
                    limit_to_use = min(comp_max, 100) if comp_config.get("location_scope") == "all" else comp_max
                    comp_jobs = await self._collect_company_jobs(
                        client=client,
                        comp_config=comp_config,
                        comp_key=comp_key,
                        max_limit=limit_to_use,
                        target_roles=roles,
                        target_locations=locations,
                    )
                    all_jobs.extend(comp_jobs)
                except Exception as comp_err:
                    logger.warning("[WORKDAY] Independent failure for %s: %s", comp_name, comp_err)
                    self.diagnostics["by_company"][comp_key] = {
                        "name": comp_name,
                        "status": "FAILED",
                        "error": str(comp_err),
                        "collected": 0,
                        "available": 0,
                        "gap": 0,
                    }

                # Polite inter-company rate limit delay
                if self.request_delay_sec > 0:
                    await asyncio.sleep(self.request_delay_sec)

        self.last_collected_count = len(all_jobs)
        companies_with_errors = [
            c for c in self.diagnostics["by_company"].values()
            if c.get("error") is not None or c.get("status") in ("FAILED", "PARTIAL")
        ]
        error_count = len(companies_with_errors)
        if error_count > 0:
            err_summaries = [f"{c['name']} ({c.get('error') or c.get('status')})" for c in companies_with_errors]
            if len(all_jobs) > 0:
                self.last_status = "PARTIAL"
                self.last_error = f"{error_count} error(s): {'; '.join(err_summaries)}"
            else:
                self.last_status = "FAILED"
                self.last_error = f"{error_count} company failure(s): {'; '.join(err_summaries)}"
        else:
            self.last_status = "COMPLETED"
            self.last_error = None

        logger.info("[WORKDAY] Finished collection across %d companies. Total jobs: %d", len(self.configured_companies), len(all_jobs))
        return all_jobs

    async def fetch_job_detail(
        self,
        client: httpx.AsyncClient,
        comp_config: Dict[str, Any],
        ext_path: str,
    ) -> Optional[str]:
        """Fetch full job posting detail from Workday CXS API."""
        if not ext_path:
            return None
        host = comp_config["host"]
        tenant = comp_config["tenant"]
        site = comp_config["site"]
        if not ext_path.startswith("/"):
            ext_path = "/" + ext_path
        detail_url = f"https://{host}/wday/cxs/{tenant}/{site}{ext_path}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        try:
            resp = await client.get(detail_url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                job_info = data.get("jobPostingInfo", {})
                raw_desc = job_info.get("jobDescription")
                return clean_html_description(raw_desc)
            else:
                logger.debug("[WORKDAY] Detail request HTTP %d for %s", resp.status_code, detail_url)
        except Exception as e:
            logger.debug("[WORKDAY] Failed to fetch job detail for %s: %s", detail_url, e)
        return None

    async def _collect_company_jobs(
        self,
        client: httpx.AsyncClient,
        comp_config: Dict[str, Any],
        comp_key: str,
        max_limit: int,
        target_roles: Optional[List[str]] = None,
        target_locations: Optional[List[str]] = None,
    ) -> List[Job]:
        """Collect and normalize jobs for a single Workday company using portal facets, backoff, and targeted queries."""
        comp_name = comp_config["name"]
        comp_config["company_key"] = comp_key
        host = comp_config["host"]
        tenant = comp_config["tenant"]
        site = comp_config["site"]
        applied_facets = comp_config.get("applied_facets", {})
        location_scope = comp_config.get("location_scope")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/en-US/{site}/jobs",
        }

        # Step 1: Initial GET to establish session cookies (prevents 429 rate limit / bot challenge)
        try:
            await client.get(
                f"https://{host}/en-US/{site}/jobs",
                headers={"User-Agent": headers["User-Agent"]},
            )
        except Exception as init_err:
            logger.debug("[WORKDAY] Initial session GET for %s notice: %s", comp_name, init_err)

        collected_jobs: List[Job] = []
        seen_job_ids = set()
        total_available = 0
        req_error: Optional[str] = None
        search_endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"

        # Targeted role and early-career query list
        targeted_terms = [
            "",  # Primary query with location facet (captures all India jobs for the company)
            "python", "backend", "software engineer", "full stack",
            "web developer", "ai engineer", "ml engineer",
            "intern", "internship", "graduate", "new grad",
            "trainee", "associate", "fresher", "entry level",
        ]

        for query_idx, term in enumerate(targeted_terms):
            if len(collected_jobs) >= max_limit:
                break
            if req_error:
                break

            # If the primary query with applied location facets has run, it already paginated through all India vacancies
            if query_idx > 0 and applied_facets and total_available > 0:
                logger.debug(
                    "[WORKDAY] %s: location facet query already retrieved entire India inventory (%d total); skipping targeted query '%s'",
                    comp_name, total_available, term,
                )
                break

            offset = 0
            page_size = 20
            query_total = 0

            while len(collected_jobs) < max_limit:
                payload = {
                    "appliedFacets": applied_facets,
                    "limit": page_size,
                    "offset": offset,
                    "searchText": term if (applied_facets or term or location_scope == "all") else "India",
                }

                # Retry loop with exponential backoff on HTTP 429
                resp = None
                max_retries = 3
                base_backoff = 2.0
                for attempt in range(max_retries + 1):
                    try:
                        resp = await client.post(search_endpoint, headers=headers, json=payload)
                        if resp.status_code == 429:
                            if attempt < max_retries:
                                retry_after = resp.headers.get("Retry-After")
                                backoff = float(retry_after) if retry_after and retry_after.isdigit() else (base_backoff * (2 ** attempt))
                                logger.warning(
                                    "[WORKDAY] HTTP 429 Rate Limit for %s query='%s' (offset %d). Retrying in %.1fs (attempt %d/%d)...",
                                    comp_name, term, offset, backoff, attempt + 1, max_retries
                                )
                                await asyncio.sleep(backoff)
                                continue
                            else:
                                req_error = f"HTTP 429 rate limit exceeded after {max_retries} retries"
                                break
                        elif resp.status_code != 200:
                            req_error = f"HTTP {resp.status_code}"
                            break
                        else:
                            break
                    except Exception as req_err:
                        if attempt < max_retries:
                            await asyncio.sleep(1.0)
                            continue
                        req_error = str(req_err)
                        break

                if not resp or resp.status_code != 200:
                    break

                try:
                    data = resp.json()
                except Exception as json_err:
                    req_error = f"Non-JSON response (temporary portal maintenance): {json_err}"
                    break
                if offset == 0:
                    page_total = data.get("total", 0)
                    if query_idx == 0 or total_available == 0:
                        total_available = page_total
                    query_total = page_total

                postings = data.get("jobPostings", [])
                if not postings:
                    break

                for p in postings:
                    if len(collected_jobs) >= max_limit:
                        break

                    job_item = self.parse_workday_posting(p, comp_config)
                    if not job_item:
                        continue

                    # Deduplicate across queries by job_id
                    if job_item.job_id in seen_job_ids:
                        continue

                    # Verify India location pre-filter (skip if location_scope == "all")
                    if location_scope != "all":
                        if not is_india_location(job_item.location):
                            ext_p = (p.get("externalPath") or "")
                            if is_india_location(ext_p):
                                pass
                            elif applied_facets and re.search(r"^\d+\s+locations?", (p.get("locationsText") or ""), re.I):
                                pass
                            elif not applied_facets:
                                self.diagnostics["overseas_skipped"] += 1
                                logger.debug("[WORKDAY] Skipping non-India listing for %s: '%s' (%s)", comp_name, job_item.title, job_item.location)
                                continue

                    seen_job_ids.add(job_item.job_id)

                    # Detail fetching for postings passing title/location pre-filters
                    if (
                        self.fetch_details
                        and self.details_fetched_count < self.max_details_per_run
                        and passes_title_location_prefilters(
                            job_item,
                            target_roles=target_roles,
                            target_locations=target_locations,
                            location_scope=location_scope,
                        )
                    ):
                        ext_p = (p.get("externalPath") or "").strip()
                        if ext_p:
                            detail_desc = await self.fetch_job_detail(client, comp_config, ext_p)
                            if detail_desc:
                                job_item.description = detail_desc
                                self.details_fetched_count += 1
                                self.diagnostics["details_fetched"] = self.details_fetched_count
                                logger.info(
                                    "[WORKDAY] Fetched full detail for '%s' (%s) [%d/%d]",
                                    job_item.title,
                                    comp_name,
                                    self.details_fetched_count,
                                    self.max_details_per_run,
                                )
                                if self.detail_delay_sec > 0:
                                    await asyncio.sleep(self.detail_delay_sec)

                    collected_jobs.append(job_item)
                    self.diagnostics["valid_normalized"] += 1

                offset += len(postings)
                if query_total > 0 and offset >= query_total:
                    break

                # Polite inter-page delay
                if self.request_delay_sec > 0:
                    await asyncio.sleep(self.request_delay_sec)

            # Delay between targeted queries if multiple were run
            if query_idx < len(targeted_terms) - 1 and self.request_delay_sec > 0:
                await asyncio.sleep(self.request_delay_sec)

        gap = max(0, total_available - len(collected_jobs))
        if req_error:
            status = "PARTIAL" if len(collected_jobs) > 0 else "FAILED"
        elif total_available > len(collected_jobs):
            status = "PARTIAL"
        else:
            status = "COMPLETED"

        self.diagnostics["by_company"][comp_key] = {
            "name": comp_name,
            "status": status,
            "available": total_available,
            "collected": len(collected_jobs),
            "gap": gap,
            "error": req_error,
        }
        self.diagnostics["total_collected"] += len(collected_jobs)
        logger.info(
            "[WORKDAY] %s: total available: %d, fetched: %d, gap: %d (status: %s%s)",
            comp_name, total_available, len(collected_jobs), gap, status,
            f", error: {req_error}" if req_error else ""
        )
        return collected_jobs

    def parse_workday_posting(self, posting: Dict[str, Any], comp_config: Dict[str, Any]) -> Optional[Job]:
        """Convert a single Workday CXS job item into a standardized Job model instance."""
        title = (posting.get("title") or "").strip()
        if not title:
            return None

        comp_name = comp_config["name"]
        host = comp_config["host"]
        site = comp_config["site"]
        ext_path = (posting.get("externalPath") or "").strip()

        job_id = extract_workday_job_id(posting)
        if not job_id:
            self.diagnostics["missing_job_id"] += 1
            job_id = f"WD-{abs(hash(title + ext_path)) % 1000000}"

        direct_url = build_workday_direct_url(host, site, ext_path) if ext_path else f"https://{host}/en-US/{site}/jobs"
        location = (posting.get("locationsText") or "").strip()
        if not location or re.search(r"^\d+\s+locations?", location, re.I):
            # Try to resolve location from externalPath
            for city in ["Bangalore", "Bengaluru", "Chennai", "Hyderabad", "Pune", "Mumbai", "Noida", "Gurgaon", "Gurugram"]:
                if city.lower() in ext_path.lower():
                    location = f"{city}, India"
                    break
            if not location:
                location = "Worldwide" if comp_config.get("location_scope") == "all" else "India"

        posted_on = (posting.get("postedOn") or "Unknown").strip()

        job = Job(
            source=self.source_name,
            title=title,
            company=comp_name,
            location=location,
            url=direct_url,
            job_id=job_id,
            source_job_id=job_id,
            date_posted=posted_on,
            description=f"{title} at {comp_name}. Location: {location}. Posted: {posted_on}.",
            date_found=datetime.now(timezone.utc),
            extra_metadata={
                "company_key": comp_config.get("company_key", comp_name.lower().replace(" ", "_")),
                "application_url": direct_url,
            },
        )
        return job

    def format_diagnostics(self) -> str:
        """Format detailed per-company diagnostic report for logs and summaries."""
        lines = ["Workday CXS Diagnostics:"]
        lines.append(f"  Total collected: {self.diagnostics.get('total_collected', 0)}")
        lines.append(f"  Valid normalized: {self.diagnostics.get('valid_normalized', 0)}")
        lines.append(f"  Overseas filtered out: {self.diagnostics.get('overseas_skipped', 0)}")
        lines.append(f"  Missing job IDs: {self.diagnostics.get('missing_job_id', 0)}")
        lines.append(f"  Details fetched: {self.diagnostics.get('details_fetched', 0)}")
        lines.append("Company breakdown:")

        for comp_key, info in self.diagnostics.get("by_company", {}).items():
            name = info.get("name", comp_key)
            status = info.get("status", "UNKNOWN")
            coll = info.get("collected", 0)
            avail = info.get("available", 0)
            gap = info.get("gap", max(0, avail - coll))
            err = info.get("error")
            if err:
                if coll > 0:
                    lines.append(f"  - {name}: status={status}, collected={coll}, error={err}, total_available={avail}, gap={gap}")
                else:
                    lines.append(f"  - {name}: status={status}, error={err}, total_available={avail}, gap={gap}")
            else:
                lines.append(f"  - {name}: status={status}, collected={coll}, total_available={avail}, gap={gap}")

        return "\n".join(lines)

