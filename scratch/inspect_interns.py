"""Inspect why specific intern and software engineer jobs in India were filtered."""

import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from app.config.settings import get_settings
from app.sources.lever import LeverJobSource
from app.sources.greenhouse import GreenhouseJobSource
from app.services.filter import JobFilter

async def inspect_interns():
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

    print("Searching for intern/junior/tech jobs in India across all 343 collected jobs...")
    interesting_jobs = []
    for j in all_jobs:
        t_low = (j.title or "").lower()
        if any(k in t_low for k in ["intern", "sde", "engineer", "developer", "backend", "python", "ai", "ml"]):
            if any(l in (j.location or "").lower() for l in ["india", "bangalore", "bengaluru", "delhi", "noida", "remote"]):
                interesting_jobs.append(j)

    print(f"Found {len(interesting_jobs)} tech jobs in India/Remote. Let's see how JobFilter treats them:")
    for j in interesting_jobs:
        title_lower = (j.title or "").lower()
        combined_text = f"{j.title} {j.description or ''} {j.experience_required or ''}".lower()
        location_lower = (j.location or "").lower()

        neg_title = [k for k in profile.negative_keywords if re.search(r"\b" + re.escape(k.lower()) + r"\b" if k.lower().isalnum() else re.escape(k.lower()), title_lower)]
        neg_desc = [k for k in profile.negative_keywords if re.search(r"\b" + re.escape(k.lower()) + r"\b" if k.lower().isalnum() else re.escape(k.lower()), combined_text)]

        role_match = any(
            role.lower() in title_lower or all(part in title_lower for part in role.lower().split())
            for role in profile.target_roles
        )

        is_job_remote = "remote" in location_lower or "remote" in combined_text
        loc_match = False
        if is_job_remote and profile.preferences.remote_allowed:
            loc_match = True
        else:
            for p in profile.preferred_locations:
                if p.lower() in location_lower:
                    loc_match = True
                    break

        print(f"[{j.company}] '{j.title}' | Loc: '{j.location}'")
        print(f"    NegInTitle: {neg_title} | NegInCombined: {neg_desc} | RoleMatch: {role_match} | LocMatch: {loc_match}")

if __name__ == "__main__":
    asyncio.run(inspect_interns())
