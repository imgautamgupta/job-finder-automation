"""Accenture Careers job source module.

This module implements controlled, compliant job collection from the official
Accenture Careers job search interface (https://www.accenture.com/in-en/careers/jobsearch).

Safety & Compliance Rules:
- Uses ONLY publicly accessible job-search endpoints used by Accenture's official portal
  (POST https://www.accenture.com/api/accenture/elastic/findjobs).
- Does NOT require authentication or API keys.
- Does NOT bypass CAPTCHA, authentication, or anti-bot protections.
- Does NOT use browser stealth, proxies, or fingerprint spoofing.
- Gracefully handles HTTP 401/403/404/429/timeout errors without crashing the pipeline.
- If portal access is blocked or restricted, stops safely and records status BLOCKED.
- Official Job ID (requisitionId) is mandatory: never fabricated or randomly generated.
  If unavailable, the listing is preserved and the ID is labeled 'UNAVAILABLE'.
- Direct URLs link straight to the individual job posting, not merely search results.
"""

import asyncio
from datetime import datetime, timezone
import html
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from app.config.settings import Settings, get_settings
from app.models.job import Job
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)

ACCENTURE_FINDJOBS_URL = "https://www.accenture.com/api/accenture/elastic/findjobs"
DEFAULT_COUNTRY = "India"
DEFAULT_COUNTRY_SITE = "in-en"
DEFAULT_LANGUAGE = "en"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 JobFinderAutomation/1.0"
)


def clean_html_text(raw_content: Optional[str]) -> Optional[str]:
    """Safely convert HTML content into clean plain text.

    Args:
        raw_content: HTML-encoded or raw HTML string.

    Returns:
        Clean plain-text string, or None if empty.
    """
    if not raw_content or not isinstance(raw_content, str):
        return None

    text = html.unescape(raw_content)
    text = re.sub(r"<(?:br|p|div|li|h[1-6]|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:strong|b|em|i|u|span|a|code)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    cleaned = "\n".join([line for line in lines if line]).strip()
    return cleaned if cleaned else None


def extract_accenture_job_id(item: Dict[str, Any]) -> Tuple[Optional[str], bool]:
    """Extract official Accenture Requisition ID / Job ID from listing payload.

    Args:
        item: Raw job dictionary from Accenture findjobs response.

    Returns:
        Tuple of (job_id_string_or_None, is_available_bool).
        Never invents an ID; returns (None, False) if missing.
    """
    # 1. Primary: official requisitionId (e.g. 'ATCI-5436805-S1978279')
    req_id = item.get("requisitionId")
    if req_id and isinstance(req_id, str) and req_id.strip():
        cleaned_id = req_id.strip()
        if cleaned_id.lower() not in ("none", "null", "n/a", "unavailable"):
            return cleaned_id, True

    # 2. Secondary: guid field (e.g. 'ATCI-5436805-S1978279_en')
    guid = item.get("guid")
    if guid and isinstance(guid, str) and guid.strip():
        cleaned_guid = guid.strip()
        # Strip trailing locale suffix like '_en'
        base_id = re.sub(r"_[a-zA-Z]{2}(?:-[a-zA-Z]{2})?$", "", cleaned_guid)
        if base_id and base_id.lower() not in ("none", "null", "n/a", "unavailable"):
            return base_id, True

    # 3. Tertiary: parse from jobDetailUrl or internalReferURL if present
    for url_key in ("jobDetailUrl", "internalReferURL"):
        url_val = item.get(url_key)
        if isinstance(url_val, str) and url_val.strip():
            parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(url_val).query)
            for param in ("id", "JRID", "jobId"):
                if param in parsed_q and parsed_q[param]:
                    extracted = parsed_q[param][0].strip()
                    extracted_base = re.sub(r"_[a-zA-Z]{2}(?:-[a-zA-Z]{2})?$", "", extracted)
                    if extracted_base and extracted_base.lower() not in ("none", "null", "n/a", "unavailable"):
                        return extracted_base, True

    return None, False


