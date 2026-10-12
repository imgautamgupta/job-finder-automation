"""Job tracking service for querying and updating job application statuses and notes."""

import logging
from typing import Any, Optional, Union

from app.database.database import DatabaseManager
from app.models.job import Job, JobStatus

logger = logging.getLogger(__name__)


class JobTracker:
    """Manages job status tracking and user notes in the SQLite database."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def get_status(self, job_id: int) -> Optional[JobStatus]:
        """Retrieve the current JobStatus for a job by ID.

        Args:
            job_id: Database primary key ID.

        Returns:
            JobStatus enum member if job exists, None otherwise.
        """
        job = self.db.get_job_by_id(job_id)
        if not job:
            return None
        return job.status

    def get_job(self, job_id: int) -> Optional[Job]:
        """Retrieve full Job details by ID."""
        return self.db.get_job_by_id(job_id)

    def update_status(
        self,
        job_id: int,
        status: Union[JobStatus, str],
        notes: Optional[str] = None,
    ) -> bool:
        """Update the tracking status of a job.

        Validates the status against JobStatus enum.
        Sets status_updated_at to current timestamp.
        Leaves first_seen_at and last_seen_at unchanged.

        Args:
            job_id: Database primary key ID.
            status: JobStatus enum or valid status string.
            notes: Optional note text to attach with this status update.

        Returns:
            True if updated successfully, False if job not found.

        Raises:
            ValueError: If status is not a valid JobStatus member.
        """
        success = self.db.update_job_status(job_id=job_id, status=status, notes=notes)
        if success:
            logger.info("Updated job %d status to %s", job_id, status)
        else:
            logger.warning("Failed to update status: job %d not found", job_id)
        return success

    def update_notes(self, job_id: int, notes: str) -> bool:
        """Update persistent user notes for a job.

        Args:
            job_id: Database primary key ID.
            notes: Note text string.

        Returns:
            True if updated successfully, False if job not found.
        """
        success = self.db.update_job_notes(job_id=job_id, notes=notes)
        if success:
            logger.info("Updated notes for job %d", job_id)
        else:
            logger.warning("Failed to update notes: job %d not found", job_id)
        return success

    def update_follow_up(
        self,
        job_id: int,
        follow_up_date: Optional[str] = None,
        follow_up_notes: Optional[str] = None,
    ) -> bool:
        """Update follow-up due date and notes for a job.

        Args:
            job_id: Database primary key ID.
            follow_up_date: Follow-up target date string (YYYY-MM-DD).
            follow_up_notes: Optional follow-up note text.

        Returns:
            True if updated successfully, False if job not found.
        """
        success = self.db.update_job_follow_up(
            job_id=job_id,
            follow_up_date=follow_up_date,
            follow_up_notes=follow_up_notes,
        )
        if success:
            logger.info("Updated follow-up for job %d (date=%s)", job_id, follow_up_date)
        else:
            logger.warning("Failed to update follow-up: job %d not found", job_id)
        return success

    def get_upcoming_follow_ups(self, limit: int = 10):
        """Retrieve upcoming and due follow-ups."""
        return self.db.get_upcoming_follow_ups(limit=limit)

    def update_preparation_status(
        self,
        job_id: int,
        status: Any,
        notes: Optional[str] = None,
    ) -> bool:
        """Update Phase 10 preparation status and optionally notes for a job.

        Args:
            job_id: Database primary key ID.
            status: PreparationStatus enum member or valid status string.
            notes: Optional updated preparation notes.

        Returns:
            True if updated successfully, False if job not found.
        """
        success = self.db.update_preparation_status(job_id=job_id, status=status, notes=notes)
        if success:
            logger.info("Updated job %d preparation status to %s", job_id, status)
        else:
            logger.warning("Failed to update preparation status: job %d not found", job_id)
        return success

    def update_preparation_notes(self, job_id: int, notes: str) -> bool:
        """Update Phase 10 preparation notes for a job.

        Args:
            job_id: Database primary key ID.
            notes: Preparation notes text string.

        Returns:
            True if updated successfully, False if job not found.
        """
        success = self.db.update_preparation_notes(job_id=job_id, notes=notes)
        if success:
            logger.info("Updated preparation notes for job %d", job_id)
        else:
            logger.warning("Failed to update preparation notes: job %d not found", job_id)
        return success

    def update_interview(
        self,
        job_id: int,
        interview_date: Optional[str] = None,
        interview_stage: Optional[str] = None,
        interview_status: Optional[str] = None,
        interview_notes: Optional[str] = None,
        interview_preparation_status: Optional[str] = None,
    ) -> bool:
        """Update Phase 11 interview tracking fields for a job."""
        success = self.db.update_interview(
            job_id=job_id,
            interview_date=interview_date,
            interview_stage=interview_stage,
            interview_status=interview_status,
            interview_notes=interview_notes,
            interview_preparation_status=interview_preparation_status,
        )
        if success:
            logger.info("Updated interview details for job %d", job_id)
        else:
            logger.warning("Failed to update interview details: job %d not found", job_id)
        return success

    def update_interview_prep_status(self, job_id: int, status: str, notes: Optional[str] = None) -> bool:
        """Update interview preparation status and optional notes."""
        success = self.db.update_interview_prep_status(job_id=job_id, status=status, notes=notes)
        if success:
            logger.info("Updated interview preparation status for job %d to %s", job_id, status)
        else:
            logger.warning("Failed to update interview prep status: job %d not found", job_id)
        return success

    def get_daily_actions(self, limit: int = 50):
        """Retrieve prioritized daily actions for the 'What should I work on today?' plan."""
        return self.db.get_daily_actions(limit=limit)

    def get_applications_pipeline_counts(self):
        """Retrieve count breakdown of jobs by application pipeline stage."""
        return self.db.get_applications_pipeline_counts()

    def get_applications_filtered(self, **kwargs):
        """Query applications with Command Center filters and sorting."""
        return self.db.get_applications_filtered(**kwargs)

    def get_follow_ups_summary(self):
        """Retrieve categorized summary of follow-ups (due today, overdue, upcoming)."""
        counts = self.db.get_dashboard_counts()
        return {
            "due": counts.get("follow_ups_due", 0),
            "due_today": counts.get("follow_ups_due_today", 0),
            "overdue": counts.get("overdue_follow_ups", 0),
            "upcoming": counts.get("upcoming_follow_ups", 0),
            "items": self.db.get_upcoming_follow_ups(limit=25),
        }

    def get_analytics_report(self, **kwargs):
        """Retrieve complete Phase 12 analytics report."""
        from app.config.settings import Settings
        from app.services.analytics import AnalyticsService
        try:
            settings = Settings()
            profile = settings.load_profile()
        except Exception:
            profile = None
        svc = AnalyticsService(self.db, profile)
        return svc.get_report(**kwargs)


