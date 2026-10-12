"""Comprehensive, read-only data integrity auditor for SQLite job database."""

import argparse
from datetime import date, datetime
from pathlib import Path
import sqlite3
import sys
from typing import Any, Optional
from urllib.parse import urlparse

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import get_settings
from app.models.job import JobStatus
from app.models.resume import PreparationStatus


VALID_STATUSES = {s.value for s in JobStatus}
APPLICATION_STATUSES = {"APPLIED", "INTERVIEW", "OFFER"}
VALID_INTERVIEW_STATUSES = {"NOT_SCHEDULED", "SCHEDULED", "COMPLETED", "PASSED", "FAILED", "RESCHEDULED", "CANCELLED"}
VALID_INTERVIEW_PREP_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "COMPLETED"}
VALID_RESUME_PREP_STATUSES = {s.value for s in PreparationStatus}


def audit_database(db_path: Optional[Path] = None) -> dict[str, Any]:
    """Perform a comprehensive read-only data integrity audit on the database.

    Returns:
        Structured dictionary of findings, metrics, and anomaly logs.
    """
    settings = get_settings()
    target_path = (db_path or settings.DATABASE_PATH).resolve()

    if not target_path.exists():
        raise FileNotFoundError(f"Database file not found: {target_path}")

    anomalies: list[dict[str, Any]] = []
    historical_notes: list[dict[str, Any]] = []
    today = date.today().isoformat()

    with sqlite3.connect(f"file:{target_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. Total counts
        cur.execute("SELECT COUNT(*) FROM jobs;")
        total_jobs = cur.fetchone()[0]

        cur.execute("SELECT * FROM jobs;")
        all_jobs = cur.fetchall()

        # 2. Duplicate Detection
        fingerprints = {}
        source_job_ids = {}
        for row in all_jobs:
            jid = row["id"]
            fp = row["fingerprint"]
            src = row["source"]
            src_id = row["source_job_id"]

            if fp:
                if fp in fingerprints:
                    anomalies.append({
                        "job_id": jid,
                        "type": "DUPLICATE_FINGERPRINT",
                        "severity": "HIGH",
                        "message": f"Job {jid} shares fingerprint with Job {fingerprints[fp]}",
                    })
                else:
                    fingerprints[fp] = jid

            if src_id:
                key = (src, src_id)
                if key in source_job_ids:
                    anomalies.append({
                        "job_id": jid,
                        "type": "DUPLICATE_SOURCE_JOB_ID",
                        "severity": "HIGH",
                        "message": f"Job {jid} shares source ID '{src_id}' on '{src}' with Job {source_job_ids[key]}",
                    })
                else:
                    source_job_ids[key] = jid

        # 3. Row-by-Row Checks
        valid_applications_count = 0
        scheduled_interviews_count = 0
        overdue_followups_count = 0

        for row in all_jobs:
            jid = row["id"]
            title = row["title"] or ""
            company = row["company"] or ""
            url = row["url"] or ""
            status = row["status"] or ""
            applied_at = row["applied_at"]
            match_score = row["match_score"]
            readiness_score = row["application_readiness_score"]
            resume_score = row["resume_alignment_score"]
            prep_status = row["preparation_status"]
            interview_status = row["interview_status"]
            interview_date = row["interview_date"]
            interview_prep = row["interview_preparation_status"]
            follow_up_date = row["follow_up_date"]
            follow_up_notes = row["follow_up_notes"]

            # Required fields
            if not title.strip():
                anomalies.append({"job_id": jid, "type": "MISSING_FIELD", "severity": "HIGH", "message": "Missing title"})
            if not company.strip():
                anomalies.append({"job_id": jid, "type": "MISSING_FIELD", "severity": "HIGH", "message": "Missing company"})
            if not url.strip():
                anomalies.append({"job_id": jid, "type": "MISSING_FIELD", "severity": "HIGH", "message": "Missing URL"})
            if not row["date_found"]:
                anomalies.append({"job_id": jid, "type": "MISSING_FIELD", "severity": "HIGH", "message": "Missing date_found"})
            if not row["fingerprint"]:
                anomalies.append({"job_id": jid, "type": "MISSING_FIELD", "severity": "HIGH", "message": "Missing fingerprint"})

            # URL validation (syntactic, no network requests)
            if url:
                parsed = urlparse(url)
                if not parsed.scheme or parsed.scheme not in ("http", "https") or not parsed.netloc:
                    anomalies.append({
                        "job_id": jid,
                        "type": "INVALID_URL",
                        "severity": "MEDIUM",
                        "message": f"Malformed or non-HTTP URL: {url}",
                    })

            # Status validation
            if status not in VALID_STATUSES:
                anomalies.append({
                    "job_id": jid,
                    "type": "INVALID_STATUS",
                    "severity": "HIGH",
                    "message": f"Status '{status}' not in recognized JobStatus set",
                })

            # Application Lifecycle Consistency
            is_application = status in APPLICATION_STATUSES
            if is_application:
                valid_applications_count += 1

            if applied_at and not is_application:
                historical_notes.append({
                    "job_id": jid,
                    "type": "HISTORICAL_APPLIED_TIMESTAMP",
                    "severity": "INFO",
                    "message": f"Job has historical applied_at timestamp ({applied_at}) but current status is '{status}'",
                })

            # Score ranges 0-100
            for score_val, score_name in [
                (match_score, "match_score"),
                (readiness_score, "application_readiness_score"),
                (resume_score, "resume_alignment_score"),
            ]:
                if score_val is not None:
                    if score_val < 0 or score_val > 100:
                        anomalies.append({
                            "job_id": jid,
                            "type": "INVALID_SCORE",
                            "severity": "HIGH",
                            "message": f"{score_name} value {score_val} is outside [0, 100] range",
                        })

            # Resume Prep Status
            if prep_status and prep_status not in VALID_RESUME_PREP_STATUSES:
                anomalies.append({
                    "job_id": jid,
                    "type": "INVALID_PREP_STATUS",
                    "severity": "LOW",
                    "message": f"Unknown preparation_status '{prep_status}'",
                })

            # Interview Consistency
            if interview_status and interview_status not in VALID_INTERVIEW_STATUSES:
                anomalies.append({
                    "job_id": jid,
                    "type": "INVALID_INTERVIEW_STATUS",
                    "severity": "MEDIUM",
                    "message": f"Unknown interview_status '{interview_status}'",
                })

            if interview_date and (not interview_status or interview_status == "NOT_SCHEDULED"):
                anomalies.append({
                    "job_id": jid,
                    "type": "INTERVIEW_INCONSISTENCY",
                    "severity": "MEDIUM",
                    "message": f"Interview date present ({interview_date}) but status is '{interview_status}'",
                })

            if interview_status in ("SCHEDULED", "COMPLETED", "PASSED") and status not in ("INTERVIEW", "APPLIED", "OFFER"):
                anomalies.append({
                    "job_id": jid,
                    "type": "INTERVIEW_INCONSISTENCY",
                    "severity": "MEDIUM",
                    "message": f"Active interview status '{interview_status}' on non-interview lifecycle job '{status}'",
                })

            if interview_prep == "COMPLETED" and not (is_application or interview_status != "NOT_SCHEDULED"):
                anomalies.append({
                    "job_id": jid,
                    "type": "INTERVIEW_PREP_INCONSISTENCY",
                    "severity": "LOW",
                    "message": "Interview prep COMPLETED without active application or scheduled interview",
                })

            if interview_status == "SCHEDULED":
                scheduled_interviews_count += 1

            # Follow-up Consistency
            if follow_up_date:
                if status in ("REJECTED", "ARCHIVED"):
                    anomalies.append({
                        "job_id": jid,
                        "type": "FOLLOW_UP_INCONSISTENCY",
                        "severity": "LOW",
                        "message": f"Follow-up date present on terminal lifecycle job status '{status}'",
                    })
                if follow_up_date < today and is_application:
                    overdue_followups_count += 1

            if follow_up_notes and not follow_up_date:
                historical_notes.append({
                    "job_id": jid,
                    "type": "FOLLOW_UP_NOTE_WITHOUT_DATE",
                    "severity": "INFO",
                    "message": f"Job has follow-up notes but no follow_up_date set",
                })

    return {
        "status": "PASS" if not any(a["severity"] == "HIGH" for a in anomalies) else "FAIL",
        "database_path": str(target_path),
        "total_jobs": total_jobs,
        "valid_applications": valid_applications_count,
        "scheduled_interviews": scheduled_interviews_count,
        "overdue_followups": overdue_followups_count,
        "anomalies_count": len(anomalies),
        "anomalies": anomalies,
        "historical_notes_count": len(historical_notes),
        "historical_notes": historical_notes,
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only SQLite job database integrity audit.")
    parser.add_argument("--database", type=Path, default=None, help="Path to database file to audit.")
    args = parser.parse_args()

    try:
        report = audit_database(args.database)
        print("==================================================")
        print("SQLite Database Integrity Audit Report")
        print("==================================================")
        print(f"Database:              {report['database_path']}")
        print(f"Overall Status:        {report['status']}")
        print(f"Total Jobs:            {report['total_jobs']}")
        print(f"Active Applications:   {report['valid_applications']} (status in APPLIED, INTERVIEW, OFFER)")
        print(f"Scheduled Interviews:  {report['scheduled_interviews']}")
        print(f"Overdue Follow-ups:    {report['overdue_followups']}")
        print(f"Integrity Anomalies:   {report['anomalies_count']}")
        print(f"Historical Notes:      {report['historical_notes_count']}")
        print("==================================================")

        if report["anomalies"]:
            print("\nIntegrity Anomalies:")
            for a in report["anomalies"]:
                print(f"  [{a['severity']}] Job {a['job_id']}: {a['type']} - {a['message']}")

        if report["historical_notes"]:
            print("\nHistorical Information Notes:")
            for h in report["historical_notes"]:
                print(f"  [{h['severity']}] Job {h['job_id']}: {h['type']} - {h['message']}")

        print("==================================================")
        sys.exit(0 if report["status"] == "PASS" else 1)
    except Exception as exc:
        print(f"[ERROR] Audit failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
