"""Reusable, config-driven SmartRecruiters Public Postings Source Connector.

Collects public job postings from SmartRecruiters API:
https://api.smartrecruiters.com/v1/companies/{company}/postings?country=in

Safety & Compliance Rules:
- Uses ONLY publicly exposed candidate experience JSON endpoints.
- Does NOT require private credentials or API keys.
- Gracefully handles HTTP 401/403/404/429 and network errors without crashing pipeline.
- Performs India pre-filtering and per-company health diagnostics.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config.settings import Settings, get_settings
from app.models.job import Job, normalize_url
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


class SmartRecruitersJobSource(BaseJobSource):
    """Reusable, config-driven source connector for SmartRecruiters public job boards."""

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
            else getattr(self._settings, "SMARTRECRUITERS_ENABLED", False)
        )
        super().__init__(is_enabled=enabled_flag)

        self.max_jobs_per_company = getattr(self._settings, "SMARTRECRUITERS_MAX_JOBS_PER_COMPANY", 25)
        self.request_delay_sec = getattr(self._settings, "SMARTRECRUITERS_REQUEST_DELAY_SEC", 1.0)

        if companies:
            self.configured_companies = [c.strip().lower() for c in companies if c.strip()]
        else:
            raw = getattr(self._settings, "SMARTRECRUITERS_COMPANIES", "")
            self.configured_companies = [c.strip().lower() for c in raw.split(",") if c.strip()]

        self.diagnostics: Dict[str, Any] = {
            "by_company": {},
            "total_collected": 0,
            "valid_normalized": 0,
        }

    @property
    def source_name(self) -> str:
        return "smartrecruiters"

    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Collect job postings across all configured SmartRecruiters companies."""
        if not self.is_enabled:
            logger.info("SmartRecruiters collection is disabled in configuration.")
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

        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            for comp in self.configured_companies:
                logger.info("[SMARTRECRUITERS] Collecting jobs for company: %s...", comp)
                try:
                    comp_jobs = await self._collect_company_jobs(client, comp, min(max_results, self.max_jobs_per_company))
                    all_jobs.extend(comp_jobs)
                except Exception as comp_err:
                    logger.warning("[SMARTRECRUITERS] Independent failure for %s: %s", comp, comp_err)
                    self.diagnostics["by_company"][comp] = {
                        "name": comp.capitalize(),
                        "status": "FAILED",
                        "error": str(comp_err),
                        "collected": 0,
                    }

                if self.request_delay_sec > 0:
                    await asyncio.sleep(self.request_delay_sec)

        self.last_collected_count = len(all_jobs)
        companies_with_errors = [
            c for c in self.diagnostics["by_company"].values()
            if c.get("error") is not None or c.get("status") in ("FAILED", "PARTIAL") or str(c.get("status", "")).startswith("HTTP_")
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

        return all_jobs

    async def _collect_company_jobs(
        self,
        client: httpx.AsyncClient,
        comp: str,
        max_limit: int,
    ) -> List[Job]:
        """Collect listings for a single SmartRecruiters company."""
        url = f"https://api.smartrecruiters.com/v1/companies/{comp}/postings?country=in"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }

        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning("[SMARTRECRUITERS] %s returned HTTP status %d", comp, resp.status_code)
            self.diagnostics["by_company"][comp] = {
                "name": comp.capitalize(),
                "status": f"HTTP_{resp.status_code}",
                "error": f"Status code {resp.status_code}",
                "collected": 0,
            }
            return []

        data = resp.json()
        total_found = data.get("totalFound", 0)
        items = data.get("content", [])

        collected_jobs: List[Job] = []
        for it in items[:max_limit]:
            title = (it.get("name") or "").strip()
            job_id = str(it.get("id") or "").strip()
            if not title or not job_id:
                continue

            loc_data = it.get("location") or {}
            city = loc_data.get("city") or ""
            region = loc_data.get("region") or ""
            loc_str = f"{city}, {region}".strip(", ") or "India"

            apply_url = f"https://jobs.smartrecruiters.com/{comp}/{job_id}"
            released = it.get("releasedDate") or ""

            job = Job(
                source=self.source_name,
                title=title,
                company=comp.capitalize(),
                location=loc_str,
                url=apply_url,
                job_id=job_id,
                source_job_id=job_id,
                date_posted=released,
                description=f"{title} at {comp.capitalize()}. Location: {loc_str}. Released: {released}.",
                date_found=datetime.now(timezone.utc),
            )
            collected_jobs.append(job)

        self.diagnostics["by_company"][comp] = {
            "name": comp.capitalize(),
            "status": "COMPLETED",
            "available": total_found,
            "collected": len(collected_jobs),
            "error": None,
        }
        self.diagnostics["total_collected"] += len(collected_jobs)
        self.diagnostics["valid_normalized"] += len(collected_jobs)
        return collected_jobs
