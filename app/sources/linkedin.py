"""LinkedIn job collection source module (Placeholder).

Note:
This module adheres strictly to project safety and architecture requirements.
Browser-based collection will be implemented in subsequent phases using
permitted navigation patterns while fully respecting platform terms,
rate limits, and access controls.
"""

import logging
from typing import List

from app.models.job import Job
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


class LinkedInJobSource(BaseJobSource):
    """Source connector for collecting job postings from LinkedIn."""

    @property
    def source_name(self) -> str:
        return "linkedin"

    async def setup(self) -> None:
        """Initialize browser session or context for LinkedIn if needed."""
        logger.info("Initializing LinkedIn connector...")

    async def teardown(self) -> None:
        """Clean up LinkedIn connection/browser resources."""
        logger.info("Closing LinkedIn connector resources.")

    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Placeholder collection method for LinkedIn listings.

        In Part 1 initialization, this returns an empty list. The actual
        Playwright extraction logic will be implemented in the next step.
        """
        if not self.is_enabled:
            logger.info("LinkedIn collection is disabled in settings.")
            return []

        logger.info(
            "LinkedIn connector ready for roles: %s in locations: %s (limit: %d).",
            roles,
            locations,
            max_results,
        )
        # Note: Do not implement fake data or unpermitted scraping.
        # Collection implementation will be added in subsequent phase.
        return []
