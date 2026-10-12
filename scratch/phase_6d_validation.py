import sys
sys.path.insert(0, r"c:\Users\gauta\job-finder-automation")

import asyncio
from collections import Counter
import json
from app.config.settings import Settings, get_settings
from app.sources.lever import LeverJobSource
from app.sources.greenhouse import GreenhouseJobSource
from app.sources.naukri import NaukriJobSource
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher
from app.database.database import DatabaseManager
from app.services.deduplicator import JobDeduplicator

async def run_validation():
    print("=" * 60)
    print("PHASE 6D MULTI-SOURCE QUALITY VALIDATION RUN")
    print("=" * 60)

    settings = get_settings()
    profile = settings.load_profile()
    matcher = JobMatcher(profile=profile)
    job_filter = JobFilter(profile=profile)

    # 1. Collect from Lever
    print("\n[1/3] Collecting from Lever (palantir)...")
    lever_source = LeverJobSource(is_enabled=settings.LEVER_ENABLED, settings=settings)
    await lever_source.setup()
    lever_jobs = await lever_source.collect_jobs(profile.target_roles, profile.preferred_locations, max_results=25)
    await lever_source.teardown()
    print(f"Lever collected: {len(lever_jobs)} jobs. Available: {lever_source.diagnostics.get('available_postings', 0)}")

    # 2. Collect from Greenhouse
    print("\n[2/3] Collecting from Greenhouse (cloudflare)...")
    gh_source = GreenhouseJobSource(is_enabled=settings.GREENHOUSE_ENABLED, settings=settings)
    await gh_source.setup()
    gh_jobs = await gh_source.collect_jobs(profile.target_roles, profile.preferred_locations, max_results=25)
    await gh_source.teardown()
    print(f"Greenhouse collected: {len(gh_jobs)} jobs. Available: {gh_source.diagnostics.get('available_postings', 0)}")

    # 3. Check Naukri status
    print("\n[3/3] Checking Naukri status...")
    naukri_source = NaukriJobSource(is_enabled=True)
    await naukri_source.setup()
    naukri_jobs = await naukri_source.collect_jobs(profile.target_roles, profile.preferred_locations, max_results=10)
    await naukri_source.teardown()
    print(f"Naukri collected: {len(naukri_jobs)} jobs.")

    all_raw_jobs = lever_jobs + gh_jobs + naukri_jobs
    print(f"\nTotal collected across all sources: {len(all_raw_jobs)}")

    # Analyze by source
    source_buckets = {
        "lever": lever_jobs,
        "greenhouse": gh_jobs,
        "naukri": naukri_jobs,
    }

    print("\n" + "=" * 60)
    print("SOURCE-LEVEL DIAGNOSTICS & SCORING")
    print("=" * 60)

    for s_name, s_jobs in source_buckets.items():
        print(f"\n--- Source: {s_name.upper()} ({len(s_jobs)} jobs) ---")
        filtered = [j for j in s_jobs if job_filter.is_match(j)]
        
        # Score ALL collected jobs to evaluate potential relevance vs filter behavior
        scores = []
        rel_60 = 0
        good_70 = 0
        strong_80 = 0
        excel_90 = 0
        
        loc_match_cnt = 0
        role_match_cnt = 0
        skill_match_cnt = 0
        exp_match_cnt = 0

        for j in s_jobs:
            m = matcher.match(j)
            j.apply_match_result(m)
            scores.append(m.score)
            if m.score >= 60: rel_60 += 1
            if m.score >= 70: good_70 += 1
            if m.score >= 80: strong_80 += 1
            if m.score >= 90: excel_90 += 1
            if m.location_score > 0: loc_match_cnt += 1
            if m.role_score > 0: role_match_cnt += 1
            if m.skills_score > 0: skill_match_cnt += 1
            if m.experience_score >= 10: exp_match_cnt += 1

        print(f"Total collected: {len(s_jobs)}")
        print(f"Passed filter: {len(filtered)}")
        print(f"Filtered out: {len(s_jobs) - len(filtered)}")
        print(f"Score breakdown across all collected:")
        print(f"  Score >= 60 (Relevant):  {rel_60}")
        print(f"  Score >= 70 (Good):      {good_70}")
        print(f"  Score >= 80 (Strong):    {strong_80}")
        print(f"  Score >= 90 (Excellent): {excel_90}")
        print(f"Component matches:")
        print(f"  Role score > 0:       {role_match_cnt} / {len(s_jobs)}")
        print(f"  Skill score > 0:      {skill_match_cnt} / {len(s_jobs)}")
        print(f"  Location score > 0:   {loc_match_cnt} / {len(s_jobs)}")
        print(f"  Experience score =10: {exp_match_cnt} / {len(s_jobs)}")

    # 4. Target Roles Analysis
    print("\n" + "=" * 60)
    print("TARGET ROLES ANALYSIS (across all 50 collected jobs)")
    print("=" * 60)
    target_role_counts = Counter()
    non_target_role_counts = Counter()

    for j in all_raw_jobs:
        # Check if matched any target role
        m = matcher.match(j)
        if m.matched_roles:
            for r in m.matched_roles:
                target_role_counts[r] += 1
        else:
            clean_title = j.title.split(" - ")[0].split(",")[0].strip()
            non_target_role_counts[clean_title] += 1

    print("\nTarget roles matched in titles:")
    for role in profile.target_roles:
        cnt = target_role_counts.get(role, 0)
        print(f"  {role:25s}: {cnt}")

    print("\nNon-target roles encountered:")
    for r, cnt in non_target_role_counts.most_common(12):
        print(f"  {r:35s}: {cnt}")

    # 5. Target Locations Analysis
    print("\n" + "=" * 60)
    print("TARGET LOCATIONS ANALYSIS")
    print("=" * 60)
    target_loc_counts = Counter()
    unrelated_loc_counts = Counter()

    for j in all_raw_jobs:
        m = matcher.match(j)
        if m.matched_locations:
            for loc in m.matched_locations:
                target_loc_counts[loc] += 1
        else:
            unrelated_loc_counts[j.location or "None/Missing"] += 1

    print("\nPreferred locations matched:")
    for pref in ["Delhi", "Noida", "Bangalore", "Bengaluru", "Remote", "Ahmedabad", "India", "Pan India"]:
        print(f"  {pref:20s}: {target_loc_counts.get(pref, 0)}")

    print("\nUnrelated / Unmatched locations encountered (all awarded 0 pts):")
    for loc, cnt in unrelated_loc_counts.most_common(10):
        print(f"  {loc:45s}: {cnt}")

    # Check for India fallback leakage on unrelated cities
    print("\nVerifying unrelated cities do NOT receive India fallback (12 pts):")
    leakage_count = 0
    for j in all_raw_jobs:
        m = matcher.match(j)
        loc_low = (j.location or "").lower()
        unrelated_cities = ["london", "new york", "washington", "palo alto", "austin", "singapore", "dubai", "seoul", "amsterdam", "lisboa", "münchen"]
        if any(c in loc_low for c in unrelated_cities) and m.location_score > 0 and not any(pref in loc_low for pref in ["bangalore", "bengaluru", "delhi", "noida", "remote", "ahmedabad"]):
            print(f"  LEAKAGE ALERT! Job '{j.title}' in '{j.location}' got location_score={m.location_score}")
            leakage_count += 1
    if leakage_count == 0:
        print("  VERIFIED: Zero unrelated city location score leakage.")

    # 6. Missing Location Verification
    print("\nVerifying missing locations:")
    missing_loc_jobs = [j for j in all_raw_jobs if not j.location]
    print(f"  Jobs with missing location: {len(missing_loc_jobs)}")
    for j in missing_loc_jobs:
        assert j.location is None
        m = matcher.match(j)
        assert m.location_score == 0
    print("  VERIFIED: All missing locations are None and award 0 points.")

    # 7. Deduplication Analysis
    print("\n" + "=" * 60)
    print("DEDUPLICATION ANALYSIS")
    print("=" * 60)
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db_path = tf.name

    try:
        db = DatabaseManager(db_path=temp_db_path)
        dedup = JobDeduplicator(db_manager=db)

        # Batch dedup
        unique_batch = dedup.deduplicate(all_raw_jobs)
        print(f"Total collected:        {len(all_raw_jobs)}")
        print(f"Unique jobs in batch:   {len(unique_batch)}")
        print(f"Batch duplicates:       {len(all_raw_jobs) - len(unique_batch)}")

        # Insert to DB
        inserts = db.save_jobs(unique_batch)
        print(f"New DB inserts:         {inserts}")

        # Run 2 against DB
        second_run_unique = dedup.deduplicate(all_raw_jobs)
        print(f"Second run unique:      {len(second_run_unique)}")
        print(f"Existing DB matches:    {len(all_raw_jobs) - len(second_run_unique)}")
    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

    # 8. False Negatives Investigation
    print("\n" + "=" * 60)
    print("FALSE NEGATIVES INVESTIGATION (Technical jobs with score < 60)")
    print("=" * 60)
    suspicious_jobs = []
    for j in all_raw_jobs:
        m = matcher.match(j)
        t_low = j.title.lower()
        if any(term in t_low for term in ["engineer", "developer", "technologist", "architect"]):
            if m.score < 60:
                suspicious_jobs.append((j, m))

    print(f"Total technical / engineering jobs scoring < 60: {len(suspicious_jobs)}")
    for j, m in suspicious_jobs:
        passed = job_filter.is_match(j)
        print(f"\n  Job:       {j.title}")
        print(f"  Company:   {j.company} ({j.source})")
        print(f"  Location:  {j.location}")
        print(f"  Score:     {m.score} ({m.category}) | Filtered: {not passed}")
        print(f"  Breakdown: Role={m.role_score}, Skills={m.skills_score}, Loc={m.location_score}, Exp={m.experience_score}")
        print(f"  Excluded:  {m.excluded_reasons}")
        
        # Why rejected
        reasons = []
        if m.location_score == 0:
            reasons.append(f"Location '{j.location}' not in preferred ({profile.preferred_locations})")
        if m.role_score == 0:
            reasons.append("Title did not match target roles")
        if m.excluded_reasons:
            reasons.append("Contains negative keywords: " + ", ".join(m.excluded_reasons))
        print(f"  Root cause: {'; '.join(reasons)}")

    # 9. False Positives Investigation
    print("\n" + "=" * 60)
    print("FALSE POSITIVES INVESTIGATION (Jobs with score >= 60 that are not suitable)")
    print("=" * 60)
    false_positives = [j for j in all_raw_jobs if (j.match_score or 0) >= 60]
    print(f"Jobs with score >= 60: {len(false_positives)}")
    for j in false_positives:
        print(f"  {j.title} | {j.company} | Score: {j.match_score}")

    # 10. The Architect Issue Deep Dive
    print("\n" + "=" * 60)
    print("THE 'ARCHITECT' NEGATIVE KEYWORD DEEP DIVE")
    print("=" * 60)
    architect_jobs = []
    for j in all_raw_jobs:
        comb = f"{j.title} {j.description or ''} {j.experience_required or ''}".lower()
        import re
        if re.search(r"\barchitect\b", comb):
            m = matcher.match(j)
            architect_jobs.append((j, m, "architect" in j.title.lower()))

    print(f"Total jobs containing 'architect': {len(architect_jobs)}")
    for j, m, in_title in architect_jobs:
        print(f"\n  Job: {j.title} | in_title={in_title}")
        print(f"  Location: {j.location} | Loc score: {m.location_score}")
        print(f"  Score: {m.score} ({m.category})")
        # Check if it would be relevant if architect was NOT excluded
        # What would score be without architect?
        # Architect currently prevents score from being Excellent/Strong/Good in matcher, and drops in filter
        # But look at its actual score:
        print(f"  Components: Role={m.role_score}, Skills={m.skills_score}, Loc={m.location_score}, Exp={m.experience_score}")
        if m.location_score == 0:
            print("  -> NOTE: Already excluded by location (0 location points)!")
        else:
            print("  -> NOTE: Location matched! Check if this is a genuine false negative!")

if __name__ == "__main__":
    asyncio.run(run_validation())
