import asyncio
import httpx
import json

from inspect_workday_facets import companies

async def dump_facets(key, cfg):
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
    
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            await client.get(f"https://{host}/en-US/{site}/jobs", headers={"User-Agent": headers["User-Agent"]})
            resp = await client.post(url, headers=headers, json={"limit": 1, "offset": 0, "searchText": ""})
            if resp.status_code == 200:
                data = resp.json()
                facets = data.get("facets", [])
                print(f"\n=================== {key.upper()} ===================")
                for f in facets:
                    p = f.get("facetParameter")
                    d = f.get("descriptor")
                    vals = f.get("values", [])
                    print(f"Facet: {p} | descriptor: {d} | count of values: {len(vals)}")
                    for v in vals:
                        desc = v.get("descriptor")
                        vid = v.get("id")
                        cnt = v.get("count")
                        # Print if mentions India or city or if count < 10
                        if any(w in str(desc).lower() for w in ["india", "bengaluru", "bangalore", "noida", "delhi", "ahmedabad", "gurgaon", "hyderabad", "pune", "chennai", "mumbai", "apac", "asia"]):
                            print(f"   -> [MATCH] {desc} (id={vid}, count={cnt})")
                        elif len(vals) <= 5:
                            print(f"   -> {desc} (id={vid}, count={cnt})")
        except Exception as e:
            print(f"[{key}] Error: {e}")

async def main():
    for k, v in companies.items():
        await dump_facets(k, v)
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
