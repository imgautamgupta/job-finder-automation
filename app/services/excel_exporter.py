"""Production-ready Excel export service creating structured, styled multi-sheet job workbooks."""

from datetime import date, datetime, timezone
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models.job import Job, JobStatus, normalize_url

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

# Accenture-specific worksheet columns adhering to report requirements
ACCENTURE_COLUMNS = [
    "Match Score",
    "Job Title",
    "Official Job ID",
    "Location",
    "Experience Requirement",
    "Skills Match",
    "Eligibility",
    "Decision",
    "Decision Reason",
    "Posting Date",
    "Company",
    "Source",
    "Direct Job URL",
    "Date Collected",
    "Application Status",
]

# Master "All Jobs" worksheet columns (Task 5, Task 14, Phase 1)
ALL_JOBS_COLUMNS = [
    "Company",
    "Job Title",
    "Official Job ID",
    "Location",
    "Country",
    "Experience Requirement",
    "Match Score",
    "Skills Match",
    "Decision",
    "Decision Reason",
    "All Failing Rules",
    "Posting Date",
    "Source/Portal",
    "Application URL",
    "Date Collected",
    "Application Status",
    "Employment Type",
]

# Sheet "My Jobs" columns (Task 12)
MY_JOBS_COLUMNS = [
    "Decision",
    "New?",
    "Company",
    "Job Title",
    "Location",
    "Country",
    "Experience",
    "Why",
    "Apply Link",
    "Posted",
    "Job ID",
    "Date Found",
    "Application Status",
    "Follow-up Date",
    "Notes",
]

