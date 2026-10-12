"""Inspect all 112 remote jobs and classify them by exact location string."""

import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from collections import Counter
from app.config.settings import get_settings
from app.sources.lever import LeverJobSource
from app.sources.greenhouse import GreenhouseJobSource

async def audit_remote():
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

    remote_loc_counts = Counter()
    for j in all_jobs:
        loc = j.location or ""
        if "remote" in loc.lower():
            remote_loc_counts[loc] += 1

    print(f"Total distinct Remote location strings: {len(remote_loc_counts)}")
    print(f"Total Remote jobs: {sum(remote_loc_counts.values())}\n")

    for loc, count in sorted(remote_loc_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  [{count:2d}] {loc}")

if __name__ == "__main__":
    asyncio.run(audit_remote())
