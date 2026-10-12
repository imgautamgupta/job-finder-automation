"""Base connector interface for modular job collection sources."""

from abc import ABC, abstractmethod
import logging
from typing import List, Optional

from app.models.job import Job

logger = logging.getLogger(__name__)


class BaseJobSource(ABC):
    """Abstract Base Class defining the interface for all job collection sources.

    All platform-specific sources (e.g. LinkedIn, Naukri, Indeed) must inherit
    from this class and implement the required lifecycle and collection methods.
    This guarantees that the core pipeline can query any source without changing
    pipeline code.
    """

    def __init__(self, is_enabled: bool = True):
        self.is_enabled = is_enabled
        self.last_status: str = "IDLE"
        self.last_error: Optional[str] = None
        self.last_collected_count: int = 0

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifier name of the source (e.g. 'linkedin', 'naukri')."""
        pass

    async def setup(self) -> None:
        """Initialize source resources (e.g. browser context, session).
        Subclasses may override this.
        """
        logger.debug("Setting up source connector: %s", self.source_name)

    async def teardown(self) -> None:
        """Release source resources (e.g. close browser tabs, close session).
        Subclasses may override this.
        """
        logger.debug("Tearing down source connector: %s", self.source_name)

    @abstractmethod
    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Collect job listings for given roles and locations up to max_results.

        Args:
            roles: List of target job role titles or queries.
            locations: List of target locations or 'Remote'.
            max_results: Maximum number of raw listings to attempt collecting.

        Returns:
            List of standardized Job objects.
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.source_name!r} enabled={self.is_enabled}>"