def build_accenture_job_url(
    item: Dict[str, Any],
    country_site: str = DEFAULT_COUNTRY_SITE,
) -> str:
    """Build direct canonical URL to individual job details page.

    Args:
        item: Raw job posting dictionary.
        country_site: Country/language code path segment (default: 'in-en').

    Returns:
        Full direct URL to the job listing.
    """
    raw_url = item.get("jobDetailUrl")
    if isinstance(raw_url, str) and raw_url.strip():
        url_str = raw_url.strip()
        if "{0}" in url_str:
            url_str = url_str.format(country_site)
        if url_str.startswith("/"):
            url_str = f"https://www.accenture.com{url_str}"
        return url_str

    # Fallback direct construction from job ID and title slug
    job_id, _ = extract_accenture_job_id(item)
    raw_title = item.get("title") or "job"
    title_slug = urllib.parse.quote_plus(str(raw_title).strip())
    guid_val = item.get("guid") or (f"{job_id}_{DEFAULT_LANGUAGE}" if job_id else "unknown")
    return f"https://www.accenture.com/{country_site}/careers/jobdetails?id={guid_val}&title={title_slug}"


def normalize_accenture_location(
    location_val: Any,
    country: str = DEFAULT_COUNTRY,
) -> Optional[str]:
    """Normalize location data from Accenture listing.

    Args:
        location_val: String or list of location names from listing payload.
        country: Country string (default: 'India').

    Returns:
        Formatted location string (e.g. 'Bengaluru, India') or None.
    """
    if not location_val:
        return None

    if isinstance(location_val, list):
        items = [str(x).strip() for x in location_val if x and str(x).strip()]
        if not items:
            return None
        loc_str = ", ".join(items)
    elif isinstance(location_val, str):
        loc_str = location_val.strip()
    else:
        loc_str = str(location_val).strip()

    if not loc_str or loc_str.lower() in ("none", "null", "unknown", "n/a", "not specified"):
        return None

    # Append country if not already mentioned
    if country and country.lower() not in loc_str.lower():
        loc_str = f"{loc_str}, {country}"

    return loc_str


def determine_accenture_eligibility(
    experience_text: Optional[str],
    description_text: Optional[str] = None,
    job_title: Optional[str] = None,
) -> str:
    """Determine candidate eligibility grade (Fresher / 0-2 yrs vs Senior vs Needs Review).

    Adheres strictly to the requirement:
    - Never classifies a job as fresher-friendly merely because the title contains 'Engineer'.
    - Uses published experience requirements and qualifications.
    - If eligibility is unclear, returns 'Needs Review'.

    Args:
        experience_text: Experience requirement string (e.g. '0-2 years', '5-10 years').
        description_text: Job description text.
        job_title: Job title string.

    Returns:
        'Eligible', 'Ineligible', or 'Needs Review'.
    """
    exp_clean = (experience_text or "").strip().lower()
    desc_clean = (description_text or "").strip().lower()
    title_clean = (job_title or "").strip().lower()

    # 1. Seniority checks -> Ineligible
    # Title seniority check (Senior, Lead, Principal, Manager, etc.)
    from app.services.filter import match_seniority_title
    if match_seniority_title(title_clean):
        return "Ineligible"

    # Experience field seniority check:
    # Ranges starting with 0-4 (e.g. '0-2 years', '2-5 years') are NOT senior requirements.
    is_senior_exp = False
    if exp_clean:
        if not re.search(r"\b[0-4]\s*(?:[-–—]|to)\s*", exp_clean):
            if (
                re.search(r"\b(?:5|6|7|8|9|10|11|12|13|14|15)\s*(?:[-–—]|to)\s*(?:10|12|14|15|20)\s*years?\b", exp_clean)
                or re.search(r"\b(?:5|6|7|8|9|10|11|12|13|14|15)\+?\s*years?\b", exp_clean)
            ):
                is_senior_exp = True

    if is_senior_exp:
        return "Ineligible"

    # Explicit requirement of 5+ years in description (not accidental mentions like company age or 15 yrs education)
    desc_senior_match = re.search(
        r"\b(?:minimum|min|at least|requires?|requiring)\s*(?:of\s*)?(\d+)\+?\s*years?(?:\s+of)?\s+experience\b",
        desc_clean,
    )
    if desc_senior_match:
        try:
            years_num = int(desc_senior_match.group(1))
            if years_num >= 5:
                return "Ineligible"
        except (ValueError, TypeError):
            pass

    desc_explicit_senior = re.search(r"\b(?:5|6|7|8|9|10)\+\s*years(?:\s+of)?\s+experience\b", desc_clean)
    if desc_explicit_senior:
        return "Ineligible"

    # 2. Fresher / Entry Level / 0-2 years -> Eligible
    # Supports ASCII hyphen (-), Unicode en-dash (– \u2013), em-dash (— \u2014), and 'to'
    fresher_patterns = [
        r"\b(?:0\s*(?:[-–—]|to)\s*[12]|1\s*(?:[-–—]|to)\s*2)\s*years?\b",
        r"\b(?:0|1)\s*(?:[-–—]|to)\s*[12]\s*years?\b",
        r"\b(?:0|1)\s*(?:years?|yrs)\s*(?:of\s*)?experience\b",
        r"\b(?:fresher|freshers|entry[- ]level|intern|internship|fresh\s+graduate|trainee)\b",
    ]
    for pat in fresher_patterns:
        if re.search(pat, exp_clean) or re.search(pat, title_clean):
            return "Eligible"

    # Description mentions fresher / intern / 0-2 years without requiring senior experience
    if any(re.search(pat, desc_clean) for pat in fresher_patterns):
        return "Eligible"

    # 3. If experience requirement is intermediate (e.g. 2-5 years) or unspecified -> Needs Review
    return "Needs Review"


