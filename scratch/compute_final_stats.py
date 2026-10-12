"""Compute exact location and role counts across collected jobs and relevant jobs."""

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

async def analyze_stats():
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
    
    # 1. Location counts across all collected jobs
    loc_counts = {
        "Delhi / New Delhi": 0,
        "Noida": 0,
        "Bangalore / Bengaluru": 0,
        "Remote": 0,
        "Ahmedabad": 0,
        "India / Pan India": 0,
    }
    
    for j in all_jobs:
        loc = (j.location or "").lower()
        if "delhi" in loc:
            loc_counts["Delhi / New Delhi"] += 1
        if "noida" in loc:
            loc_counts["Noida"] += 1
        if "bangalore" in loc or "bengaluru" in loc:
            loc_counts["Bangalore / Bengaluru"] += 1
        if "remote" in loc:
            loc_counts["Remote"] += 1
        if "ahmedabad" in loc:
            loc_counts["Ahmedabad"] += 1
        if "india" in loc:
            loc_counts["India / Pan India"] += 1
            
    print("=== Location counts across ALL 343 collected jobs ===")
    for k, v in loc_counts.items():
        print(f"  {k}: {v}")
        
    # 2. Role counts across all collected jobs
    target_roles = [
        "Python Developer", "Backend Developer", "Software Engineer",
        "Full Stack Developer", "Web Developer", "ML Engineer", "AI Engineer",
        "SDE Intern", "Python Developer Intern", "Machine Learning Intern",
        "Web Developer Intern"
    ]
    role_counts_all = {r: 0 for r in target_roles}
    for j in all_jobs:
        t_low = j.title.lower()
        for r in target_roles:
            if r.lower() in t_low or all(p in t_low for p in r.lower().split()):
                role_counts_all[r] += 1

    print("\n=== Target role matches across ALL 343 collected jobs ===")
    for k, v in role_counts_all.items():
        print(f"  {k}: {v}")

    # 3. Passed / Relevant jobs analysis
    passed_jobs = [j for j in all_jobs if job_filter.is_match(j)]
    print(f"\n=== Scored details for the {len(passed_jobs)} passed jobs ===")
    for j in passed_jobs:
        m = matcher.match(j)
        print(f"  Score: {m.score:2d} ({m.category}) | Title: {j.title} | Company: {j.company} | Location: {j.location} | Role: {m.matched_roles} | Skills: {m.matched_skills} | LocMatch: {m.matched_locations}")

if __name__ == "__main__":
    asyncio.run(analyze_stats())
