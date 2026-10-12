"""Test prototype of is_india_eligible_remote against all 65 remote location strings."""

import re
from typing import Optional

FOREIGN_REGIONS = [
    r"\bus\b", r"\busa\b", r"\bunited states\b", r"\bcanada\b", r"\buk\b",
    r"\bunited kingdom\b", r"\bengland\b", r"\bpoland\b", r"\bgermany\b",
    r"\bfrance\b", r"\bspain\b", r"\bireland\b", r"\bestonia\b", r"\bcolombia\b",
    r"\bbrazil\b", r"\bmexico\b", r"\bturkey\b", r"\btrkiye\b", r"\btürkiye\b",
    r"\baustralia\b", r"\bjapan\b", r"\bsweden\b", r"\bnetherlands\b",
    r"\bemea\b", r"\blatam\b", r"\btoronto\b", r"\bvancouver\b", r"\blondon\b",
    r"\bberlin\b", r"\bparis\b", r"\bdenver\b", r"\batlanta\b", r"\baustin\b",
    r"\bsan francisco\b", r"\bseattle\b", r"\bchicago\b", r"\bnew york\b",
    r"\bflorida\b", r"\bcalifornia\b", r"\bcolorado\b", r"\btexas\b"
]

INDIA_REGIONS = [
    r"\bindia\b", r"\bbangalore\b", r"\bbengaluru\b", r"\bdelhi\b",
    r"\bnoida\b", r"\bahmedabad\b", r"\bmumbai\b", r"\bpune\b",
    r"\bhyderabad\b", r"\bchennai\b", r"\bgurgaon\b", r"\bgurugram\b"
]

WORLDWIDE_PATTERNS = [
    r"\bworldwide\b", r"\bglobally\b", r"\bglobal remote\b",
    r"\banywhere in the world\b", r"\bwork from anywhere\b"
]

def is_india_eligible_remote(location: Optional[str]) -> bool:
    if not location or not location.strip():
        return False
    loc_lower = location.strip().lower()
    if "remote" not in loc_lower and "anywhere" not in loc_lower and "distributed" not in loc_lower:
        return False

    has_india = any(re.search(pat, loc_lower) for pat in INDIA_REGIONS)
    is_worldwide = any(re.search(pat, loc_lower) for pat in WORLDWIDE_PATTERNS)
    has_foreign = any(re.search(pat, loc_lower) for pat in FOREIGN_REGIONS)

    if has_india:
        return True
    if is_worldwide and not has_foreign:
        return True
    if has_foreign:
        return False
    # If location is simply "Remote" or "Remote, Distributed" without any country restrictions
    return True

# Test against the distinct strings
test_cases = [
    ("Bangalore, India - Remote", True),
    ("Remote, India; India", True),
    ("Remote - India", True),
    ("India - Remote", True),
    ("Bangalore, India; India - Remote", True),
    ("Delhi, India - Remote; Bangalore, India - Remote", True),
    ("Ankara, Türkiye - Remote; Delhi, India - Remote", True),
    ("Remote Globally", True),
    ("Remote - Worldwide", True),
    ("Remote", True),
    ("Remote, Canada; Remote, Poland; Remote, United Kingdom", False),
    ("Remote - US", False),
    ("Mexico City, Mexico - Remote", False),
    ("Ankara, Türkiye - Remote", False),
    ("Remote - Colombia", False),
    ("Remote, United States", False),
    ("Remote - Ireland", False),
    ("Remote - Spain", False),
    ("Remote - Germany", False),
    ("London, England - Remote", False),
    ("São Paulo, Brazil - Remote", False),
    ("None", False),
    ("", False),
    ("Mumbai, India", False), # Not remote
]

def run_tests():
    all_passed = True
    for loc, expected in test_cases:
        actual = is_india_eligible_remote(loc)
        status = "PASS" if actual == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"[{status}] '{loc}' -> Expected: {expected}, Got: {actual}")
    print("\nAll passed:", all_passed)

if __name__ == "__main__":
    run_tests()
