"""FastAPI application factory and configuration for Job Review Dashboard."""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config.settings import get_settings

current_dir = Path(__file__).resolve().parent
templates_dir = current_dir / "templates"
static_dir = current_dir / "static"

app = FastAPI(
    title="Job Review Dashboard",
    description="Personal local job review and application tracking UI",
    version="1.0.0",
)

# Ensure static and template directories exist
templates_dir.mkdir(parents=True, exist_ok=True)
static_dir.mkdir(parents=True, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize Jinja2 templates
templates = Jinja2Templates(directory=str(templates_dir))


def format_datetime_filter(value: Any, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Format datetime object or ISO string for display."""
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime(fmt)
        except Exception:
            return value[:16] if len(value) >= 16 else value
    return str(value)


def score_badge_class_filter(score: Optional[int]) -> str:
    """Return CSS class for score badge based on numerical match score."""
    if score is None:
        return "badge-score-none"
    if score >= 90:
        return "badge-score-excellent"
    if score >= 80:
        return "badge-score-strong"
    if score >= 70:
        return "badge-score-good"
    if score >= 60:
        return "badge-score-possible"
    return "badge-score-low"


def status_badge_class_filter(status: Any) -> str:
    """Return CSS class for application status badge."""
    st = str(status.value if hasattr(status, "value") else (status or "")).upper()
    mapping = {
        "NEW": "badge-status-new",
        "VIEWED": "badge-status-viewed",
        "SHORTLISTED": "badge-status-shortlisted",
        "APPLIED": "badge-status-applied",
        "INTERVIEW": "badge-status-interview",
        "OFFER": "badge-status-offer",
        "REJECTED": "badge-status-rejected",
        "NOT_INTERESTED": "badge-status-not-interested",
    }
    return mapping.get(st, "badge-status-default")


def priority_badge_class_filter(priority: Any) -> str:
    """Return CSS class for application priority badge."""
    prio = str(priority.value if hasattr(priority, "value") else (priority or "")).upper()
    mapping = {
        "URGENT": "badge-priority-urgent",
        "HIGH": "badge-priority-high",
        "NORMAL": "badge-priority-normal",
        "LOW": "badge-priority-low",
        "SKIP": "badge-priority-skip",
    }
    return mapping.get(prio, "badge-priority-normal")


def readiness_badge_class_filter(score: Optional[int]) -> str:
    """Return CSS class for application readiness score badge."""
    if score is None:
        return "badge-score-none"
    if score >= 85:
        return "badge-score-excellent"
    if score >= 75:
        return "badge-score-strong"
    if score >= 60:
        return "badge-score-good"
    if score >= 45:
        return "badge-score-possible"
    return "badge-score-low"


# Register custom filters
templates.env.filters["format_datetime"] = format_datetime_filter
templates.env.filters["score_badge_class"] = score_badge_class_filter
templates.env.filters["status_badge_class"] = status_badge_class_filter
templates.env.filters["priority_badge_class"] = priority_badge_class_filter
templates.env.filters["readiness_badge_class"] = readiness_badge_class_filter
templates.env.filters["resume_badge_class"] = readiness_badge_class_filter

# Import and attach router
from app.dashboard.routes import router  # noqa: E402
app.include_router(router)