COUNTRY_KEYWORDS = [
    ("United States", [
        "united states", "usa", "u.s.a.", r"\bu\.s\.\b", r"\bus\b",
        "new york", "california", "texas", "washington", "massachusetts",
        "illinois", "colorado", "virginia", "florida", "georgia",
        "san francisco", "seattle", "austin", "boston", "chicago", "los angeles",
    ]),
    ("United Kingdom", ["united kingdom", "great britain", "england", "scotland", "wales", r"\buk\b", "london", "manchester"]),
    ("United Arab Emirates", ["united arab emirates", r"\buae\b", "abu dhabi", "dubai"]),
    ("Saudi Arabia", ["saudi arabia", "riyadh", "jeddah"]),
    ("Sri Lanka", ["sri lanka", "colombo"]),
    ("Mauritius", ["mauritius", "port louis", "ebene"]),
    ("Maldives", ["maldives", "male"]),
    ("India", ["india", "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "chennai", "gurgaon", "gurugram", "noida", "delhi", "kolkata", "ahmedabad", "kochi", "cochin", "indore", "bhopal", "coimbatore", "chandigarh", "jaipur", "karnataka", "telangana", "maharashtra", "tamil nadu"]),
    ("Canada", ["canada", "toronto", "vancouver", "montreal", "ottawa", "calgary", "waterloo", "ontario", "quebec", "british columbia"]),
    ("Australia", ["australia", "sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra", "new south wales", "victoria", "queensland"]),
    ("Germany", ["germany", "deutschland", "berlin", "munich", "frankfurt", "hamburg", "stuttgart", "cologne", "dusseldorf"]),
    ("Singapore", ["singapore"]),
    ("Ireland", ["ireland", "dublin", "cork", "galway"]),
    ("Netherlands", ["netherlands", "amsterdam", "rotterdam", "the hague", "utrecht"]),
    ("France", ["france", "paris", "lyon", "toulouse"]),
    ("Poland", ["poland", "warsaw", "krakow", "katowice", "wroclaw", "poznan"]),
    ("Switzerland", ["switzerland", "zurich", "geneva", "basel", "bern", "lausanne"]),
    ("Japan", ["japan", "tokyo", "osaka", "kyoto"]),
    ("Spain", ["spain", "madrid", "barcelona", "valencia"]),
    ("Italy", ["italy", "rome", "milan"]),
    ("Sweden", ["sweden", "stockholm", "gothenburg"]),
    ("Brazil", ["brazil", "brasil", "sao paulo", "rio de janeiro"]),
    ("Mexico", ["mexico", "mexico city", "guadalajara", "monterrey"]),
    ("New Zealand", ["new zealand", "auckland", "wellington"]),
    ("South Africa", ["south africa", "johannesburg", "cape town"]),
    ("Philippines", ["philippines", "manila", "cebu"]),
    ("Malaysia", ["malaysia", "kuala lumpur", "penang"]),
    ("Indonesia", ["indonesia", "jakarta", "bali"]),
    ("Vietnam", ["vietnam", "ho chi minh", "hanoi"]),
    ("Romania", ["romania", "bucharest", "cluj"]),
    ("Czech Republic", ["czech republic", "czechia", "prague", "brno"]),
    ("Portugal", ["portugal", "lisbon", "porto"]),
    ("Austria", ["austria", "vienna"]),
    ("Belgium", ["belgium", "brussels"]),
    ("Denmark", ["denmark", "copenhagen"]),
    ("Norway", ["norway", "oslo"]),
    ("Finland", ["finland", "helsinki"]),
    ("Israel", ["israel", "tel aviv", "jerusalem", "haifa"]),
]


def derive_country(location: Optional[str]) -> str:
    """Derive country name from location string.

    - Returns 'Unknown' if empty or not specified
    - Returns 'Remote' if location contains 'remote' (case-insensitive)
    - Otherwise extracts country using mapping of city->country and country keyword detection
    - Returns the last comma-separated token if no other match (often the country)
    - Returns 'Unknown' if empty
    """
    if not location:
        return "Unknown"

    loc_str = str(location).strip()
    if not loc_str or loc_str.lower() in ("not specified", "n/a", "none", "unknown", "null"):
        return "Unknown"

    if re.search(r"\bremote\b", loc_str, re.IGNORECASE):
        return "Remote"

    loc_lower = loc_str.lower()

    # Check keyword patterns
    for country_name, patterns in COUNTRY_KEYWORDS:
        for pat in patterns:
            if pat.startswith(r"\b"):
                if re.search(pat, loc_lower, re.IGNORECASE):
                    return country_name
            else:
                if re.search(r"\b" + re.escape(pat) + r"\b", loc_lower, re.IGNORECASE):
                    return country_name

    # Check US state 2-letter postal abbreviation in location (e.g., "Austin, TX", "New York, NY", "Atlanta, GA 30303")
    if re.search(r",\s*(?:al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy)(?:\s+\d{5})?(?:\s*,\s*|\s*$)", loc_lower):
        return "United States"

    # Fallback to last comma-separated token if present
    if "," in loc_str:
        tokens = [t.strip() for t in loc_str.split(",") if t.strip()]
        if tokens:
            cand = tokens[-1]
            cand_clean = re.sub(r"[\d\-]+$", "", cand).strip()
            if cand_clean:
                return cand_clean.title()

    return loc_str.title() if len(loc_str) < 40 else "Unknown"

STATUS_DISPLAY_MAP = {
    "NEW": "Not applied",
    "NOT_APPLIED": "Not applied",
    "NOT APPLIED": "Not applied",
    "VIEWED": "Not applied",
    "SHORTLISTED": "Not applied",
    "APPLIED": "Applied",
    "INTERVIEW": "Interview",
    "OFFER": "Offer",
    "REJECTED": "Rejected",
    "SKIPPED": "Skipped",
    "NOT_INTERESTED": "Skipped",
}

STATUS_PARSE_MAP = {
    "not applied": "NOT_APPLIED",
    "applied": "APPLIED",
    "interview": "INTERVIEW",
    "offer": "OFFER",
    "rejected": "REJECTED",
    "skipped": "SKIPPED",
}


def sort_my_jobs(jobs: List[Job]) -> List[Job]:
    """Sort jobs for 'My Jobs' sheet:
    1. Decision priority: MATCH first (0), REVIEW second (1), other/tracked (2)
    2. Match Score descending
    3. Newest first (Date Posted or Date Found)
    """
    def _key(j: Job):
        dec = str((j.extra_metadata or {}).get("decision") or getattr(j, "decision", "REVIEW")).upper().strip()
        if dec == "MATCH":
            prio = 0
        elif dec == "REVIEW":
            prio = 1
        else:
            prio = 2

        score = j.match_score if j.match_score is not None else -1

        date_ts = 0.0
        if j.date_posted:
            try:
                date_ts = datetime.fromisoformat(str(j.date_posted).strip()[:19]).timestamp()
            except Exception:
                pass
        if not date_ts and j.date_found:
            date_ts = j.date_found.timestamp()

        return (prio, -score, -date_ts, (j.title or "").lower())

    return sorted(jobs, key=_key)


def sync_excel_tracking_to_db(db_manager: Any, exports_dir: Union[str, Path] = "data/exports") -> int:
    """Read Application Status, Follow-up Date, and Notes from the newest My_Jobs_*.xlsx and save to SQLite.

    Key: company + job ID (or URL). Never overwrites existing database values with blanks.
    """
    exports_path = Path(exports_dir)
    if not exports_path.exists():
        return 0

    excel_files = [
        f for f in exports_path.glob("My_Jobs_*.xlsx")
        if not f.name.startswith("~$")
    ]
    if not excel_files:
        return 0

    newest_file = max(excel_files, key=lambda f: f.stat().st_mtime)
    logger.info("[TRACKING] Synchronizing user edits from latest Excel: %s", newest_file.name)

    try:
        wb = openpyxl.load_workbook(str(newest_file), data_only=True)
    except Exception as exc:
        logger.warning("[TRACKING] Could not open '%s' to read tracking edits: %s", newest_file.name, exc)
        return 0

    if "My Jobs" not in wb.sheetnames:
        return 0

    ws = wb["My Jobs"]
    if ws.max_row < 2:
        return 0

    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    header_map = {str(h).strip(): c for c, h in enumerate(headers, start=1) if h}

    comp_col = header_map.get("Company")
    jid_col = header_map.get("Job ID")
    status_col = header_map.get("Application Status")
    follow_up_col = header_map.get("Follow-up Date")
    notes_col = header_map.get("Notes")
    url_col = header_map.get("Apply Link")

    if not comp_col or not jid_col:
        return 0

    updated_count = 0
    for r in range(2, ws.max_row + 1):
        comp_val = ws.cell(row=r, column=comp_col).value
        if not comp_val or str(comp_val).strip() in ("No matching jobs this run", "None", ""):
            continue
        comp_str = str(comp_val).strip()

        jid_val = ws.cell(row=r, column=jid_col).value
        jid_str = str(jid_val).strip() if jid_val is not None else ""
        if jid_str.lower() in ("n/a", "none", "unknown"):
            jid_str = ""

        url_str = ""
        if url_col:
            cell = ws.cell(row=r, column=url_col)
            if cell.hyperlink and cell.hyperlink.target:
                url_str = str(cell.hyperlink.target).strip()
            elif cell.value and str(cell.value).startswith("http"):
                url_str = str(cell.value).strip()

        status_raw = ws.cell(row=r, column=status_col).value if status_col else None
        follow_up_raw = ws.cell(row=r, column=follow_up_col).value if follow_up_col else None
        notes_raw = ws.cell(row=r, column=notes_col).value if notes_col else None

        status_clean = None
        if status_raw is not None:
            s = str(status_raw).strip()
            if s and s.lower() not in ("none", "null", ""):
                status_clean = STATUS_PARSE_MAP.get(s.lower(), s.upper())

        follow_up_clean = None
        if follow_up_raw is not None:
            if isinstance(follow_up_raw, (datetime, date)):
                follow_up_clean = follow_up_raw.strftime("%Y-%m-%d")
            else:
                f_str = str(follow_up_raw).strip()
                if f_str and f_str.lower() not in ("none", "null", "n/a", ""):
                    follow_up_clean = f_str

        notes_clean = None
        if notes_raw is not None:
            n_str = str(notes_raw).strip()
            if n_str and n_str.lower() not in ("none", "null", "n/a", ""):
                notes_clean = n_str

        if (status_clean is not None or follow_up_clean is not None or notes_clean is not None) and (jid_str or url_str):
            # Check if this represents an actual edit compared to DB state
            existing_job = None
            if hasattr(db_manager, "get_job_by_source_id") and jid_str:
                existing_job = db_manager.get_job_by_source_id(jid_str)
            if not existing_job and hasattr(db_manager, "get_job_by_url") and url_str:
                existing_job = db_manager.get_job_by_url(url_str)

            if existing_job:
                current_st = (existing_job.status.value if hasattr(existing_job.status, "value") else str(existing_job.status or "")).upper()
                is_default_status = status_clean in ("NEW", "NOT_APPLIED")
                was_default_status = current_st in ("NEW", "NOT_APPLIED", "")

                # If Excel has default status and no follow-up/notes, and DB was already default: nothing to update
                if is_default_status and was_default_status and not follow_up_clean and not notes_clean:
                    continue

                # Check if there is any actual difference from what is in DB
                has_status_change = status_clean and status_clean != current_st
                has_followup_change = follow_up_clean and follow_up_clean != (existing_job.follow_up_date or "")
                has_notes_change = notes_clean and notes_clean != (existing_job.notes or "")

                if not (has_status_change or has_followup_change or has_notes_change):
                    continue

            ok = db_manager.update_job_tracking(
                company=comp_str,
                source_job_id=jid_str if jid_str else None,
                url=url_str if url_str else None,
                status=status_clean,
                follow_up_date=follow_up_clean,
                notes=notes_clean,
            )
            if ok:
                updated_count += 1

    return updated_count



def sort_all_jobs(jobs: List[Job]) -> List[Job]:
    """Sort jobs for master 'All Jobs' sheet:
    1. Decision priority: MATCH (0), REVIEW (1), REJECT (2), other (3)
    2. Match Score descending
    3. Date Found / Date Posted newest first
    """
    def _key(j: Job):
        dec = str((j.extra_metadata or {}).get("decision") or getattr(j, "decision", "REVIEW")).upper().strip()
        prio = {"MATCH": 0, "REVIEW": 1, "REJECT": 2}.get(dec, 1)
        score = j.match_score if j.match_score is not None else -1
        date_ts = j.date_found.timestamp() if j.date_found else 0
        return (prio, -score, -date_ts, (j.title or "").lower())

    return sorted(jobs, key=_key)


def get_enabled_companies_from_settings(settings=None) -> List[str]:
    """Return a list of enabled company names based on configuration."""
    if settings is None:
        try:
            from app.config.settings import get_settings
            settings = get_settings()
        except Exception:
            return []

    enabled = []
    if getattr(settings, "ACCENTURE_ENABLED", False):
        enabled.append("Accenture")
    if getattr(settings, "WORKDAY_ENABLED", False):
        wd_comps = [c.strip() for c in getattr(settings, "WORKDAY_COMPANIES", "").split(",") if c.strip()]
        from app.sources.workday import DEFAULT_WORKDAY_COMPANIES
        for c in wd_comps:
            c_low = c.lower()
            if c_low in DEFAULT_WORKDAY_COMPANIES:
                enabled.append(DEFAULT_WORKDAY_COMPANIES[c_low]["name"])
            else:
                enabled.append(c.capitalize())
    if getattr(settings, "SUCCESSFACTORS_ENABLED", False):
        sf_comps = [c.strip() for c in getattr(settings, "SUCCESSFACTORS_COMPANIES", "").split(",") if c.strip()]
        from app.sources.successfactors import DEFAULT_SUCCESSFACTORS_COMPANIES
        for c in sf_comps:
            c_low = c.lower()
            if c_low in DEFAULT_SUCCESSFACTORS_COMPANIES:
                enabled.append(DEFAULT_SUCCESSFACTORS_COMPANIES[c_low]["name"])
            else:
                enabled.append(c.capitalize())
    if getattr(settings, "ORACLE_HCM_ENABLED", False):
        ora_comps = [c.strip() for c in getattr(settings, "ORACLE_HCM_COMPANIES", "").split(",") if c.strip()]
        from app.sources.oracle_hcm import DEFAULT_ORACLE_HCM_COMPANIES
        for c in ora_comps:
            c_low = c.lower()
            if c_low in DEFAULT_ORACLE_HCM_COMPANIES:
                enabled.append(DEFAULT_ORACLE_HCM_COMPANIES[c_low]["name"])
            else:
                enabled.append(c.capitalize())
    if getattr(settings, "COMPANY_JSON_ENABLED", False):
        cj_comps = [c.strip() for c in getattr(settings, "COMPANY_JSON_COMPANIES", "").split(",") if c.strip()]
        from app.sources.company_json import DEFAULT_COMPANY_JSON_REGISTRY
        for c in cj_comps:
            c_low = c.lower()
            if c_low in DEFAULT_COMPANY_JSON_REGISTRY:
                enabled.append(DEFAULT_COMPANY_JSON_REGISTRY[c_low]["name"])
            else:
                enabled.append(c.capitalize())
    if getattr(settings, "TURBOHIRE_ENABLED", False):
        tb_comps = [c.strip() for c in getattr(settings, "TURBOHIRE_COMPANIES", "").split(",") if c.strip()]
        from app.sources.turbohire import DEFAULT_TURBOHIRE_COMPANIES
        for c in tb_comps:
            c_low = c.lower()
            if c_low in DEFAULT_TURBOHIRE_COMPANIES:
                enabled.append(DEFAULT_TURBOHIRE_COMPANIES[c_low]["name"])
            else:
                enabled.append(c.capitalize())
    if getattr(settings, "SMARTRECRUITERS_ENABLED", False):
        sr_comps = [c.strip() for c in getattr(settings, "SMARTRECRUITERS_COMPANIES", "").split(",") if c.strip()]
        enabled.extend([c.capitalize() for c in sr_comps] or ["SmartRecruiters"])
    if getattr(settings, "LEVER_ENABLED", False):
        lever_comps = [c.strip() for c in getattr(settings, "LEVER_COMPANIES", "").split(",") if c.strip()]
        enabled.extend(lever_comps or ["Lever"])
    if getattr(settings, "GREENHOUSE_ENABLED", False):
        gh_comps = [c.strip() for c in getattr(settings, "GREENHOUSE_COMPANIES", "").split(",") if c.strip()]
        enabled.extend(gh_comps or ["Greenhouse"])
    if getattr(settings, "NAUKRI_ENABLED", False):
        enabled.append("Naukri")
    if getattr(settings, "LINKEDIN_ENABLED", False):
        enabled.append("LinkedIn")
    return enabled


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


def is_job_actively_tracked(job: Job) -> bool:
    """Check if a job has a user-assigned tracking status other than 'Not applied'."""
    st = getattr(job, "status", None)
    if hasattr(st, "value"):
        st_val = str(st.value).strip().upper()
    else:
        st_val = str(st or "").strip().upper()

    if not st_val or st_val in ("NEW", "NOT_APPLIED", "NOT APPLIED"):
        meta_st = str((job.extra_metadata or {}).get("status") or "").strip().upper()
        if meta_st:
            st_val = meta_st

    return bool(st_val and st_val not in ("NEW", "NOT_APPLIED", "NOT APPLIED", "NONE", ""))


def is_job_source_enabled(job: Job, enabled_sources: Optional[List[str]]) -> bool:
    """Check if job belongs to an enabled source connector or company portal."""
    if not enabled_sources:
        return True
    enabled_set = {s.strip().lower() for s in enabled_sources if s and s.strip()}
    src = (job.source or "").strip().lower()
    if src in enabled_set:
        return True
    comp = (job.company or "").strip().lower()
    if comp in enabled_set:
        return True
    for token in enabled_set:
        if token and len(token) >= 3 and token in comp:
            return True
    meta = job.extra_metadata or {}
    meta_comp = str(meta.get("company_key") or meta.get("company") or "").strip().lower()
    if meta_comp in enabled_set:
        return True
    return False


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
        full_report: bool = False,
        db_manager: Optional[Any] = None,
        include_accenture_sheet: bool = False,
        accenture_jobs: Optional[List[Job]] = None,
        all_jobs: Optional[List[Job]] = None,
        enabled_companies: Optional[List[str]] = None,
        enabled_sources: Optional[List[str]] = None,
    ) -> Path:
        """Export job postings to Excel.

        By default (full_report=False): Generates a clean, single-sheet 'My Jobs' workbook
        containing only MATCH, REVIEW, and active tracked jobs, saved to My_Jobs_<timestamp>.xlsx
        and overwriting My_Jobs_latest.xlsx.

        If full_report=True: Generates the comprehensive multi-sheet report (All Jobs,
        Top Matches, Analytics, Search Intelligence, Job Agent, Accenture, etc.) saved
        to jobs_full_<timestamp>.xlsx.
        """
        if full_report:
            return self.export_full_report(
                jobs=jobs,
                output_path=output_path,
                current_run_id=current_run_id,
                include_accenture_sheet=include_accenture_sheet,
                accenture_jobs=accenture_jobs,
                all_jobs=all_jobs,
                enabled_companies=enabled_companies,
                enabled_sources=enabled_sources,
            )
        return self.export_my_jobs(
            jobs=jobs,
            output_path=output_path,
            current_run_id=current_run_id,
            db_manager=db_manager,
            all_jobs=all_jobs,
            enabled_sources=enabled_sources,
        )

    def export_my_jobs(
        self,
        jobs: List[Job],
        output_path: Optional[Union[str, Path]] = None,
        current_run_id: Optional[str] = None,
        db_manager: Optional[Any] = None,
        all_jobs: Optional[List[Job]] = None,
        enabled_sources: Optional[List[str]] = None,
    ) -> Path:
        """Export a clean, single-sheet Excel workbook 'My Jobs' with only MATCH, REVIEW, and tracked jobs."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "My Jobs"

        candidate_pool = all_jobs if all_jobs is not None else jobs
        relevant_jobs: List[Job] = []
        seen_keys = set()

        for j in candidate_pool:
            # Task 16: Exclude jobs from disabled sources unless actively tracked (status != 'Not applied')
            actively_tracked = is_job_actively_tracked(j)
            if enabled_sources and not actively_tracked:
                if not is_job_source_enabled(j, enabled_sources):
                    continue

            dec = str((j.extra_metadata or {}).get("decision") or getattr(j, "decision", "")).upper()
            if not dec:
                if (j.match_score or 0) >= 80:
                    dec = "MATCH"
                elif (j.match_score or 0) >= 60:
                    dec = "REVIEW"
                else:
                    continue
            if dec in ("MATCH", "REVIEW"):
                key = (
                    j.company.lower().strip(),
                    (j.source_job_id or j.job_id or "").strip(),
                    normalize_url(j.url),
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    relevant_jobs.append(j)

        # Include tracked jobs from database that are no longer MATCH/REVIEW but have status != 'Not applied'
        if db_manager is not None:
            try:
                tracked_jobs = db_manager.get_active_tracked_jobs()
                for tj in tracked_jobs:
                    t_key = (
                        tj.company.lower().strip(),
                        (tj.source_job_id or tj.job_id or "").strip(),
                        normalize_url(tj.url),
                    )
                    if t_key not in seen_keys:
                        seen_keys.add(t_key)
                        relevant_jobs.append(tj)
            except Exception as e:
                logger.warning("[EXCEL] Error loading tracked jobs from database: %s", e)

        self._populate_my_jobs_sheet(ws, relevant_jobs, current_run_id=current_run_id)

        if output_path is not None:
            target_path = Path(output_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            wb.save(str(target_path))
            return target_path

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = self.exports_dir / f"My_Jobs_{timestamp}.xlsx"
        wb.save(str(target_path))

        # Overwrite My_Jobs_latest.xlsx (skip with warning if open/locked)
        latest_path = self.exports_dir / "My_Jobs_latest.xlsx"
        try:
            wb.save(str(latest_path))
            logger.info("[EXCEL] Updated latest workbook at: %s", latest_path)
        except (PermissionError, IOError) as exc:
            logger.warning("[EXCEL] '%s' is open or locked in another program. Skipping latest overwrite: %s", latest_path, exc)
        except Exception as exc:
            logger.warning("[EXCEL] Failed to overwrite '%s': %s", latest_path, exc)

        return target_path

    def _populate_my_jobs_sheet(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        jobs: List[Job],
        current_run_id: Optional[str] = None,
    ) -> None:
        """Populate single 'My Jobs' worksheet with only MATCH, REVIEW, and tracked jobs."""
        from openpyxl.worksheet.datavalidation import DataValidation

        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        thin_side = Side(border_style="thin", color="E5E7EB")
        border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        match_fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
        match_decision_font = Font(name="Calibri", size=10, bold=True, color="065F46")

        review_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
        review_decision_font = Font(name="Calibri", size=10, bold=True, color="92400E")

        other_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
        other_decision_font = Font(name="Calibri", size=10, bold=True, color="4B5563")

        regular_font = Font(name="Calibri", size=10, color="111827")
        new_font = Font(name="Calibri", size=10, bold=True, color="1D4ED8")
        link_font = Font(name="Calibri", size=10, color="0000EE", underline="single")

        center_align = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")
        wrap_align = Alignment(horizontal="left", vertical="center", wrap_text=True)

        # 1. Write Headers
        ws.row_dimensions[1].height = 26
        for col_idx, col_name in enumerate(MY_JOBS_COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
            cell.border = border

        def _normalize_dt(dt):
            if dt is None:
                return None
            if isinstance(dt, str):
                try:
                    dt = datetime.fromisoformat(dt)
                except Exception:
                    return None
            if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt

        def is_genuinely_new(job: Job) -> bool:
            if getattr(job, "_is_new_in_run", None) is not None:
                return bool(job._is_new_in_run)
            if current_run_id:
                if job.last_seen_run_id == current_run_id or getattr(job, "run_id", None) == current_run_id:
                    dt1 = _normalize_dt(job.first_seen_at)
                    dt2 = _normalize_dt(job.last_seen_at)
                    if dt1 and dt2:
                        return abs((dt1 - dt2).total_seconds()) < 60
                    return True
                return False
            dt1 = _normalize_dt(job.first_seen_at)
            dt2 = _normalize_dt(job.last_seen_at)
            if dt1 and dt2:
                return abs((dt1 - dt2).total_seconds()) < 60
            return False

        if not jobs:
            # Empty-result message: write one row "No matching jobs this run"
            ws.row_dimensions[2].height = 24
            cell = ws.cell(row=2, column=1, value="No matching jobs this run")
            cell.font = Font(name="Calibri", size=11, bold=True, color="6B7280")
            cell.alignment = left_align
            cell.border = border
            for c in range(2, len(MY_JOBS_COLUMNS) + 1):
                empty_cell = ws.cell(row=2, column=c, value="")
                empty_cell.border = border
            max_data_row = 2
        else:
            sorted_jobs = sort_my_jobs(jobs)
            for row_idx, job in enumerate(sorted_jobs, start=2):
                ws.row_dimensions[row_idx].height = 24

                decision_val = str((job.extra_metadata or {}).get("decision") or getattr(job, "decision", "REVIEW")).upper()
                if decision_val == "MATCH":
                    row_fill = match_fill
                    dec_font = match_decision_font
                elif decision_val == "REVIEW":
                    row_fill = review_fill
                    dec_font = review_decision_font
                else:
                    row_fill = other_fill
                    dec_font = other_decision_font

                is_new = is_genuinely_new(job)
                new_str = "NEW" if is_new else ""

                official_id = (job.source_job_id or job.job_id or "").strip() or "N/A"
                why_reason = (job.extra_metadata or {}).get("decision_reason") or getattr(job, "decision_reason", "")
                if not why_reason and job.recommendation_reasons:
                    why_reason = "; ".join(job.recommendation_reasons)

                if (job.extra_metadata or {}).get("work_auth_flag"):
                    if "; check work-authorization requirement" not in why_reason:
                        why_reason = f"{why_reason}; check work-authorization requirement" if why_reason else "check work-authorization requirement"

                country_str = derive_country(job.location)
                posted_str = str(job.date_posted) if job.date_posted else "Unknown"
                found_str = job.date_found.strftime("%Y-%m-%d") if job.date_found else ""

                st_key = (job.status.value if hasattr(job.status, "value") else str(job.status or "")).upper()
                app_status_display = STATUS_DISPLAY_MAP.get(st_key, "Not applied")

                follow_up_str = str(job.follow_up_date) if job.follow_up_date else ""
                notes_str = str(job.notes) if job.notes else ""

                row_data = [
                    decision_val,                             # 1. Decision
                    new_str,                                  # 2. New?
                    job.company,                              # 3. Company
                    job.title,                                # 4. Job Title
                    job.location or "Not Specified",          # 5. Location
                    country_str,                              # 6. Country
                    job.experience_required or "Not Specified",# 7. Experience
                    why_reason,                               # 8. Why
                    "Apply",                                  # 9. Apply Link
                    posted_str,                               # 10. Posted
                    official_id,                              # 11. Job ID
                    found_str,                                # 12. Date Found
                    app_status_display,                       # 13. Application Status
                    follow_up_str,                            # 14. Follow-up Date
                    notes_str,                                # 15. Notes
                ]

                for col_idx, val in enumerate(row_data, start=1):
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                    cell.border = border
                    cell.fill = row_fill

                    if col_idx == 1:
                        cell.font = dec_font
                        cell.alignment = center_align
                    elif col_idx == 2:
                        cell.font = new_font if is_new else regular_font
                        cell.alignment = center_align
                    elif col_idx in (3, 4, 5):
                        cell.font = regular_font
                        cell.alignment = left_align
                    elif col_idx == 6:
                        cell.font = regular_font
                        cell.alignment = center_align
                    elif col_idx == 7:
                        cell.font = regular_font
                        cell.alignment = center_align
                    elif col_idx == 8:
                        cell.font = regular_font
                        cell.alignment = wrap_align
                    elif col_idx == 9:
                        cell.font = link_font
                        cell.alignment = center_align
                        cell.hyperlink = job.url
                    elif col_idx in (10, 11, 12):
                        cell.font = regular_font
                        cell.alignment = center_align
                    elif col_idx == 13:
                        cell.font = regular_font
                        cell.alignment = center_align
                    elif col_idx == 14:
                        cell.font = regular_font
                        cell.alignment = center_align
                    elif col_idx == 15:
                        cell.font = regular_font
                        cell.alignment = wrap_align

            max_data_row = len(sorted_jobs) + 1

        # Sensible column widths
        col_widths = {
            "A": 12,  # Decision
            "B": 8,   # New?
            "C": 18,  # Company
            "D": 36,  # Job Title
            "E": 22,  # Location
            "F": 16,  # Country
            "G": 16,  # Experience
            "H": 48,  # Why
            "I": 12,  # Apply Link
            "J": 14,  # Posted
            "K": 18,  # Job ID
            "L": 14,  # Date Found
            "M": 20,  # Application Status
            "N": 16,  # Follow-up Date
            "O": 35,  # Notes
        }
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width

        # Freeze row 1 and columns A, B, C
        ws.freeze_panes = "D2"

        # Auto-filter
        ws.auto_filter.ref = f"A1:O{max(2, max_data_row)}"

        # Dropdown validation for Column 13 (Application Status)
        dv = DataValidation(
            type="list",
            formula1='"Not applied,Applied,Interview,Offer,Rejected,Skipped"',
            allow_blank=True,
        )
        dv.error = "Please select a valid application status from the dropdown."
        dv.errorTitle = "Invalid Status"
        dv.prompt = "Choose application status"
        dv.promptTitle = "Status"
        ws.add_data_validation(dv)
        dv.add(f"M2:M{max(2, max_data_row)}")

    def export_full_report(
        self,
        jobs: List[Job],
        output_path: Optional[Union[str, Path]] = None,
        current_run_id: Optional[str] = None,
        include_accenture_sheet: bool = False,
        accenture_jobs: Optional[List[Job]] = None,
        all_jobs: Optional[List[Job]] = None,
        enabled_companies: Optional[List[str]] = None,
        enabled_sources: Optional[List[str]] = None,
    ) -> Path:
        """Export the comprehensive multi-sheet Excel workbook (All Jobs, Top Matches, Analytics, etc.).

        Args:
            jobs: List of Job instances.
            output_path: Optional specific file path. If None, auto-generated with timestamp.
            current_run_id: Optional unique identifier for the current pipeline run.
            include_accenture_sheet: Whether to explicitly include Accenture worksheet even if empty.
            accenture_jobs: Optional explicit list of all collected Accenture jobs (MATCH, REVIEW, REJECT).
            all_jobs: Optional explicit list of all collected jobs across all enabled companies.
            enabled_companies: Optional explicit list of enabled companies to filter All Jobs.

        Returns:
            Path to the saved Excel file.
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"jobs_full_{timestamp}.xlsx"
            target_path = self.exports_dir / file_name
        else:
            target_path = Path(output_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.Workbook()

        # Sheet 1: All Jobs (first worksheet for every enabled company - Task 5)
        ws_all_jobs = wb.active
        ws_all_jobs.title = "All Jobs"

        # Sheet 2: New Matches (score >= 60, newly discovered in current run)
        ws_new = wb.create_sheet(title="New Matches")

        # Sheet 3: Top Matches (score >= 80)
        ws_top = wb.create_sheet(title="Top Matches")

        # Sheet 4: All Relevant Jobs (score >= 60)
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

        # Sheet 5: Apply Today (actionable recommended jobs)
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

        # Sheet 6: Resume Preparation (Phase 10)
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

        # Sheet 7: Applications (Phase 11 Command Center)
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

        # Sheet 8: Interview Preparation (Phase 11)
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

        # Sheet 9: Analytics (Phase 12)
        ws_analytics = wb.create_sheet(title="Analytics")

        # Sheet 10: Search Intelligence (Phase 13)
        ws_search_intel = wb.create_sheet(title="Search Intelligence")

        # Sheet 11: Job Agent (Phase 14)
        ws_job_agent = wb.create_sheet(title="Job Agent")

        # Determine candidate jobs for "All Jobs" (Task 5)
        from app.services.deduplicator import deduplicate_for_all_jobs

        if all_jobs is not None:
            raw_all_jobs = list(all_jobs)
        else:
            raw_all_jobs = list(jobs)
            if accenture_jobs:
                raw_all_jobs.extend(accenture_jobs)

        # Deduplicate using company + job ID, falling back to company + normalized title + location + URL
        deduped_all = deduplicate_for_all_jobs(raw_all_jobs)

        # Filter by enabled companies if provided or data-driven from settings
        resolved_enabled = enabled_companies or enabled_sources
        if resolved_enabled is None:
            resolved_enabled = get_enabled_companies_from_settings()

        if resolved_enabled:
            enabled_norm = {c.strip().lower() for c in resolved_enabled if c.strip()}
            final_all_jobs = []
            for j in deduped_all:
                comp_norm = (j.company or "").strip().lower()
                src_norm = (j.source or "").strip().lower()
                if comp_norm in enabled_norm or src_norm in enabled_norm or is_job_actively_tracked(j):
                    final_all_jobs.append(j)
                else:
                    logger.info(
                        "[FILTER] Excluded job '%s' (%s): company/source not enabled in config",
                        j.title,
                        j.company,
                    )
        else:
            final_all_jobs = deduped_all

        sorted_all_jobs = sort_all_jobs(final_all_jobs)

        # Populate worksheets
        self._populate_all_jobs_sheet(ws_all_jobs, sorted_all_jobs)
        self._populate_sheet(ws_new, new_matches)
        self._populate_sheet(ws_top, top_matches)
        self._populate_sheet(ws_all, all_relevant)
        self._populate_sheet(ws_apply, apply_sorted)
        self._populate_sheet(ws_prep, prep_sorted)
        self._populate_sheet(ws_apps, apps_sorted)
        self._populate_sheet(ws_int_prep, int_prep_sorted)
        self._populate_analytics_sheet(ws_analytics, jobs, all_jobs=sorted_all_jobs)
        self._populate_search_intelligence_sheet(ws_search_intel, jobs)
        self._populate_job_agent_sheet(ws_job_agent, jobs)

        # Sheet 12: Accenture (created when Accenture jobs are present or explicitly requested)
        if accenture_jobs is not None:
            acc_source_jobs = list(accenture_jobs)
        else:
            acc_source_jobs = [j for j in jobs if j.source.lower() == "accenture"]

        def _acc_sort_key(j: Job):
            dec = (j.extra_metadata or {}).get("decision", "")
            # MATCH first (0), then REVIEW (1), then REJECT (2), then other
            prio = {"MATCH": 0, "REVIEW": 1, "REJECT": 2}.get(dec, 1)
            score = j.match_score if j.match_score is not None else -1
            return (prio, -score)

        sorted_accenture_jobs = sorted(acc_source_jobs, key=_acc_sort_key)
        if sorted_accenture_jobs or include_accenture_sheet:
            ws_accenture = wb.create_sheet(title="Accenture")
            self._populate_accenture_sheet(ws_accenture, sorted_accenture_jobs)

        # Focus workbook on Top Matches for backward compatibility with existing tests
        wb.active = ws_top

        # Save workbook
        wb.save(str(target_path))
        logger.info(
            "Exported report to %s (All Jobs: %d, New: %d, Top: %d, All Rel: %d, Apply Today: %d, Prep: %d, Apps: %d, IntPrep: %d, Analytics: 1)",
            target_path,
            len(sorted_all_jobs),
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

    def _populate_all_jobs_sheet(
        self, ws: openpyxl.worksheet.worksheet.Worksheet, jobs: List[Job]
    ) -> None:
        """Populate and format the master 'All Jobs' worksheet (Task 5).

        Columns:
        Company, Job Title, Official Job ID, Location, Experience Requirement,
        Match Score, Skills Match, Decision, Decision Reason, Posting Date,
        Source/Portal, Application URL, Date Collected, Application Status.
        """
        # 1. Visual Styles
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        thin_side = Side(style="thin", color="CBD5E1")
        border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        regular_font = Font(name="Calibri", size=10)
        regular_align = Alignment(vertical="center")
        center_align = Alignment(horizontal="center", vertical="center")
        url_font = Font(name="Calibri", size=10, color="0000FF", underline="single")
        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        # Score Highlights
        high_score_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        high_score_font = Font(name="Calibri", size=10, bold=True, color="166534")

        med_score_fill = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")
        med_score_font = Font(name="Calibri", size=10, bold=True, color="0369A1")

        norm_score_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        norm_score_font = Font(name="Calibri", size=10, color="334155")

        # Decision Highlights
        match_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        match_font = Font(name="Calibri", size=10, bold=True, color="166534")

        review_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
        review_font = Font(name="Calibri", size=10, bold=True, color="92400E")

        reject_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        reject_font = Font(name="Calibri", size=10, bold=True, color="991B1B")

        # 2. Write Headers
        ws.row_dimensions[1].height = 26
        for col_idx, col_name in enumerate(ALL_JOBS_COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
            cell.border = border

        # 3. Write Data Rows
        for row_idx, job in enumerate(jobs, start=2):
            ws.row_dimensions[row_idx].height = 20
            is_even = (row_idx % 2 == 0)

            score_val = job.match_score if job.match_score is not None else "N/A"
            official_id = (job.source_job_id or job.job_id or "").strip() or "N/A"
            skills_match_str = ", ".join(job.matched_skills) if job.matched_skills else "None"
            decision_val = (job.extra_metadata or {}).get("decision") or getattr(job, "decision", "REVIEW")
            decision_reason = (job.extra_metadata or {}).get("decision_reason") or getattr(job, "decision_reason", "")
            all_failing_rules = (job.extra_metadata or {}).get("all_failing_rules")
            if not all_failing_rules and job.excluded_reasons:
                all_failing_rules = "; ".join(job.excluded_reasons)
            if not all_failing_rules:
                all_failing_rules = "None" if str(decision_val).upper() != "REJECT" else decision_reason
            status_str = (job.status.value if hasattr(job.status, "value") else str(job.status)) if job.status else "NEW"
            collected_str = job.date_found.strftime("%Y-%m-%d %H:%M:%S") if job.date_found else ""

            country_str = derive_country(job.location)
            emp_type_str = job.employment_type or "Full-time"
            row_data = [
                job.company,                                            # 1. Company
                job.title,                                              # 2. Job Title
                official_id,                                            # 3. Official Job ID
                job.location or "Not Specified",                        # 4. Location
                country_str,                                            # 5. Country
                job.experience_required or "Not Specified",             # 6. Experience Requirement
                score_val,                                              # 7. Match Score
                skills_match_str,                                       # 8. Skills Match
                decision_val,                                           # 9. Decision
                decision_reason,                                        # 10. Decision Reason
                all_failing_rules,                                      # 11. All Failing Rules
                job.date_posted or "Unknown",                           # 12. Posting Date
                (job.source or "Unknown").capitalize(),                 # 13. Source/Portal
                job.url,                                                # 14. Application URL
                collected_str,                                          # 15. Date Collected
                status_str,                                             # 16. Application Status
                emp_type_str,                                           # 17. Employment Type
            ]

            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = border
                cell.font = regular_font

                if col_idx in (3, 5, 7, 9, 12, 13, 15, 16, 17):
                    cell.alignment = center_align
                else:
                    cell.alignment = regular_align

                if is_even:
                    cell.fill = zebra_fill

                # Hyperlink for Application URL (Col 14)
                if col_idx == 14:
                    url_str = str(val or "").strip()
                    if url_str.startswith("http"):
                        cell.hyperlink = url_str
                        cell.font = url_font

                # Score highlighting (Col 7)
                if col_idx == 7 and isinstance(score_val, int):
                    if score_val >= 90:
                        cell.fill = high_score_fill
                        cell.font = high_score_font
                    elif score_val >= 80:
                        cell.fill = med_score_fill
                        cell.font = med_score_font
                    elif score_val >= 60:
                        cell.fill = norm_score_fill
                        cell.font = norm_score_font

                # Decision highlighting (Col 9)
                if col_idx == 9:
                    dec_str = str(decision_val).upper().strip()
                    if dec_str == "MATCH":
                        cell.fill = match_fill
                        cell.font = match_font
                    elif dec_str == "REVIEW":
                        cell.fill = review_fill
                        cell.font = review_font
                    elif dec_str == "REJECT":
                        cell.fill = reject_fill
                        cell.font = reject_font

        # 4. Auto-fit Column Widths with sensible caps
        max_rows = len(jobs) + 1
        for col_idx, col_name in enumerate(ALL_JOBS_COLUMNS, start=1):
            col_letter = get_column_letter(col_idx)
            max_len = len(col_name)
            for r_idx in range(2, max_rows + 1):
                v = ws.cell(row=r_idx, column=col_idx).value
                if v is not None:
                    max_len = max(max_len, min(len(str(v)), 50))
            min_width = 14
            if col_name in ("Job Title", "Location", "Country", "Application URL", "Experience Requirement", "Decision Reason", "All Failing Rules", "Skills Match"):
                min_width = 24
            ws.column_dimensions[col_letter].width = max(max_len + 3, min_width)

        # 5. Usability Enhancements: Freeze header row & Enable AutoFilter
        ws.freeze_panes = "A2"
        max_col_letter = get_column_letter(len(ALL_JOBS_COLUMNS))
        filter_bottom = max_rows if max_rows > 1 else 1
        ws.auto_filter.ref = f"A1:{max_col_letter}{filter_bottom}"

    def _populate_accenture_sheet(
        self, ws: openpyxl.worksheet.worksheet.Worksheet, jobs: List[Job]
    ) -> None:
        """Populate and format an Accenture-specific worksheet with required columns and styling."""
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        thin_side = Side(style="thin", color="E2E8F0")
        border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        regular_font = Font(name="Calibri", size=10)
        regular_align = Alignment(vertical="center")
        center_align = Alignment(horizontal="center", vertical="center")
        url_font = Font(name="Calibri", size=10, color="0000FF", underline="single")

        high_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        high_font = Font(name="Calibri", size=10, bold=True, color="166534")

        med_fill = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")
        med_font = Font(name="Calibri", size=10, bold=True, color="0369A1")

        norm_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        norm_font = Font(name="Calibri", size=10, color="334155")

        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        match_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        match_font = Font(name="Calibri", size=10, bold=True, color="166534")

        review_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
        review_font = Font(name="Calibri", size=10, bold=True, color="92400E")

        reject_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        reject_font = Font(name="Calibri", size=10, bold=True, color="991B1B")

        # 1. Write Headers
        ws.row_dimensions[1].height = 28
        for col_idx, col_name in enumerate(ACCENTURE_COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
            cell.border = border

        # 2. Write Data Rows
        url_col_idx = ACCENTURE_COLUMNS.index("Direct Job URL") + 1
        score_col_idx = ACCENTURE_COLUMNS.index("Match Score") + 1
        job_id_col_idx = ACCENTURE_COLUMNS.index("Official Job ID") + 1
        eligibility_col_idx = ACCENTURE_COLUMNS.index("Eligibility") + 1
        decision_col_idx = ACCENTURE_COLUMNS.index("Decision") + 1

        for row_idx, job in enumerate(jobs, start=2):
            ws.row_dimensions[row_idx].height = 20
            score_val = job.match_score
            is_even = (row_idx % 2 == 0)

            # Official Job ID extraction: mandatory if published, labeled UNAVAILABLE if not
            official_id = (
                job.source_job_id
                or job.job_id
                or (job.extra_metadata or {}).get("official_job_id")
                or "UNAVAILABLE"
            )

            # Eligibility calculation
            eligibility_val = (
                (job.extra_metadata or {}).get("eligibility")
                or ("Eligible" if job.experience_match else "Needs Review")
            )

            # Decision calculation
            decision_val = (job.extra_metadata or {}).get("decision")
            if not decision_val:
                if (job.extra_metadata or {}).get("eligibility") == "Eligible":
                    decision_val = "MATCH"
                elif (job.extra_metadata or {}).get("eligibility") == "Ineligible":
                    decision_val = "REJECT"
                else:
                    decision_val = "REVIEW"

            decision_reason = (job.extra_metadata or {}).get("decision_reason")
            if not decision_reason:
                if decision_val == "REJECT" and job.excluded_reasons:
                    decision_reason = "; ".join(job.excluded_reasons)
                elif decision_val == "MATCH":
                    decision_reason = "Matches target role, location, and entry-level criteria"
                else:
                    decision_reason = "Intermediate/unspecified experience requires review"

            skills_match_str = ", ".join(job.matched_skills) if job.matched_skills else "None"
            status_str = job.status.value if isinstance(job.status, JobStatus) else str(job.status or "NEW")
            collected_str = job.date_found.strftime("%Y-%m-%d %H:%M:%S") if job.date_found else ""

            row_data = [
                score_val if score_val is not None else "N/A",
                job.title,
                official_id,
                job.location or "Not Specified",
                job.experience_required or "Not Specified",
                skills_match_str,
                eligibility_val,
                decision_val,
                decision_reason,
                job.date_posted or "Unknown",
                job.company,
                job.source.capitalize(),
                job.url,
                collected_str,
                status_str,
            ]

            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = border
                cell.font = regular_font

                if col_idx in (score_col_idx, job_id_col_idx, eligibility_col_idx, decision_col_idx, 10, 12, 14, 15):
                    cell.alignment = center_align
                else:
                    cell.alignment = regular_align

                if is_even:
                    cell.fill = zebra_fill

                # Clickable hyperlink for Direct Job URL
                if col_idx == url_col_idx:
                    url_str = str(val or "").strip()
                    if url_str.startswith("http"):
                        cell.hyperlink = url_str
                        cell.font = url_font

                # Score highlighting
                if col_idx == score_col_idx and isinstance(score_val, int):
                    if score_val >= 90:
                        cell.fill = high_fill
                        cell.font = high_font
                    elif score_val >= 80:
                        cell.fill = med_fill
                        cell.font = med_font
                    elif score_val >= 60:
                        cell.fill = norm_fill
                        cell.font = norm_font

                # Decision column color highlighting
                if col_idx == decision_col_idx:
                    if decision_val == "MATCH":
                        cell.fill = match_fill
                        cell.font = match_font
                    elif decision_val == "REVIEW":
                        cell.fill = review_fill
                        cell.font = review_font
                    elif decision_val == "REJECT":
                        cell.fill = reject_fill
                        cell.font = reject_font

        # 3. Auto-fit Column Widths with sensible caps
        max_rows = len(jobs) + 1
        for col_idx, col_name in enumerate(ACCENTURE_COLUMNS, start=1):
            col_letter = get_column_letter(col_idx)
            max_len = len(col_name)
            for r_idx in range(2, max_rows + 1):
                v = ws.cell(row=r_idx, column=col_idx).value
                if v is not None:
                    max_len = max(max_len, min(len(str(v)), 50))
            min_width = 14
            if col_name in ("Job Title", "Location", "Direct Job URL", "Experience Requirement", "Decision Reason"):
                min_width = 24
            ws.column_dimensions[col_letter].width = max(max_len + 3, min_width)

        # 4. Usability Enhancements: Freeze header row & Enable AutoFilter
        ws.freeze_panes = "A2"
        max_col_letter = get_column_letter(len(ACCENTURE_COLUMNS))
        filter_bottom = max_rows if max_rows > 1 else 1
        ws.auto_filter.ref = f"A1:{max_col_letter}{filter_bottom}"

    def _populate_analytics_sheet(
        self,
        ws: openpyxl.worksheet.worksheet.Worksheet,
        jobs: List[Job],
        all_jobs: Optional[List[Job]] = None,
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

        # Compute Metrics across all stored jobs when provided
        pool = all_jobs if (all_jobs is not None and len(all_jobs) > 0) else jobs
        total_found = len(pool)
        relevant_jobs = [j for j in pool if (j.match_score or 0) >= 60]
        relevant_count = len(relevant_jobs)
        recommended_count = sum(
            1 for j in pool
            if getattr(getattr(j, "application_priority", None), "value", str(getattr(j, "application_priority", ""))) in ("URGENT", "HIGH", "NORMAL")
        )
        applied_jobs = [
            j for j in pool
            if j.status in (JobStatus.APPLIED, JobStatus.INTERVIEW, JobStatus.OFFER)
            or j.applied_at is not None
        ]
        applied_count = len(applied_jobs)
        interview_jobs = [
            j for j in pool
            if j.status == JobStatus.INTERVIEW
            or j.interview_date is not None
            or (j.interview_status and str(getattr(j.interview_status, "value", j.interview_status)) not in ("", "NOT_SCHEDULED"))
        ]
        interview_count = len(interview_jobs)
        offer_count = sum(1 for j in pool if j.status == JobStatus.OFFER)
        rejected_count = sum(1 for j in pool if j.status == JobStatus.REJECTED)
        not_interested_count = sum(1 for j in pool if j.status == JobStatus.NOT_INTERESTED)

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
        for j in pool:
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
            tier_jobs = [j for j in pool if fn(j.match_score or 0)]
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



