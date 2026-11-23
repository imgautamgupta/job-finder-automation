"""Job filtering service matching jobs against user preferences."""

import logging
import re
from typing import List, Optional, Tuple, Union
import unicodedata

from app.models.profile import JobProfile
from app.models.job import Job
from app.services.matcher import is_india_eligible_remote

logger = logging.getLogger(__name__)

WORD_TO_NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20,
}

NUM_WORDS_PATTERN = r"(?:\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
DASH_PATTERN = r"(?:[\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]|to)"

SENIORITY_TITLE_PATTERN = re.compile(
    r"\b(?:"
    r"(?:sr\.?|snr\.?|senior|lead|principal|staff)\s*[-]?\s*consultant(?:\s+level)?\b|"
    r"consultant\s*[-]?\s*level\b|"
    r"head\s+of\b|"
    r"(?:sr|snr)(?:\.|\b)|"
    r"(?:senior|lead|principal|staff|manager|director|architect|distinguished|fellow)\b"
    r")",
    re.IGNORECASE,
)

# Work authorization flag
WORK_AUTH_PATTERN = re.compile(
    r"\b(?:work\s+authoriz(?:ation|ed)|right\s+to\s+work|citizenship\s+required|"
    r"visa\s+sponsorship\s+(?:not\s+(?:available|provided|offered)|unavailable|is\s+not)|"
    r"must\s+be\s+(?:a\s+)?(?:us|uk|australian|canadian)\s+citizen|"
    r"security\s+clearance\s+required)\b",
    re.IGNORECASE,
)


def match_seniority_title(title: Optional[str]) -> Optional[str]:
    """Check if title contains senior markers.

    Catches whole words/abbreviations, case-insensitive, with or without period/hyphen:
    Sr, Sr., Snr, Senior, Lead, Principal, Staff, Manager, Director, Architect,
    Head of, Distinguished, Fellow, and consultant-level wording (e.g. Sr. Consultant).
    Avoids false positives inside other words (e.g. Srinivas, Leader in team name, Staffing).

    Returns the matched marker string, or None if no match.
    """
    if not title:
        return None
    cleaned_title = unicodedata.normalize("NFKC", str(title).strip())
    match = SENIORITY_TITLE_PATTERN.search(cleaned_title)
    if match:
        return match.group(0).strip()
    return None


LEVEL_TITLE_PATTERN = re.compile(
    r"(?:"
    r"\b(?:III|IV|V|VI)\b|"
    r"\bL[6-9]\b|\bL\d{2,}\b|"
    r"\b(?:level|lvl)\s*[-_]?\s*(?:[3-9]|\d{2,}|III|IV|V|VI)\b|"
    r"\b(?:sde|swe|mle|qa|qae|sdet|dev(?:eloper)?|engineer|architect|scientist|consultant|analyst)\s*[-_]?\s*(?:[3-9]|\d{2,})\b|"
    r"\b(?:[3-9])\s*(?:nd|rd|th)?\s*level\b"
    r")",
    re.IGNORECASE,
)


def match_level_title(title: Optional[str]) -> Optional[str]:
    """Check if title contains mid/senior level markers to reject:
    - Level III, IV, V, VI (Roman numerals)
    - Level 3, 4, 5, etc.
    - SDE 3, SWE 3, Engineer 3, etc.
    - L6, L7, L8, L9, L10+

    Keeping allowed:
    - Level I, II, 1, 2, L1, L2, L3, L4, L5
    - SDE 1, SDE 2, SWE 1, SWE 2
    - Associate, Junior, Fresher, New Grad

    Returns matched level string or None.
    """
    if not title:
        return None
    cleaned_title = unicodedata.normalize("NFKC", str(title).strip())
    match = LEVEL_TITLE_PATTERN.search(cleaned_title)
    if match:
        return match.group(0).strip()
    return None


BELOW_PROFILE_PATTERN = re.compile(
    r"\b(?:intern(?:ship)?|trainee|apprentice)\b",
    re.IGNORECASE,
)


def match_below_profile_title(title: Optional[str]) -> Optional[str]:
    """Check if title contains intern/trainee/apprentice markers (below profile level).

    Returns matched string or None.
    """
    if not title:
        return None
    cleaned_title = unicodedata.normalize("NFKC", str(title).strip())
    match = BELOW_PROFILE_PATTERN.search(cleaned_title)
    if match:
        return match.group(0).strip()
    return None


def is_hp_or_deloitte_source(job: Job) -> bool:
    """Identify if a job originates strictly from HP Careers or Deloitte sources.

    Task 16 requirement: ENTRY_LEVEL_LOCATION_SCOPE=all and ROLE_FILTER=off
    apply ONLY to HP and the Deloitte sources. Every other source must use the profile's
    preferred locations and the role filter.
    """
    comp = (job.company or "").strip().lower()
    if comp == "hp" or comp.startswith("hp ") or comp in ("hewlett packard", "hewlett-packard"):
        return True
    if "deloitte" in comp:
        return True
    meta = job.extra_metadata or {}
    meta_comp = str(meta.get("company_key") or meta.get("company") or "").strip().lower()
    if meta_comp == "hp" or "deloitte" in meta_comp:
        return True
    return False


def parse_num(val: str) -> Optional[Union[int, float]]:
    v = val.strip().lower()
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except ValueError:
        return WORD_TO_NUM.get(v)


