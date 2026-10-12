"""Greenhouse public job board source module.

This module implements controlled, safe job collection from Greenhouse's public
Job Board API (https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs?content=true).

Safety & Compliance Rules:
- Uses ONLY publicly exposed Greenhouse job-board data.
- Does NOT require private credentials or API keys.
- Does NOT bypass authentication, CAPTCHAs, or rate limits.
- Does NOT use browser stealth, proxies, or fingerprint spoofing.
- Gracefully handles HTTP 401/403/404/429/timeout errors without crashing the pipeline.
- Missing location is strictly set to None (never defaulted to India).
- Easy Apply is strictly False (never guessed).
"""

import asyncio
from datetime import datetime, timezone
import html
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


def build_greenhouse_jobs_url(board_token: str, content: bool = True) -> str:
    """Construct the official public Greenhouse job board API endpoint URL.

    Args:
        board_token: Company board identifier/token (e.g. 'cloudflare').
        content: Whether to request full HTML job content in the response.

    Returns:
        Formatted endpoint URL.
    """
    clean_token = board_token.strip().lower()
    url = f"https://boards-api.greenhouse.io/v1/boards/{clean_token}/jobs"
    if content:
        url += "?content=true"
    return url


def clean_html_description(raw_content: Optional[str]) -> Optional[str]:
    """Safely convert HTML job description into clean plain text.

    Preserves paragraph breaks and readable layout while removing HTML markup.

    Args:
        raw_content: HTML-encoded or raw HTML description string.

    Returns:
        Clean plain-text description, or None if empty.
    """
    if not raw_content or not isinstance(raw_content, str):
        return None

    # Step 1: Unescape HTML entities (e.g. &lt;div&gt; -> <div>, &quot; -> ")
    text = html.unescape(raw_content)

    # Step 2: Convert block tags into newlines to maintain section separations
    text = re.sub(r"<(?:br|p|div|li|h[1-6]|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)

    # Step 3: Remove inline formatting tags without injecting extra spaces
    text = re.sub(r"</?(?:strong|b|em|i|u|span|a|code)[^>]*>", "", text, flags=re.IGNORECASE)

    # Step 4: Strip any remaining HTML tags with a space
    text = re.sub(r"<[^>]+>", " ", text)

    # Step 5: Unescape again for nested entities (e.g. &amp;nbsp;)
    text = html.unescape(text)

    # Step 6: Clean up spaces before punctuation (e.g. "word ." -> "word.")
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)

    # Step 7: Clean whitespace per line while preserving meaningful line breaks
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    cleaned = "\n".join([line for line in lines if line]).strip()

    return cleaned if cleaned else None


