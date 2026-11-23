"""Collector service coordinating modular job source connectors."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from app.models.job import Job
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


class JobCollector:
    """Orchestrates job collection across multiple modular source connectors."""

    def __init__(
        self,
        sources: Optional[List[BaseJobSource]] = None,
        source_timeout_sec: Optional[float] = None,
    ):
        self._sources: Dict[str, BaseJobSource] = {}
        self.source_results: Dict[str, Dict[str, Any]] = {}
        if source_timeout_sec is not None:
            self.source_timeout_sec = source_timeout_sec
        else:
            try:
                from app.config.settings import get_settings
                self.source_timeout_sec = getattr(get_settings(), "SOURCE_TIMEOUT_SEC", 90.0)
            except Exception:
                self.source_timeout_sec = 90.0

        if sources:
            for src in sources:
                self.register_source(src)

    def register_source(self, source: BaseJobSource) -> None:
        """Register a new source connector into the collector registry."""
        self._sources[source.source_name.lower()] = source
        logger.debug("Registered source connector: %s", source.source_name)

    @property
    def registered_sources(self) -> List[str]:
        """List of all registered source names."""
        return list(self._sources.keys())

    def get_source_results(self) -> Dict[str, Dict[str, Any]]:
        """Return structured execution results for each registered source."""
        return dict(self.source_results)

    def has_source_warnings(self) -> bool:
        """Check if any enabled source encountered warnings or blocks."""
        for res in self.source_results.values():
            if res.get("status") in ("BLOCKED", "UNAVAILABLE", "WARNING", "ERROR", "PARTIAL", "FAILED"):
                return True
        return False

    async def collect_all(
        self,
        roles: List[str],
        locations: List[str],
        max_results_per_source: int = 25,
    ) -> List[Job]:
        """Collect listings sequentially across all active sources.

        Args:
            roles: List of target role query strings.
            locations: List of target locations.
            max_results_per_source: Max items per source connector.

        Returns:
            Aggregated list of collected Job items across all sources.
        """
        all_jobs: List[Job] = []
        self.source_results = {}

        for name, source in self._sources.items():
            if not source.is_enabled:
                logger.info("Skipping disabled source: %s", name)
                self.source_results[name] = {
                    "source": name,
                    "status": "DISABLED",
                    "total_available": 0,
                    "collected": 0,
                    "error": None,
                    "duration_sec": 0.0,
                }
                continue

            logger.info("Executing collection for source: %s (timeout=%.1fs)", name, self.source_timeout_sec)
            source_jobs: List[Job] = []
            start_time = time.time()
            try:
                await source.setup()
                if self.source_timeout_sec and self.source_timeout_sec > 0:
                    source_jobs = await asyncio.wait_for(
                        source.collect_jobs(
                            roles=roles,
                            locations=locations,
                            max_results=max_results_per_source,
                        ),
                        timeout=self.source_timeout_sec,
                    )
                else:
                    source_jobs = await source.collect_jobs(
                        roles=roles,
                        locations=locations,
                        max_results=max_results_per_source,
                    )
                duration = round(time.time() - start_time, 2)
                logger.info(
                    "Collected %d jobs from source '%s' in %.2fs", len(source_jobs), name, duration
                )
                all_jobs.extend(source_jobs)

                status_val = getattr(source, "last_status", "COMPLETED")
                if status_val in ("IDLE", None):
                    status_val = "COMPLETED"
                elif status_val == "ERROR":
                    status_val = "FAILED"
                error_val = getattr(source, "last_error", None)

                # Extract total available from diagnostics if available
                diag = getattr(source, "diagnostics", {})
                avail = (
                    diag.get("total_available")
                    or diag.get("available_postings")
                    or diag.get("total_jobs")
                    or len(source_jobs)
                )

                self.source_results[name] = {
                    "source": name,
                    "status": status_val,
                    "total_available": avail,
                    "collected": len(source_jobs),
                    "error": error_val,
                    "duration_sec": duration,
                    "diagnostics": diag,
                }
            except asyncio.TimeoutError:
                duration = round(time.time() - start_time, 2)
                err_msg = f"Timed out after {self.source_timeout_sec:.1f}s"
                logger.warning("Source '%s' timed out after %.2fs", name, duration)
                if not source_jobs and hasattr(source, "_current_collected"):
                    source_jobs = list(source._current_collected)
                status_val = "PARTIAL" if source_jobs else "FAILED"
                self.source_results[name] = {
                    "source": name,
                    "status": status_val,
                    "total_available": len(source_jobs),
                    "collected": len(source_jobs),
                    "error": err_msg,
                    "duration_sec": duration,
                    "diagnostics": getattr(source, "diagnostics", {}),
                }
                all_jobs.extend(source_jobs)
            except Exception as e:
                duration = round(time.time() - start_time, 2)
                logger.exception("Error during job collection from '%s': %s", name, e)
                self.source_results[name] = {
                    "source": name,
                    "status": "FAILED",
                    "total_available": 0,
                    "collected": 0,
                    "error": str(e),
                    "duration_sec": duration,
                    "diagnostics": getattr(source, "diagnostics", {}),
                }
            finally:
                try:
                    await source.teardown()
                except Exception as e:
                    logger.warning("Error tearing down source '%s': %s", name, e)

        return all_jobs
