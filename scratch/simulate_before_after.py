"""Simulate Before vs After on the exact 343 jobs collected in Phase 6E."""

import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from app.config.settings import get_settings
from app.sources.lever import LeverJobSource
from app.sources.greenhouse import GreenhouseJobSource
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher
from app.models.job import Job
from app.models.match import MatchResult

from test_matcher_refinements import (
    is_india_eligible_remote,
    check_negative_exclusion,
    has_explicit_seniority_experience,
)

async def simulate():
    settings = get_settings()
    profile = settings.load_profile()

    # Collect live batch of 343 jobs
    lever_source = LeverJobSource(is_enabled=settings.LEVER_ENABLED, settings=settings)
    gh_source = GreenhouseJobSource(is_enabled=settings.GREENHOUSE_ENABLED, settings=settings)

    await lever_source.setup()
    lever_jobs = await lever_source.collect_jobs(profile.target_roles, profile.preferred_locations, max_results=25)
    await lever_source.teardown()

    await gh_source.setup()
    gh_jobs = await gh_source.collect_jobs(profile.target_roles, profile.preferred_locations, max_results=25)
    await gh_source.teardown()

    all_jobs = lever_jobs + gh_jobs
    print(f"Total collected: {len(all_jobs)}")

    current_filter = JobFilter(profile=profile)
    current_matcher = JobMatcher(profile=profile)

    # 1. BEFORE (Current behavior)
    before_passed = []
    before_scores = {}
    for j in all_jobs:
        if current_filter.is_match(j):
            m = current_matcher.match(j)
            before_passed.append((j, m))
            before_scores[j.url] = m.score

    print("\n--- BEFORE ---")
    print(f"Passed Filter: {len(before_passed)}")
    b_rel = sum(1 for _, m in before_passed if m.score >= 60)
    b_good = sum(1 for _, m in before_passed if m.score >= 70)
    b_strong = sum(1 for _, m in before_passed if m.score >= 80)
    b_exc = sum(1 for _, m in before_passed if m.score >= 90)
    print(f"Relevant >=60: {b_rel}")
    print(f"Good >=70:     {b_good}")
    print(f"Strong >=80:   {b_strong}")
    print(f"Excellent >=90:{b_exc}")

    # 2. AFTER (Refined filter and matcher)
    def refined_is_match(job: Job) -> tuple[bool, str]:
        title_lower = (job.title or "").lower()
        location_lower = (job.location or "").lower()
        combined_text = f"{job.title} {job.description or ''} {job.experience_required or ''}".lower()

        # 1. Negative exclusion
        is_neg, reasons = check_negative_exclusion(job, profile)
        if is_neg:
            return False, f"Negative keyword: {reasons[0]}"

        # 2. Remote check (India-aware)
        is_job_remote = "remote" in location_lower or "remote" in combined_text
        if profile.remote_only and not is_job_remote:
            return False, "Not remote"
        if not profile.preferences.remote_allowed and is_job_remote:
            return False, "Remote not allowed"

        # 3. Internship check
        is_internship = "intern" in title_lower or "internship" in title_lower
        if is_internship and not profile.preferences.internship_allowed:
            return False, "Internship not allowed"

        # 4. Target role match
        if profile.target_roles:
            role_matched = any(
                role.lower() in title_lower or all(part in title_lower for part in role.lower().split())
                for role in profile.target_roles
            )
            if not role_matched:
                return False, "Role not matched"

        # 5. Location match (India-aware remote!)
        if profile.preferred_locations:
            is_loc_matched = False
            if is_india_eligible_remote(job.location) and profile.preferences.remote_allowed:
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

                for pref_loc in profile.preferred_locations:
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
                return False, f"Location not matched: {job.location}"

        return True, "Passed"

    def refined_score_location(location: str | None) -> tuple[int, list[str]]:
        if not location or not location.strip():
            return 0, []
        loc_clean = location.strip()
        loc_lower = loc_clean.lower()
        if loc_lower in ("unknown", "none", "n/a", "not specified"):
            return 0, []

        pref_set = {p.strip().lower() for p in profile.preferred_locations}

        # 1. Delhi / New Delhi
        if ("delhi" in pref_set or "new delhi" in pref_set) and re.search(r"\b(delhi|new delhi)\b", loc_lower):
            return 20, ["Delhi"]

        # 2. Noida
        if "noida" in pref_set and re.search(r"\bnoida\b", loc_lower):
            return 20, ["Noida"]

        # 3. Bangalore / Bengaluru
        is_blr_preferred = any(p in ("bangalore", "bengaluru") for p in pref_set)
        if is_blr_preferred:
            if re.search(r"\bbengaluru\b", loc_lower):
                return 18, ["Bengaluru"]
            elif re.search(r"\bbangalore\b", loc_lower):
                return 18, ["Bangalore"]

        # 4. India-eligible Remote (18 pts)
        if is_india_eligible_remote(loc_clean):
            if profile.preferences.remote_allowed or "remote" in pref_set:
                return 18, ["Remote"]
            return 0, []

        # 5. Ahmedabad (15 pts)
        if "ahmedabad" in pref_set and re.search(r"\bahmedabad\b", loc_lower):
            return 15, ["Ahmedabad"]

        # 6. India fallback (12 pts)
        if "india" in pref_set and re.search(r"\b(india|pan[- ]india|all[- ]india)\b", loc_lower):
            unrelated_cities = {
                "mumbai", "pune", "hyderabad", "chennai", "kolkata", "jaipur",
                "lucknow", "chandigarh", "kochi", "indore", "bhopal", "gurgaon",
                "gurugram", "nagpur", "patna", "bhubaneswar", "visakhapatnam",
                "trivandrum", "coimbatore", "surat", "vadodara"
            }
            if not any(re.search(r"\b" + re.escape(c) + r"\b", loc_lower) for c in unrelated_cities):
                return 12, ["India"]

        return 0, []

    def refined_match(job: Job) -> MatchResult:
        title_text = job.title or ""
        desc_text = job.description or ""
        exp_text = job.experience_required or ""
        loc_text = job.location or ""
        combined_text = f"{title_text} {desc_text} {exp_text}".strip()

        is_neg, excluded_reasons = check_negative_exclusion(job, profile)
        has_negative_title = any("Title contains" in r for r in excluded_reasons)

        role_score, matched_roles = current_matcher._score_role(title_text, profile.target_roles, has_negative_title)
        skills_score, matched_skills, matched_kws = current_matcher._score_skills(combined_text, profile.skills, profile.positive_keywords)
        location_score, matched_locations = refined_score_location(loc_text)
        experience_score, experience_match = current_matcher._score_experience(exp_text, title_text, desc_text, has_negative_title)

        total_score = role_score + skills_score + location_score + experience_score
        total_score = max(0, min(100, total_score))

        from app.services.matcher import get_score_category
        category = get_score_category(total_score)
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

    after_passed = []
    for j in all_jobs:
        passed, reason = refined_is_match(j)
        if passed:
            m = refined_match(j)
            after_passed.append((j, m))

    print("\n--- AFTER (Refined Matcher & Remote Eligibility) ---")
    print(f"Passed Filter: {len(after_passed)}")
    a_rel = sum(1 for _, m in after_passed if m.score >= 60)
    a_good = sum(1 for _, m in after_passed if m.score >= 70)
    a_strong = sum(1 for _, m in after_passed if m.score >= 80)
    a_exc = sum(1 for _, m in after_passed if m.score >= 90)
    print(f"Relevant >=60: {a_rel}")
    print(f"Good >=70:     {a_good}")
    print(f"Strong >=80:   {a_strong}")
    print(f"Excellent >=90:{a_exc}")

    print("\nJobs in AFTER result:")
    for j, m in after_passed:
        b_score = before_scores.get(j.url, "Filtered")
        print(f"  Score: {m.score:2d} ({m.category:8s}) | Before: {b_score} | [{j.company}] {j.title} | Loc: {j.location} | LocScore: {m.location_score} ({m.matched_locations})")

    # Demoted remote jobs analysis
    print("\nJobs that were in BEFORE but demoted/removed in AFTER:")
    for j, bm in before_passed:
        after_entry = next((am for aj, am in after_passed if aj.url == j.url), None)
        if not after_entry:
            print(f"  REMOVED from filter: [{j.company}] '{j.title}' (Loc: {j.location}) | Before Score: {bm.score} ({bm.category})")
        elif after_entry.score < bm.score:
            print(f"  DEMOTED: [{j.company}] '{j.title}' (Loc: {j.location}) | Before: {bm.score} -> After: {after_entry.score}")

if __name__ == "__main__":
    asyncio.run(simulate())
