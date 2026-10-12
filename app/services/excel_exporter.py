"""Production-ready Excel export service creating structured, styled multi-sheet job workbooks."""

from datetime import datetime
import logging
from pathlib import Path
from typing import List, Optional, Union

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models.job import Job, JobStatus

logger = logging.getLogger(__name__)

# Column headers: Phase 5 original 17 columns preserved in order, tracking columns appended
REPORT_COLUMNS = [
    "Priority",
    "Match Score",
    "Match Category",
    "Company",
    "Job Title",
    "Location",
    "Source",
    "Easy Apply",
    "Date Posted",
    "Date Found",
    "Job URL",
    "Matched Roles",
    "Matched Skills",
    "Matched Locations",
    "Experience Match",
    "Excluded Reasons",
    "Notes",
    "Status",
    "First Seen",
    "Last Seen",
    "Application Readiness",
    "Application Priority",
    "Profile Alignment",
    "Missing Skills",
    "Recommendation Reasons",
    "Risk Reasons",
    "Follow-up Date",
    "Resume Alignment",
    "Resume Alignment Category",
    "Skills to Emphasize",
    "Missing Resume Keywords",
    "Recommended Project",
    "Recommended Experience",
    "Resume Concerns",
    "Recommended Resume",
    "Preparation Status",
    "Applied At",
    "Interview Date",
    "Interview Stage",
    "Interview Status",
    "Interview Prep Status",
    "Interview Notes",
]


def get_priority(score: Optional[int]) -> str:
    """Calculate priority level based on match score."""
    if score is None:
        return ""
    if score >= 90:
        return "HIGH"
    elif score >= 80:
        return "MEDIUM"
    elif score >= 60:
        return "NORMAL"
    return ""


def sort_jobs(jobs: List[Job]) -> List[Job]:
    """Sort jobs by:
    1. Match Score descending
    2. Easy Apply first (True before False) when scores are equal
    3. Date Found / Date Posted newest first
    """
    return sorted(
        jobs,
        key=lambda j: (
            -(j.match_score if j.match_score is not None else -1),
            0 if j.easy_apply else 1,
            -(j.date_found.timestamp() if j.date_found else 0),
            j.date_posted or "",
        ),
    )