def normalize_greenhouse_location(
    location_obj: Any,
    offices: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """Extract and normalize location text from Greenhouse posting metadata.

    Preserves multi-location listings (e.g. 'Bangalore, India; Remote') without
    defaulting missing values to India or overriding explicit city assignments.

    Args:
        location_obj: The 'location' object or string from Greenhouse payload.
        offices: Optional list of office objects from Greenhouse payload.
        metadata: Optional list of custom metadata entries.

    Returns:
        Normalized location string, or None if no valid location was specified.
    """
    valid_locs: List[str] = []
    seen_lower: set[str] = set()

    def add_location_token(token: Optional[str]) -> None:
        if not token or not isinstance(token, str):
            return
        clean = token.strip()
        if not clean:
            return
        clean_lower = clean.lower()
        if clean_lower in ("unknown", "none", "n/a", "not specified", "null"):
            return
        if clean_lower not in seen_lower:
            valid_locs.append(clean)
            seen_lower.add(clean_lower)

    # 1. Primary location name
    if isinstance(location_obj, dict):
        add_location_token(location_obj.get("name"))
    elif isinstance(location_obj, str):
        add_location_token(location_obj)

    # 2. Associated office locations
    if offices and isinstance(offices, list):
        for office in offices:
            if isinstance(office, dict):
                office_loc = office.get("location") or office.get("name")
                add_location_token(office_loc)

    # 3. Location from custom metadata fields if available
    if metadata and isinstance(metadata, list):
        for meta in metadata:
            if isinstance(meta, dict):
                meta_name = (meta.get("name") or "").lower()
                if "location" in meta_name:
                    meta_val = meta.get("value")
                    if isinstance(meta_val, list):
                        for item in meta_val:
                            add_location_token(str(item))
                    elif isinstance(meta_val, str):
                        add_location_token(meta_val)

    if not valid_locs:
        return None

    return "; ".join(valid_locs)


def parse_greenhouse_posting(posting: Dict[str, Any], company_id: str) -> Optional[Job]:
    """Convert a raw Greenhouse public job posting JSON object into a standardized Job model.

    Args:
        posting: Dictionary representing a single Greenhouse job item.
        company_id: Configured Greenhouse company/board identifier.

    Returns:
        Standardized Job object, or None if required fields are missing or invalid.
    """
    if not isinstance(posting, dict):
        return None

    title = (posting.get("title") or "").strip()
    source_job_id = str(posting.get("id") or "").strip()

    if not title or not source_job_id:
        logger.debug("Skipping invalid Greenhouse posting missing title or ID: %s", posting)
        return None

    # Company name: prefer company_name attribute if provided, fallback to board identifier
    company_name = (posting.get("company_name") or "").strip() or company_id.strip()

    # Location normalization (strictly None if missing, never defaulted to 'India')
    location = normalize_greenhouse_location(
        location_obj=posting.get("location"),
        offices=posting.get("offices"),
        metadata=posting.get("metadata"),
    )

    # Hosted URL
    hosted_url = (posting.get("absolute_url") or "").strip()
    if not hosted_url:
        hosted_url = f"https://boards.greenhouse.io/{company_id}/jobs/{source_job_id}"

    # Description extraction with safe HTML cleaning
    description = clean_html_description(posting.get("content"))

    # Date posted conversion from ISO timestamp (e.g. 2026-10-02T14:24:13-04:00)
    date_posted = None
    raw_date = posting.get("first_published") or posting.get("updated_at")
    if raw_date and isinstance(raw_date, str):
        try:
            date_clean = raw_date.replace("Z", "+00:00")
            dt = datetime.fromisoformat(date_clean)
            date_posted = dt.strftime("%Y-%m-%d")
        except Exception:
            if len(raw_date) >= 10 and raw_date[:4].isdigit():
                date_posted = raw_date[:10]

    # Metadata extraction for employment type, experience, salary
    employment_type = None
    experience_required = None
    salary = None

    raw_meta_list = posting.get("metadata")
    if isinstance(raw_meta_list, list):
        for item in raw_meta_list:
            if isinstance(item, dict):
                m_name = (item.get("name") or "").lower()
                m_val = item.get("value")
                val_str = str(m_val) if m_val is not None else None
                if not val_str or val_str.lower() in ("none", "null", "n/a"):
                    continue

                if "employment type" in m_name or "commitment" in m_name:
                    employment_type = val_str
                elif "experience" in m_name:
                    experience_required = val_str
                elif "salary" in m_name or "compensation" in m_name:
                    salary = val_str

    # Raw metadata preserved for traceability
    raw_meta: Dict[str, Any] = {
        "greenhouse_board_id": company_id,
        "internal_job_id": posting.get("internal_job_id"),
        "requisition_id": posting.get("requisition_id"),
        "departments": posting.get("departments"),
        "offices": posting.get("offices"),
        "updated_at": posting.get("updated_at"),
    }

    try:
        return Job(
            source="greenhouse",
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
        logger.warning("Failed to construct Job from Greenhouse posting %s: %s", source_job_id, exc)
        return None


def fetch_greenhouse_postings_http(
    board_token: str,
    timeout_sec: float = 15.0,
) -> List[Dict[str, Any]]:
    """Fetch raw public job postings from Greenhouse Job Board API using standard urllib.

    Args:
        board_token: Greenhouse company/board identifier.
        timeout_sec: Network request timeout in seconds.

    Returns:
        List of posting dictionaries, or empty list on error/restriction.
    """
    url = build_greenhouse_jobs_url(board_token, content=True)
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
            if isinstance(parsed, dict) and "jobs" in parsed:
                return parsed["jobs"]
            elif isinstance(parsed, list):
                return parsed
            logger.warning("Unexpected response structure from Greenhouse for board='%s'", board_token)
            return []
    except urllib.error.HTTPError as http_err:
        if http_err.code in (401, 403):
            logger.warning(
                "Greenhouse access restricted for board='%s' (HTTP %d). Stopping that company safely.",
                board_token,
                http_err.code,
            )
        elif http_err.code == 404:
            logger.warning(
                "Greenhouse board not found for company='%s' (HTTP 404). Continuing with remaining companies.",
                board_token,
            )
        elif http_err.code == 429:
            logger.warning(
                "Greenhouse rate limit reached for board='%s' (HTTP 429). Stopping that company safely.",
                board_token,
            )
        else:
            logger.warning(
                "Greenhouse HTTP error %d encountered for board='%s'.",
                http_err.code,
                board_token,
            )
        return []
    except urllib.error.URLError as url_err:
        logger.warning(
            "Greenhouse network connection error for board='%s': %s",
            board_token,
            url_err,
        )
        return []
    except json.JSONDecodeError as json_err:
        logger.warning(
            "Malformed JSON returned by Greenhouse for board='%s': %s",
            board_token,
            json_err,
        )
        return []
    except Exception as exc:
        logger.warning(
            "Unexpected error fetching Greenhouse postings for board='%s': %s",
            board_token,
            exc,
        )
        return []


class GreenhouseJobSource(BaseJobSource):
    """Source connector for collecting public job postings from Greenhouse.

    Collects listings from configured company board identifiers via Greenhouse's public
    Job Board API (https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs?content=true).
    Adheres strictly to safety constraints: no authentication required, no
    CAPTCHA solving, conservative rate limits, and graceful error handling.
    """

    def __init__(
        self,
        is_enabled: Optional[bool] = None,
        settings: Optional[Settings] = None,
    ):
        self._settings = settings or get_settings()
        enabled_flag = is_enabled if is_enabled is not None else self._settings.GREENHOUSE_ENABLED
        super().__init__(is_enabled=enabled_flag)

        self.max_jobs_per_company = self._settings.GREENHOUSE_MAX_JOBS_PER_COMPANY
        self.request_delay_sec = self._settings.GREENHOUSE_REQUEST_DELAY_SEC
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
        return "greenhouse"

    @property
    def companies(self) -> List[str]:
        """Parsed, non-empty list of configured Greenhouse board identifiers."""
        return self._settings.greenhouse_company_list

    async def setup(self) -> None:
        """Initialize Greenhouse connector lifecycle."""
        if not self.is_enabled:
            return
        logger.info(
            "Initializing Greenhouse public connector (configured companies: %d)...",
            len(self.companies),
        )

    async def teardown(self) -> None:
        """Clean up Greenhouse connector resources."""
        logger.info("Closing Greenhouse connector resources.")

    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Collect job postings across all configured Greenhouse company boards.

        Args:
            roles: Target role titles (used by pipeline filtering).
            locations: Target locations (used by pipeline filtering).
            max_results: Maximum results to collect.

        Returns:
            List of normalized Job objects across configured companies.
        """
        if not self.is_enabled:
            logger.info("Greenhouse collection is disabled in settings.")
            self.last_status = "DISABLED"
            self.last_error = None
            return []

        companies = self.companies
        if not companies:
            logger.info("No Greenhouse companies configured (GREENHOUSE_COMPANIES is empty). Skipping collection.")
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
            "Starting Greenhouse collection across %d companies (max_jobs_per_company=%d, delay=%.1fs)...",
            len(companies),
            self.max_jobs_per_company,
            self.request_delay_sec,
        )

        all_collected_jobs: List[Job] = []

        for idx, company in enumerate(companies):
            logger.info("Fetching Greenhouse public postings for company='%s'...", company)
            try:
                # Execute HTTP call via thread to avoid blocking asyncio event loop
                raw_postings = await asyncio.to_thread(
                    fetch_greenhouse_postings_http,
                    company,
                )

                if not raw_postings:
                    logger.debug("No postings returned for Greenhouse company='%s'", company)
                    continue

                available_count = len(raw_postings)
                self.diagnostics["available_postings"] += available_count

                if len(raw_postings) > self.max_jobs_per_company:
                    logger.info(
                        "Limiting Greenhouse jobs for company='%s' from %d to %d",
                        company,
                        len(raw_postings),
                        self.max_jobs_per_company,
                    )
                    collected_raw = raw_postings[: self.max_jobs_per_company]
                else:
                    collected_raw = raw_postings

                self.diagnostics["collected"] += len(collected_raw)

                # Record location and role distributions from the collected batch
                for item in collected_raw:
                    if isinstance(item, dict):
                        loc = normalize_greenhouse_location(
                            item.get("location"),
                            item.get("offices"),
                            item.get("metadata"),
                        ) or "Unspecified"
                        self.diagnostics["locations"][loc] = self.diagnostics["locations"].get(loc, 0) + 1

                        raw_title = (item.get("title") or "Untitled").strip()
                        role_family = raw_title.split(" - ")[0].strip() if " - " in raw_title else raw_title
                        if "," in role_family:
                            role_family = role_family.split(",")[0].strip()
                        self.diagnostics["roles"][role_family] = self.diagnostics["roles"].get(role_family, 0) + 1

                company_jobs: List[Job] = []
                for item in collected_raw:
                    job = parse_greenhouse_posting(item, company_id=company)
                    if job:
                        company_jobs.append(job)
                        self.diagnostics["valid_normalized"] += 1
                    else:
                        self.diagnostics["invalid_skipped"] += 1

                logger.info(
                    "Collected %d valid job postings from Greenhouse company='%s'",
                    len(company_jobs),
                    company,
                )
                all_collected_jobs.extend(company_jobs)

            except Exception as exc:
                self.last_status = "WARNING"
                self.last_error = str(exc)
                logger.warning(
                    "Unexpected error during Greenhouse collection for company='%s': %s",
                    company,
                    exc,
                )

            # Apply request delay between company queries
            if idx < len(companies) - 1 and self.request_delay_sec > 0:
                await asyncio.sleep(self.request_delay_sec)

        self.last_collected_count = len(all_collected_jobs)
        logger.info("Greenhouse collection complete. Total jobs collected: %d", len(all_collected_jobs))
        return all_collected_jobs

    def format_diagnostics(
        self,
        filtered_jobs: Optional[List[Job]] = None,
        scored_jobs: Optional[List[Job]] = None,
    ) -> str:
        """Format collection and pipeline diagnostics for Greenhouse.

        Args:
            filtered_jobs: Optional list of jobs that passed profile filter.
            scored_jobs: Optional list of scored jobs with match categories.

        Returns:
            Structured diagnostic report string.
        """
        diag = self.diagnostics
        valid_count = diag.get("valid_normalized", 0)

        if filtered_jobs is not None:
            gh_filtered = [j for j in filtered_jobs if j.source == "greenhouse"]
            filtered_out_count = max(0, valid_count - len(gh_filtered))
        else:
            filtered_out_count = 0
            gh_filtered = []

        if scored_jobs is not None:
            gh_scored = [j for j in scored_jobs if j.source == "greenhouse"]
        else:
            gh_scored = gh_filtered

        excellent = sum(1 for j in gh_scored if j.match_category == "Excellent")
        strong = sum(1 for j in gh_scored if j.match_category == "Strong")
        good = sum(1 for j in gh_scored if j.match_category == "Good")
        possible = sum(1 for j in gh_scored if j.match_category == "Possible")
        relevant = excellent + strong + good + possible

        lines = [
            "Greenhouse:",
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
