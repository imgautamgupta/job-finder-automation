import asyncio
import httpx
import json

from test_applied_facets import FACET_CONFIGS
from inspect_workday_facets import companies

TARGETED_QUERIES = [
    # Roles
    "python",
    "backend",
    "software engineer",
    "full stack",
    "web developer",
    "ai engineer",
    "ml engineer",
    # Early career
    "intern",
    "internship",
    "graduate",
    "new grad",
    "trainee",
    "associate",
    "fresher",
    "entry level",
]

async def test_targeted_queries_for_company(key):
    cfg = companies[key]
    fc = FACET_CONFIGS[key]
    host = cfg["host"]
    tenant = cfg["tenant"]
    site = cfg["site"]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": f"https://{host}",
        "Referer": f"https://{host}/en-US/{site}/jobs",
    }
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    
    seen_ids = set()
    query_counts = {}
    
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        # First test base facet (no searchText)
        payload = {
            "appliedFacets": fc["appliedFacets"],
            "limit": 20,
            "offset": 0,
            "searchText": "",
        }
        resp = await client.post(url, headers=headers, json=payload)
        base_total = resp.json().get("total", 0) if resp.status_code == 200 else 0
        
        for q in TARGETED_QUERIES:
            payload = {
                "appliedFacets": fc["appliedFacets"],
                "limit": 20,
                "offset": 0,
                "searchText": q,
            }
            try:
                r = await client.post(url, headers=headers, json=payload)
                if r.status_code == 200:
                    d = r.json()
                    tot = d.get("total", 0)
                    query_counts[q] = tot
                    for p in d.get("jobPostings", []):
                        jid = p.get("bulletFields", [None])[0] or p.get("externalPath")
                        seen_ids.add(jid)
                else:
                    query_counts[q] = f"HTTP {r.status_code}"
            except Exception as e:
                query_counts[q] = str(e)
            await asyncio.sleep(0.3)
            
        print(f"[{key.upper()}] Base total: {base_total} | Unique jobs sampled across targeted queries: {len(seen_ids)}")
        print(f"  Targeted query totals: {query_counts}")

async def main():
    for k in ["adobe", "walmart", "paypal"]:
        await test_targeted_queries_for_company(k)

if __name__ == "__main__":
    asyncio.run(main())
