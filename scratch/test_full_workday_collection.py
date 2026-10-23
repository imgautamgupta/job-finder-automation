import asyncio
import httpx
from datetime import datetime, timezone

from test_applied_facets import FACET_CONFIGS
from inspect_workday_facets import companies

async def test_full_collection():
    print("Testing full Workday collection across all 8 companies...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    results = {}
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for key, fc in FACET_CONFIGS.items():
            cfg = companies[key]
            host = cfg["host"]
            tenant = cfg["tenant"]
            site = cfg["site"]
            name = key.capitalize()
            url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
            
            # Warm up GET
            try:
                await client.get(f"https://{host}/en-US/{site}/jobs", headers=headers)
            except Exception:
                pass
                
            offset = 0
            limit = 20
            total_avail = 0
            collected = []
            req_err = None
            
            while True:
                payload = {
                    "appliedFacets": fc["appliedFacets"],
                    "limit": limit,
                    "offset": offset,
                    "searchText": "",
                }
                
                resp = None
                for attempt in range(4):
                    try:
                        resp = await client.post(url, headers=headers, json=payload)
                        if resp.status_code == 429:
                            wait = 2.0 * (2 ** attempt)
                            print(f"[{name}] 429 at offset {offset}. Backoff {wait}s...")
                            await asyncio.sleep(wait)
                            continue
                        break
                    except Exception as e:
                        if attempt < 3:
                            await asyncio.sleep(1.0)
                            continue
                        req_err = str(e)
                        break
                        
                if not resp or resp.status_code != 200:
                    req_err = f"HTTP {resp.status_code if resp else 'None'}"
                    break
                    
                data = resp.json()
                if offset == 0:
                    total_avail = data.get("total", 0)
                    
                postings = data.get("jobPostings", [])
                if not postings:
                    break
                    
                collected.extend(postings)
                offset += len(postings)
                if total_avail > 0 and offset >= total_avail:
                    break
                    
                await asyncio.sleep(1.0)
                
            gap = max(0, total_avail - len(collected))
            status = "COMPLETED" if not req_err else ("PARTIAL" if collected else "FAILED")
            results[name] = {"available": total_avail, "fetched": len(collected), "gap": gap, "status": status, "error": req_err}
            print(f"[{name}] Total Available: {total_avail} | Fetched: {len(collected)} | Gap: {gap} | Status: {status}")
            await asyncio.sleep(1.5)
            
    print("\n--- SUMMARY ---")
    for comp, r in results.items():
        print(f"{comp:<12} | Avail: {r['available']:<5} | Fetched: {r['fetched']:<5} | Gap: {r['gap']:<4} | Status: {r['status']}")

if __name__ == "__main__":
    asyncio.run(test_full_collection())