def parse_structured_experience_min(exp_text: Optional[str]) -> Optional[Union[int, float]]:
    """Parse minimum required years from structured portal fields (Gate 1).

    Returns integer or float minimum years, or None if no experience info stated.
    """
    if not exp_text:
        return None
    text = unicodedata.normalize("NFKC", str(exp_text).strip().lower())
    if text in ("", "none", "null", "not specified", "unspecified", "n/a", "unknown", "na"):
        return None

    # Fresher / entry-level keywords
    if re.search(r"\b(?:fresher|freshers|entry[- ]level|intern|internship|trainee|graduate)\b", text):
        return 0

    # Months to years range pattern: e.g. "6 months to 2 years", "6months to 2 yrs"
    m_range = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*months?\s*{DASH_PATTERN}\s*({NUM_WORDS_PATTERN})\s*(?:years?|yrs)\b",
        text,
    )
    if m_range:
        num = parse_num(m_range.group(1))
        if num is not None:
            val = round(num / 12.0, 2)
            return int(val) if isinstance(val, float) and val.is_integer() else val

    # Months to months range pattern: e.g. "6 to 12 months", "6-12 months"
    m_to_m = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*(?:months?|mos?)?\s*{DASH_PATTERN}\s*({NUM_WORDS_PATTERN})\s*(?:months?|mos?)\b",
        text,
    )
    if m_to_m:
        num = parse_num(m_to_m.group(1))
        if num is not None:
            val = round(num / 12.0, 2)
            return int(val) if isinstance(val, float) and val.is_integer() else val

    # Range pattern: e.g. "2-5 years", "2 - 5 yrs", "2 to 5 years", "two to five years"
    range_match = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*{DASH_PATTERN}\s*{NUM_WORDS_PATTERN}\s*(?:years?|yrs)?\b",
        text,
    )
    if range_match:
        val = parse_num(range_match.group(1))
        if val is not None:
            return val

    # Plus pattern: e.g. "2+ years", "2 + yrs", "two plus years"
    plus_match = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*(?:\+|plus)\s*(?:years?|yrs)?\b",
        text,
    )
    if plus_match:
        val = parse_num(plus_match.group(1))
        if val is not None:
            return val

    # Minimum / At least pattern: e.g. "minimum 3 years", "at least 2 years"
    min_match = re.search(
        rf"\b(?:minimum|min|at\s+least)\s*(?:of\s*)?({NUM_WORDS_PATTERN})\+?\s*(?:years?|yrs)?\b",
        text,
    )
    if min_match:
        val = parse_num(min_match.group(1))
        if val is not None:
            return val

    # Standalone: e.g. "3 years", "1 year", "two years"
    single_match = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*(?:years?|yrs)\b",
        text,
    )
    if single_match:
        val = parse_num(single_match.group(1))
        if val is not None:
            return val

    # Standalone digits range e.g. "0-2" or "2"
    digits_range = re.search(rf"\b({NUM_WORDS_PATTERN})\s*{DASH_PATTERN}\s*{NUM_WORDS_PATTERN}\b", text)
    if digits_range:
        val = parse_num(digits_range.group(1))
        if val is not None:
            return val

    return None


def parse_title_experience_min(title: Optional[str]) -> Optional[Union[int, float]]:
    """Parse experience phrases from job titles ("6 months to 2 years", "0-2 years", "fresher") as a Gate 1 source.

    Returns float or integer minimum years (e.g. 0.5 for 6 months, 0 for fresher/0-2),
    or None if no experience phrase is stated in title.
    """
    if not title:
        return None
    text = unicodedata.normalize("NFKC", str(title).strip().lower())
    if not text:
        return None

    # 1. Months to Years range: e.g. "6months to 2 years", "6 months - 2 years", "six months to two years"
    m_range = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*months?\s*{DASH_PATTERN}\s*({NUM_WORDS_PATTERN})\s*(?:years?|yrs)\b",
        text,
    )
    if m_range:
        num = parse_num(m_range.group(1))
        if num is not None:
            val = round(num / 12.0, 2)
            return int(val) if isinstance(val, float) and val.is_integer() else val

    # 2. Months to Months range: e.g. "6 to 12 months", "6-12 months"
    m_to_m = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*(?:months?|mos?)?\s*{DASH_PATTERN}\s*({NUM_WORDS_PATTERN})\s*(?:months?|mos?)\b",
        text,
    )
    if m_to_m:
        num = parse_num(m_to_m.group(1))
        if num is not None:
            val = round(num / 12.0, 2)
            return int(val) if isinstance(val, float) and val.is_integer() else val

    # 3. Fresher / freshers keywords in title
    if re.search(r"\b(?:fresher|freshers)\b", text):
        return 0

    # 4. Years Range: e.g. "0-2 years", "0 to 2 years", "1-3 yrs", "0.5 to 2 years"
    y_range = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*{DASH_PATTERN}\s*({NUM_WORDS_PATTERN})\s*(?:years?|yrs)\b",
        text,
    )
    if y_range:
        num = parse_num(y_range.group(1))
        if num is not None:
            return num

    # 5. Plus pattern: e.g. "2+ years", "2 + yrs"
    y_plus = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*(?:\+|plus)\s*(?:years?|yrs)\b",
        text,
    )
    if y_plus:
        num = parse_num(y_plus.group(1))
        if num is not None:
            return num

    # 6. Minimum pattern: e.g. "minimum 2 years", "at least 1 year"
    y_min = re.search(
        rf"\b(?:minimum|min|at\s+least)\s*(?:of\s*)?({NUM_WORDS_PATTERN})\+?\s*(?:years?|yrs)\b",
        text,
    )
    if y_min:
        num = parse_num(y_min.group(1))
        if num is not None:
            return num

    # 7. Standalone years with experience keyword: e.g. "2 years experience", "1 yr exp"
    y_exp = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*(?:years?|yrs)\s*(?:of\s*)?exp(?:erience)?\b",
        text,
    )
    if y_exp:
        num = parse_num(y_exp.group(1))
        if num is not None:
            return num

    return None


