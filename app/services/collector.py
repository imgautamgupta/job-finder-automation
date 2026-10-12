"""Collector service coordinating modular job source connectors."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.models.job import Job
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


class JobCollector:
    """Orchestrates job collection across multiple modular source connectors."""

    def __init__(self, sources: Optional[List[BaseJobSource]] = None):
        self._sources: Dict[str, BaseJobSource] = {}
        self.source_results: Dict[str, Dict[str, Any]] = {}
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
            if res.get("status") in ("BLOCKED", "UNAVAILABLE", "WARNING", "ERROR"):
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
                    "collected": 0,
                    "error": None,
                }
                continue

            logger.info("Executing collection for source: %s", name)
            source_jobs: List[Job] = []
            try:
                await source.setup()
                source_jobs = await source.collect_jobs(
                    roles=roles,
                    locations=locations,
                    max_results=max_results_per_source,
                )
                logger.info(
                    "Collected %d jobs from source '%s'", len(source_jobs), name
                )
                all_jobs.extend(source_jobs)

                status_val = getattr(source, "last_status", "COMPLETED")
                error_val = getattr(source, "last_error", None)
                self.source_results[name] = {
                    "source": name,
                    "status": status_val,
                    "collected": len(source_jobs),
                    "error": error_val,
                }
            except Exception as e:
                logger.exception("Error during job collection from '%s': %s", name, e)
                self.source_results[name] = {
                    "source": name,
                    "status": "ERROR",
                    "collected": 0,
                    "error": str(e),
                }
            finally:
                try:
                    await source.teardown()
                except Exception as e:
                    logger.warning("Error tearing down source '%s': %s", name, e)

        return all_jobs
