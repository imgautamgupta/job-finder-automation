"""Analyze all 343 jobs from the collection run, why they passed or were filtered."""

import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from app.config.settings import get_settings
from app.services.collector import JobCollector
from app.sources.lever import LeverJobSource
from app.sources.greenhouse import GreenhouseJobSource
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher

async def analyze():
    settings = get_settings()
    profile = settings.load_profile()
    
    lever_source = LeverJobSource(is_enabled=settings.LEVER_ENABLED, settings=settings)
    gh_source = GreenhouseJobSource(is_enabled=settings.GREENHOUSE_ENABLED, settings=settings)
    
    await lever_source.setup()
    lever_jobs = await lever_source.collect_jobs(profile.target_roles, profile.preferred_locations, max_results=25)
    await lever_source.teardown()
    
    await gh_source.setup()
    gh_jobs = await gh_source.collect_jobs(profile.target_roles, profile.preferred_locations, max_results=25)
    await gh_source.teardown()
    
    all_jobs = lever_jobs + gh_jobs
    job_filter = JobFilter(profile=profile)
    matcher = JobMatcher(profile=profile)
    
    print(f"Total collected: {len(all_jobs)} (Lever: {len(lever_jobs)}, GH: {len(gh_jobs)})")
    
    filter_reasons = {
        "negative_keyword": 0,
        "role_not_matched": 0,
        "location_not_matched": 0,
        "other": 0,
    }
    passed_jobs = []
    
    for job in all_jobs:
        combined_text = f"{job.title} {job.description or ''} {job.experience_required or ''}".lower()
        title_lower = job.title.lower()
        location_lower = (job.location or "").lower()

        # Check negative keyword
        neg_hit = None
        for neg_kw in profile.negative_keywords:
            neg_lower = neg_kw.lower().strip()
            if neg_lower.isalnum():
                pattern = r"\b" + re.escape(neg_lower) + r"\b"
                if re.search(pattern, combined_text):
                    neg_hit = neg_kw
                    break
            elif neg_lower in combined_text:
                neg_hit = neg_kw
                break

        # Check role match
        role_matched = any(
            role.lower() in title_lower or all(part in title_lower for part in role.lower().split())
            for role in profile.target_roles
        )

        # Check location match
        is_job_remote = "remote" in location_lower or "remote" in combined_text
        is_loc_matched = False
        if is_job_remote and profile.preferences.remote_allowed:
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

        if job_filter.is_match(job):
            passed_jobs.append(job)
        else:
            if neg_hit:
                filter_reasons["negative_keyword"] += 1
            elif not role_matched:
                filter_reasons["role_not_matched"] += 1
            elif not is_loc_matched:
                filter_reasons["location_not_matched"] += 1
            else:
                filter_reasons["other"] += 1
                    
    print("\nFilter Exclusion Reasons Breakdown:")
    for r, count in sorted(filter_reasons.items(), key=lambda x: x[1], reverse=True):
        print(f"  {r}: {count}")

    print(f"\nPassed Jobs Count: {len(passed_jobs)}")
    for j in passed_jobs:
        m = matcher.match(j)
        print(f"  [{m.score:2d}] {j.title} | {j.company} | {j.location} | Matched Role: {m.matched_target_roles} | Skills: {m.matched_skills}")

if __name__ == "__main__":
    asyncio.run(analyze())
