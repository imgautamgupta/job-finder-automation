import re
import unicodedata
from typing import Optional, Tuple

WORD_TO_NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20,
}

NUM_WORDS_PATTERN = r"(?:\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
DASH_PATTERN = r"(?:[\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]|to)"

def parse_num(val: str) -> Optional[int]:
    v = val.strip().lower()
    if v.isdigit():
        return int(v)
    return WORD_TO_NUM.get(v)

def parse_structured_experience_min(exp_text: Optional[str]) -> Optional[int]:
    """Parse minimum required years from structured portal field (Gate 1).
    Returns integer minimum years, or None if no experience info stated.
    """
    if not exp_text:
        return None
    text = unicodedata.normalize("NFKC", exp_text.strip().lower())
    if text in ("", "none", "null", "not specified", "unspecified", "n/a", "unknown", "na"):
        return None

    # Check fresher/intern/entry-level keywords
    if re.search(r"\b(?:fresher|freshers|entry[- ]level|intern|internship|trainee|graduate)\b", text):
        return 0

    # Range pattern: e.g. "2-5 years", "2 - 5 yrs", "2 to 5 years", "two to five years"
    range_match = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*{DASH_PATTERN}\s*{NUM_WORDS_PATTERN}\s*(?:years?|yrs)?\b",
        text
    )
    if range_match:
        val = parse_num(range_match.group(1))
        if val is not None:
            return val

    # Plus pattern: e.g. "2+ years", "2 + yrs", "two plus years"
    plus_match = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*(?:\+|plus)\s*(?:years?|yrs)?\b",
        text
    )
    if plus_match:
        val = parse_num(plus_match.group(1))
        if val is not None:
            return val

    # Minimum / At least pattern: e.g. "minimum 3 years", "at least 2 years"
    min_match = re.search(
        rf"\b(?:minimum|min|at\s+least)\s*(?:of\s*)?({NUM_WORDS_PATTERN})\+?\s*(?:years?|yrs)?\b",
        text
    )
    if min_match:
        val = parse_num(min_match.group(1))
        if val is not None:
            return val

    # Standalone: e.g. "3 years", "1 year", "two years"
    single_match = re.search(
        rf"\b({NUM_WORDS_PATTERN})\s*(?:years?|yrs)\b",
        text
    )
    if single_match:
        val = parse_num(single_match.group(1))
        if val is not None:
            return val

    # Standalone digits e.g. "0-2" or "2"
    digits_range = re.search(rf"\b({NUM_WORDS_PATTERN})\s*{DASH_PATTERN}\s*{NUM_WORDS_PATTERN}\b", text)
    if digits_range:
        val = parse_num(digits_range.group(1))
        if val is not None:
            return val

    return None


