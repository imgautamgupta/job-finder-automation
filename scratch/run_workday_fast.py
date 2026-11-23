import asyncio
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import get_settings
from app.sources.workday import WorkdayJobSource

async def test_workday():
    start = time.time()
    settings = get_settings()
    src = WorkdayJobSource(
        companies=["mastercard"],
    )
    src.fetch_details = False
    jobs = await src.collect_jobs(roles=["Engineer", "Developer"], locations=["India"])
    dur = round(time.time() - start, 2)
    print(f"Workday collected {len(jobs)} jobs in {dur}s")
    by_comp = src.diagnostics.get("by_company", {})
    for c, info in by_comp.items():
        print(f"  {c}: collected {info.get('collected')} (avail: {info.get('available')}, status: {info.get('status')})")

if __name__ == "__main__":
    asyncio.run(test_workday())
