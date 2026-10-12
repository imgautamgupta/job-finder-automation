"""Controlled depth tuning experiment comparing 25 vs 50 jobs on selected high-value boards."""

import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from app.config.settings import get_settings
from app.sources.lever import fetch_lever_postings_http, parse_lever_posting
from app.sources.greenhouse import fetch_greenhouse_postings_http, parse_greenhouse_posting
from app.models.job import Job
from app.models.match import MatchResult

from test_matcher_refinements import (
    is_india_eligible_remote,
    check_negative_exclusion,
)

EXPERIMENT_BOARDS = [
    ("HackerRank", "Greenhouse", "hackerrank"),
    ("Paytm", "Lever", "paytm"),
    ("JumpCloud", "Lever", "jumpcloud"),
    ("Rubrik", "Greenhouse", "rubrik"),
    ("MongoDB", "Greenhouse", "mongodb"),
    ("Stripe", "Greenhouse", "stripe"),
    ("Samsara", "Greenhouse", "samsara"),
    ("GitLab", "Greenhouse", "gitlab"),
]

def refined_match_pipeline(job: Job, profile):
    title_lower = (job.title or "").lower()
    location_lower = (job.location or "").lower()
    combined_text = f"{job.title} {job.description or ''} {job.experience_required or ''}".lower()

    # Negative exclusion
    is_neg, reasons = check_negative_exclusion(job, profile)
    if is_neg:
        return False, None

    # Role match
    role_matched = any(
        role.lower() in title_lower or all(part in title_lower for part in role.lower().split())
        for role in profile.target_roles
    )
    if not role_matched:
        return False, None

    # Location match
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
        return False, None

    # Match scoring
    from app.services.matcher import JobMatcher
    matcher = JobMatcher(profile=profile)
    res = matcher.match(job)
    # Adjust location score with India-aware remote
    if is_india_eligible_remote(job.location):
        loc_score = 18
    elif any(c in location_lower for c in ["delhi", "new delhi", "noida"]):
        loc_score = 20
    elif "bangalore" in location_lower or "bengaluru" in location_lower:
        loc_score = 18
    elif "ahmedabad" in location_lower:
        loc_score = 15
    elif "india" in location_lower and not has_unrelated_city:
        loc_score = 12
    else:
        loc_score = 0

    adj_total = res.role_score + res.skills_score + loc_score + res.experience_score
    adj_total = max(0, min(100, adj_total))
    from app.services.matcher import get_score_category
    adj_category = get_score_category(adj_total)

    final_res = MatchResult(
        score=adj_total,
        category=adj_category,
        role_score=res.role_score,
        skills_score=res.skills_score,
        location_score=loc_score,
        experience_score=res.experience_score,
        matched_roles=res.matched_roles,
        matched_skills=res.matched_skills,
        matched_locations=["India-Eligible Remote" if is_india_eligible_remote(job.location) else "India Loc"],
        experience_match=res.experience_match,
        matched_keywords=res.matched_keywords,
        excluded_reasons=reasons,
    )
    return True, final_res

async def run_experiment():
    print("=" * 80)
    print("CONTROLLED COLLECTION DEPTH EXPERIMENT: 25 vs 50 JOBS/COMPANY")
    print("=" * 80)

    profile = get_settings().load_profile()
    table_rows = []

    for name, platform, identifier in EXPERIMENT_BOARDS:
        print(f"\nTesting {name} ({platform}: '{identifier}')...")
        if platform == "Lever":
            raw_data = await asyncio.to_thread(fetch_lever_postings_http, identifier)
            total_avail = len(raw_data)
            jobs_25 = [parse_lever_posting(x, company_id=identifier) for x in raw_data[:25]]
            jobs_50 = [parse_lever_posting(x, company_id=identifier) for x in raw_data[:50]]
        else:
            raw_data = await asyncio.to_thread(fetch_greenhouse_postings_http, identifier)
            total_avail = len(raw_data)
            jobs_25 = [parse_greenhouse_posting(x, company_id=identifier) for x in raw_data[:25]]
            jobs_50 = [parse_greenhouse_posting(x, company_id=identifier) for x in raw_data[:50]]

        jobs_25 = [j for j in jobs_25 if j is not None]
        jobs_50 = [j for j in jobs_50 if j is not None]

        # Evaluate 25
        rel_25 = []
        strong_25 = []
        exc_25 = []
        for j in jobs_25:
            passed, m = refined_match_pipeline(j, profile)
            if passed and m.score >= 60:
                rel_25.append((j, m))
                if m.score >= 80:
                    strong_25.append((j, m))
                if m.score >= 90:
                    exc_25.append((j, m))

        # Evaluate 50
        rel_50 = []
        strong_50 = []
        exc_50 = []
        for j in jobs_50:
            passed, m = refined_match_pipeline(j, profile)
            if passed and m.score >= 60:
                rel_50.append((j, m))
                if m.score >= 80:
                    strong_50.append((j, m))
                if m.score >= 90:
                    exc_50.append((j, m))

        new_jobs = [j for j, m in rel_50 if j.url not in {x.url for x, _ in rel_25}]

        decision = "Increase to 50" if len(new_jobs) > 0 else "Keep 25"
        table_rows.append({
            "Company": name,
            "Platform": platform,
            "Identifier": identifier,
            "Available": total_avail,
            "Rel_25": len(rel_25),
            "Rel_50": len(rel_50),
            "Strong_25": len(strong_25),
            "Strong_50": len(strong_50),
            "Exc_25": len(exc_25),
            "Exc_50": len(exc_50),
            "NewJobs": len(new_jobs),
            "NewTitles": [j.title for j in new_jobs],
            "Decision": decision,
        })

        print(f"  Available: {total_avail:3d} | At 25: Rel={len(rel_25)}, Strong={len(strong_25)} | At 50: Rel={len(rel_50)}, Strong={len(strong_50)} | New: {len(new_jobs)}")
        if new_jobs:
            for nj in new_jobs:
                print(f"    * New Job: '{nj.title}' at {nj.company} ({nj.location})")

    print("\n" + "=" * 80)
    print(f"{'Company':12} | {'Available':9} | {'25 Rel':6} | {'50 Rel':6} | {'25 Str':6} | {'50 Str':6} | {'New Jobs':8} | {'Decision'}")
    print("-" * 80)
    for r in table_rows:
        print(f"{r['Company']:12} | {r['Available']:9d} | {r['Rel_25']:6d} | {r['Rel_50']:6d} | {r['Strong_25']:6d} | {r['Strong_50']:6d} | {r['NewJobs']:8d} | {r['Decision']}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_experiment())