def scan_description_experience_min(desc_text: Optional[str]) -> Optional[int]:
    """Scan full job description for required experience patterns (Gate 2).
    Returns stated minimum years, or None if no experience requirements detected.
    """
    if not desc_text:
        return None
    text = unicodedata.normalize("NFKC", desc_text.strip().lower())
    if not text:
        return None

    # We want to identify candidate experience requirements while avoiding company history
    # (e.g. "our team has 10 years of experience", "company founded 5 years ago")

    candidates = []

    # 1. Range: e.g. "2-5 years", "2–5 years", "2 to 5 years", "two to five years"
    # followed by or preceded by experience indicators
    for m in re.finditer(
        rf"\b({NUM_WORDS_PATTERN})\s*{DASH_PATTERN}\s*{NUM_WORDS_PATTERN}\s*(?:years?|yrs)?(?:\s+(?:of\s+)?experience)?\b",
        text
    ):
        start, end = m.span()
        # Context check: avoid "founded X years ago", "over the past X-Y years"
        snippet_before = text[max(0, start - 30):start]
        if "founded" in snippet_before or "past" in snippet_before or "last" in snippet_before:
            continue
        val = parse_num(m.group(1))
        if val is not None:
            candidates.append(val)

    # 2. Plus: e.g. "2+ years", "2 + years", "two plus years"
    for m in re.finditer(
        rf"\b({NUM_WORDS_PATTERN})\s*(?:\+|plus)\s*(?:years?|yrs)?(?:\s+(?:of\s+)?experience)?\b",
        text
    ):
        start, end = m.span()
        snippet_before = text[max(0, start - 30):start]
        if "founded" in snippet_before or "past" in snippet_before or "last" in snippet_before:
            continue
        val = parse_num(m.group(1))
        if val is not None:
            candidates.append(val)

    # 3. Minimum / At least / Requires:
    # e.g. "minimum 3 years", "at least 2 years", "requires 2 years"
    for m in re.finditer(
        rf"\b(?:minimum|min|at\s+least|requires?|requiring|must\s+have)\s*(?:of\s*)?({NUM_WORDS_PATTERN})\+?\s*(?:years?|yrs)?(?:\s+(?:of\s+)?experience)?\b",
        text
    ):
        start, end = m.span()
        snippet_before = text[max(0, start - 30):start]
        if "team has" in snippet_before or "company" in snippet_before:
            continue
        val = parse_num(m.group(1))
        if val is not None:
            candidates.append(val)

    # 4. "X years of experience required / needed"
    for m in re.finditer(
        rf"\b({NUM_WORDS_PATTERN})\s*(?:years?|yrs)(?:\s+of)?\s+experience\s+(?:required|needed|must\s+have|preferred|mandatory)\b",
        text
    ):
        start, end = m.span()
        snippet_before = text[max(0, start - 30):start]
        if "team has" in snippet_before or "company" in snippet_before:
            continue
        val = parse_num(m.group(1))
        if val is not None:
            candidates.append(val)

    # 5. Explicit fresher in description:
    if not candidates:
        if re.search(r"\b(?:fresher|freshers|entry[- ]level|intern|internship|trainee|0\s*(?:[-–—]|to)\s*1\s*years?)\b", text):
            return 0

    if candidates:
        # If any candidate requirement states a minimum experience, what is the stated minimum?
        # If there are multiple, e.g. "2-5 years experience", candidate is 2.
        # If there are multiple requirements, the strictest requirement or the first requirement?
        # If any requirement > MAX_REQUIRED_MIN_YEARS, it violates the requirement!
        # Let's return max(candidates) if any > MAX_REQUIRED_MIN_YEARS, or min(candidates).
        # Specifically, if any requirement is > MAX_REQUIRED_MIN_YEARS, we want to know about it.
        violating = [c for c in candidates if c > 1]
        if violating:
            return max(violating)
        return min(candidates)

    return None

test_cases = [
    ("2-5 years", 2),
    ("2–5 years", 2), # en dash
    ("2—5 years", 2), # em dash
    ("2−5 years", 2), # minus
    ("two to five years", 2),
    ("2+ years", 2),
    ("2+ yrs", 2),
    ("two plus years", 2),
    ("minimum 3 years", 3),
    ("at least 2 years", 2),
    ("0-2 years", 0),
    ("0–1 years", 0),
    ("1-3 years", 1),
    ("1 year", 1),
    ("Fresher", 0),
    ("Not Specified", None),
    (None, None),
]

print("=== Structured Tests ===")
for text, expected in test_cases:
    actual = parse_structured_experience_min(text)
    print(f"{ascii(text)} -> {actual} (expected {expected}) {'OK' if actual == expected else 'FAIL'}")

print("\n=== Description Tests ===")
desc_cases = [
    ("We require 2+ years of experience in Python.", 2),
    ("Minimum 3 years of hands-on React development.", 3),
    ("At least 2 years in backend systems.", 2),
    ("Candidate should have 2-5 years experience.", 2),
    ("Candidate should have two to five years experience.", 2),
    ("Must have 2–5 years experience with PostgreSQL.", 2), # en-dash
    ("Must have 2—5 years experience.", 2), # em-dash
    ("Must have 2−5 years experience.", 2), # minus
    ("Looking for freshers and entry-level candidates.", 0),
    ("Our team has over 10 years of experience in AI.", None),
    ("Founded 5 years ago, we are growing fast.", None),
    ("General backend development without mentioning years.", None),
]
for text, expected in desc_cases:
    actual = scan_description_experience_min(text)
    print(f"{ascii(text[:40])}... -> {actual} (expected {expected}) {'OK' if actual == expected else 'FAIL'}")