def parse_accenture_job(
    item: Dict[str, Any],
    country_site: str = DEFAULT_COUNTRY_SITE,
    country: str = DEFAULT_COUNTRY,
) -> Optional[Job]:
    """Parse and normalize a raw Accenture listing dictionary into a standard Job instance.

    Args:
        item: Raw job posting dictionary from findjobs endpoint.
        country_site: Country/language code segment.
        country: Target country name.

    Returns:
        Standardized Job instance, or None if invalid/corrupt.
    """
    if not isinstance(item, dict):
        return None

    raw_title = item.get("title")
    if not raw_title or not isinstance(raw_title, str) or not raw_title.strip():
        logger.debug("Skipping Accenture job with missing title.")
        return None

    title = raw_title.strip()
    job_id, id_available = extract_accenture_job_id(item)
    job_url = build_accenture_job_url(item, country_site=country_site)

    # Location normalization
    loc_val = item.get("location") or item.get("feedCity")
    location = normalize_accenture_location(loc_val, country=country)

    # Description
    desc_raw = item.get("jobDescriptionClean") or item.get("jobDescription")
    desc = clean_html_text(desc_raw)

    # Experience requirement
    years_exp = item.get("yearsOfExperience")
    exp_text = None
    if isinstance(years_exp, str) and years_exp.strip():
        exp_cleaned = years_exp.strip()
        if exp_cleaned.startswith("Experience:"):
            exp_text = exp_cleaned[len("Experience:"):].strip()
        else:
            exp_text = exp_cleaned

    # Employment type
    emp_type = item.get("employeeType") or item.get("jobScheduleDescription")
    if isinstance(emp_type, str):
        emp_type = emp_type.strip()

    # Posting date
    date_posted = item.get("postedDateText") or item.get("updateDate")
    if isinstance(date_posted, str):
        date_posted = date_posted.strip()

    # Determine eligibility grade
    eligibility = determine_accenture_eligibility(
        experience_text=exp_text,
        description_text=desc,
        job_title=title,
    )

    # Required skills
    must_have = item.get("mustHaveSkills") or []
    if isinstance(must_have, list):
        must_have_skills = [str(s).strip() for s in must_have if s and str(s).strip() and str(s).upper() != "NA"]
    else:
        must_have_skills = [str(must_have).strip()] if str(must_have).strip() and str(must_have).upper() != "NA" else []

    good_to_have = item.get("goodToHaveSkills") or []
    if isinstance(good_to_have, list):
        good_have_skills = [str(s).strip() for s in good_to_have if s and str(s).strip() and str(s).upper() != "NA"]
    else:
        good_have_skills = [str(good_to_have).strip()] if str(good_to_have).strip() and str(good_to_have).upper() != "NA" else []

    extra_meta: Dict[str, Any] = {
        "requisition_id": item.get("requisitionId"),
        "guid": item.get("guid"),
        "job_id_available": id_available,
        "official_job_id": job_id if id_available else "UNAVAILABLE",
        "eligibility": eligibility,
        "must_have_skills": must_have_skills,
        "good_to_have_skills": good_have_skills,
        "career_level": item.get("careerLevel"),
        "area_of_interest": item.get("areaOfInterest"),
        "feed_city": item.get("feedCity"),
    }

    try:
        job = Job(
            source="accenture",
            source_job_id=job_id,
            job_id=job_id,
            title=title,
            company="Accenture",
            location=location,
            url=job_url,
            description=desc,
            easy_apply=False,
            date_posted=date_posted,
            employment_type=emp_type,
            experience_required=exp_text,
            extra_metadata=extra_meta,
        )
        return job
    except Exception as exc:
        logger.warning("Failed to construct Job from Accenture listing %s: %s", job_id, exc)
        return None