class ExcelExporter:
    """Exports collected job postings to professional, styled Excel (.xlsx) workbooks."""

    def __init__(self, exports_dir: Union[str, Path] = "data/exports"):
        self.exports_dir = Path(exports_dir)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        jobs: List[Job],
        output_path: Optional[Union[str, Path]] = None,
        current_run_id: Optional[str] = None,
    ) -> Path:
        """Export a list of jobs to an Excel file with 'New Matches', 'Top Matches', and 'All Relevant Jobs' sheets.

        Args:
            jobs: List of Job instances.
            output_path: Optional specific file path. If None, auto-generated with timestamp.
            current_run_id: Optional unique identifier for the current pipeline run.

        Returns:
            Path to the saved Excel file.
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"jobs_{timestamp}.xlsx"
            target_path = self.exports_dir / file_name
        else:
            target_path = Path(output_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.Workbook()

        # Sheet 1: New Matches (score >= 60, newly discovered in current run)
        ws_new = wb.active
        ws_new.title = "New Matches"

        # Sheet 2: Top Matches (score >= 80)
        ws_top = wb.create_sheet(title="Top Matches")

        # Sheet 3: All Relevant Jobs (score >= 60)
        ws_all = wb.create_sheet(title="All Relevant Jobs")

        def is_genuinely_new(job: Job) -> bool:
            if (job.match_score or 0) < 60:
                return False
            if getattr(job, "_is_new_in_run", False):
                return True
            if current_run_id:
                if job.last_seen_run_id == current_run_id:
                    if job.first_seen_at and job.last_seen_at:
                        return abs((job.first_seen_at - job.last_seen_at).total_seconds()) < 60
                    return True
                return False
            if job.first_seen_at and job.last_seen_at:
                return abs((job.first_seen_at - job.last_seen_at).total_seconds()) < 60
            return True

        # Filter & Sort subsets
        new_matches = sort_jobs([j for j in jobs if is_genuinely_new(j)])
        top_matches = sort_jobs([j for j in jobs if (j.match_score or 0) >= 80])
        all_relevant = sort_jobs([j for j in jobs if (j.match_score or 0) >= 60])

        # Sheet 4: Apply Today (actionable recommended jobs)
        ws_apply = wb.create_sheet(title="Apply Today")

        apply_jobs = [
            j for j in jobs
            if (j.application_priority and (j.application_priority.value if hasattr(j.application_priority, "value") else str(j.application_priority)) in ("URGENT", "HIGH", "NORMAL"))
            and j.status not in (JobStatus.APPLIED, JobStatus.REJECTED, JobStatus.NOT_INTERESTED, JobStatus.INTERVIEW, JobStatus.OFFER)
        ]
        apply_sorted = sorted(
            apply_jobs,
            key=lambda j: (
                1 if (j.application_priority.value if hasattr(j.application_priority, "value") else str(j.application_priority)) == "URGENT" else (2 if (j.application_priority.value if hasattr(j.application_priority, "value") else str(j.application_priority)) == "HIGH" else 3),
                -(j.application_readiness_score or 0),
                -(j.match_score or 0),
            )
        )

        # Sheet 5: Resume Preparation (Phase 10)
        ws_prep = wb.create_sheet(title="Resume Preparation")
        prep_jobs = [
            j for j in jobs
            if (
                (j.application_priority and (j.application_priority.value if hasattr(j.application_priority, "value") else str(j.application_priority)) in ("URGENT", "HIGH"))
                or (j.match_score or 0) >= 70
            )
            and j.status not in (JobStatus.APPLIED, JobStatus.REJECTED, JobStatus.NOT_INTERESTED, JobStatus.INTERVIEW, JobStatus.OFFER)
        ]
        prep_sorted = sorted(
            prep_jobs,
            key=lambda j: (
                -(j.resume_alignment_score if j.resume_alignment_score is not None else -1),
                -(j.application_readiness_score if j.application_readiness_score is not None else -1),
                -(j.match_score if j.match_score is not None else -1),
            )
        )

        # Sheet 6: Applications (Phase 11 Command Center)
        ws_apps = wb.create_sheet(title="Applications")
        apps_jobs = [
            j for j in jobs
            if j.status in (JobStatus.APPLIED, JobStatus.INTERVIEW, JobStatus.OFFER, JobStatus.REJECTED, JobStatus.NOT_INTERESTED)
            or j.applied_at is not None
        ]
        apps_sorted = sorted(
            apps_jobs,
            key=lambda j: (
                -(j.applied_at.timestamp() if j.applied_at else 0),
                -(j.match_score or 0),
            ),
        )

        # Sheet 7: Interview Preparation (Phase 11)
        ws_int_prep = wb.create_sheet(title="Interview Preparation")
        int_prep_jobs = [
            j for j in jobs
            if j.status == JobStatus.INTERVIEW
            or j.interview_date is not None
            or (j.interview_status and str(getattr(j.interview_status, "value", j.interview_status)) not in ("", "NOT_SCHEDULED"))
            or (j.status == JobStatus.APPLIED and (j.match_score or 0) >= 70)
        ]
        int_prep_sorted = sorted(
            int_prep_jobs,
            key=lambda j: (
                0 if j.status == JobStatus.INTERVIEW else 1,
                j.interview_date or "9999-99-99",
                -(j.match_score or 0),
            ),
        )

        # Sheet 8: Analytics (Phase 12)
        ws_analytics = wb.create_sheet(title="Analytics")

        # Sheet 9: Search Intelligence (Phase 13)
        ws_search_intel = wb.create_sheet(title="Search Intelligence")

        # Sheet 10: Job Agent (Phase 14)
        ws_job_agent = wb.create_sheet(title="Job Agent")

        # Populate worksheets
        self._populate_sheet(ws_new, new_matches)
        self._populate_sheet(ws_top, top_matches)
        self._populate_sheet(ws_all, all_relevant)
        self._populate_sheet(ws_apply, apply_sorted)
        self._populate_sheet(ws_prep, prep_sorted)
        self._populate_sheet(ws_apps, apps_sorted)
        self._populate_sheet(ws_int_prep, int_prep_sorted)
        self._populate_analytics_sheet(ws_analytics, jobs)
        self._populate_search_intelligence_sheet(ws_search_intel, jobs)
        self._populate_job_agent_sheet(ws_job_agent, jobs)

        # Focus workbook on Top Matches for backward compatibility with existing tests
        wb.active = ws_top

        # Save workbook
        wb.save(str(target_path))
        logger.info(
            "Exported report to %s (New: %d, Top: %d, All: %d, Apply Today: %d, Prep: %d, Apps: %d, IntPrep: %d, Analytics: 1)",
            target_path,
            len(new_matches),
            len(top_matches),
            len(all_relevant),
            len(apply_sorted),
            len(prep_sorted),
            len(apps_sorted),
            len(int_prep_sorted),
        )
        return target_path

    def _populate_sheet(self, ws: openpyxl.worksheet.worksheet.Worksheet, jobs: List[Job]) -> None:
        """Populate and format an individual worksheet."""
        # 1. Styles
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        thin_side = Side(style="thin", color="E2E8F0")
        border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        regular_font = Font(name="Calibri", size=10)
        regular_align = Alignment(vertical="center")
        center_align = Alignment(horizontal="center", vertical="center")
        wrap_align = Alignment(vertical="center", wrap_text=True)

        url_font = Font(name="Calibri", size=10, color="0000FF", underline="single")

        # Score / Priority Highlights
        high_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        high_font = Font(name="Calibri", size=10, bold=True, color="166534")

        med_fill = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")
        med_font = Font(name="Calibri", size=10, bold=True, color="0369A1")

        norm_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        norm_font = Font(name="Calibri", size=10, color="334155")

        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        # 2. Write Headers
        ws.row_dimensions[1].height = 28
        for col_idx, col_name in enumerate(REPORT_COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
            cell.border = border

        # 3. Write Data Rows
        url_col_idx = REPORT_COLUMNS.index("Job URL") + 1
        score_col_idx = REPORT_COLUMNS.index("Match Score") + 1
        priority_col_idx = REPORT_COLUMNS.index("Priority") + 1
        category_col_idx = REPORT_COLUMNS.index("Match Category") + 1
        easy_apply_col_idx = REPORT_COLUMNS.index("Easy Apply") + 1
        status_col_idx = REPORT_COLUMNS.index("Status") + 1
        first_seen_col_idx = REPORT_COLUMNS.index("First Seen") + 1
        last_seen_col_idx = REPORT_COLUMNS.index("Last Seen") + 1

        for row_idx, job in enumerate(jobs, start=2):
            ws.row_dimensions[row_idx].height = 20
            score_val = job.match_score
            priority_str = get_priority(score_val)
            is_even = (row_idx % 2 == 0)

            status_str = job.status.value if isinstance(job.status, JobStatus) else str(job.status or "NEW")
            first_seen_str = job.first_seen_at.strftime("%Y-%m-%d %H:%M:%S") if job.first_seen_at else ""
            last_seen_str = job.last_seen_at.strftime("%Y-%m-%d %H:%M:%S") if job.last_seen_at else ""

            row_data = [
                priority_str,
                score_val if score_val is not None else "",
                job.match_category or "",
                job.company,
                job.title,
                job.location,
                job.source.capitalize(),
                "Yes" if job.easy_apply else "No",
                job.date_posted or "",
                job.date_found.strftime("%Y-%m-%d %H:%M:%S") if job.date_found else "",
                job.url,
                ", ".join(job.matched_roles) if job.matched_roles else "",
                ", ".join(job.matched_skills) if job.matched_skills else "",
                ", ".join(job.matched_locations) if job.matched_locations else "",
                "Yes" if job.experience_match else "No",
                "; ".join(job.excluded_reasons) if job.excluded_reasons else "",
                job.notes or "",
                status_str,
                first_seen_str,
                last_seen_str,
                job.application_readiness_score if job.application_readiness_score is not None else "",
                job.application_priority.value if hasattr(job.application_priority, "value") else (str(job.application_priority) if job.application_priority else ""),
                job.profile_alignment or "",
                ", ".join(job.missing_skills) if job.missing_skills else "",
                "; ".join(job.recommendation_reasons) if job.recommendation_reasons else "",
                "; ".join(job.risk_reasons) if job.risk_reasons else "",
                job.follow_up_date or "",
                job.resume_alignment_score if job.resume_alignment_score is not None else "",
                job.resume_alignment_category or "",
                ", ".join(job.skills_to_emphasize) if job.skills_to_emphasize else "",
                ", ".join(job.resume_missing_keywords) if job.resume_missing_keywords else "",
                job.recommended_project or "",
                job.recommended_experience or "",
                "; ".join(job.resume_concerns) if job.resume_concerns else "",
                job.recommended_resume or "",
                job.preparation_status.value if hasattr(job.preparation_status, "value") else str(job.preparation_status or "NOT_REVIEWED"),
                job.applied_at.strftime("%Y-%m-%d %H:%M:%S") if job.applied_at else "",
                job.interview_date or "",
                job.interview_stage.value if hasattr(job.interview_stage, "value") else (str(job.interview_stage) if job.interview_stage else ""),
                job.interview_status.value if hasattr(job.interview_status, "value") else (str(job.interview_status) if job.interview_status else ""),
                job.interview_preparation_status.value if hasattr(job.interview_preparation_status, "value") else (str(job.interview_preparation_status) if job.interview_preparation_status else ""),
                job.interview_notes or "",
            ]

            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = border
                cell.font = regular_font
                cell.alignment = regular_align

                if is_even:
                    cell.fill = zebra_fill

                # Special Column Stylings
                if col_idx in (priority_col_idx, score_col_idx):
                    cell.alignment = center_align
                    if score_val is not None:
                        if score_val >= 90:
                            cell.fill = high_fill
                            cell.font = high_font
                        elif score_val >= 80:
                            cell.fill = med_fill
                            cell.font = med_font
                        elif score_val >= 60:
                            cell.fill = norm_fill
                            cell.font = norm_font

                elif col_idx in (category_col_idx, easy_apply_col_idx, status_col_idx, first_seen_col_idx, last_seen_col_idx):
                    cell.alignment = center_align

                elif col_idx == url_col_idx:
                    url_str = str(val or "").strip()
                    if url_str.startswith("http"):
                        cell.hyperlink = url_str
                        cell.font = url_font

                elif col_idx in (
                    REPORT_COLUMNS.index("Matched Skills") + 1,
                    REPORT_COLUMNS.index("Excluded Reasons") + 1,
                ):
                    cell.alignment = wrap_align

        # 4. Auto-fit Column Widths with sensible caps
        max_rows = len(jobs) + 1
        for col_idx, col_name in enumerate(REPORT_COLUMNS, start=1):
            col_letter = get_column_letter(col_idx)
            max_len = len(col_name)
            for r_idx in range(2, max_rows + 1):
                v = ws.cell(row=r_idx, column=col_idx).value
                if v is not None:
                    max_len = max(max_len, min(len(str(v)), 45))

            # Set sensible min/max constraints
            min_width = 12
            if col_name in ("Job Title", "Company", "Matched Skills", "Excluded Reasons"):
                min_width = 20
            ws.column_dimensions[col_letter].width = max(max_len + 3, min_width)

        # 5. Usability Enhancements: Freeze header row & Enable AutoFilter
        ws.freeze_panes = "A2"
        max_col_letter = get_column_letter(len(REPORT_COLUMNS))
        filter_bottom = max_rows if max_rows > 1 else 1
        ws.auto_filter.ref = f"A1:{max_col_letter}{filter_bottom}"

    def _populate_analytics_sheet(
        self, ws: openpyxl.worksheet.worksheet.Worksheet, jobs: List[Job]
    ) -> None:
        """Populate Phase 12 Analytics summary sheet in Excel workbook."""
        # Visual Styles
        title_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        title_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        sub_font = Font(name="Calibri", size=10, bold=True, color="1E293B")
        bold_font = Font(name="Calibri", size=10, bold=True)
        regular_font = Font(name="Calibri", size=10)
        center_align = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")
        thin_side = Side(style="thin", color="CBD5E1")
        border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        # Compute Metrics
        total_found = len(jobs)
        relevant_jobs = [j for j in jobs if (j.match_score or 0) >= 60]
        relevant_count = len(relevant_jobs)
        recommended_count = sum(
            1 for j in jobs
            if getattr(getattr(j, "application_priority", None), "value", str(getattr(j, "application_priority", ""))) in ("URGENT", "HIGH", "NORMAL")
        )
        applied_jobs = [
            j for j in jobs
            if j.status in (JobStatus.APPLIED, JobStatus.INTERVIEW, JobStatus.OFFER)
            or j.applied_at is not None
        ]
        applied_count = len(applied_jobs)
        interview_jobs = [
            j for j in jobs
            if j.status == JobStatus.INTERVIEW
            or j.interview_date is not None
            or (j.interview_status and str(getattr(j.interview_status, "value", j.interview_status)) not in ("", "NOT_SCHEDULED"))
        ]
        interview_count = len(interview_jobs)
        offer_count = sum(1 for j in jobs if j.status == JobStatus.OFFER)
        rejected_count = sum(1 for j in jobs if j.status == JobStatus.REJECTED)
        not_interested_count = sum(1 for j in jobs if j.status == JobStatus.NOT_INTERESTED)

        # Conversions
        app_rate = f"{round((applied_count / relevant_count) * 100, 1)}%" if relevant_count > 0 else "N/A"
        rec_to_app_rate = f"{round((applied_count / recommended_count) * 100, 1)}%" if recommended_count > 0 else "N/A"
        int_rate = f"{round((interview_count / applied_count) * 100, 1)}%" if applied_count > 0 else "N/A"
        offer_rate = f"{round((offer_count / applied_count) * 100, 1)}%" if applied_count > 0 else "N/A"
        int_to_offer_rate = f"{round((offer_count / interview_count) * 100, 1)}%" if interview_count > 0 else "N/A"

        row = 1
        # Section 1: Overview Funnel
        headers_1 = ["Pipeline Metric", "Count / Value", "Conversion / Yield", "Definition & Notes"]
        ws.row_dimensions[row].height = 24
        for col_idx, h in enumerate(headers_1, start=1):
            cell = ws.cell(row=row, column=col_idx, value=h)
            cell.fill = title_fill
            cell.font = title_font
            cell.alignment = center_align
            cell.border = border
        row += 1

        funnel_rows = [
            ("1. Jobs Found", total_found, "100.0%", "Total opportunities stored in database"),
            ("2. Relevant Jobs", relevant_count, f"{round((relevant_count/total_found)*100, 1)}% of found" if total_found else "N/A", "Match score >= 60 threshold"),
            ("3. Recommended Jobs", recommended_count, f"{round((recommended_count/relevant_count)*100, 1)}% of relevant" if relevant_count else "N/A", "Priority Urgent / High / Normal"),
            ("4. Manual Applications", applied_count, f"{app_rate} of rel ({rec_to_app_rate} of rec)", "Status is APPLIED, INTERVIEW, or OFFER"),
            ("5. Interviews", interview_count, f"{int_rate} of applied", "Status INTERVIEW or interview scheduled"),
            ("6. Offers", offer_count, f"{offer_rate} of applied ({int_to_offer_rate} of int)", "Status is OFFER"),
            ("Rejected", rejected_count, "—", "Status is REJECTED"),
            ("Not Interested", not_interested_count, "—", "Status is NOT_INTERESTED"),
        ]

        for item in funnel_rows:
            ws.row_dimensions[row].height = 19
            for c_idx, val in enumerate(item, start=1):
                cell = ws.cell(row=row, column=c_idx, value=val)
                cell.font = bold_font if c_idx == 1 else regular_font
                cell.alignment = left_align if c_idx in (1, 4) else center_align
                cell.border = border
                if row % 2 == 0:
                    cell.fill = zebra_fill
            row += 1

        row += 1  # Blank spacing
        # Section 2: Source Performance
        ws.row_dimensions[row].height = 24
        headers_2 = ["Source Connector", "Jobs Found", "Relevant", "Recommended", "Applied", "Interviews", "Relevance Rate", "Application Rate"]
        for col_idx, h in enumerate(headers_2, start=1):
            cell = ws.cell(row=row, column=col_idx, value=h)
            cell.fill = title_fill
            cell.font = title_font
            cell.alignment = center_align
            cell.border = border
        row += 1

        source_groups: Dict[str, Dict[str, int]] = {}
        for j in jobs:
            s_name = (j.source or "unknown").capitalize()
            if s_name not in source_groups:
                source_groups[s_name] = {"found": 0, "relevant": 0, "rec": 0, "applied": 0, "int": 0}
            source_groups[s_name]["found"] += 1
            if (j.match_score or 0) >= 60:
                source_groups[s_name]["relevant"] += 1
            prio = getattr(getattr(j, "application_priority", None), "value", str(getattr(j, "application_priority", "")))
            if prio in ("URGENT", "HIGH", "NORMAL"):
                source_groups[s_name]["rec"] += 1
            if j.status in (JobStatus.APPLIED, JobStatus.INTERVIEW, JobStatus.OFFER) or j.applied_at is not None:
                source_groups[s_name]["applied"] += 1
            if j.status == JobStatus.INTERVIEW or (j.interview_status and str(getattr(j.interview_status, "value", j.interview_status)) not in ("", "NOT_SCHEDULED")):
                source_groups[s_name]["int"] += 1

        for s_name, counts in sorted(source_groups.items(), key=lambda x: x[1]["found"], reverse=True):
            ws.row_dimensions[row].height = 19
            rel_p = f"{round((counts['relevant'] / counts['found']) * 100, 1)}%" if counts["found"] > 0 else "N/A"
            app_p = f"{round((counts['applied'] / counts['relevant']) * 100, 1)}%" if counts["relevant"] > 0 else "N/A"
            s_row = [s_name, counts["found"], counts["relevant"], counts["rec"], counts["applied"], counts["int"], rel_p, app_p]
            for c_idx, val in enumerate(s_row, start=1):
                cell = ws.cell(row=row, column=c_idx, value=val)
                cell.font = bold_font if c_idx == 1 else regular_font
                cell.alignment = left_align if c_idx == 1 else center_align
                cell.border = border
                if row % 2 == 0:
                    cell.fill = zebra_fill
            row += 1

        row += 1
        # Section 3: Match Score Performance
        ws.row_dimensions[row].height = 24
        headers_3 = ["Match Score Tier", "Jobs Count", "Applied", "Interviews", "Offers", "Interview Rate"]
        for col_idx, h in enumerate(headers_3, start=1):
            cell = ws.cell(row=row, column=col_idx, value=h)
            cell.fill = title_fill
            cell.font = title_font
            cell.alignment = center_align
            cell.border = border
        row += 1

        tiers = [
            ("90–100 (Excellent)", lambda s: s >= 90),
            ("80–89 (Strong)", lambda s: 80 <= s < 90),
            ("70–79 (Good)", lambda s: 70 <= s < 80),
            ("60–69 (Possible)", lambda s: 60 <= s < 70),
            ("Below 60 (Not Relevant)", lambda s: s < 60),
        ]
        for t_name, fn in tiers:
            tier_jobs = [j for j in jobs if fn(j.match_score or 0)]
            t_app = sum(1 for j in tier_jobs if j.status in (JobStatus.APPLIED, JobStatus.INTERVIEW, JobStatus.OFFER) or j.applied_at is not None)
            t_int = sum(1 for j in tier_jobs if j.status == JobStatus.INTERVIEW or (j.interview_status and str(getattr(j.interview_status, "value", j.interview_status)) not in ("", "NOT_SCHEDULED")))
            t_off = sum(1 for j in tier_jobs if j.status == JobStatus.OFFER)
            t_rate = f"{round((t_int / t_app) * 100, 1)}%" if t_app > 0 else "N/A"

            ws.row_dimensions[row].height = 19
            t_row = [t_name, len(tier_jobs), t_app, t_int, t_off, t_rate]
            for c_idx, val in enumerate(t_row, start=1):
                cell = ws.cell(row=row, column=c_idx, value=val)
                cell.font = bold_font if c_idx == 1 else regular_font
                cell.alignment = left_align if c_idx == 1 else center_align
                cell.border = border
                if row % 2 == 0:
                    cell.fill = zebra_fill
            row += 1

        # Auto-adjust column widths for Analytics sheet
        for col_idx in range(1, 9):
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = 24
        ws.freeze_panes = "A2"

    def _populate_search_intelligence_sheet(self, ws, jobs: List[Job]) -> None:
        """Populate Phase 13 Search Intelligence worksheet with deterministic strategy and metrics."""
        from app.services.search_intelligence import SearchIntelligenceService

        # Convert jobs to dictionary format
        job_dicts = []
        for j in jobs:
            if hasattr(j, "model_dump"):
                d = j.model_dump()
            elif isinstance(j, dict):
                d = dict(j)
            else:
                d = {
                    "id": getattr(j, "id", None),
                    "title": getattr(j, "title", ""),
                    "company": getattr(j, "company", ""),
                    "location": getattr(j, "location", ""),
                    "source": getattr(j, "source", ""),
                    "match_score": getattr(j, "match_score", 0),
                    "application_priority": getattr(j, "application_priority", None),
                    "status": getattr(j, "status", None),
                    "applied_at": getattr(j, "applied_at", None),
                    "interview_date": getattr(j, "interview_date", None),
                    "interview_status": getattr(j, "interview_status", None),
                    "application_readiness_score": getattr(j, "application_readiness_score", 0),
                    "resume_alignment_score": getattr(j, "resume_alignment_score", 0),
                    "matched_roles": getattr(j, "matched_roles", None),
                    "matched_locations": getattr(j, "matched_locations", None),
                }
            for enum_k in ("status", "application_priority", "interview_status"):
                val = d.get(enum_k)
                if hasattr(val, "value"):
                    d[enum_k] = val.value
            job_dicts.append(d)

        intel_service = SearchIntelligenceService(db=None)
        report = intel_service.get_search_intelligence_report(jobs=job_dicts)

        title_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        section_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        title_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        section_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        bold_font = Font(name="Calibri", size=10, bold=True)
        regular_font = Font(name="Calibri", size=10)
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
        thin_side = Side(style="thin", color="CBD5E1")
        border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        row = 1
        # Section 1: Search Strategy Header
        ws.row_dimensions[row].height = 24
        strategy_headers = ["Strategy Element", "Value / Rating", "Context & Guidance"]
        for c_idx, h in enumerate(strategy_headers, start=1):
            cell = ws.cell(row=row, column=c_idx, value=h)
            cell.fill = section_fill
            cell.font = section_font
            cell.alignment = center_align
            cell.border = border
        row += 1

        strategy_rows = [
            ("Search Strategy Status", report.strategy.overall_status.value, "Current operational health of job discovery"),
            ("Data Confidence", report.strategy.data_confidence.value, "Statistical protection against small-dataset overfitting"),
            ("Strategy Summary", report.strategy.summary, "High-level deterministic evaluation"),
            ("Recommended Key Actions", "; ".join(report.strategy.key_actions), "Operational guidance for future runs"),
            ("Warnings & Limitations", "; ".join(report.strategy.warnings) if report.strategy.warnings else "None", "Active operational constraints"),
        ]

        for s_item in strategy_rows:
            ws.row_dimensions[row].height = 20
            for c_idx, val in enumerate(s_item, start=1):
                cell = ws.cell(row=row, column=c_idx, value=val)
                cell.font = bold_font if c_idx == 1 else regular_font
                cell.alignment = left_align
                cell.border = border
                if row % 2 == 0:
                    cell.fill = zebra_fill
            row += 1

        # Priority Corridor Sub-rows
        ws.row_dimensions[row].height = 20
        cell_p = ws.cell(row=row, column=1, value="Top Ranked Search Priorities")
        cell_p.font = bold_font
        cell_p.border = border
        cell_pv = ws.cell(row=row, column=2, value=" | ".join(report.strategy.ranked_priorities[:3]))
        cell_pv.font = regular_font
        cell_pv.border = border
        cell_pc = ws.cell(row=row, column=3, value="Ranked combination corridors for next daily collection")
        cell_pc.font = regular_font
        cell_pc.border = border
        row += 2  # Spacing

        # Section 2: Detailed Search Recommendations Table
        ws.row_dimensions[row].height = 24
        rec_headers = [
            "Recommendation Type",
            "Source",
            "Role",
            "Location",
            "Jobs Found",
            "Relevant Jobs",
            "Recommended Jobs",
            "Average Match",
            "Average Readiness",
            "Confidence",
            "Recommendation",
            "Explanation",
        ]
        for c_idx, h in enumerate(rec_headers, start=1):
            cell = ws.cell(row=row, column=c_idx, value=h)
            cell.fill = title_fill
            cell.font = title_font
            cell.alignment = center_align
            cell.border = border
        row += 1

        rec_table_data = []

        # 1. Sources
        for s in report.sources:
            rec_table_data.append([
                "SOURCE",
                s.source,
                "All Configured Roles",
                "Preferred Corridors",
                s.jobs_found,
                s.relevant_jobs,
                s.recommended_jobs,
                "—",
                "—",
                s.confidence.value,
                s.recommendation.value,
                s.recommendation_reason,
            ])

        # 2. Roles (Top 5)
        for r in report.roles[:5]:
            rec_table_data.append([
                "ROLE",
                "All Sources",
                r.role_name,
                "All Locations",
                r.jobs_found,
                r.relevant_jobs,
                r.recommended_jobs,
                r.avg_match_score if r.avg_match_score is not None else "—",
                r.avg_readiness_score if r.avg_readiness_score is not None else "—",
                r.confidence.value,
                r.priority.value,
                r.notes,
            ])

        # 3. Locations
        for loc in report.locations:
            rec_table_data.append([
                "LOCATION",
                "All Sources",
                "All Target Roles",
                loc.location_name,
                loc.jobs_found,
                loc.relevant_jobs,
                loc.recommended_jobs,
                loc.avg_match_score if loc.avg_match_score is not None else "—",
                loc.avg_readiness_score if loc.avg_readiness_score is not None else "—",
                loc.confidence.value,
                loc.priority.value,
                loc.notes,
            ])

        # 4. Top Role × Location Combinations
        for rl in report.role_locations[:5]:
            rec_table_data.append([
                "ROLE_LOCATION",
                "All Sources",
                rl.role_name,
                rl.location_name,
                rl.jobs_found,
                rl.relevant_jobs,
                rl.recommended_jobs,
                rl.avg_match_score if rl.avg_match_score is not None else "—",
                rl.avg_readiness_score if rl.avg_readiness_score is not None else "—",
                rl.confidence.value,
                rl.priority.value,
                rl.status_label,
            ])

        # 5. Search Coverage Gaps
        for gap in report.search_gaps:
            rec_table_data.append([
                "SEARCH_GAP",
                "All Sources",
                gap.item_name if gap.gap_type.value == "ROLE_GAP" else "—",
                gap.item_name if gap.gap_type.value == "LOCATION_GAP" else "—",
                0,
                0,
                0,
                "—",
                "—",
                "INSUFFICIENT_DATA",
                "MONITOR",
                f"{gap.details} {gap.suggestion}",
            ])

        # 6. Budget Allocations
        for b in report.budget_allocations:
            rec_table_data.append([
                "SEARCH_BUDGET",
                b.source,
                "—",
                "—",
                "—",
                "—",
                "—",
                "—",
                "—",
                b.confidence.value,
                f"{b.allocated_percentage}% Effort",
                b.basis,
            ])

        for item in rec_table_data:
            ws.row_dimensions[row].height = 20
            for c_idx, val in enumerate(item, start=1):
                cell = ws.cell(row=row, column=c_idx, value=val)
                cell.font = bold_font if c_idx in (1, 11) else regular_font
                cell.alignment = left_align if c_idx in (1, 2, 3, 4, 11, 12) else center_align
                cell.border = border
                if row % 2 == 0:
                    cell.fill = zebra_fill
            row += 1

        # Adjust column dimensions
        col_widths = {
            1: 22,   # Recommendation Type
            2: 18,   # Source
            3: 26,   # Role
            4: 26,   # Location
            5: 14,   # Jobs Found
            6: 14,   # Relevant Jobs
            7: 18,   # Recommended Jobs
            8: 16,   # Avg Match
            9: 16,   # Avg Readiness
            10: 20,  # Confidence
            11: 24,  # Recommendation
            12: 45,  # Explanation
        }
        for col_idx, width in col_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        ws.freeze_panes = "A9"

    def _populate_job_agent_sheet(self, ws: openpyxl.worksheet.worksheet.Worksheet, jobs: List[Job]) -> None:
        """Populate Phase 14 Job Agent daily action plan worksheet."""
        from datetime import date
        from app.models.job_agent import AgentActionPriority
        from app.services.job_agent import JobAgentService

        agent_service = JobAgentService()
        today_str = date.today().isoformat()

        # Generate actions deterministically from passed jobs
        actions = []
        actions.extend(agent_service._generate_follow_up_actions(jobs, today_str))
        actions.extend(agent_service._generate_interview_actions(jobs, today_str))
        actions.extend(agent_service._generate_application_and_prep_actions(jobs))
        actions.extend(agent_service._generate_system_and_search_actions(5, 0, None))

        def sort_key(act):
            prio_order = {
                AgentActionPriority.URGENT: 0,
                AgentActionPriority.HIGH: 1,
                AgentActionPriority.MEDIUM: 2,
                AgentActionPriority.LOW: 3,
            }
            score = agent_service._calculate_action_score(act, today_str)
            return (prio_order.get(act.priority, 4), -score)

        sorted_actions = sorted(actions, key=sort_key)

        # Styles
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        thin_side = Side(style="thin", color="E2E8F0")
        border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        regular_font = Font(name="Calibri", size=10)
        center_align = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")
        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        urgent_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        urgent_font = Font(name="Calibri", size=10, bold=True, color="991B1B")

        high_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
        high_font = Font(name="Calibri", size=10, bold=True, color="92400E")

        med_fill = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")
        med_font = Font(name="Calibri", size=10, bold=True, color="0369A1")

        headers = [
            "Action Priority",
            "Action Type",
            "Job",
            "Company",
            "Match Score",
            "Readiness",
            "Resume Alignment",
            "Lifecycle Status",
            "Due Date",
            "Recommended Action",
            "Reason",
        ]

        ws.row_dimensions[1].height = 28
        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=c_idx, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
            cell.border = border

        for row_idx, act in enumerate(sorted_actions, start=2):
            ws.row_dimensions[row_idx].height = 22
            row_data = [
                act.priority.value if hasattr(act.priority, "value") else str(act.priority),
                act.action_type.value if hasattr(act.action_type, "value") else str(act.action_type),
                act.job_title or "—",
                act.company or "—",
                act.match_score if act.match_score is not None else "—",
                act.readiness_score if act.readiness_score is not None else "—",
                act.resume_score if act.resume_score is not None else "—",
                act.lifecycle_status or "—",
                act.due_date or "—",
                act.title,
                act.reason,
            ]
            for c_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=c_idx, value=val)
                cell.font = regular_font
                cell.alignment = left_align if c_idx in (3, 4, 10, 11) else center_align
                cell.border = border
                if row_idx % 2 == 0:
                    cell.fill = zebra_fill

                # Priority column highlighting
                if c_idx == 1:
                    prio_str = str(val).upper()
                    if prio_str == "URGENT":
                        cell.fill = urgent_fill
                        cell.font = urgent_font
                    elif prio_str == "HIGH":
                        cell.fill = high_fill
                        cell.font = high_font
                    elif prio_str == "MEDIUM":
                        cell.fill = med_fill
                        cell.font = med_font

        col_widths = {
            1: 18,  # Priority
            2: 24,  # Action Type
            3: 32,  # Job Title
            4: 24,  # Company
            5: 14,  # Match Score
            6: 14,  # Readiness
            7: 18,  # Resume Alignment
            8: 18,  # Lifecycle Status
            9: 16,  # Due Date
            10: 36, # Recommended Action
            11: 52, # Reason
        }
        for col_idx, width in col_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        ws.freeze_panes = "A2"