def scan_description_experience_min(desc_text: Optional[str]) -> Optional[int]:
    """Scan full job description for required experience patterns (Gate 2).

    Backward-compatible wrapper returning only the stated minimum years.
    """
    val, _ = scan_description_experience(desc_text)
    return val


COMPANY_HISTORY_PATTERN = re.compile(
    r"(?:"
    r"\b(?:over|for\s+over|for\s+more\s+than|\d+\+?)\s+years\s+(?:of\s+)?(?:innovation|history|excellence|leadership|service|industry\s+leadership|growth|success|expertise|experience\s+in\s+the\s+industry)\b|"
    r"\bfor\s+(?:over|more\s+than)\s+\d+\s+years\b|"
    r"\b(?:founded|established|operating|serving\s+customers)\s+(?:for\s+over\s+\d+\s+years|in\s+\d{4}|since\s+\d{4})\b|"
    r"\bsince\s+(?:19|20)\d{2}\b|"
    r"\b\d+\s+years\s+(?:in\s+business|as\s+a\s+company|of\s+history|of\s+legacy)\b|"
    r"\bcelebrating\s+(?:over\s+)?\d+\s+years\b|"
    r"\b(?:over\s+)?(?:\d+)\s+years\s+of\s+innovation\b"
    r")",
    re.IGNORECASE,
)


def is_company_history_phrase(subtext: str, start: int, end: int) -> bool:
    """Check if a matched span is part of or immediately adjacent to company-history context."""
    window_start = max(0, start - 50)
    window_end = min(len(subtext), end + 50)
    window = subtext[window_start:window_end]
    if COMPANY_HISTORY_PATTERN.search(window):
        return True
    before = subtext[max(0, start - 35):start].lower()
    if any(k in before for k in ["founded", "past", "last", "celebrating", "since", "over the", "history of", "in business", "team has", "company has"]):
        return True
    return False


def extract_qualifications_section(desc: str) -> Optional[Tuple[str, int]]:
    """Return (section_text, start_offset) if a qualifications/requirements section can be identified."""
    headers_regex = (
        r"(?:(?:basic|minimum|required|key|job|role|technical|core)\s+qualifications?|"
        r"qualifications?|requirements?|what\s+you(?:'ll)?\s+(?:need|bring|have)|"
        r"who\s+you\s+are|what\s+we(?:'re)?\s+looking\s+for|eligibility(?:\s+criteria)?|"
        r"skills\s+(?:&|and)\s+requirements|candidate\s+profile|what\s+you\s+should\s+have)"
    )
    boundary_regex = (
        r"(?:preferred\s+qualifications?|nice\s+to\s+have|bonus\s+points|responsibilities|"
        r"what\s+you(?:'ll)?\s+do|key\s+responsibilities|day\s+in\s+the\s+life|"
        r"about\s+(?:us|the\s+team|the\s+company|our\s+company|adobe|intel|nvidia|salesforce|walmart|mastercard|visa|paypal)|"
        r"what\s+we\s+offer|benefits|perks|compensation|life\s+at|"
        r"our\s+culture|equal\s+opportunity|how\s+to\s+apply|ai\s+use\s+guidelines)"
    )
    pattern = rf"(?:^|\n|\r|[#*_\-–—]+|\b)({headers_regex})\s*[:\-–—\n\r]"
    matches = list(re.finditer(pattern, desc, re.IGNORECASE))
    if not matches:
        return None

    # Prefer basic/minimum/required if multiple headings exist
    best_m = None
    for m in matches:
        h = m.group(1).lower()
        if any(k in h for k in ["basic", "minimum", "required"]):
            best_m = m
            break
    if not best_m:
        best_m = matches[0]

    sec_start = best_m.end()
    remaining = desc[sec_start:]
    end_pattern = rf"(?:^|\n|\r|[#*_\-–—]+|\b)({boundary_regex})\s*[:\-–—\n\r]"
    end_m = re.search(end_pattern, remaining, re.IGNORECASE)
    if end_m:
        sec_text = remaining[:end_m.start()]
    else:
        sec_text = remaining
    return sec_text.strip(), sec_start


