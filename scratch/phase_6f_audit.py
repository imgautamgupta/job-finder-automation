"""Comprehensive Phase 6F Audit Script.

Audits negative keyword behavior (title vs description) and remote location eligibility
using the real Phase 6E dataset (343 jobs across the 15 activated companies).
"""

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

async def run_audit():
    print("=" * 70)
    print("PHASE 6F AUDIT: NEGATIVE KEYWORDS & REMOTE ELIGIBILITY ON REAL DATA")
    print("=" * 70)

    settings = get_settings()
    profile = settings.load_profile()
    matcher = JobMatcher(profile=profile)
    job_filter = JobFilter(profile=profile)

    print("Fetching active live dataset across the 15 configured companies...")
    lever_source = LeverJobSource(is_enabled=settings.LEVER_ENABLED, settings=settings)
    gh_source = GreenhouseJobSource(is_enabled=settings.GREENHOUSE_ENABLED, settings=settings)

    await lever_source.setup()
    lever_jobs = await lever_source.collect_jobs(profile.target_roles, profile.preferred_locations, max_results=25)
    await lever_source.teardown()

    await gh_source.setup()
    gh_jobs = await gh_source.collect_jobs(profile.target_roles, profile.preferred_locations, max_results=25)
    await gh_source.teardown()

    all_jobs = lever_jobs + gh_jobs
    print(f"Total jobs collected: {len(all_jobs)} (Lever: {len(lever_jobs)}, Greenhouse: {len(gh_jobs)})")

    # =========================================================================
    # PART 1: NEGATIVE KEYWORD AUDIT
    # =========================================================================
    print("\n" + "=" * 70)
    print("PART 1: NEGATIVE KEYWORD AUDIT (Title vs Description)")
    print("=" * 70)

    # Count how negative keywords match
    title_neg_count = 0
    desc_only_neg_count = 0
    exp_field_neg_count = 0
    no_neg_count = 0

    desc_only_jobs = []

    for job in all_jobs:
        title_lower = (job.title or "").lower()
        desc_lower = (job.description or "").lower()
        exp_lower = (job.experience_required or "").lower()

        title_hits = []
        desc_hits = []
        exp_hits = []

        for neg in profile.negative_keywords:
            neg_low = neg.lower().strip()
            if not neg_low:
                continue
            pattern = r"\b" + re.escape(neg_low) + r"\b" if neg_low.isalnum() else re.escape(neg_low)
            if re.search(pattern, title_lower):
                title_hits.append(neg)
            if re.search(pattern, desc_lower):
                desc_hits.append(neg)
            if re.search(pattern, exp_lower):
                exp_hits.append(neg)

        if title_hits:
            title_neg_count += 1
        elif exp_hits:
            exp_field_neg_count += 1
        elif desc_hits:
            desc_only_neg_count += 1
            desc_only_jobs.append((job, desc_hits))
        else:
            no_neg_count += 1

    print(f"Total jobs evaluated: {len(all_jobs)}")
    print(f"Jobs with negative keyword in TITLE: {title_neg_count}")
    print(f"Jobs with negative keyword in EXPERIENCE FIELD: {exp_field_neg_count}")
    print(f"Jobs with negative keyword ONLY in DESCRIPTION: {desc_only_neg_count}")
    print(f"Jobs with NO negative keywords: {no_neg_count}")

    # Analyze the desc_only_jobs: check if their title is a target role!
    print(f"\nAnalyzing {len(desc_only_jobs)} jobs with negative keywords ONLY in description...")
    
    rescued_candidates = []
    for job, hits in desc_only_jobs:
        t_low = (job.title or "").lower()
        role_matched = any(
            role.lower() in t_low or all(part in t_low for part in role.lower().split())
            for role in profile.target_roles
        )
        if role_matched:
            rescued_candidates.append((job, hits))

    print(f"Jobs with TARGET ROLE in title among description-only matches: {len(rescued_candidates)}")
    for j, hits in rescued_candidates:
        print(f"  Candidate: '{j.title}' at {j.company} ({j.location}) | Hits in desc: {hits[:3]}")

    # Check scores of these rescued candidates using existing matcher
    print("\nScoring rescued candidates with existing matcher:")
    rescued_scores = []
    for j, hits in rescued_candidates:
        m = matcher.match(j)
        rescued_scores.append((j, m, hits))
        print(f"  Score: {m.score:2d} ({m.category}) | {j.title} | {j.company} | Loc: {j.location} | LocScore: {m.location_score} | MatchedRole: {m.matched_roles} | Skills: {m.matched_skills}")

    # =========================================================================
    # PART 2: REMOTE ELIGIBILITY AUDIT
    # =========================================================================
    print("\n" + "=" * 70)
    print("PART 2: REMOTE ELIGIBILITY AUDIT")
    print("=" * 70)

    # Classify remote jobs in the collected batch
    cat_a_india_remote = []
    cat_b_worldwide_remote = []
    cat_c_non_india_remote = []
    cat_d_mixed = []
    missing_loc_jobs = []
    other_jobs = []

    foreign_country_patterns = [
        r"\bcanada\b", r"\bpoland\b", r"\buk\b", r"\bunited kingdom\b",
        r"\bunited states\b", r"\bus\b", r"\busa\b", r"\bgermany\b",
        r"\bfrance\b", r"\bspain\b", r"\bireland\b", r"\baustralia\b",
        r"\bjapan\b", r"\bmexico\b", r"\bbrazil\b", r"\btrkiye\b",
        r"\bturkey\b", r"\bcolombia\b", r"\bnetherlands\b", r"\bemea\b"
    ]

    for job in all_jobs:
        loc = (job.location or "").strip()
        loc_low = loc.lower()

        if not loc or loc_low in ("unknown", "none", "n/a", "not specified"):
            missing_loc_jobs.append(job)
            continue

        if "remote" not in loc_low:
            other_jobs.append(job)
            continue

        # Has "remote"
        has_india = "india" in loc_low or "bangalore" in loc_low or "bengaluru" in loc_low or "delhi" in loc_low or "noida" in loc_low
        has_foreign = any(re.search(pat, loc_low) for pat in foreign_country_patterns)
        is_worldwide = any(kw in loc_low for kw in ["worldwide", "global remote", "anywhere", "work from anywhere"])

        if is_worldwide and not has_foreign:
            cat_b_worldwide_remote.append(job)
        elif has_india and not has_foreign:
            cat_a_india_remote.append(job)
        elif has_india and has_foreign:
            cat_d_mixed.append(job)
        elif has_foreign and not has_india:
            cat_c_non_india_remote.append(job)
        else:
            # "Remote" alone without country
            cat_b_worldwide_remote.append(job)

    print(f"Total jobs containing 'Remote' in location: {len(cat_a_india_remote) + len(cat_b_worldwide_remote) + len(cat_c_non_india_remote) + len(cat_d_mixed)}")
    print(f"  Category A (India-eligible Remote): {len(cat_a_india_remote)}")
    print(f"  Category B (Worldwide / Ambiguous Remote): {len(cat_b_worldwide_remote)}")
    print(f"  Category C (Non-India Foreign Remote): {len(cat_c_non_india_remote)}")
    print(f"  Category D (Mixed India + Foreign): {len(cat_d_mixed)}")
    print(f"Jobs with missing/unknown location: {len(missing_loc_jobs)}")

    print("\nSample Non-India Remote Jobs currently receiving 18 Remote points:")
    for j in cat_c_non_india_remote[:8]:
        m = matcher.match(j)
        print(f"  [{j.company}] '{j.title}' -> Location: '{j.location}' | Current LocScore: {m.location_score} (Matched: {m.matched_locations})")

    print("\nSpecial Inspection: The 5 Matched Jobs from Phase 6E:")
    for j in all_jobs:
        if j.url in [
            "https://job-boards.greenhouse.io/gitlab/jobs/8620720002",
            "https://job-boards.greenhouse.io/gitlab/jobs/8704363002",
            "https://jobs.elastic.co/jobs?gh_jid=8247206&gh_jid=8247206",
            "https://jobs.lever.co/jumpcloud/756b176a-817b-4088-8eda-af8fbb389f9a",
            "https://jobs.lever.co/jumpcloud/90522edf-3575-4b45-a631-988e5771abb3"
        ]:
            m = matcher.match(j)
            print(f"  * [{j.company}] '{j.title}' | Location: '{j.location}' | Score: {m.score} ({m.category}) | LocScore: {m.location_score} ({m.matched_locations})")

if __name__ == "__main__":
    asyncio.run(run_audit())
