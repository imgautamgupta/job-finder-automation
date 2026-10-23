import asyncio
import json
import sys
from pathlib import Path

# Setup paths
sys.path.insert(0, ".")

from app.config.settings import Settings
from app.sources.accenture import AccentureJobSource
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher

async def run_live_validation():
    settings = Settings(
        ACCENTURE_ENABLED=True,
        ACCENTURE_MAX_JOBS=25,
        ACCENTURE_REQUEST_DELAY_SEC=1.0,
    )
    profile = settings.load_profile()
    job_filter = JobFilter(profile=profile)
    matcher = JobMatcher(profile=profile)

    source = AccentureJobSource(is_enabled=True, settings=settings)
    await source.setup()

    # Collect limited batch for validation
    target_roles = profile.target_roles[:5]
    print(f"Executing live collection for roles: {target_roles} (limit=25)...")
    
    jobs = await source.collect_jobs(
        roles=target_roles,
        locations=profile.preferred_locations,
        max_results=25,
    )
    await source.teardown()

    print(f"\n--- LIVE VALIDATION RESULTS ---")
    print(f"Status: {source.last_status}")
    print(f"Error: {source.last_error}")
    print(f"Total raw listings collected: {len(jobs)}")

    jobs_with_ids = [j for j in jobs if j.source_job_id]
    print(f"Listings with official Job IDs: {len(jobs_with_ids)}/{len(jobs)}")

    # Filter and score against real profile
    passed_filter = []
    excluded_with_reasons = []

    for j in jobs:
        if job_filter.is_match(j):
            match_res = matcher.match(j)
            j.apply_match_result(match_res)
            passed_filter.append(j)
        else:
            # Check reasons
            match_res = matcher.match(j)
            reasons = list(match_res.excluded_reasons)
            if not reasons:
                reasons.append("Did not pass profile preference criteria (role/location/experience)")
            excluded_with_reasons.append((j, reasons))

    print(f"Listings passing profile filter: {len(passed_filter)}")
    print(f"Listings excluded: {len(excluded_with_reasons)}")

    # Categorize exclusion reasons
    reason_counts = {}
    for _, reasons in excluded_with_reasons:
        for r in reasons:
            reason_counts[r] = reason_counts.get(r, 0) + 1

    print("\nMain Exclusion Reasons:")
    for r, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  - {r}: {count}")

    print("\nSample Collected Listings (First 5):")
    for idx, j in enumerate(jobs[:5], 1):
        print(f"{idx}. Title: {j.title}")
        print(f"   Job ID: {j.source_job_id or 'UNAVAILABLE'}")
        print(f"   Location: {j.location}")
        print(f"   Experience: {j.experience_required}")
        print(f"   Direct Link: {j.url}")
        print(f"   Eligibility: {j.extra_metadata.get('eligibility')}")
        print()

    if passed_filter:
        print("Profile-Matched Listings:")
        for idx, j in enumerate(passed_filter, 1):
            print(f"{idx}. [{j.match_score} pts] {j.title} | ID: {j.source_job_id} | Loc: {j.location} | Skills: {j.matched_skills}")
            print(f"   URL: {j.url}")

    # Output JSON summary for artifact
    summary = {
        "status": source.last_status,
        "collected_count": len(jobs),
        "with_job_ids_count": len(jobs_with_ids),
        "passed_filter_count": len(passed_filter),
        "excluded_count": len(excluded_with_reasons),
        "exclusion_reasons": reason_counts,
        "samples": [
            {
                "title": j.title,
                "job_id": j.source_job_id,
                "location": j.location,
                "url": j.url,
                "experience": j.experience_required,
                "eligibility": j.extra_metadata.get("eligibility")
            }
            for j in jobs[:5]
        ]
    }
    with open("scratch/live_validation_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run_live_validation())
