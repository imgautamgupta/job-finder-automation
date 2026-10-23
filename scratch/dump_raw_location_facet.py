import asyncio
import httpx
import json

from inspect_workday_facets import companies

async def dump_raw_location_facet(key, cfg):
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
                for f in facets:
                    if f.get("facetParameter") == "locationMainGroup" or "country" in str(f).lower():
                        print(f"\n[{key}] Raw facet {f.get('facetParameter')}:")
                        print(json.dumps(f, indent=2)[:1000])
        except Exception as e:
            print(f"[{key}] Error: {e}")

async def main():
    for k in ["adobe", "walmart", "visa", "intel", "salesforce"]:
        await dump_raw_location_facet(k, companies[k])
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