def fetch_accenture_jobs_http(
    keyword: str,
    start_index: int = 0,
    max_result_size: int = 25,
    country: str = DEFAULT_COUNTRY,
    country_site: str = DEFAULT_COUNTRY_SITE,
    job_filters: Optional[List[Dict[str, Any]]] = None,
    timeout_sec: float = 15.0,
    sort_by: str = "0",
) -> Dict[str, Any]:
    """Execute HTTP POST call to Accenture's findjobs elastic endpoint.

    Args:
        keyword: Search query keyword string.
        start_index: Offset start index for pagination.
        max_result_size: Page size limit.
        country: Target country (default: 'India').
        country_site: Portal site locale (default: 'in-en').
        job_filters: Optional filter items list.
        timeout_sec: Network request timeout in seconds.
        sort_by: Sorting mode ('0' = Relevance/Vector similarity, '1' = Newest).

    Returns:
        Parsed response dictionary with 'data' and 'totalHits', or empty dict on failure.
    """
    payload_data = {
        "startIndex": str(start_index),
        "maxResultSize": str(max_result_size),
        "jobKeyword": keyword.strip(),
        "jobCountry": country,
        "jobLanguage": DEFAULT_LANGUAGE,
        "countrySite": country_site,
        "sortBy": str(sort_by),  # '0' = Relevance (Vector Search), '1' = Newest
        "searchType": "vectorSearch",
        "enableQueryBoost": "true",
        "minScore": "0.6" if keyword.strip() else "0.0",
        "getFeedbackJudgmentEnabled": "true",
        "useCleanEmbedding": "true",
        "score": "true",
        "totalHits": "true",
        "debugQuery": "false",
        "jobFilters": json.dumps(job_filters or []),
    }

    encoded_data = urllib.parse.urlencode(payload_data).encode("utf-8")
    headers = {
        "User-Agent": USER_AGENT,
        "Origin": "https://www.accenture.com",
        "Referer": f"https://www.accenture.com/{country_site}/careers/jobsearch",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

    req = urllib.request.Request(
        ACCENTURE_FINDJOBS_URL,
        data=encoded_data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = resp.read().decode("utf-8", errors="ignore")
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return parsed
            logger.warning("Unexpected non-dict response structure from Accenture endpoint.")
            return {}
    except urllib.error.HTTPError as http_err:
        if http_err.code in (401, 403):
            logger.warning(
                "Accenture portal access restricted/blocked (HTTP %d). Stopping collection safely.",
                http_err.code,
            )
            raise http_err
        elif http_err.code == 429:
            logger.warning("Accenture rate limit reached (HTTP 429).")
            raise http_err
        else:
            logger.warning("Accenture HTTP error %d encountered: %s", http_err.code, http_err.reason)
            return {}
    except urllib.error.URLError as url_err:
        logger.warning("Accenture network connection error: %s", url_err)
        return {}
    except json.JSONDecodeError as json_err:
        logger.warning("Malformed JSON response from Accenture portal: %s", json_err)
        return {}
    except TimeoutError as timeout_err:
        logger.warning("Accenture request timed out after %.1fs: %s", timeout_sec, timeout_err)
        return {}
    except Exception as exc:
        logger.warning("Unexpected error during Accenture HTTP fetch: %s", exc)
        return {}


class AccentureJobSource(BaseJobSource):
    """Source connector for collecting public job postings from Accenture Careers portal.

    Collects listings for Accenture India vacancies using the official public
    endpoint utilized by https://www.accenture.com/in-en/careers/jobsearch.
    Adheres strictly to safety constraints: no credentials required, no CAPTCHA
    solving, conservative rate limits, and graceful error handling.
    """

    def __init__(
        self,
        is_enabled: Optional[bool] = None,
        settings: Optional[Settings] = None,
    ):
        self._settings = settings or get_settings()
        enabled_flag = is_enabled if is_enabled is not None else getattr(self._settings, "ACCENTURE_ENABLED", False)
        super().__init__(is_enabled=enabled_flag)

        self.max_jobs = getattr(self._settings, "ACCENTURE_MAX_JOBS", 50)
        self.request_delay_sec = getattr(self._settings, "ACCENTURE_REQUEST_DELAY_SEC", 1.0)
        self.country = getattr(self._settings, "ACCENTURE_COUNTRY", DEFAULT_COUNTRY)
        self.country_site = getattr(self._settings, "ACCENTURE_COUNTRY_SITE", DEFAULT_COUNTRY_SITE)
        self.sort_by = str(getattr(self._settings, "ACCENTURE_SORT_BY", "0"))

        self.diagnostics: Dict[str, Any] = {
            "available_postings": 0,
            "collection_limit": self.max_jobs,
            "collected": 0,
            "valid_normalized": 0,
            "invalid_skipped": 0,
            "missing_job_id": 0,
            "queries_attempted": 0,
            "pages_requested": 0,
            "query_pages": {},
            "locations": {},
            "roles": {},
        }

    @property
    def source_name(self) -> str:
        return "accenture"

    @property
    def configured_search_roles(self) -> List[str]:
        """Parsed list of search role queries from settings if configured."""
        return getattr(self._settings, "accenture_search_roles_list", [])

    async def setup(self) -> None:
        """Initialize Accenture connector lifecycle."""
        if not self.is_enabled:
            return
        logger.info(
            "Initializing Accenture Careers public connector (country=%s, site=%s, limit=%d)...",
            self.country,
            self.country_site,
            self.max_jobs,
        )

    async def teardown(self) -> None:
        """Clean up Accenture connector resources."""
        logger.info("Closing Accenture connector resources.")

    async def collect_jobs(
        self,
        roles: List[str],
        locations: List[str],
        max_results: int = 25,
    ) -> List[Job]:
        """Collect job postings from official Accenture Careers search interface.

        Args:
            roles: Target role titles (used by pipeline filtering and search queries).
            locations: Target locations (used by pipeline filtering).
            max_results: Maximum raw listings to collect across queries.

        Returns:
            List of standardized, normalized Job objects.
        """
        if not self.is_enabled:
            logger.info("Accenture collection is disabled in settings.")
            self.last_status = "DISABLED"
            self.last_error = None
            return []

        self.last_status = "COMPLETED"
        self.last_error = None

        # Reset diagnostic metrics
        effective_limit = min(self.max_jobs, max_results) if max_results > 0 else self.max_jobs
        self.diagnostics = {
            "available_postings": 0,
            "collection_limit": effective_limit,
            "collected": 0,
            "valid_normalized": 0,
            "invalid_skipped": 0,
            "missing_job_id": 0,
            "queries_attempted": 0,
            "pages_requested": 0,
            "query_pages": {},
            "locations": {},
            "roles": {},
        }

        # Determine queries to run
        if self.configured_search_roles:
            query_list = self.configured_search_roles
        elif roles:
            # Pick representative keywords to cover target roles without redundant calls
            unique_queries: List[str] = []
            seen: set = set()
            for r in roles:
                clean_r = r.strip()
                if clean_r and clean_r.lower() not in seen:
                    unique_queries.append(clean_r)
                    seen.add(clean_r.lower())
            query_list = unique_queries
        else:
            query_list = [
                "Python Developer",
                "Software Engineer",
                "Backend Developer",
                "Full Stack Developer",
                "Machine Learning",
                "Intern",
            ]

        logger.info(
            "Starting Accenture Careers collection across %d queries (limit=%d, delay=%.1fs)...",
            len(query_list),
            effective_limit,
            self.request_delay_sec,
        )

        all_collected_jobs: List[Job] = []
        seen_identifiers: set = set()

        # Initialize query state tracking
        # Each query tracks start_index, has_more, pages_requested, and seen_signatures
        query_states: Dict[str, Dict[str, Any]] = {
            q: {
                "start_index": 0,
                "has_more": True,
                "pages_requested": 0,
                "seen_signatures": set(),
            }
            for q in query_list
        }

        # Calculate per-query batch size for multi-query distributions
        # If single query: fetch standard 25 per page up to effective_limit.
        # If multiple queries: divide budget proportionally so each query gets a chance to run,
        # but minimum 2 and maximum 25 per request.
        num_queries = len(query_list)
        if num_queries == 1:
            base_page_size = min(25, effective_limit)
        else:
            base_page_size = max(1, min(25, effective_limit // num_queries))

        round_num = 0
        MAX_ROUNDS = 20  # Safe cap to avoid infinite loops

        while len(all_collected_jobs) < effective_limit and round_num < MAX_ROUNDS:
            active_queries_this_round = [q for q in query_list if query_states[q]["has_more"]]
            if not active_queries_this_round:
                logger.info("All configured queries exhausted available results.")
                break

            round_num += 1
            for q_idx, query in enumerate(query_list):
                if len(all_collected_jobs) >= effective_limit:
                    break

                q_state = query_states[query]
                if not q_state["has_more"]:
                    continue

                # Mark query as attempted on its first request
                if q_state["pages_requested"] == 0:
                    self.diagnostics["queries_attempted"] += 1

                start_index = q_state["start_index"]
                remaining = effective_limit - len(all_collected_jobs)
                page_size = min(base_page_size, remaining)

                logger.info(
                    "Searching Accenture for query='%s' round=%d page=%d (startIndex=%d, pageSize=%d)...",
                    query,
                    round_num,
                    q_state["pages_requested"],
                    start_index,
                    page_size,
                )

                try:
                    resp_data = await asyncio.to_thread(
                        fetch_accenture_jobs_http,
                        keyword=query,
                        start_index=start_index,
                        max_result_size=page_size,
                        country=self.country,
                        country_site=self.country_site,
                        sort_by=self.sort_by,
                    )
                except urllib.error.HTTPError as http_err:
                    if http_err.code in (401, 403):
                        self.last_status = "BLOCKED"
                        self.last_error = f"Accenture portal access restricted (HTTP {http_err.code})"
                        logger.warning("Accenture collection halted safely: %s", self.last_error)
                        return all_collected_jobs
                    elif http_err.code == 429:
                        self.last_status = "WARNING"
                        self.last_error = "Rate limit reached (HTTP 429)"
                        logger.warning("Accenture rate limited: %s", self.last_error)
                        return all_collected_jobs
                    else:
                        self.last_error = f"HTTP {http_err.code}"
                        q_state["has_more"] = False
                        continue
                except Exception as exc:
                    logger.warning("Failed query '%s' on Accenture: %s", query, exc)
                    q_state["has_more"] = False
                    continue

                q_state["pages_requested"] += 1
                self.diagnostics["pages_requested"] += 1
                self.diagnostics["query_pages"][query] = q_state["pages_requested"]

                raw_jobs = resp_data.get("data", [])
                total_hits = resp_data.get("totalHits", {})
                total_count = total_hits.get("total", len(raw_jobs)) if isinstance(total_hits, dict) else len(raw_jobs)
                if q_state["pages_requested"] == 1:
                    self.diagnostics["available_postings"] = max(self.diagnostics["available_postings"], total_count)

                # Condition 1: Empty page returned
                if not raw_jobs:
                    logger.debug("No jobs returned from Accenture for query='%s' at startIndex=%d.", query, start_index)
                    q_state["has_more"] = False
                    continue

                # Condition 2: Detect page repetition / cycle
                page_ids = tuple(
                    j.get("requisitionId") or j.get("guid") or j.get("title")
                    for j in raw_jobs
                    if isinstance(j, dict)
                )
                if page_ids in q_state["seen_signatures"]:
                    logger.info("Repeated page detected for query='%s' at startIndex=%d. Halting pagination for this query.", query, start_index)
                    q_state["has_more"] = False
                    continue
                q_state["seen_signatures"].add(page_ids)

                self.diagnostics["collected"] += len(raw_jobs)

                for raw_item in raw_jobs:
                    if len(all_collected_jobs) >= effective_limit:
                        break

                    job = parse_accenture_job(
                        raw_item,
                        country_site=self.country_site,
                        country=self.country,
                    )
                    if not job:
                        self.diagnostics["invalid_skipped"] += 1
                        continue

                    # Deduplicate within connector
                    dedup_id = job.source_job_id or job.url
                    if dedup_id in seen_identifiers:
                        continue
                    seen_identifiers.add(dedup_id)

                    if not job.source_job_id:
                        self.diagnostics["missing_job_id"] += 1

                    self.diagnostics["valid_normalized"] += 1
                    all_collected_jobs.append(job)

                    # Track location and role distributions
                    loc_name = job.location or "Unspecified"
                    self.diagnostics["locations"][loc_name] = self.diagnostics["locations"].get(loc_name, 0) + 1

                    role_title = job.title or "Untitled"
                    self.diagnostics["roles"][role_title] = self.diagnostics["roles"].get(role_title, 0) + 1

                # Condition 3: Partial page received indicates end of results for this query
                if len(raw_jobs) < page_size:
                    logger.debug("Partial page returned (%d < %d) for query='%s'. End of results.", len(raw_jobs), page_size, query)
                    q_state["has_more"] = False

                # Advance start_index for subsequent page requests
                q_state["start_index"] += len(raw_jobs)

                # Politeness delay between HTTP requests
                if len(all_collected_jobs) < effective_limit and self.request_delay_sec > 0:
                    await asyncio.sleep(self.request_delay_sec)

        self.last_collected_count = len(all_collected_jobs)
        total_avail = self.diagnostics.get("available_postings", 0)
        if total_avail > len(all_collected_jobs):
            self.last_status = "PARTIAL"
        else:
            self.last_status = "COMPLETED"

        logger.info(
            "Accenture collection finished: %d valid jobs collected (attempted=%d queries, total_pages=%d).",
            len(all_collected_jobs),
            self.diagnostics["queries_attempted"],
            self.diagnostics["pages_requested"],
        )
        return all_collected_jobs

    def format_diagnostics(
        self,
        filtered_jobs: Optional[List[Job]] = None,
        scored_jobs: Optional[List[Job]] = None,
    ) -> str:
        """Format collection and pipeline diagnostics for Accenture.

        Args:
            filtered_jobs: Optional list of jobs that passed profile filter.
            scored_jobs: Optional list of scored jobs with match categories.

        Returns:
            Structured diagnostic report string.
        """
        diag = self.diagnostics
        valid_count = diag.get("valid_normalized", 0)

        if filtered_jobs is not None:
            acc_filtered = [j for j in filtered_jobs if j.source.lower() == "accenture"]
            filtered_out_count = max(0, valid_count - len(acc_filtered))
        else:
            filtered_out_count = 0
            acc_filtered = []

        if scored_jobs is not None:
            acc_scored = [j for j in scored_jobs if j.source.lower() == "accenture"]
        else:
            acc_scored = acc_filtered

        excellent = sum(1 for j in acc_scored if j.match_category == "Excellent")
        strong = sum(1 for j in acc_scored if j.match_category == "Strong")
        good = sum(1 for j in acc_scored if j.match_category == "Good")
        possible = sum(1 for j in acc_scored if j.match_category == "Possible")
        relevant = excellent + strong + good + possible

        lines = [
            "Accenture:",
            f"  Available postings: {diag.get('available_postings', 0)}",
            f"  Collection limit: {diag.get('collection_limit', self.max_jobs)}",
            f"  Collected: {diag.get('collected', 0)}",
            f"  Valid normalized jobs: {valid_count}",
            f"  Missing Job ID: {diag.get('missing_job_id', 0)}",
            f"  Invalid/skipped: {diag.get('invalid_skipped', 0)}",
            f"  Filtered out: {filtered_out_count}",
            f"  Relevant jobs: {relevant}",
            f"  Excellent: {excellent}",
            f"  Strong: {strong}",
            f"  Good: {good}",
            f"  Possible: {possible}",
        ]

        loc_items = sorted(diag.get("locations", {}).items(), key=lambda x: x[1], reverse=True)
        if loc_items:
            lines.append("")
            lines.append("Location distribution:")
            for loc, count in loc_items:
                lines.append(f"  {loc}: {count}")

        role_items = sorted(diag.get("roles", {}).items(), key=lambda x: x[1], reverse=True)
        if role_items:
            lines.append("")
            lines.append("Role distribution:")
            for role, count in role_items:
                lines.append(f"  {role}: {count}")

        return "\n".join(lines)
