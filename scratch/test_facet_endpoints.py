import asyncio
import httpx
import json

from inspect_workday_facets import companies

async def check_facet_endpoints(key, cfg):
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
        # Try GET /wday/cxs/{tenant}/{site}/facets/locationCountry
        # or /wday/cxs/{tenant}/{site}/facets/locations
        test_paths = [
            f"https://{host}/wday/cxs/{tenant}/{site}/facets",
            f"https://{host}/wday/cxs/{tenant}/{site}/facets/country",
            f"https://{host}/wday/cxs/{tenant}/{site}/facets/locationCountry",
            f"https://{host}/wday/cxs/{tenant}/{site}/facets/locations",
            f"https://{host}/wday/cxs/{tenant}/{site}/facets/locationHierarchy1",
            f"https://{host}/wday/cxs/{tenant}/{site}/facets/locationHierarchy2",
        ]
        print(f"\n--- Checking endpoints for {key} ---")
        for p in test_paths:
            try:
                resp = await client.get(p, headers=headers)
                if resp.status_code == 200:
                    d = resp.json()
                    print(f"  [GET 200] {p.split('/')[-1]}: {list(d.keys()) if isinstance(d, dict) else len(d)}")
                    if isinstance(d, dict) and "values" in d:
                        india = [v for v in d["values"] if "india" in str(v).lower() or "bengaluru" in str(v).lower()]
                        print(f"    India matches in {p.split('/')[-1]}: {india}")
                elif resp.status_code != 404:
                    print(f"  [{resp.status_code}] {p.split('/')[-1]}")
            except Exception as e:
                pass

        # Try POST to /jobs with location facets or locationCountry
        # What happens if we POST appliedFacets={"locationCountry": ["..."]}?
        # Let's inspect the HTML of the main page to see the initial state JSON!
        try:
            page_resp = await client.get(f"https://{host}/en-US/{site}/jobs", headers=headers)
            if "window.workday" in page_resp.text or "workdayClientConfig" in page_resp.text:
                print(f"  Found client config in HTML for {key}")
            # Search for facets or locationCountry in HTML
            for word in ["locationCountry", "country", "locationHierarchy", "locations"]:
                if word in page_resp.text:
                    print(f"  Found '{word}' in HTML for {key}")
        except Exception as e:
            pass

async def main():
    for k in ["adobe", "walmart", "visa", "intel", "mastercard"]:
        await check_facet_endpoints(k, companies[k])
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
