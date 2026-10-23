"""Reusable, config-driven SAP SuccessFactors RSS Career Portal Source Connector.

Collects public job postings from SuccessFactors RSS feeds used by enterprise career portals:
- Capgemini (https://careers.capgemini.com/services/rss/job/?locale=en_US&keywords=(India))
- Wipro (https://careers.wipro.com/services/rss/job/?locale=en_US&keywords=(India))
- HCLTech (https://careers.hcltech.com/services/rss/job/?locale=en_US&keywords=(India))

Safety & Compliance Rules:
- Uses ONLY publicly exposed candidate experience RSS endpoints.
- Does NOT require private credentials or API keys.
- Gracefully handles HTTP 401/403/404/429 and timeouts without crashing the pipeline.
- Handles SuccessFactors RSS single-page stream limitation (20 items max per query) and reports PARTIAL.
- Supports role-targeted queries with polite delays and deduplication across queries.
- Provides per-company health diagnostics and independent failure isolation.
"""

import asyncio
from datetime import datetime, timezone
import html
import json
import logging
import re
from typing import Any, Dict, List, Optional
import urllib.parse
import xml.etree.ElementTree as ET

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


# Verified SuccessFactors RSS company registry
DEFAULT_SUCCESSFACTORS_COMPANIES: Dict[str, Dict[str, Any]] = {
    "capgemini": {
        "name": "Capgemini",
        "base_url": "https://careers.capgemini.com/services/rss/job/",
        "locale": "en_US",
        "default_keywords": "(India)",
        "supports_role_queries": True,
    },
    "wipro": {
        "name": "Wipro",
        "base_url": "https://careers.wipro.com/services/rss/job/",
        "locale": "en_US",
        "default_keywords": "(India)",
        "supports_role_queries": True,
    },
    "hcltech": {
        "name": "HCLTech",
        "base_url": "https://careers.hcltech.com/services/rss/job/",
        "locale": "en_US",
        "default_keywords": "(India)",
        "supports_role_queries": True,
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


def extract_successfactors_job_id(url: str, guid: Optional[str] = None) -> str:
    """Extract job ID from SuccessFactors URL pattern e.g. /1388884033/ or /183806-en_US/."""
    m = re.search(r"/([0-9]+(?:-[A-Za-z0-9_]+)?)/", url or "")
    if m:
        return m.group(1)
    if guid:
        m2 = re.search(r"/([0-9]+(?:-[A-Za-z0-9_]+)?)/", guid)
        if m2:
            return m2.group(1)
    return f"SF-{abs(hash(url)) % 1000000}"


def parse_successfactors_location(title: str, description: str, link: Optional[str] = None) -> str:
    """Extract location from URL slug, title parenthetical, or description.

    Returns specific location string (e.g. 'Katowice', 'Bangalore, India')
    or 'Not Specified' if none can be identified. Never defaults to 'India'
    for unknown/overseas locations.
    """
    # 1. Check URL slug /job/{City}-{Title}/... (e.g. Capgemini)
    if link and "/job/" in link:
        try:
            slug = link.split("/job/")[1].split("/")[0]
            slug = urllib.parse.unquote(slug)
            parts = slug.split("-")
            if parts:
                city_cand = parts[0].strip()
                if city_cand and not city_cand.isdigit():
                    if INDIAN_LOCATIONS_REGEX.search(city_cand):
                        return f"{city_cand.title()}, India" if "india" not in city_cand.lower() else city_cand.title()
                    elif any(c in city_cand.lower() for c in ["katowice", "paris", "london", "munich", "berlin", "madrid", "singapore", "mexico"]):
                        return city_cand.title()
        except Exception:
            pass

    # 2. Check title parenthetical
    m = re.search(r"\(([^)]+)\)$", title.strip())
    if m:
        loc_cand = m.group(1).strip()
        if INDIAN_LOCATIONS_REGEX.search(loc_cand):
            return loc_cand
        # Detect explicit overseas markers
        if any(w in loc_cand.lower() for w in ["m/w/d", "w/m/d", "germany", "poland", "mxico", "mexico", "france", "uk", "usa"]):
            return loc_cand

    # 3. Check description
    if description and INDIAN_LOCATIONS_REGEX.search(description):
        m_loc = INDIAN_LOCATIONS_REGEX.search(description)
        if m_loc:
            return f"{m_loc.group(1).capitalize()}, India"

    # 4. If URL slug has city, return that city even if foreign
    if link and "/job/" in link:
        try:
            slug = link.split("/job/")[1].split("/")[0]
            slug = urllib.parse.unquote(slug)
            parts = slug.split("-")
            if parts and parts[0].strip() and not parts[0].strip().isdigit():
                return parts[0].strip().title()
        except Exception:
            pass

    return "Not Specified"


class SuccessFactorsJobSource(BaseJobSource):
    """Reusable, config-driven source connector for SAP SuccessFactors RSS career portals."""

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
            else getattr(self._settings, "SUCCESSFACTORS_ENABLED", True)
        )
        super().__init__(is_enabled=enabled_flag)

        self.max_jobs_per_company = getattr(self._settings, "SUCCESSFACTORS_MAX_JOBS_PER_COMPANY", 100)
        self.request_delay_sec = getattr(self._settings, "SUCCESSFACTORS_REQUEST_DELAY_SEC", 1.0)

        # Build company registry from defaults + custom configs
        self.company_configs = dict(DEFAULT_SUCCESSFACTORS_COMPANIES)
        custom_json = getattr(self._settings, "SUCCESSFACTORS_CUSTOM_CONFIGS", "")
        if custom_json:
            try:
                custom_dict = json.loads(custom_json)
                self.company_configs.update(custom_dict)
            except Exception as e:
                logger.warning("Failed to parse SUCCESSFACTORS_CUSTOM_CONFIGS: %s", e)

        if companies:
            self.configured_companies = [c.strip().lower() for c in companies if c.strip()]
        else:
            raw_companies = getattr(self._settings, "SUCCESSFACTORS_COMPANIES", "")
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
        return "successfactors"

    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Collect postings across configured SuccessFactors RSS companies with independent failure isolation."""
        if not self.is_enabled:
            logger.info("SuccessFactors collection is disabled in configuration.")
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
                    logger.warning("[SUCCESSFACTORS] Unknown company key '%s'; skipping.", comp_key)
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
                logger.info("[SUCCESSFACTORS] Collecting RSS feeds for: %s (%s)...", comp_name, comp_key)

                try:
                    comp_jobs = await self._collect_company_jobs(
                        client=client,
                        comp_config=comp_config,
                        comp_key=comp_key,
                        max_limit=comp_limit,
                    )
                    all_jobs.extend(comp_jobs)
                except Exception as comp_err:
                    logger.warning("[SUCCESSFACTORS] Independent failure for %s: %s", comp_name, comp_err)
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
        # Any partial status or feed limitation sets overall status to PARTIAL
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
            "[SUCCESSFACTORS] Finished collection across %d companies. Total jobs: %d",
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
        """Fetch and parse RSS items for a single SuccessFactors company."""
        comp_name = comp_config["name"]
        base_url = comp_config["base_url"]
        locale = comp_config.get("locale", "en_US")
        default_kw = comp_config.get("default_keywords", "(India)")
        supports_role_queries = comp_config.get("supports_role_queries", False)

        collected_jobs: List[Job] = []
        seen_job_ids = set()
        req_error: Optional[str] = None

        queries = [default_kw]
        if supports_role_queries:
            # Targeted role queries for large feeds like Capgemini
            targeted_terms = [
                "python", "backend", "software engineer", "full stack",
                "web developer", "ai engineer", "ml engineer",
                "intern", "graduate", "trainee", "associate", "fresher", "entry level",
            ]
            queries.extend([f"(India)+({term})" for term in targeted_terms])

        pages_attempted = 0
        pages_succeeded = 0

        for q_idx, kw in enumerate(queries):
            if len(collected_jobs) >= max_limit:
                break
            if req_error:
                break

            url = f"{base_url}?locale={locale}&keywords={kw}"
            pages_attempted += 1

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
                continue

            pages_succeeded += 1
            feed_jobs = self.parse_rss_content(resp.text, comp_config)

            for job in feed_jobs:
                if len(collected_jobs) >= max_limit:
                    break
                if job.job_id in seen_job_ids:
                    continue
                seen_job_ids.add(job.job_id)
                collected_jobs.append(job)

            if self.request_delay_sec > 0 and q_idx < len(queries) - 1:
                await asyncio.sleep(self.request_delay_sec)

        # SuccessFactors RSS feed returns first 20 items per stream and does not paginate further
        # Mark PARTIAL to explicitly inform user that feed is a 20-item rolling stream
        status = "PARTIAL"
        note = "SuccessFactors RSS feed capped at first 20 items per query (pagination not supported by RSS)"
        if req_error:
            note = f"{note}; error: {req_error}"

        self.diagnostics["by_company"][comp_key] = {
            "name": comp_name,
            "status": status,
            "available": f"{len(collected_jobs)}+ (RSS stream)",
            "collected": len(collected_jobs),
            "gap": 0,
            "error": note,
            "pages_attempted": pages_attempted,
            "pages_succeeded": pages_succeeded,
        }
        self.diagnostics["total_collected"] += len(collected_jobs)
        self.diagnostics["valid_normalized"] += len(collected_jobs)

        logger.info(
            "[SUCCESSFACTORS] %s: fetched %d jobs across %d RSS queries (status: %s, note: %s)",
            comp_name, len(collected_jobs), pages_succeeded, status, note
        )
        return collected_jobs

    def parse_rss_content(self, xml_text: str, comp_config: Dict[str, Any]) -> List[Job]:
        """Parse raw SuccessFactors XML RSS feed text into Job model instances."""
        jobs: List[Job] = []
        try:
            root = ET.fromstring(xml_text)
        except Exception as e:
            logger.warning("[SUCCESSFACTORS] Failed to parse RSS XML: %s", e)
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        comp_name = comp_config["name"]
        items = channel.findall("item")

        for item in items:
            raw_title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()

            if not raw_title or not link:
                continue

            clean_link = re.sub(r"[?&]feedId=null.*", "", link)
            job_id = extract_successfactors_job_id(clean_link, guid)
            location = parse_successfactors_location(raw_title, desc, clean_link)

            # Clean parenthetical location from title if desired
            title = re.sub(r"\s*\([^)]+\)$", "", raw_title).strip() or raw_title
            desc_clean = clean_html(desc)
            full_desc = f"{title} at {comp_name}. Location: {location}. {desc_clean}".strip() if desc_clean else f"{title} at {comp_name}. Location: {location}."

            job = Job(
                source=self.source_name,
                title=title,
                company=comp_name,
                location=location,
                url=clean_link,
                job_id=job_id,
                source_job_id=job_id,
                date_posted=pub_date or "Unknown",
                description=full_desc,
                date_found=datetime.now(timezone.utc),
            )
            jobs.append(job)

        return jobs

    _parse_rss_xml = parse_rss_content

    def format_diagnostics(self) -> str:
        """Format detailed per-company diagnostic report for logs and summaries."""
        lines = ["SuccessFactors RSS Diagnostics:"]
        lines.append(f"  Total collected: {self.diagnostics.get('total_collected', 0)}")
        lines.append(f"  Valid normalized: {self.diagnostics.get('valid_normalized', 0)}")
        lines.append("Company breakdown:")

        for comp_key, info in self.diagnostics.get("by_company", {}).items():
            name = info.get("name", comp_key)
            status = info.get("status", "UNKNOWN")
            coll = info.get("collected", 0)
            avail = info.get("available", 0)
            err = info.get("error")
            lines.append(f"  - {name}: status={status}, collected={coll}, available={avail}, note={err}")

        return "\n".join(lines)


# Convenient alias
SuccessFactorsRssSource = SuccessFactorsJobSource
