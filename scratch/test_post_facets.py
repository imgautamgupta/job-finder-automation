import asyncio
import httpx
import json

from inspect_workday_facets import companies

async def test_post_facets(key, cfg):
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
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        # First test POST /facets/locationCountry or /facets/locations
        test_facets = ["locationCountry", "country", "locations", "locationHierarchy1", "locationHierarchy2", "primaryLocation"]
        print(f"\n--- Testing POST facets for {key} ---")
        for f in test_facets:
            url = f"https://{host}/wday/cxs/{tenant}/{site}/facets/{f}"
            try:
                resp = await client.post(url, headers=headers, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""})
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("values", [])
                    print(f"  [POST 200] {f}: {len(items)} values")
                    for it in items:
                        desc = it.get("descriptor")
                        vid = it.get("id")
                        cnt = it.get("count")
                        if any(w in str(desc).lower() for w in ["india", "bengaluru", "bangalore", "noida", "delhi", "ahmedabad", "chennai", "hyderabad", "pune", "mumbai", "gurgaon"]):
                            print(f"    -> [MATCH] {desc} (id={vid}, count={cnt})")
                else:
                    if resp.status_code != 404:
                        print(f"  [{resp.status_code}] {f}")
            except Exception as e:
                print(f"  Error {f}: {e}")

async def main():
    for k in ["adobe", "walmart", "visa", "intel", "mastercard", "paypal", "nvidia"]:
        await test_post_facets(k, companies[k])
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
