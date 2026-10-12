"""Prototype and verify matcher refinements and regression test cases."""

import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.job import Job
from app.models.profile import JobProfile
from app.config.settings import get_settings

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

EXPLICIT_EXP_PATTERNS = [
    r"\b(?:minimum|min|at least|requires?|requiring|\+)\s*(?:5|6|7|8|9|10)\+?\s*years(?:\s+of)?\s+experience\b",
    r"\b(?:5|7|10)\+\s*years(?:\s+of)?\s+experience\s+(?:required|needed|must have)\b",
    r"\b(?:5|7|10)\+\s*years(?:\s+of)?\s+experience\b",
]

def is_india_eligible_remote(location: str | None) -> bool:
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
    return True

def has_explicit_seniority_experience(text: str) -> bool:
    if not text:
        return False
    t_lower = text.lower()
    return any(re.search(pat, t_lower) for pat in EXPLICIT_EXP_PATTERNS)

def check_negative_exclusion(job: Job, profile: JobProfile) -> tuple[bool, list[str]]:
    title_lower = (job.title or "").lower()
    desc_lower = (job.description or "").lower()
    exp_lower = (job.experience_required or "").lower()

    title_role_negatives = {"senior", "lead", "staff", "principal", "manager", "director", "architect", "vp", "head of"}
    reasons = []

    for neg in profile.negative_keywords:
        neg_clean = neg.strip().lower()
        if not neg_clean:
            continue
        pattern = r"\b" + re.escape(neg_clean) + r"\b" if neg_clean.isalnum() else re.escape(neg_clean)

        # 1. Check title
        if re.search(pattern, title_lower):
            reasons.append(f"Title contains negative keyword: '{neg}'")

        # 2. Check structured experience field
        elif exp_lower and re.search(pattern, exp_lower):
            reasons.append(f"Experience required contains negative keyword: '{neg}'")

        # 3. Explicit experience requirement in description
        elif neg_clean in ("5+ years", "7+ years", "10+ years") and has_explicit_seniority_experience(desc_lower):
            reasons.append(f"Description requires senior experience: '{neg}'")

    is_excluded = len(reasons) > 0
    return is_excluded, reasons

def test_regressions():
    profile = get_settings().load_profile()
    
    test_cases = [
        # Must pass
        (Job(title="Junior Backend Engineer", description="You will work closely with senior engineers.", url="http://test/1", company="TestCo", source="lever"), True, "Junior Backend Engineer"),
        (Job(title="Backend Engineer", description="Reports to the Engineering Manager.", url="http://test/2", company="TestCo", source="lever"), True, "Backend Engineer"),
        (Job(title="Software Engineer", description="Collaborate with technical leads.", url="http://test/3", company="TestCo", source="lever"), True, "Software Engineer"),
        (Job(title="Software Engineer", description="Our team has over 10 years of experience building scalable systems.", url="http://test/4", company="TestCo", source="lever"), True, "10 years team exp"),
        # Must fail
        (Job(title="Senior Software Engineer", description="Normal coding job.", url="http://test/5", company="TestCo", source="lever"), False, "Senior in title"),
        (Job(title="Staff Backend Engineer", description="Normal coding job.", url="http://test/6", company="TestCo", source="lever"), False, "Staff in title"),
        (Job(title="Engineering Manager", description="Leading a team.", url="http://test/7", company="TestCo", source="lever"), False, "Manager in title"),
        (Job(title="Principal Software Engineer", description="Technical strategy.", url="http://test/8", company="TestCo", source="lever"), False, "Principal in title"),
        (Job(title="Software Engineer", description="Must have 5+ years of experience required in backend systems.", url="http://test/9", company="TestCo", source="lever"), False, "5+ years explicit exp"),
        (Job(title="Software Engineer", experience_required="5+ years", description="Coding job.", url="http://test/10", company="TestCo", source="lever"), False, "5+ years in experience_required"),
    ]

    print("Running Regression Test Cases:")
    all_ok = True
    for job, should_pass, label in test_cases:
        is_excl, reasons = check_negative_exclusion(job, profile)
        passed = not is_excl
        status = "PASS" if passed == should_pass else "FAIL"
        if status == "FAIL":
            all_ok = False
        print(f"  [{status}] {label:28} -> Expected Pass: {should_pass}, Actual Pass: {passed} (Reasons: {reasons})")

    print("\nAll Regression Tests Passed:", all_ok)

if __name__ == "__main__":
    test_regressions()
