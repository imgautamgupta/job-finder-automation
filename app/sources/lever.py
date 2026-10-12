"""Lever public job postings source module.

This module implements controlled, safe job collection from Lever's public
Postings API (https://api.lever.co/v0/postings/<company>?mode=json).

Safety & Compliance Rules:
- Uses ONLY publicly exposed Lever job-posting data.
- Does NOT require private credentials or API keys.
- Does NOT bypass authentication, CAPTCHAs, or rate limits.
- Does NOT use browser stealth, proxies, or fingerprint spoofing.
- Gracefully handles HTTP 401/403/404/429 without crashing the pipeline.
- Missing location is strictly set to None (never defaulted to India).
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.config.settings import Settings, get_settings
from app.models.job import Job
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


def build_lever_postings_url(company: str, limit: Optional[int] = None) -> str:
    """Construct the official public Lever postings JSON endpoint URL.

    Args:
        company: Lever company/site identifier (e.g. 'example-company').
        limit: Optional maximum number of postings to return from endpoint.

    Returns:
        Formatted endpoint URL.
    """
    clean_company = company.strip().lower()
    url = f"https://api.lever.co/v0/postings/{clean_company}?mode=json"
    if limit is not None and limit > 0:
        url += f"&limit={int(limit)}"
    return url


def normalize_lever_location(categories: Dict[str, Any], workplace_type: Optional[str] = None) -> Optional[str]:
    """Extract and normalize location text from Lever posting categories and workplace metadata.

    Preserves multi-location listings (e.g. 'Bangalore, India; Remote') without incorrectly
    assigning a preferred city or defaulting missing values to India.

    Args:
        categories: Lever 'categories' dictionary.
        workplace_type: Value of 'workplaceType' attribute (e.g. 'remote', 'hybrid', 'onsite').

    Returns:
        Normalized location string, or None if no valid location was specified.
    """
    primary_loc = (categories.get("location") or "").strip()
    all_locs = categories.get("allLocations") or []

    valid_locs: List[str] = []
    if primary_loc and primary_loc.lower() not in ("unknown", "none", "n/a", "not specified"):
        valid_locs.append(primary_loc)

    for item in all_locs:
        if isinstance(item, str):
            clean_item = item.strip()
            if clean_item and clean_item.lower() not in ("unknown", "none", "n/a", "not specified"):
                if clean_item not in valid_locs:
                    valid_locs.append(clean_item)

    is_remote = False
    if workplace_type and workplace_type.strip().lower() == "remote":
        is_remote = True

    if is_remote and not any("remote" in loc.lower() for loc in valid_locs):
        valid_locs.append("Remote")

    if not valid_locs:
        return None

    # Multi-location joined with semicolon
    return "; ".join(valid_locs)


def parse_lever_posting(posting: Dict[str, Any], company_id: str) -> Optional[Job]:
    """Convert a raw Lever public posting JSON object into a standardized Job model.

    Args:
        posting: Dictionary representing a single Lever posting item.
        company_id: Configured Lever company site identifier.

    Returns:
        Standardized Job object, or None if required fields are missing or invalid.
    """
    if not isinstance(posting, dict):
        return None

    title = (posting.get("text") or "").strip()
    source_job_id = str(posting.get("id") or "").strip()

    if not title or not source_job_id:
        logger.debug("Skipping invalid Lever posting missing title or ID: %s", posting)
        return None

    # Company name: prefer posting company attribute if provided; fallback to company identifier
    company_name = (posting.get("company") or "").strip() or company_id.strip()

    categories = posting.get("categories") or {}
    workplace_type = posting.get("workplaceType")

    # Location normalization (None if missing, never 'India')
    location = normalize_lever_location(categories, workplace_type)

    # URL extraction
    hosted_url = (posting.get("hostedUrl") or posting.get("applyUrl") or "").strip()
    if not hosted_url:
        hosted_url = f"https://jobs.lever.co/{company_id}/{source_job_id}"

    # Description extraction (prefer plain-text description)
    description = (posting.get("descriptionPlain") or "").strip()
    if not description and posting.get("description"):
        description = re.sub(r"<[^>]+>", "", str(posting.get("description"))).strip()

    if not description:
        description = None

    # Date posted conversion from epoch milliseconds
    date_posted = None
    created_at_ms = posting.get("createdAt")
    if isinstance(created_at_ms, (int, float)) and created_at_ms > 0:
        try:
            dt = datetime.fromtimestamp(created_at_ms / 1000.0, tz=timezone.utc)
            date_posted = dt.strftime("%Y-%m-%d")
        except Exception:
            date_posted = None

    # Employment type (commitment)
    employment_type = categories.get("commitment")
    if employment_type and isinstance(employment_type, str):
        employment_type = employment_type.strip() or None
    else:
        employment_type = None

    # Explicit experience level if available
    experience_level = categories.get("level")
    if experience_level and isinstance(experience_level, str):
        experience_required = experience_level.strip() or None
    else:
        experience_required = None

    # Salary information if publicly exposed
    salary = None
    sal_range = posting.get("salaryRange")
    if isinstance(sal_range, dict) and sal_range.get("min") is not None:
        min_val = sal_range.get("min")
        max_val = sal_range.get("max")
        curr = sal_range.get("currency") or ""
        interval = sal_range.get("interval") or ""
        if max_val is not None:
            salary = f"{min_val} - {max_val} {curr} ({interval})".strip()
        else:
            salary = f"{min_val} {curr} ({interval})".strip()

    # Raw metadata storage
    raw_meta: Dict[str, Any] = {
        "department": categories.get("department"),
        "team": categories.get("team"),
        "workplaceType": workplace_type,
        "createdAt": created_at_ms,
        "lever_company_id": company_id,
    }

    try:
        return Job(
            source="lever",
            source_job_id=source_job_id,
            job_id=source_job_id,
            title=title,
            company=company_name,
            location=location,
            url=hosted_url,
            description=description,
            easy_apply=False,  # Never guessed
            date_posted=date_posted,
            employment_type=employment_type,
            experience_required=experience_required,
            salary=salary,
            extra_metadata=raw_meta,
        )
    except Exception as exc:
        logger.warning("Failed to construct Job from Lever posting %s: %s", source_job_id, exc)
        return None


def fetch_lever_postings_http(
    company: str,
    timeout_sec: float = 15.0,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch raw public job postings from Lever Postings API using standard urllib.

    Args:
        company: Lever company identifier.
        timeout_sec: Network request timeout in seconds.
        limit: Optional maximum number of postings to return from endpoint.

    Returns:
        List of posting dictionaries, or empty list on error/restriction.
    """
    url = build_lever_postings_url(company, limit=limit)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "JobFinderAutomation/1.0",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = resp.read().decode("utf-8")
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return parsed
            logger.warning("Unexpected non-list response structure from Lever for company='%s'", company)
            return []
    except urllib.error.HTTPError as http_err:
        if http_err.code in (401, 403):
            logger.warning(
                "Lever access restricted for company='%s' (HTTP %d). Stopping that company safely.",
                company,
                http_err.code,
            )
        elif http_err.code == 404:
            logger.warning(
                "Lever company/site not found for company='%s' (HTTP 404). Continuing with remaining companies.",
                company,
            )
        elif http_err.code == 429:
            logger.warning(
                "Lever rate limit reached for company='%s' (HTTP 429). Stopping that company safely.",
                company,
            )
        else:
            logger.warning(
                "Lever HTTP error %d encountered for company='%s'.",
                http_err.code,
                company,
            )
        return []
    except urllib.error.URLError as url_err:
        logger.warning(
            "Lever network connection error for company='%s': %s",
            company,
            url_err,
        )
        return []
    except json.JSONDecodeError as json_err:
        logger.warning(
            "Malformed JSON returned by Lever for company='%s': %s",
            company,
            json_err,
        )
        return []
    except Exception as exc:
        logger.warning(
            "Unexpected error fetching Lever postings for company='%s': %s",
            company,
            exc,
        )
        return []