def scan_description_experience(desc_text: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """Scan full job description for required experience patterns (Gate 2).

    - Reads only qualifications/requirements section when one can be identified.
    - Elsewhere accepts ONLY candidate-tied phrases ('you have', 'years of experience in', 'minimum of').
    - Ignores company-history phrases ('30+ years of innovation', 'for over 50 years', 'since 19xx').
    - Treats any minimum above 15 years as a parse error: logs warning and treats as 'experience not stated'.
    - Returns (stated_minimum_years, matched_snippet).
    """
    if not desc_text:
        return None, None
    text = unicodedata.normalize("NFKC", str(desc_text).strip())
    if not text:
        return None, None
    text_lower = text.lower()

    sec_info = extract_qualifications_section(text)
    if sec_info:
        scan_text = sec_info[0]
        is_scoped_section = True
    else:
        scan_text = text_lower
        is_scoped_section = False

    candidates: List[Tuple[int, str]] = []

    if is_scoped_section:
        # 1. Range: e.g. "2-5 years", "2 to 5 years", "two to five years"
        for m in re.finditer(
            rf"\b({NUM_WORDS_PATTERN})\s*{DASH_PATTERN}\s*{NUM_WORDS_PATTERN}\s*(?:years?|yrs)(?:\s+(?:of\s+)?experience)?\b",
            scan_text,
            re.IGNORECASE,
        ):
            if is_company_history_phrase(scan_text, m.start(), m.end()):
                continue
            val = parse_num(m.group(1))
            if val is not None:
                if val > 15:
                    logger.warning("Gate 2 parse error: extracted %d years (> 15) from '%s'; treating as experience not stated", val, m.group(0))
                    continue
                candidates.append((val, m.group(0).strip()))

        # 2. Plus: e.g. "2+ years", "2 + years", "two plus years" (years/yrs is required)
        for m in re.finditer(
            rf"\b({NUM_WORDS_PATTERN})\s*(?:\+|plus)\s*(?:years?|yrs)(?:\s+(?:of\s+)?experience)?\b",
            scan_text,
            re.IGNORECASE,
        ):
            start, _ = m.span()
            snippet_before = scan_text[max(0, start - 30):start]
            if re.search(rf"\b{NUM_WORDS_PATTERN}\s*{DASH_PATTERN}\s*$", snippet_before):
                continue
            if is_company_history_phrase(scan_text, m.start(), m.end()):
                continue
            val = parse_num(m.group(1))
            if val is not None:
                if val > 15:
                    logger.warning("Gate 2 parse error: extracted %d years (> 15) from '%s'; treating as experience not stated", val, m.group(0))
                    continue
                candidates.append((val, m.group(0).strip()))

        # 3. Minimum / At least / Requires / Must have
        for m in re.finditer(
            rf"\b(?:minimum|min|at\s+least|requires?|requiring|must\s+have)\s*(?:of\s*)?({NUM_WORDS_PATTERN})\+?\s*(?:years?|yrs)(?:\s+(?:of\s+)?experience)?\b",
            scan_text,
            re.IGNORECASE,
        ):
            start, _ = m.span()
            snippet_before = scan_text[max(0, start - 30):start]
            if re.search(rf"\b{NUM_WORDS_PATTERN}\s*{DASH_PATTERN}\s*$", snippet_before):
                continue
            if is_company_history_phrase(scan_text, m.start(), m.end()):
                continue
            val = parse_num(m.group(1))
            if val is not None:
                if val > 15:
                    logger.warning("Gate 2 parse error: extracted %d years (> 15) from '%s'; treating as experience not stated", val, m.group(0))
                    continue
                candidates.append((val, m.group(0).strip()))

        # 4. "X years of experience required / needed / preferred / mandatory"
        for m in re.finditer(
            rf"\b({NUM_WORDS_PATTERN})\s*(?:years?|yrs)(?:\s+of)?\s+experience\s+(?:required|needed|must\s+have|preferred|mandatory)\b",
            scan_text,
            re.IGNORECASE,
        ):
            start, _ = m.span()
            snippet_before = scan_text[max(0, start - 30):start]
            if re.search(rf"\b{NUM_WORDS_PATTERN}\s*{DASH_PATTERN}\s*$", snippet_before):
                continue
            if is_company_history_phrase(scan_text, m.start(), m.end()):
                continue
            val = parse_num(m.group(1))
            if val is not None:
                if val > 15:
                    logger.warning("Gate 2 parse error: extracted %d years (> 15) from '%s'; treating as experience not stated", val, m.group(0))
                    continue
                candidates.append((val, m.group(0).strip()))
    else:
        # Outside qualifications section: accepts ONLY candidate-tied phrases

        # 1. Candidate subject phrases: e.g. "candidate must have 3+ years", "applicant has two plus years"
        for m in re.finditer(
            rf"\b(?:you|candidate|applicant|individual|engineer|developer)\s+(?:must\s+have|should\s+have|have|has|bring|possess)\s+(?:at\s+least\s+|a\s+minimum\s+of\s+)?({NUM_WORDS_PATTERN})\s*(?:\+|plus)?\s*(?:years?|yrs)\b",
            scan_text,
            re.IGNORECASE,
        ):
            if is_company_history_phrase(scan_text, m.start(), m.end()):
                continue
            val = parse_num(m.group(1))
            if val is not None:
                if val > 15:
                    logger.warning("Gate 2 parse error: extracted %d years (> 15) from '%s'; treating as experience not stated", val, m.group(0))
                    continue
                candidates.append((val, m.group(0).strip()))

        # 2. "you have" phrases
        for m in re.finditer(
            rf"\b(?:you\s+have)\s+(?:a\s+)?(?:minimum\s+of\s+|at\s+least\s+)?({NUM_WORDS_PATTERN})\s*(?:\+|plus)?\s*(?:years?|yrs)\b",
            scan_text,
            re.IGNORECASE,
        ):
            if is_company_history_phrase(scan_text, m.start(), m.end()):
                continue
            val = parse_num(m.group(1))
            if val is not None:
                if val > 15:
                    logger.warning("Gate 2 parse error: extracted %d years (> 15) from '%s'; treating as experience not stated", val, m.group(0))
                    continue
                candidates.append((val, m.group(0).strip()))

        # 3. "minimum of" / "min of" / "at least" / "minimum X years" phrases
        for m in re.finditer(
            rf"\b(?:minimum|min|at\s+least)\s*(?:of\s*)?({NUM_WORDS_PATTERN})\s*(?:\+|plus)?\s*(?:years?|yrs)(?:\s+(?:of\s+)?(?:[\w\-]+\s+){0,3}experience)?\b",
            scan_text,
            re.IGNORECASE,
        ):
            if is_company_history_phrase(scan_text, m.start(), m.end()):
                continue
            val = parse_num(m.group(1))
            if val is not None:
                if val > 15:
                    logger.warning("Gate 2 parse error: extracted %d years (> 15) from '%s'; treating as experience not stated", val, m.group(0))
                    continue
                candidates.append((val, m.group(0).strip()))

        # 4. "requires" and "we need / looking for / seeking" phrases
        for m in re.finditer(
            rf"\b(?:requires?|we\s+need|need|seeking|looking\s+for)\s+(?:at\s+least\s+|a\s+minimum\s+of\s+)?({NUM_WORDS_PATTERN})\s*(?:\+|plus)?\s*(?:years?|yrs)(?:\s+(?:of\s+)?(?:[\w\-]+\s+){0,3}(?:experience|in|with))?\b",
            scan_text,
            re.IGNORECASE,
        ):
            if is_company_history_phrase(scan_text, m.start(), m.end()):
                continue
            val = parse_num(m.group(1))
            if val is not None:
                if val > 15:
                    logger.warning("Gate 2 parse error: extracted %d years (> 15) from '%s'; treating as experience not stated", val, m.group(0))
                    continue
                candidates.append((val, m.group(0).strip()))

        # 5. "years of experience in / with" and "years of experience required"
        for m in re.finditer(
            rf"\b({NUM_WORDS_PATTERN})\+?\s*(?:years?|yrs)(?:\s+of)?(?:\s+(?:[\w\-]+\s+){0,3})experience(?:\s+(?:in|with|using|of|required|needed|must\s+have|mandatory))\b",
            scan_text,
            re.IGNORECASE,
        ):
            start, _ = m.span()
            snippet_before = scan_text[max(0, start - 30):start]
            if re.search(rf"\b{NUM_WORDS_PATTERN}\s*{DASH_PATTERN}\s*$", snippet_before):
                continue
            if is_company_history_phrase(scan_text, m.start(), m.end()):
                continue
            val = parse_num(m.group(1))
            if val is not None:
                if val > 15:
                    logger.warning("Gate 2 parse error: extracted %d years (> 15) from '%s'; treating as experience not stated", val, m.group(0))
                    continue
                candidates.append((val, m.group(0).strip()))

        # 6. Candidate-tied ranges: e.g. "requires 2-5 years", "two to five years of experience required"
        for m in re.finditer(
            rf"\b({NUM_WORDS_PATTERN})\s*{DASH_PATTERN}\s*{NUM_WORDS_PATTERN}\s*(?:years?|yrs)\b",
            scan_text,
            re.IGNORECASE,
        ):
            start, end = m.span()
            snippet_before = scan_text[max(0, start - 40):start]
            snippet_after = scan_text[end:min(len(scan_text), end + 40)]
            # Must be candidate-tied: either 'experience' in adjacent window or candidate marker before it
            if "experience" not in snippet_after and not any(k in snippet_before for k in ["requires", "requiring", "must have", "should have", "with", "for", "candidate", "applicant"]):
                continue
            if is_company_history_phrase(scan_text, start, end):
                continue
            val = parse_num(m.group(1))
            if val is not None:
                if val > 15:
                    logger.warning("Gate 2 parse error: extracted %d years (> 15) from '%s'; treating as experience not stated", val, m.group(0))
                    continue
                full_snippet = scan_text[start:min(len(scan_text), end + 25)].strip()
                candidates.append((val, full_snippet))

    # Check fresher keywords if no candidate requirements found
    if not candidates:
        m_fresher = re.search(r"\b(?:fresher|freshers|entry[- ]level|intern|internship|trainee|0\s*(?:[-–—]|to)\s*1\s*years?)\b", scan_text, re.IGNORECASE)
        if m_fresher:
            return 0, m_fresher.group(0).strip()

    if candidates:
        violating = [c for c in candidates if c[0] > 1]
        if violating:
            best = max(violating, key=lambda x: x[0])
            return best[0], best[1]
        best = min(candidates, key=lambda x: x[0])
        return best[0], best[1]

    return None, None


class JobFilter:
    """Filters job listings based on defined profile rules and criteria."""

    def __init__(
        self,
        profile: JobProfile,
        max_required_min_years: Optional[int] = None,
    ):
        self.profile = profile
        self._explicit_override = max_required_min_years is not None
        # Task 15: use profile-level thresholds if available, else fall back to settings
        if max_required_min_years is not None:
            # Explicit override (used in tests): treat as MATCH threshold
            self.match_max_years = max_required_min_years
            self.review_max_years = max_required_min_years + 1
        else:
            self.match_max_years = getattr(profile, "match_max_years", None) or 2
            self.review_max_years = getattr(profile, "review_max_years", None) or 3
        # Keep backward-compat attribute
        self.max_required_min_years = self.match_max_years

    def is_match(self, job: Job, profile: Optional[JobProfile] = None) -> bool:
        """Evaluate if a single Job listing satisfies user preferences."""
        active_profile = profile or self.profile
        title_lower = (job.title or "").lower()
        location_raw = job.location or ""
        location_norm = unicodedata.normalize("NFC", location_raw)
        location_lower = location_norm.lower()

        # 1. Seniority title exclusion, level title exclusion & negative keyword exclusion
        senior_marker = match_seniority_title(job.title)
        if senior_marker:
            logger.debug(
                "Job '%s' excluded by seniority title marker: '%s'", job.title, senior_marker
            )
            return False

        level_marker = match_level_title(job.title)
        if level_marker:
            logger.debug(
                "Job '%s' excluded by level title marker: '%s'", job.title, level_marker
            )
            return False

        for neg_kw in active_profile.negative_keywords:
            neg_lower = neg_kw.lower().strip()
            if not neg_lower:
                continue

            pattern = r"\b" + re.escape(neg_lower) + r"\b" if neg_lower.isalnum() else re.escape(neg_lower)
            if re.search(pattern, title_lower):
                logger.debug(
                    "Job '%s' excluded by title negative keyword: '%s'", job.title, neg_kw
                )
                return False

        # 1B. Gate 1: Parse minimum years from structured portal fields or job title
        if self._explicit_override and profile is None:
            review_max = self.review_max_years
        else:
            review_max = getattr(active_profile, "review_max_years", None) or self.review_max_years
        gate1_min = parse_structured_experience_min(job.experience_required)
        title_min = parse_title_experience_min(job.title)
        if gate1_min is None:
            gate1_min = title_min
        elif title_min is not None:
            gate1_min = min(gate1_min, title_min)

        if gate1_min is not None and gate1_min > review_max:
            logger.debug(
                "Job '%s' excluded by Gate 1 experience: %s > %d",
                job.title, gate1_min, review_max,
            )
            return False

        # 1C. Gate 2: Scan full description for experience patterns
        gate2_min = scan_description_experience_min(job.description)
        if gate2_min is not None and gate2_min > self.review_max_years:
            logger.debug(
                "Job '%s' excluded by Gate 2 description experience: %d > %d",
                job.title, gate2_min, self.review_max_years,
            )
            return False

        # 2. Remote check (India-eligible remote)
        is_hp_deloitte = is_hp_or_deloitte_source(job)
        if not is_hp_deloitte:
            is_job_remote = is_india_eligible_remote(location_norm)
            if self.profile.remote_only and not is_job_remote:
                logger.debug("Job '%s' excluded because not India-eligible remote", job.title)
                return False

            if not self.profile.preferences.remote_allowed and is_job_remote:
                logger.debug("Job '%s' excluded because remote is not allowed", job.title)
                return False

        # 3. Below-profile title check (intern/trainee/apprentice -> REJECT regardless of preferences)
        below_marker = match_below_profile_title(job.title)
        if below_marker:
            logger.debug("Job '%s' excluded by below-profile title marker: '%s'", job.title, below_marker)
            return False

        # 4. Target role match (title contains any role token/term with word boundary awareness)
        # Task 16: ROLE_FILTER=off applies ONLY to HP and Deloitte sources
        if not is_hp_deloitte and active_profile.target_roles:
            role_matched = False
            for role in active_profile.target_roles:
                role_clean = role.strip()
                if not role_clean:
                    continue
                role_lower = role_clean.lower()

                # Check 1: Exact phrase with word boundaries
                if re.search(r"\b" + re.escape(role_lower) + r"\b", title_lower):
                    role_matched = True
                    break

                # Check 2: All constituent tokens appear with word boundaries
                role_tokens = [t for t in re.split(r"[\s\-_/]+", role_lower) if t]
                if len(role_tokens) > 1 and all(
                    re.search(r"\b" + re.escape(t) + r"\b", title_lower) for t in role_tokens
                ):
                    role_matched = True
                    break

            if not role_matched:
                logger.debug("Job '%s' does not match any target roles", job.title)
                return False

        # 5. Location match (if locations specified)
        # Task 16: ENTRY_LEVEL_LOCATION_SCOPE=all applies ONLY to HP and Deloitte sources
        if not is_hp_deloitte and active_profile.preferred_locations and not (active_profile.remote_only and is_job_remote):
            is_loc_matched = False
            # Check if remote matches allowed remote and is India-eligible
            if is_job_remote and active_profile.preferences.remote_allowed:
                is_loc_matched = True
            elif location_lower and location_lower not in ("unknown", "none", "n/a", "not specified"):
                unrelated_cities = {
                    "mumbai", "pune", "hyderabad", "chennai", "kolkata", "jaipur",
                    "lucknow", "chandigarh", "kochi", "indore", "bhopal", "gurgaon",
                    "gurugram", "nagpur", "patna", "bhubaneswar", "visakhapatnam",
                    "trivandrum", "coimbatore", "surat", "vadodara", "london", "singapore",
                    "new york", "berlin", "tokyo", "sydney", "dubai", "toronto"
                }
                has_unrelated_city = any(re.search(r"\b" + re.escape(c) + r"\b", location_lower) for c in unrelated_cities)

                for pref_loc in active_profile.preferred_locations:
                    p_low = pref_loc.lower().strip()
                    if p_low == "remote":
                        continue
                    if p_low in ("bangalore", "bengaluru") and ("bangalore" in location_lower or "bengaluru" in location_lower):
                        is_loc_matched = True
                        break
                    if p_low == "india":
                        if not has_unrelated_city and re.search(r"\b(india|pan[- ]india|all[- ]india)\b", location_lower):
                            is_loc_matched = True
                            break
                    elif re.search(r"\b" + re.escape(p_low) + r"\b", location_lower):
                        is_loc_matched = True
                        break

            if not is_loc_matched:
                logger.debug(
                    "Job '%s' location '%s' does not match preferred locations",
                    job.title,
                    job.location,
                )
                return False

        # 6. Employment type check if available on the job
        if job.employment_type and active_profile.employment_types:
            job_emp_type = job.employment_type.lower()
            emp_matched = any(
                emp.lower() in job_emp_type for emp in active_profile.employment_types
            )
            if not emp_matched:
                logger.debug(
                    "Job '%s' employment type '%s' does not match preferences",
                    job.title,
                    job.employment_type,
                )
                return False

        return True

    def filter_jobs(self, jobs: List[Job], profile: Optional[JobProfile] = None) -> List[Job]:
        """Filter a list of Job instances according to profile rules."""
        matched_jobs: List[Job] = []
        for job in jobs:
            if self.is_match(job, profile=profile):
                matched_jobs.append(job)
        logger.info(
            "Filtered %d listings down to %d matching jobs",
            len(jobs),
            len(matched_jobs),
        )
        return matched_jobs

    def classify_job(self, job: Job, profile: Optional[JobProfile] = None) -> tuple[str, str]:
        """Classify a single Job into MATCH, REVIEW, or REJECT with a deterministic rationale.

        - REJECT: Fails profile filters (senior title/keywords, explicit 5+ yrs experience,
                  excluded location, role mismatch, or non-India remote).
        - REVIEW: Passes role and location filters, but experience is intermediate (e.g. 2-5 yrs)
                  or unspecified/ambiguous, requiring manual verification.
        - MATCH:  Passes role and location filters, and explicitly satisfies fresher, intern,
                  entry-level, or 0-2 years experience criteria.

        Returns:
            Tuple of (decision: str, reason: str) where decision in ('MATCH', 'REVIEW', 'REJECT').
            Also populates job.extra_metadata['decision'] and job.extra_metadata['decision_reason'].
        """
        active_profile = profile or self.profile
        if self._explicit_override and profile is None:
            match_max = self.match_max_years
            review_max = self.review_max_years
        else:
            match_max = getattr(active_profile, "match_max_years", None) or self.match_max_years
            review_max = getattr(active_profile, "review_max_years", None) or self.review_max_years

        title_lower = (job.title or "").lower()
        location_raw = job.location or ""
        location_norm = unicodedata.normalize("NFC", location_raw)
        location_lower = location_norm.lower()

        failing_reasons: List[Tuple[str, str]] = []

        # Task 16: ENTRY_LEVEL_LOCATION_SCOPE=all and ROLE_FILTER=off apply ONLY to HP and Deloitte
        is_hp_deloitte = is_hp_or_deloitte_source(job)

        # Location check
        is_job_remote = is_india_eligible_remote(location_norm)
        if not is_hp_deloitte and active_profile.preferred_locations and not (active_profile.remote_only and is_job_remote):
            is_loc_matched = False
            if is_job_remote and active_profile.preferences.remote_allowed:
                is_loc_matched = True
            elif location_lower and location_lower not in ("unknown", "none", "n/a", "not specified"):
                unrelated_cities = {
                    "mumbai", "pune", "hyderabad", "chennai", "kolkata", "jaipur",
                    "lucknow", "chandigarh", "kochi", "indore", "bhopal", "gurgaon",
                    "gurugram", "nagpur", "patna", "bhubaneswar", "visakhapatnam",
                    "trivandrum", "coimbatore", "surat", "vadodara", "london", "singapore",
                    "new york", "berlin", "tokyo", "sydney", "dubai", "toronto"
                }
                has_unrelated_city = any(re.search(r"\b" + re.escape(c) + r"\b", location_lower) for c in unrelated_cities)
                for pref_loc in active_profile.preferred_locations:
                    p_low = pref_loc.lower().strip()
                    if p_low == "remote":
                        continue
                    if p_low in ("bangalore", "bengaluru") and ("bangalore" in location_lower or "bengaluru" in location_lower):
                        is_loc_matched = True
                        break
                    if p_low == "india":
                        if not has_unrelated_city and re.search(r"\b(india|pan[- ]india|all[- ]india)\b", location_lower):
                            is_loc_matched = True
                            break
                    elif re.search(r"\b" + re.escape(p_low) + r"\b", location_lower):
                        is_loc_matched = True
                        break

            if not is_loc_matched:
                failing_reasons.append(("location", f"Location '{job.location or 'Not Specified'}' is not in preferred locations"))

        # Check title seniority markers & level titles & negative keywords
        senior_marker = match_seniority_title(job.title)
        if senior_marker:
            failing_reasons.append((f"seniority title: {senior_marker}", f"Title contains senior/negative keyword: '{senior_marker}'"))

        level_marker = match_level_title(job.title)
        if level_marker:
            failing_reasons.append((f"level title: {level_marker}", f"Title contains non-entry level marker: '{level_marker}'"))

        # Below-profile title check (intern/trainee/apprentice)
        below_marker = match_below_profile_title(job.title)
        if below_marker:
            failing_reasons.append(("below profile level", f"below profile level: '{below_marker}'"))

        for neg_kw in active_profile.negative_keywords:
            neg_clean = neg_kw.lower().strip()
            if not neg_clean:
                continue
            pattern = r"\b" + re.escape(neg_clean) + r"\b" if neg_clean.isalnum() else re.escape(neg_clean)
            if re.search(pattern, title_lower):
                failing_reasons.append((f"negative keyword: {neg_kw}", f"Title contains senior/negative keyword: '{neg_kw}'"))

        # Gate 1 - parse minimum years from structured portal fields or job title
        gate1_min = parse_structured_experience_min(job.experience_required)
        title_min = parse_title_experience_min(job.title)
        if gate1_min is None:
            gate1_min = title_min
        elif title_min is not None:
            gate1_min = min(gate1_min, title_min)

        if gate1_min is not None and gate1_min > review_max:
            failing_reasons.append((f"Gate 1: requires {gate1_min}+ years", f"requires {gate1_min}+ years"))

        # Gate 2 - scan description for experience patterns
        gate2_min, gate2_snippet = scan_description_experience(job.description)
        if gate2_min is not None and gate2_min > review_max:
            snip_str = f" ('{gate2_snippet}')" if gate2_snippet else ""
            failing_reasons.append((f"Gate 2: requires {gate2_min}+ years", f"requires {gate2_min}+ years{snip_str}"))

        # Remote check
        if not is_hp_deloitte:
            if active_profile.remote_only and not is_job_remote:
                failing_reasons.append(("remote", "Remote location is not India-eligible"))
            elif not active_profile.preferences.remote_allowed and is_job_remote:
                failing_reasons.append(("remote", "Remote roles are not permitted by profile preferences"))

        # Internship check
        is_internship = "intern" in title_lower or "internship" in title_lower
        if is_internship and not active_profile.preferences.internship_allowed:
            failing_reasons.append(("internship", "Internships are not permitted by profile preferences"))

        # Target role match
        matched_target_role = None
        if active_profile.target_roles:
            role_matched = False
            for role in active_profile.target_roles:
                role_clean = role.strip()
                if not role_clean:
                    continue
                role_lower = role_clean.lower()
                if re.search(r"\b" + re.escape(role_lower) + r"\b", title_lower):
                    role_matched = True
                    matched_target_role = role_clean
                    break
                role_tokens = [t for t in re.split(r"[\s\-_/]+", role_lower) if t]
                if len(role_tokens) > 1 and all(
                    re.search(r"\b" + re.escape(t) + r"\b", title_lower) for t in role_tokens
                ):
                    role_matched = True
                    matched_target_role = role_clean
                    break

            if not role_matched and not is_hp_deloitte:
                failing_reasons.append(("target roles", f"Title '{job.title}' does not match target roles"))
            elif is_hp_deloitte and not matched_target_role:
                matched_target_role = job.title

        # Employment type check
        if job.employment_type and active_profile.employment_types:
            job_emp_type = job.employment_type.lower()
            emp_matched = any(
                emp.lower() in job_emp_type for emp in active_profile.employment_types
            )
            if not emp_matched:
                failing_reasons.append(("employment type", f"Employment type '{job.employment_type}' does not match preferences"))

        # If any rules failed, record REJECT with all failing rules
        if failing_reasons:
            decision = "REJECT"
            primary_reason = failing_reasons[0][1]
            failing_rule_tags = [item[0] for item in failing_reasons]
            all_failing_str = "; ".join(failing_rule_tags)
            self._record_classification(
                job,
                decision,
                primary_reason,
                all_failing_rules=all_failing_str,
                excluded_reasons=[item[1] for item in failing_reasons],
            )
            return decision, primary_reason

        # Step 9: Experience Evaluation (MATCH vs REVIEW vs REJECT)
        # Gate 1: structured field or title
        gate1_min_classify = parse_structured_experience_min(job.experience_required)
        title_min_classify = parse_title_experience_min(job.title)
        if gate1_min_classify is None:
            gate1_min_classify = title_min_classify
        elif title_min_classify is not None:
            gate1_min_classify = min(gate1_min_classify, title_min_classify)

        # Gate 2: description
        gate2_min_classify, gate2_snippet_classify = scan_description_experience(job.description)

        # Pick the most constraining gate that actually found something
        stated_min = None
        stated_snippet = None
        if gate1_min_classify is not None and gate2_min_classify is not None:
            if gate2_min_classify > gate1_min_classify:
                stated_min = gate2_min_classify
                stated_snippet = gate2_snippet_classify
            else:
                stated_min = gate1_min_classify
                stated_snippet = None
        elif gate1_min_classify is not None:
            stated_min = gate1_min_classify
            stated_snippet = None
        elif gate2_min_classify is not None:
            stated_min = gate2_min_classify
            stated_snippet = gate2_snippet_classify

        role_label = matched_target_role or job.title

        # No failing rules — now classify by experience
        if stated_min is not None:
            if stated_min <= match_max:
                decision = "MATCH"
                snip_str = f" ('{stated_snippet}')" if stated_snippet else ""
                reason = f"Eligible: Stated minimum {stated_min} years{snip_str} matches criteria for '{role_label}'"
            elif stated_min <= review_max:
                decision = "REVIEW"
                snip_str = f" ('{stated_snippet}')" if stated_snippet else ""
                reason = f"stretch: asks {stated_min} years{snip_str}"
            else:
                # > review_max — REJECT (this case is also caught in failing_reasons above, but belt+suspenders)
                decision = "REJECT"
                reason = f"requires {stated_min}+ years"
                self._record_classification(job, decision, reason, all_failing_rules=f"Gate: requires {stated_min}+ years", excluded_reasons=[reason])
                return decision, reason
        else:
            # Experience not stated anywhere
            decision = "REVIEW"
            reason = "experience not stated"

        # Work authorization flag
        has_work_auth = False
        if job.description and WORK_AUTH_PATTERN.search(job.description):
            has_work_auth = True
            if not reason.endswith("; check work-authorization requirement"):
                reason = f"{reason}; check work-authorization requirement"

        self._record_classification(job, decision, reason, all_failing_rules="")
        if has_work_auth:
            if job.extra_metadata is None:
                job.extra_metadata = {}
            job.extra_metadata["work_auth_flag"] = True

        return decision, reason

    def _record_classification(
        self,
        job: Job,
        decision: str,
        reason: str,
        all_failing_rules: Optional[str] = None,
        excluded_reasons: Optional[List[str]] = None,
    ) -> None:
        """Helper to attach decision, decision_reason, and all_failing_rules to Job metadata."""
        if job.extra_metadata is None:
            job.extra_metadata = {}
        job.extra_metadata["decision"] = decision
        job.extra_metadata["decision_reason"] = reason

        if all_failing_rules is not None:
            job.extra_metadata["all_failing_rules"] = all_failing_rules
        elif decision == "REJECT":
            job.extra_metadata["all_failing_rules"] = reason
        else:
            job.extra_metadata["all_failing_rules"] = ""

        if excluded_reasons:
            for r in excluded_reasons:
                if r not in job.excluded_reasons:
                    job.excluded_reasons.append(r)
        elif decision == "REJECT" and reason not in job.excluded_reasons:
            job.excluded_reasons.append(reason)
