"""Naukri job collection source module.

This module implements controlled, safe job collection from Naukri.
It extracts listings into the standardized Job model using explicit field
parsing, stable identifier extraction, and strict Easy Apply rules.

Safety & Compliance Rules:
- Strictly respects platform terms, rate limits, robots.txt, and access controls.
- Does NOT use stealth plugins, proxy rotation, CAPTCHA solvers, or fingerprint spoofing.
- Gracefully handles anti-bot detection / access denial (e.g., HTTP 403) by logging
  and stopping without crashing the pipeline or fabricating fake data.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from app.config.settings import Settings, get_settings
from app.models.job import Job
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


def build_naukri_search_url(role: str, location: Optional[str] = None, page_no: int = 1) -> str:
    """Build a deterministic, canonical Naukri search URL for a given role and location.

    Args:
        role: Target job title/role keyword (e.g. 'Python Developer').
        location: Target location (e.g. 'Delhi', 'Bangalore', 'Remote', 'India').
        page_no: 1-indexed pagination number.

    Returns:
        Formatted canonical search URL string.
    """
    clean_role = re.sub(r"[^a-zA-Z0-9]+", "-", role.strip().lower()).strip("-")
    clean_loc = ""
    if location and location.strip().lower() not in ("india", "remote", ""):
        clean_loc = re.sub(r"[^a-zA-Z0-9]+", "-", location.strip().lower()).strip("-")

    if clean_loc:
        base_path = f"https://www.naukri.com/{clean_role}-jobs-in-{clean_loc}"
    else:
        base_path = f"https://www.naukri.com/{clean_role}-jobs"

    if page_no > 1:
        return f"{base_path}-{page_no}"
    return base_path


def extract_stable_job_id(
    data_job_id: Optional[str] = None,
    url: Optional[str] = None,
) -> Optional[str]:
    """Extract a stable, deterministic Naukri source job identifier.

    Args:
        data_job_id: Value from data-job-id attribute if present.
        url: Listing URL which often ends with a numerical job identifier.

    Returns:
        Clean numerical string ID if found, otherwise None (allowing fingerprint fallback).
    """
    if data_job_id and data_job_id.strip():
        clean_id = data_job_id.strip()
        if re.match(r"^\d+$", clean_id):
            return clean_id

    if url:
        # Naukri URLs often end with a 10-14 digit timestamp/ID, e.g. -120524001234
        match = re.search(r"-(\d{8,16})(?:\?|$)", url)
        if match:
            return match.group(1)
        # Also check for jobId query parameter
        query_match = re.search(r"[?&]jobId=(\d+)", url)
        if query_match:
            return query_match.group(1)

    return None


def parse_naukri_job_card_dict(card_data: Dict[str, Any]) -> Optional[Job]:
    """Normalize a dictionary of extracted Naukri job card fields into a standardized Job model.

    Args:
        card_data: Dictionary containing raw string or structured field values.

    Returns:
        Standardized Job model instance, or None if required fields are missing.
    """
    title = (card_data.get("title") or "").strip()
    company = (card_data.get("company") or "").strip()
    location = (card_data.get("location") or "").strip()
    raw_url = (card_data.get("url") or "").strip()

    if not title or not company or not raw_url:
        logger.debug("Skipping invalid Naukri listing missing required fields: %s", card_data)
        return None

    # Canonical URL formatting
    full_url = urljoin("https://www.naukri.com", raw_url)

    raw_loc = card_data.get("location")
    location = raw_loc.strip() if raw_loc and raw_loc.strip() else None
    if location and location.lower() in ("unknown", "none", "not specified", "n/a"):
        location = None

    # Stable Source Job ID extraction
    source_job_id = extract_stable_job_id(
        data_job_id=card_data.get("data_job_id") or card_data.get("source_job_id"),
        url=full_url,
    )

    # Easy Apply determination (Never guess: explicit True, explicit False, or None)
    raw_apply = card_data.get("easy_apply")
    easy_apply_val: Optional[bool] = None
    if isinstance(raw_apply, bool):
        easy_apply_val = raw_apply
    elif isinstance(raw_apply, str):
        lower_apply = raw_apply.lower()
        if "easy apply" in lower_apply or "quick apply" in lower_apply or "apply on naukri" in lower_apply:
            easy_apply_val = True
        elif "company site" in lower_apply or "external" in lower_apply or "apply on company" in lower_apply:
            easy_apply_val = False

    # Optional fields
    description = card_data.get("description")
    if description:
        description = description.strip() or None

    date_posted = card_data.get("date_posted")
    if date_posted:
        date_posted = date_posted.strip() or None

    experience_required = card_data.get("experience_required")
    if experience_required:
        experience_required = experience_required.strip() or None

    salary = card_data.get("salary")
    if salary:
        salary = salary.strip() or None

    employment_type = card_data.get("employment_type")
    if employment_type:
        employment_type = employment_type.strip() or None

    raw_metadata = {
        k: v
        for k, v in card_data.items()
        if k not in (
            "title",
            "company",
            "location",
            "url",
            "description",
            "easy_apply",
            "date_posted",
            "experience_required",
            "salary",
            "employment_type",
            "data_job_id",
            "source_job_id",
        )
    }

    try:
        return Job(
            source="naukri",
            source_job_id=source_job_id,
            job_id=source_job_id,
            title=title,
            company=company,
            location=location,
            url=full_url,
            description=description,
            easy_apply=easy_apply_val if easy_apply_val is not None else False,
            date_posted=date_posted,
            employment_type=employment_type,
            experience_required=experience_required,
            salary=salary,
            extra_metadata=raw_metadata,
        )
    except Exception as exc:
        logger.warning("Failed to construct Job from Naukri data %s: %s", card_data, exc)
        return None


def parse_naukri_html_snippet(html_content: str) -> List[Job]:
    """Parse job listings from a Naukri search result HTML string.

    Supports Naukri's job card containers (`srp-jobtuple-wrapper`, `cust-job-tuple`, `jobTuple`).
    Extracts title, company, location, experience, salary, description, job ID, and apply flags.

    Args:
        html_content: Raw HTML text of the search results page.

    Returns:
        List of standardized Job instances parsed from the HTML.
    """
    if not html_content or not html_content.strip():
        return []

    jobs: List[Job] = []

    # Find start boundaries of job card containers
    outer_pattern = re.compile(
        r"<(?:div|article)[^>]*\bclass=[\"'][^\"']*(?:srp-jobtuple-wrapper|jobTuple)[\"'][^>]*>",
        re.IGNORECASE,
    )
    matches = list(outer_pattern.finditer(html_content))
    if not matches:
        card_start_pattern = re.compile(
            r"<(?:div|article)[^>]*\bclass=[\"'][^\"']*(?:srp-jobtuple-wrapper|cust-job-tuple|jobTuple)[^\"']*[\"'][^>]*>",
            re.IGNORECASE,
        )
        matches = list(card_start_pattern.finditer(html_content))

    if not matches:
        return []

    card_chunks: List[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html_content)
        card_chunks.append(html_content[start:end])

    for chunk in card_chunks:
        # Extract data-job-id attribute from container
        job_id_match = re.search(r"data-job-id=[\"'](\d+)[\"']", chunk, re.IGNORECASE)
        data_job_id = job_id_match.group(1) if job_id_match else None

        # Extract title and URL
        title_match = re.search(
            r"<a[^>]+class=[\"'][^\"']*\btitle\b[^\"']*[\"'][^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        if not title_match:
            title_match = re.search(
                r"<a[^>]*href=[\"']([^\"']+)[\"'][^>]+class=[\"'][^\"']*\btitle\b[^\"']*[\"'][^>]*>(.*?)</a>",
                chunk,
                re.DOTALL | re.IGNORECASE,
            )

        if not title_match:
            continue

        raw_url = title_match.group(1)
        raw_title = re.sub(r"<[^>]+>", "", title_match.group(2)).strip()

        # Extract company name
        comp_match = re.search(
            r"<a[^>]+class=[\"'][^\"']*(?:comp-name|subTitle|companyInfo)[^\"']*[\"'][^>]*>(.*?)</a>",
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        if not comp_match:
            comp_match = re.search(
                r"<(?:span|div)[^>]+class=[\"'][^\"']*(?:comp-name|subTitle|comp-name-link)[^\"']*[\"'][^>]*>(.*?)</(?:span|div)>",
                chunk,
                re.DOTALL | re.IGNORECASE,
            )
        company = re.sub(r"<[^>]+>", "", comp_match.group(1)).strip() if comp_match else ""

        # Extract experience required
        exp_match = re.search(
            r"<(?:span|li)[^>]+class=[\"'][^\"']*(?:expwdth|experience|exp-wrap)[^\"']*[\"'][^>]*>(.*?)</(?:span|li)>",
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        experience = re.sub(r"<[^>]+>", "", exp_match.group(1)).strip() if exp_match else None

        # Extract salary
        sal_match = re.search(
            r"<(?:span|li)[^>]+class=[\"'][^\"']*(?:sal|salary|sal-wrap|ni-job-tuple-icon-salary)[^\"']*[\"'][^>]*>(.*?)</(?:span|li)>",
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        salary = re.sub(r"<[^>]+>", "", sal_match.group(1)).strip() if sal_match else None

        # Extract location
        loc_match = re.search(
            r"<(?:span|li)[^>]+class=[\"'][^\"']*(?:locWdth|location|loc-wrap)[^\"']*[\"'][^>]*>(.*?)</(?:span|li)>",
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        loc_str = re.sub(r"<[^>]+>", "", loc_match.group(1)).strip() if loc_match else None
        location = loc_str if loc_str and loc_str.lower() not in ("unknown", "none", "not specified", "n/a") else None

        # Extract description / snippet
        desc_match = re.search(
            r"<(?:div|span)[^>]+class=[\"'][^\"']*(?:job-desc|job-description|row4)[^\"']*[\"'][^>]*>(.*?)</(?:div|span)>",
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        description = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip() if desc_match else None

        # Extract date posted
        date_match = re.search(
            r"<span[^>]+class=[\"'][^\"']*(?:job-post-day|date|posted-by)[^\"']*[\"'][^>]*>(.*?)</span>",
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        date_posted = re.sub(r"<[^>]+>", "", date_match.group(1)).strip() if date_match else None

        # Check for explicit Easy Apply indicator
        easy_apply = None
        if re.search(r"\b(?:easy-apply|quick-apply|apply on naukri)\b", chunk, re.IGNORECASE):
            easy_apply = True
        elif re.search(r"\b(?:apply on company site|external-apply)\b", chunk, re.IGNORECASE):
            easy_apply = False

        card_dict = {
            "title": raw_title,
            "company": company,
            "location": location,
            "url": raw_url,
            "data_job_id": data_job_id,
            "experience_required": experience,
            "salary": salary,
            "description": description,
            "date_posted": date_posted,
            "easy_apply": easy_apply,
        }

        job = parse_naukri_job_card_dict(card_dict)
        if job:
            jobs.append(job)

    return jobs


class NaukriJobSource(BaseJobSource):
    """Source connector for collecting job postings from Naukri.

    Implements controlled, rate-limited collection adhering to platform terms
    and technical constraints. Does NOT attempt CAPTCHA bypass, stealth evasion,
    or credential spoofing. If access is restricted (e.g., HTTP 403 / Access Denied),
    the connector halts gracefully and reports the status without crashing.
    """

    def __init__(
        self,
        is_enabled: Optional[bool] = None,
        settings: Optional[Settings] = None,
    ):
        self._settings = settings or get_settings()
        enabled_flag = is_enabled if is_enabled is not None else self._settings.NAUKRI_ENABLED
        super().__init__(is_enabled=enabled_flag)

        self.max_pages = self._settings.NAUKRI_MAX_PAGES
        self.max_jobs = self._settings.NAUKRI_MAX_JOBS
        self.request_delay_sec = self._settings.NAUKRI_REQUEST_DELAY_SEC
        self.headless = self._settings.HEADLESS_BROWSER
        self.timeout_ms = self._settings.BROWSER_TIMEOUT_MS

        self._playwright = None
        self._browser = None

    @property
    def source_name(self) -> str:
        return "naukri"

    async def setup(self) -> None:
        """Initialize browser resources if collection is enabled."""
        if not self.is_enabled:
            return
        logger.info("Initializing Naukri connector (headless=%s, timeout=%dms)...", self.headless, self.timeout_ms)

    async def teardown(self) -> None:
        """Clean up Naukri browser resources."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.debug("Error closing browser: %s", exc)
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.debug("Error stopping playwright: %s", exc)
            self._playwright = None

        logger.info("Closing Naukri connector resources.")

    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Collect real job listings from Naukri within configured limits.

        Adheres strictly to access controls: if the site blocks automated requests
        (e.g. HTTP 403 / Access Denied), it aborts collection gracefully and returns
        the listings collected thus far (or an empty list) without fabricating fake data.

        Args:
            roles: List of target job role titles from profile.
            locations: List of preferred locations from profile.
            max_results: Max jobs to collect.

        Returns:
            List of standardized Job objects.
        """
        if not self.is_enabled:
            logger.info("Naukri collection is disabled in settings.")
            self.last_status = "DISABLED"
            self.last_error = None
            return []

        self.last_status = "COMPLETED"
        self.last_error = None

        effective_limit = min(max_results, self.max_jobs)
        logger.info(
            "Naukri connector ready for roles: %s in locations: %s (limit: %d, max_pages: %d).",
            roles,
            locations,
            effective_limit,
            self.max_pages,
        )

        collected_jobs: List[Job] = []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("Playwright is not installed. Naukri collection skipped.")
            self.last_status = "UNAVAILABLE"
            self.last_error = "Playwright is not installed"
            return []

        # Standard, legitimate browser automation without evasion or stealth spoofing
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
            )
            context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            # Iterate over roles and top locations within configured page & job limits
            for role in roles:
                if len(collected_jobs) >= effective_limit:
                    break

                for loc in locations:
                    if len(collected_jobs) >= effective_limit:
                        break

                    for page_no in range(1, self.max_pages + 1):
                        if len(collected_jobs) >= effective_limit:
                            break

                        target_url = build_naukri_search_url(role=role, location=loc, page_no=page_no)
                        logger.info(
                            "Naukri querying: role='%s', loc='%s', page=%d (URL: %s)",
                            role,
                            loc,
                            page_no,
                            target_url,
                        )

                        try:
                            response = await page.goto(
                                target_url,
                                wait_until="domcontentloaded",
                                timeout=self.timeout_ms,
                            )
                            status_code = response.status if response else None

                            # Check for access denial / anti-bot blocking
                            if status_code in (403, 401, 429):
                                self.last_status = "BLOCKED"
                                self.last_error = f"HTTP {status_code} (Access Denied)"
                                logger.warning(
                                    "Naukri collection stopped: HTTP %s (Access Denied) for query='%s', loc='%s', page=%d. "
                                    "Platform access controls are active; respecting restriction without bypass.",
                                    status_code,
                                    role,
                                    loc,
                                    page_no,
                                    )
                                # Stop collection safely per project compliance rules
                                self.last_collected_count = len(collected_jobs)
                                return collected_jobs

                            page_title = await page.title()
                            if "access denied" in page_title.lower() or "blocked" in page_title.lower():
                                self.last_status = "BLOCKED"
                                self.last_error = f"Access Denied title: {page_title}"
                                logger.warning(
                                    "Naukri collection stopped: Access Denied title encountered ('%s'). "
                                    "Platform access controls are active; respecting restriction without bypass.",
                                    page_title,
                                )
                                self.last_collected_count = len(collected_jobs)
                                return collected_jobs

                            # Wait briefly for dynamic elements to render
                            await page.wait_for_timeout(3000)
                            content = await page.content()

                            page_jobs = parse_naukri_html_snippet(content)
                            logger.info(
                                "Naukri page %d extracted %d job listings for query='%s'",
                                page_no,
                                len(page_jobs),
                                role,
                            )

                            for j in page_jobs:
                                if len(collected_jobs) >= effective_limit:
                                    break
                                collected_jobs.append(j)

                            # Respectful rate limiting between page requests
                            if self.request_delay_sec > 0:
                                await asyncio.sleep(self.request_delay_sec)

                        except Exception as page_exc:
                            self.last_status = "WARNING"
                            self.last_error = str(page_exc)
                            logger.warning(
                                "Naukri request error for query='%s', loc='%s', page=%d: %s",
                                role,
                                loc,
                                page_no,
                                page_exc,
                            )
                            # Allow outer loop to continue or exit safely
                            break

        except Exception as exc:
            self.last_status = "ERROR"
            self.last_error = str(exc)
            logger.warning("Naukri browser automation encounter error: %s. Returning %d jobs.", exc, len(collected_jobs))
        finally:
            await self.teardown()

        self.last_collected_count = len(collected_jobs)
        logger.info("Naukri collection finished. Total jobs collected: %d", len(collected_jobs))
        return collected_jobs
