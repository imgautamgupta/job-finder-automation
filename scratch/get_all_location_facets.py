import asyncio
import httpx
import json

from inspect_workday_facets import companies

async def get_all_location_facet_values(key, cfg):
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
                
                # Check top-level facets and nested inside locationMainGroup
                facet_list = []
                for f in facets:
                    if f.get("facetParameter") == "locationMainGroup":
                        facet_list.extend(f.get("values", []))
                    else:
                        facet_list.append(f)
                
                for f in facet_list:
                    p = f.get("facetParameter")
                    d = f.get("descriptor")
                    vals = f.get("values", [])
                    india_matches = []
                    for v in vals:
                        desc = str(v.get("descriptor", ""))
                        vid = v.get("id")
                        cnt = v.get("count")
                        if any(w in desc.lower() for w in ["india", "bengaluru", "bangalore", "noida", "delhi", "ahmedabad", "gurgaon", "gurugram", "hyderabad", "pune", "chennai", "mumbai", "kolkata"]):
                            india_matches.append((desc, vid, cnt))
                    if india_matches:
                        print(f"Facet '{p}' ({d}): {len(india_matches)} India matches:")
                        for desc, vid, cnt in india_matches:
                            print(f"   -> {desc}: id='{vid}', count={cnt}")
        except Exception as e:
            print(f"[{key}] Error: {e}")

async def main():
    for k, v in companies.items():
        await get_all_location_facet_values(k, v)
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