class LeverJobSource(BaseJobSource):
    """Source connector for collecting public job postings from Lever.

    Collects listings from configured company identifiers via Lever's public
    Postings API (api.lever.co/v0/postings/<company>?mode=json).
    Adheres strictly to safety constraints: no authentication required, no
    CAPTCHA solving, conservative rate limits, and graceful error handling.
    """

    def __init__(
        self,
        is_enabled: Optional[bool] = None,
        settings: Optional[Settings] = None,
    ):
        self._settings = settings or get_settings()
        enabled_flag = is_enabled if is_enabled is not None else self._settings.LEVER_ENABLED
        super().__init__(is_enabled=enabled_flag)

        self.max_jobs_per_company = self._settings.LEVER_MAX_JOBS_PER_COMPANY
        self.request_delay_sec = self._settings.LEVER_REQUEST_DELAY_SEC
        self.diagnostics: Dict[str, Any] = {
            "available_postings": 0,
            "collection_limit": self.max_jobs_per_company,
            "collected": 0,
            "valid_normalized": 0,
            "invalid_skipped": 0,
            "locations": {},
            "roles": {},
        }

    @property
    def source_name(self) -> str:
        return "lever"

    @property
    def companies(self) -> List[str]:
        """Parsed, non-empty list of configured Lever company identifiers."""
        return self._settings.lever_company_list

    async def setup(self) -> None:
        """Initialize Lever connector lifecycle."""
        if not self.is_enabled:
            return
        logger.info(
            "Initializing Lever public connector (configured companies: %d)...",
            len(self.companies),
        )

    async def teardown(self) -> None:
        """Clean up Lever connector resources."""
        logger.info("Closing Lever connector resources.")

    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Collect job postings across all configured Lever companies.

        Args:
            roles: Target role titles (used by pipeline filtering).
            locations: Target locations (used by pipeline filtering).
            max_results: Maximum results to collect.

        Returns:
            List of normalized Job objects across configured companies.
        """
        if not self.is_enabled:
            logger.info("Lever collection is disabled in settings.")
            self.last_status = "DISABLED"
            self.last_error = None
            return []

        companies = self.companies
        if not companies:
            logger.info("No Lever companies configured (LEVER_COMPANIES is empty). Skipping Lever collection.")
            self.last_status = "COMPLETED"
            self.last_error = None
            return []

        self.last_status = "COMPLETED"
        self.last_error = None

        # Reset diagnostic metrics for this collection run
        self.diagnostics = {
            "available_postings": 0,
            "collection_limit": self.max_jobs_per_company,
            "collected": 0,
            "valid_normalized": 0,
            "invalid_skipped": 0,
            "locations": {},
            "roles": {},
        }

        logger.info(
            "Starting Lever collection across %d companies (max_jobs_per_company=%d, delay=%.1fs)...",
            len(companies),
            self.max_jobs_per_company,
            self.request_delay_sec,
        )

        all_collected_jobs: List[Job] = []

        for idx, company in enumerate(companies):
            logger.info("Fetching Lever public postings for company='%s'...", company)
            try:
                # Execute HTTP call via thread to avoid blocking asyncio event loop
                raw_postings = await asyncio.to_thread(
                    fetch_lever_postings_http,
                    company,
                )

                if not raw_postings:
                    logger.debug("No postings returned for Lever company='%s'", company)
                    continue

                available_count = len(raw_postings)
                self.diagnostics["available_postings"] += available_count

                if len(raw_postings) > self.max_jobs_per_company:
                    logger.info(
                        "Limiting Lever jobs for company='%s' from %d to %d",
                        company,
                        len(raw_postings),
                        self.max_jobs_per_company,
                    )
                    collected_raw = raw_postings[: self.max_jobs_per_company]
                else:
                    collected_raw = raw_postings

                self.diagnostics["collected"] += len(collected_raw)

                # Collect location and role distributions from the collected batch
                for item in collected_raw:
                    if isinstance(item, dict):
                        loc = (item.get("categories", {}).get("location") or "Unspecified").strip()
                        self.diagnostics["locations"][loc] = self.diagnostics["locations"].get(loc, 0) + 1

                        raw_title = (item.get("text") or "Untitled").strip()
                        role_family = raw_title.split(" - ")[0].strip() if " - " in raw_title else raw_title
                        self.diagnostics["roles"][role_family] = self.diagnostics["roles"].get(role_family, 0) + 1

                company_jobs: List[Job] = []
                for item in collected_raw:
                    job = parse_lever_posting(item, company_id=company)
                    if job:
                        company_jobs.append(job)
                        self.diagnostics["valid_normalized"] += 1
                    else:
                        self.diagnostics["invalid_skipped"] += 1

                logger.info(
                    "Collected %d valid job postings from Lever company='%s'",
                    len(company_jobs),
                    company,
                )
                all_collected_jobs.extend(company_jobs)

            except Exception as exc:
                self.last_status = "WARNING"
                self.last_error = str(exc)
                logger.warning(
                    "Unexpected error during Lever collection for company='%s': %s",
                    company,
                    exc,
                )

            # Apply request delay between company queries
            if idx < len(companies) - 1 and self.request_delay_sec > 0:
                await asyncio.sleep(self.request_delay_sec)

        self.last_collected_count = len(all_collected_jobs)
        logger.info("Lever collection complete. Total jobs collected: %d", len(all_collected_jobs))
        return all_collected_jobs

    def format_diagnostics(
        self,
        filtered_jobs: Optional[List[Job]] = None,
        scored_jobs: Optional[List[Job]] = None,
    ) -> str:
        """Format collection and pipeline diagnostics for Lever.

        Args:
            filtered_jobs: Optional list of jobs that passed profile filter.
            scored_jobs: Optional list of scored jobs with match categories.

        Returns:
            Structured diagnostic report string.
        """
        diag = self.diagnostics
        valid_count = diag.get("valid_normalized", 0)

        if filtered_jobs is not None:
            lever_filtered = [j for j in filtered_jobs if j.source == "lever"]
            filtered_out_count = max(0, valid_count - len(lever_filtered))
        else:
            filtered_out_count = 0
            lever_filtered = []

        if scored_jobs is not None:
            lever_scored = [j for j in scored_jobs if j.source == "lever"]
        else:
            lever_scored = lever_filtered

        excellent = sum(1 for j in lever_scored if j.match_category == "Excellent")
        strong = sum(1 for j in lever_scored if j.match_category == "Strong")
        good = sum(1 for j in lever_scored if j.match_category == "Good")
        possible = sum(1 for j in lever_scored if j.match_category == "Possible")
        relevant = excellent + strong + good + possible

        lines = [
            "Lever:",
            f"  Available postings: {diag.get('available_postings', 0)}",
            f"  Collection limit: {diag.get('collection_limit', self.max_jobs_per_company)}",
            f"  Collected: {diag.get('collected', 0)}",
            f"  Valid normalized jobs: {valid_count}",
            f"  Invalid/skipped: {diag.get('invalid_skipped', 0)}",
            f"  Filtered out: {filtered_out_count}",
            f"  Relevant jobs: {relevant}",
            f"  Excellent: {excellent}",
            f"  Strong: {strong}",
            f"  Good: {good}",
            f"  Possible: {possible}",
        ]

        loc_items = sorted(diag.get("locations", {}).items(), key=lambda x: x[1], reverse=True)
        if loc_items:
            lines.append("")
            lines.append("Location distribution:")
            for loc, count in loc_items:
                lines.append(f"  {loc}: {count}")

        role_items = sorted(diag.get("roles", {}).items(), key=lambda x: x[1], reverse=True)
        if role_items:
            lines.append("")
            lines.append("Role distribution:")
            for role, count in role_items:
                lines.append(f"  {role}: {count}")

        return "\n".join(lines)
