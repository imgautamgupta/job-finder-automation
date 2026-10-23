"""Deduplication service ensuring jobs are unique across batches and historical runs."""

import logging
import re
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from app.models.job import Job, normalize_url

if TYPE_CHECKING:
    from app.database.database import DatabaseManager

logger = logging.getLogger(__name__)


class JobDeduplicator:
    """Coordinates in-batch and persistent database multi-level deduplication."""

    def __init__(self, db_manager: Optional["DatabaseManager"] = None):
        self.db_manager = db_manager

    def deduplicate(self, jobs: List[Job]) -> List[Job]:
        """Deduplicate candidate jobs against in-batch items and the SQLite database.

        Applies:
        - Level 1: Source + Source Job ID match
        - Level 2: Canonical URL match
        - Level 3: Deterministic Fingerprint match

        Args:
            jobs: List of raw candidate jobs.

        Returns:
            List of unique, previously unrecorded jobs.
        """
        unique_jobs: List[Job] = []

        # In-batch tracking sets
        seen_source_ids: Set[str] = set()
        seen_urls: Set[str] = set()
        seen_fingerprints: Set[str] = set()

        for job in jobs:
            # 1. Canonicalize URL and compute fingerprint
            job.url = normalize_url(job.url)
            if not job.fingerprint:
                job.fingerprint = job.compute_fingerprint()

            s_id = job.source_job_id or job.job_id
            source_id_key = f"{job.source.lower()}::{s_id.strip()}" if s_id else None

            # 2. Check In-Batch Duplicates
            # Level 1: Source Job ID
            if source_id_key and source_id_key in seen_source_ids:
                logger.debug("Duplicate within batch (Source Job ID): %s", job.title)
                continue

            # Level 2: Canonical URL
            if job.url and job.url in seen_urls:
                logger.debug("Duplicate within batch (Canonical URL): %s", job.title)
                continue

            # Level 3: Deterministic Fingerprint
            if job.fingerprint in seen_fingerprints:
                logger.debug("Duplicate within batch (Fingerprint): %s", job.title)
                continue

            # 3. Check Persistent Database Duplicates
            if self.db_manager and self.db_manager.job_exists(job):
                logger.debug(
                    "Job already exists in historical database: %s (%s)",
                    job.title,
                    job.url,
                )
                continue

            # 4. Retain and record in tracking sets
            if source_id_key:
                seen_source_ids.add(source_id_key)
            if job.url:
                seen_urls.add(job.url)
            seen_fingerprints.add(job.fingerprint)

            unique_jobs.append(job)

        logger.info(
            "Deduplication complete: retained %d unique jobs out of %d input jobs",
            len(unique_jobs),
            len(jobs),
        )
        return unique_jobs

    def deduplicate_batch(self, jobs: List[Job]) -> List[Job]:
        """Deduplicate candidate jobs within the current in-memory batch only.

        Filters out duplicate listings collected within the same execution run,
        without excluding jobs that already exist in the persistent database.

        Args:
            jobs: List of raw candidate jobs.

        Returns:
            List of unique jobs within the current batch.
        """
        unique_jobs: List[Job] = []
        seen_source_ids: Set[str] = set()
        seen_urls: Set[str] = set()
        seen_fingerprints: Set[str] = set()

        for job in jobs:
            job.url = normalize_url(job.url)
            if not job.fingerprint:
                job.fingerprint = job.compute_fingerprint()

            s_id = job.source_job_id or job.job_id
            source_id_key = f"{job.source.lower()}::{s_id.strip()}" if s_id else None

            if source_id_key and source_id_key in seen_source_ids:
                logger.debug("Duplicate within batch (Source Job ID): %s", job.title)
                continue
            if job.url and job.url in seen_urls:
                logger.debug("Duplicate within batch (Canonical URL): %s", job.title)
                continue
            if job.fingerprint in seen_fingerprints:
                logger.debug("Duplicate within batch (Fingerprint): %s", job.title)
                continue

            if source_id_key:
                seen_source_ids.add(source_id_key)
            if job.url:
                seen_urls.add(job.url)
            seen_fingerprints.add(job.fingerprint)

            unique_jobs.append(job)

        logger.info(
            "In-batch deduplication: retained %d unique listings out of %d input listings",
            len(unique_jobs),
            len(jobs),
        )
        return unique_jobs

    def deduplicate_for_all_jobs(self, jobs: List[Job]) -> List[Job]:
        """Deduplicate candidate jobs for the 'All Jobs' worksheet.

        Deduplication rule:
        1. Company + Job ID (if official job ID / source_job_id / job_id is present)
        2. Falling back to: Company + normalized title + location + URL

        Never drops jobs silently: every exclusion is logged with count and reason.

        Args:
            jobs: List of candidate jobs (MATCH, REVIEW, REJECT).

        Returns:
            List of unique jobs.
        """
        return deduplicate_for_all_jobs(jobs)


def deduplicate_for_all_jobs(jobs: List[Job]) -> List[Job]:
    """Deduplicate candidate jobs for the 'All Jobs' worksheet.

    Deduplication rule:
    1. Company + Job ID (if official job ID / source_job_id / job_id is present)
    2. Falling back to: Company + normalized title + location + URL

    Never drops jobs silently: every exclusion is logged with count and reason.
    """
    unique_jobs: List[Job] = []
    seen_keys: Set[Tuple] = set()
    exclusion_counts: Dict[str, int] = {}

    for job in jobs:
        comp = (job.company or "").strip().lower()
        official_id = (job.source_job_id or job.job_id or "").strip()

        if official_id:
            key = ("id", comp, official_id)
            reason = f"Duplicate company '{job.company}' and Job ID '{official_id}'"
        else:
            norm_title = re.sub(r"\s+", " ", (job.title or "").strip().lower())
            norm_loc = re.sub(r"\s+", " ", (job.location or "").strip().lower())
            norm_url = normalize_url(job.url or "")
            key = ("fallback", comp, norm_title, norm_loc, norm_url)
            reason = f"Duplicate company '{job.company}', title '{norm_title}', location '{norm_loc}', URL '{norm_url}'"

        if key in seen_keys:
            exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
            logger.info(
                "[DEDUP] Dropped duplicate job: '%s' (Company: %s, ID: %s) -> Reason: %s",
                job.title,
                job.company,
                official_id or "N/A",
                reason,
            )
            continue

        seen_keys.add(key)
        unique_jobs.append(job)

    if exclusion_counts:
        total_dropped = sum(exclusion_counts.values())
        logger.info(
            "[DEDUP] All Jobs deduplication: %d duplicate job(s) dropped across %d criteria.",
            total_dropped,
            len(exclusion_counts),
        )
        for r, cnt in exclusion_counts.items():
            logger.info("[DEDUP] Exclusion summary: %d job(s) dropped -> %s", cnt, r)
    else:
        logger.info("[DEDUP] All Jobs deduplication: all %d candidate jobs were unique.", len(unique_jobs))

    return unique_jobs

