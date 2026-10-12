"""Deterministic, explainable job matching and scoring service."""

import logging
import re
from typing import List, Optional, Set, Tuple
import unicodedata

from app.models.job import Job
from app.models.match import MatchResult
from app.models.profile import JobProfile

logger = logging.getLogger(__name__)


def get_score_category(score: int) -> str:
    """Map a numerical score (0-100) to its qualitative category."""
    if score >= 90:
        return "Excellent"
    elif score >= 80:
        return "Strong"
    elif score >= 70:
        return "Good"
    elif score >= 60:
        return "Possible"
    else:
        return "Not Relevant"


FOREIGN_REGIONS = [
    r"\bus\b", r"\busa\b", r"\bunited states\b", r"\bcanada\b", r"\buk\b",
    r"\bunited kingdom\b", r"\bengland\b", r"\bpoland\b", r"\bgermany\b",
    r"\bfrance\b", r"\bspain\b", r"\bireland\b", r"\bestonia\b", r"\bcolombia\b",
    r"\bbrazil\b", r"\bmexico\b", r"\bturkey\b", r"\btrkiye\b", r"\bt\u00fcrkiye\b",
    r"\bturkiye\b",  # ASCII fallback for encoding-corrupted Türkiye locations
    r"\bt\ufffdrkiye\b",  # Corrupted replacement character fallback
    r"\bankara\b", r"\bistanbul\b",  # Major Turkish cities
    r"\baustralia\b", r"\bjapan\b", r"\bsweden\b", r"\bnetherlands\b",
    r"\bemea\b", r"\blatam\b", r"\btoronto\b", r"\bvancouver\b", r"\blondon\b",
    r"\bberlin\b", r"\bparis\b", r"\bdenver\b", r"\batlanta\b", r"\baustin\b",
    r"\bsan francisco\b", r"\bseattle\b", r"\bchicago\b", r"\bnew york\b",
    r"\bflorida\b", r"\bcalifornia\b", r"\bcolorado\b", r"\btexas\b",
    # Additional foreign regions missing from original list (Bug B fix)
    r"\bsingapore\b", r"\bkorea\b", r"\buae\b", r"\bsouth africa\b",
    r"\bnew zealand\b", r"\bphilippines\b", r"\bvietnam\b", r"\bthailand\b",
    r"\bindonesia\b", r"\bmalaysia\b",
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

EXPLICIT_SENIORITY_EXP_PATTERNS = [
    r"\b(?:minimum|min|at least|requires?|requiring|\+)\s*(?:5|6|7|8|9|10)\+?\s*years(?:\s+of)?\s+experience\b",
    r"\b(?:5|7|10)\+\s*years(?:\s+of)?\s+experience\s+(?:required|needed|must have)\b",
    r"\b(?:5|7|10)\+\s*years(?:\s+of)?\s+experience\b",
]


def is_india_eligible_remote(location: Optional[str]) -> bool:
    """Determine if a job location represents an India-eligible or worldwide remote opportunity."""
    if not location or not location.strip():
        return False
    loc_norm = unicodedata.normalize("NFC", location.strip())
    loc_lower = loc_norm.lower()
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

    # Check for qualified remote (e.g. "Remote - <Region>", "<Region> - Remote",
    # "Remote in <Region>", "Remote, <Region>", "Remote (<Region>)").
    # If a region is specified that is not India and not Worldwide, reject.
    # Bare "Remote", "Fully Remote", "Work from Anywhere", etc. remain eligible.
    if (
        re.search(r"remote\s*[-–—,/]\s*\S", loc_lower)
        or re.search(r"\S\s*[-–—,/]\s*remote", loc_lower)
        or re.search(r"remote\s+(?:in|within)\s+\S", loc_lower)
        or re.search(r"remote\s*\([^)]+\)", loc_lower)
    ):
        return False
    return True


def has_explicit_seniority_experience(text: Optional[str]) -> bool:
    """Check if text contains explicit high-seniority experience requirement (e.g. 5+ years required)."""
    if not text:
        return False
    t_lower = text.lower()
    return any(re.search(pat, t_lower) for pat in EXPLICIT_SENIORITY_EXP_PATTERNS)


class JobMatcher:
    """Deterministic, explainable scoring engine calculating alignment between a Job and JobProfile.

    Score Breakdown (Total: 100 points):
    - Role/Title match: 40 points
    - Skills/Keywords match: 30 points
    - Location match: 20 points
    - Experience match: 10 points
    """

    def __init__(self, profile: JobProfile):
        self.profile = profile

    def match(self, job: Job, profile: Optional[JobProfile] = None) -> MatchResult:
        """Calculate complete matching breakdown for a given job.

        Args:
            job: The standardized Job model instance.
            profile: Optional override for the JobProfile (defaults to self.profile).

        Returns:
            MatchResult containing scores, category, and matched entity details.
        """
        active_profile = profile or self.profile

        title_text = job.title or ""
        desc_text = job.description or ""
        exp_text = job.experience_required or ""
        loc_text = job.location or ""
        combined_text = f"{title_text} {desc_text} {exp_text}".strip()

        excluded_reasons: List[str] = []

        # 1. Negative Keyword Evaluation
        has_negative_title = False
        for neg_kw in active_profile.negative_keywords:
            neg_clean = neg_kw.strip().lower()
            if not neg_clean:
                continue

            pattern = r"\b" + re.escape(neg_clean) + r"\b" if neg_clean.isalnum() else re.escape(neg_clean)

            if re.search(pattern, title_text.lower()):
                has_negative_title = True
                excluded_reasons.append(f"Title contains negative keyword: '{neg_kw}'")
            elif exp_text and re.search(pattern, exp_text.lower()):
                excluded_reasons.append(f"Experience required contains negative keyword: '{neg_kw}'")
            elif neg_clean in ("5+ years", "7+ years", "10+ years") and has_explicit_seniority_experience(desc_text):
                excluded_reasons.append(f"Description requires senior experience: '{neg_kw}'")

        # 2. Role Matching (0 - 40 points)
        role_score, matched_roles = self._score_role(title_text, active_profile.target_roles, has_negative_title)

        # 3. Skills & Keywords Matching (0 - 30 points)
        skills_score, matched_skills, matched_kws = self._score_skills(
            combined_text, active_profile.skills, active_profile.positive_keywords
        )

        # 4. Location Matching (0 - 20 points)
        location_score, matched_locations = self._score_location(
            loc_text,
            active_profile.preferred_locations,
            active_profile.preferences.remote_allowed,
        )

        # 5. Experience Matching (0 - 10 points)
        experience_score, experience_match = self._score_experience(
            exp_text, title_text, desc_text, has_negative_title
        )

        # 6. Total Score Calculation
        total_score = role_score + skills_score + location_score + experience_score
        total_score = max(0, min(100, total_score))

        # 7. Category Assignment
        category = get_score_category(total_score)
        # If posting has serious negative keywords, prevent it from ranking as Strong or Excellent
        if excluded_reasons and category in ("Excellent", "Strong", "Good"):
            category = "Possible"

        return MatchResult(
            score=total_score,
            category=category,
            role_score=role_score,
            skills_score=skills_score,
            location_score=location_score,
            experience_score=experience_score,
            matched_roles=matched_roles,
            matched_skills=matched_skills,
            matched_locations=matched_locations,
            experience_match=experience_match,
            matched_keywords=matched_kws,
            excluded_reasons=excluded_reasons,
        )

    def _score_role(
        self, title: str, target_roles: List[str], has_negative_title: bool
    ) -> Tuple[int, List[str]]:
        """Calculate role match score (0-40) and identify matched target roles."""
        if has_negative_title or not title:
            return 0, []

        title_lower = title.lower()
        matched: List[str] = []
        is_direct_match = False

        for role in target_roles:
            role_clean = role.strip()
            role_lower = role_clean.lower()
            if not role_lower:
                continue

            # Check 1: Exact phrase match on word boundaries
            phrase_pattern = r"\b" + re.escape(role_lower) + r"\b"
            if re.search(phrase_pattern, title_lower):
                matched.append(role_clean)
                is_direct_match = True
                continue

            # Check 2: All constituent tokens of the target role appear in the title
            role_tokens = [t for t in re.split(r"[\s\-_/]+", role_lower) if t]
            if len(role_tokens) > 1 and all(
                re.search(r"\b" + re.escape(token) + r"\b", title_lower)
                for token in role_tokens
            ):
                matched.append(role_clean)
                is_direct_match = True

        if is_direct_match:
            return 40, matched

        # Check 3: Related/partial role match (e.g. single strong domain match)
        # Check if core engineering/development keywords are present
        partial_tokens = {"developer", "engineer", "programmer", "intern", "sde"}
        title_tokens = set(re.findall(r"\b[a-zA-Z]+\b", title_lower))
        if any(t in title_tokens for t in partial_tokens):
            for role in target_roles:
                for token in re.split(r"[\s\-_/]+", role.lower()):
                    if token in title_tokens and token not in partial_tokens:
                        matched.append(role)
                        return 20, matched

        return 0, []

    def _score_skills(
        self,
        text: str,
        skills: List[str],
        positive_keywords: List[str],
    ) -> Tuple[int, List[str], List[str]]:
        """Calculate skills and positive keywords score (0-30)."""
        if not text:
            return 0, [], []

        text_lower = text.lower()
        matched_skills: List[str] = []
        matched_kws: List[str] = []
        seen_skills: Set[str] = set()

        for skill in skills:
            skill_clean = skill.strip()
            skill_lower = skill_clean.lower()
            if not skill_lower or skill_lower in seen_skills:
                continue

            # Build token pattern (supports dots like Next.js, plus like C++)
            escaped = re.escape(skill_lower)
            if skill_lower.isalnum():
                pattern = r"\b" + escaped + r"\b"
            else:
                pattern = r"(?:^|\s|[^\w])" + escaped + r"(?:$|\s|[^\w])"

            if re.search(pattern, text_lower):
                matched_skills.append(skill_clean)
                seen_skills.add(skill_lower)

        for kw in positive_keywords:
            kw_clean = kw.strip()
            kw_lower = kw_clean.lower()
            if not kw_lower or kw_lower in seen_skills:
                continue

            escaped = re.escape(kw_lower)
            pattern = r"\b" + escaped + r"\b" if kw_lower.isalnum() else escaped

            if re.search(pattern, text_lower):
                matched_kws.append(kw_clean)
                seen_skills.add(kw_lower)

        # Proportional scoring capped at 30:
        # Each matched technical skill awards 6 points.
        # Each matched positive keyword awards 3 points.
        raw_score = len(matched_skills) * 6 + len(matched_kws) * 3
        skills_score = min(30, raw_score)

        return skills_score, matched_skills, matched_kws

    def _score_location(
        self,
        location: Optional[str],
        preferred_locations: List[str],
        remote_allowed: bool,
    ) -> Tuple[int, List[str]]:
        """Calculate location match score (0-20) based on priority hierarchy:
        - Delhi / Noida: 20 points (Highest)
        - Bangalore / Bengaluru: 18 points (High)
        - Remote: 18 points (when remote is allowed)
        - Ahmedabad: 15 points (Medium)
        - India / Pan India: 12 points (Broad fallback)
        - Unknown / missing location: 0 points
        - Unrelated location: 0 points
        """
        if not location or not location.strip():
            return 0, []

        loc_clean = unicodedata.normalize("NFC", location.strip())
        loc_lower = loc_clean.lower()
        if loc_lower in ("unknown", "none", "n/a", "not specified"):
            return 0, []

        pref_set = {p.strip().lower() for p in preferred_locations}

        # 1. Delhi / New Delhi (20 pts - Highest Priority)
        if ("delhi" in pref_set or "new delhi" in pref_set) and re.search(r"\b(delhi|new delhi)\b", loc_lower):
            return 20, ["Delhi"]

        # 2. Noida (20 pts - Highest Priority)
        if "noida" in pref_set and re.search(r"\bnoida\b", loc_lower):
            return 20, ["Noida"]

        # 3. Bangalore / Bengaluru equivalence (18 pts - High Priority)
        is_blr_preferred = any(p in ("bangalore", "bengaluru") for p in pref_set)
        if is_blr_preferred:
            if re.search(r"\bbengaluru\b", loc_lower):
                return 18, ["Bengaluru"]
            elif re.search(r"\bbangalore\b", loc_lower):
                return 18, ["Bangalore"]

        # 4. India-eligible Remote (18 pts when remote is allowed and India-eligible / worldwide)
        if is_india_eligible_remote(loc_clean):
            if remote_allowed or "remote" in pref_set:
                return 18, ["Remote"]
            return 0, []

        # 5. Ahmedabad (15 pts - Medium Priority)
        if "ahmedabad" in pref_set and re.search(r"\bahmedabad\b", loc_lower):
            return 15, ["Ahmedabad"]

        # Check for any other explicitly configured preferred locations in profile
        for pref in preferred_locations:
            p_low = pref.strip().lower()
            if p_low in ("delhi", "new delhi", "noida", "bangalore", "bengaluru", "ahmedabad", "remote", "india"):
                continue
            if re.search(r"\b" + re.escape(p_low) + r"\b", loc_lower):
                return 15, [pref.strip()]

        # 6. India / Pan India / All India broad fallback (12 pts)
        # Avoid treating specific unrelated cities as broad India fallback
        unrelated_cities = {
            "mumbai", "pune", "hyderabad", "chennai", "kolkata", "jaipur",
            "lucknow", "chandigarh", "kochi", "indore", "bhopal", "gurgaon",
            "gurugram", "nagpur", "patna", "bhubaneswar", "visakhapatnam",
            "trivandrum", "coimbatore", "surat", "vadodara", "london", "singapore",
            "new york", "berlin", "tokyo", "sydney", "dubai", "toronto"
        }
        has_unrelated_city = any(re.search(r"\b" + re.escape(c) + r"\b", loc_lower) for c in unrelated_cities)

        if "india" in pref_set and not has_unrelated_city:
            if re.search(r"\b(pan[- ]india|all[- ]india|across[- ]india)\b", loc_lower):
                return 12, ["Pan India"]
            elif re.search(r"\bindia\b", loc_lower):
                return 12, ["India"]

        return 0, []

    def _score_experience(
        self,
        experience_text: str,
        title: str,
        description: str,
        has_negative_title: bool,
    ) -> Tuple[int, bool]:
        """Calculate experience match score (0-10)."""
        if has_negative_title:
            return 0, False

        exp_clean = (experience_text or "").strip().lower()
        title_clean = (title or "").strip().lower()
        desc_clean = (description or "").strip().lower()
        search_text = f"{exp_clean} {title_clean} {desc_clean}".strip()

        # 1. Overqualified / High-Seniority Indicators (0 points)
        senior_patterns = [
            r"\b(senior|lead|principal|staff|architect|director)\b",
            r"\b(sde\s*[-_]?\s*(?:iii|iv|3|4)|software\s+engineer\s*[-_]?\s*(?:iii|iv|3|4))\b",
            r"\b(3-5|4-6|5\+|6\+|7\+|8\+|10\+)\s*(?:years|yrs)\b",
            r"\b(?:at least|minimum|min)\s*[3-9]\s*(?:years|yrs)\b",
            r"\b(?:requires?|requiring)\s*[3-9]\+?\s*(?:years|yrs)\b",
        ]
        for pattern in senior_patterns:
            if re.search(pattern, search_text):
                return 0, False

        # If structured experience field explicitly requires 3+ years or 2+ years
        if exp_clean:
            if re.search(r"\b[3-9]\+?\s*(?:years|yrs)\b", exp_clean) or re.search(r"\b2\+\s*(?:years|yrs)\b", exp_clean):
                return 0, False

        # 2. Explicit entry-level / fresher / intern indicators (10 points)
        entry_patterns = [
            r"\b(fresher|entry[- ]level|intern|internship|fresh graduate|trainee)\b",
            r"\b(?:0[- ]1|0[- ]2|1[- ]2|0\s*to\s*[12]|1\s*to\s*2|up\s*to\s*2|upto\s*2|max(?:imum)?\s*2)\s*(?:years|yrs)\b",
            r"\b(?:0|1)\s*(?:years|yrs|yr)\s*(?:of)?\s*experience\b",
        ]
        for pattern in entry_patterns:
            if re.search(pattern, search_text):
                return 10, True

        # 3. Explicit requirement of > 2 years in description with requirement wording
        if re.search(r"\b(?:minimum|min|at least|requires?|requiring)\s*[2-9]\+?\s*(?:years|yrs)\b", desc_clean):
            return 0, False

        # 4. Missing / unspecified experience: not treated as perfect (10), awards partial 5 points
        return 5, False
