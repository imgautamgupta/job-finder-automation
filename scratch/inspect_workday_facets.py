import asyncio
import httpx
import json

companies = {
    "adobe": {
        "host": "adobe.wd5.myworkdayjobs.com",
        "tenant": "adobe",
        "site": "external_experienced",
    },
    "intel": {
        "host": "intel.wd1.myworkdayjobs.com",
        "tenant": "intel",
        "site": "External",
    },
    "nvidia": {
        "host": "nvidia.wd5.myworkdayjobs.com",
        "tenant": "nvidia",
        "site": "NVIDIAExternalCareerSite",
    },
    "salesforce": {
        "host": "salesforce.wd12.myworkdayjobs.com",
        "tenant": "salesforce",
        "site": "External_Career_Site",
    },
    "walmart": {
        "host": "walmart.wd504.myworkdayjobs.com",
        "tenant": "walmart",
        "site": "WalmartExternal",
    },
    "mastercard": {
        "host": "mastercard.wd1.myworkdayjobs.com",
        "tenant": "mastercard",
        "site": "CorporateCareers",
    },
    "visa": {
        "host": "visa.wd5.myworkdayjobs.com",
        "tenant": "visa",
        "site": "visa",
    },
    "paypal": {
        "host": "paypal.wd1.myworkdayjobs.com",
        "tenant": "paypal",
        "site": "jobs",
    },
}

async def inspect_company(key, cfg):
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
        # 1. Warm up GET
        try:
            await client.get(f"https://{host}/en-US/{site}/jobs", headers={"User-Agent": headers["User-Agent"]})
        except Exception as e:
            print(f"[{key}] Warmup error: {e}")

        # 2. Query empty payload to see available facets
        payload = {"limit": 1, "offset": 0, "searchText": ""}
        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                total = data.get("total", 0)
                facets = data.get("facets", [])
                facet_names = [f.get("descriptor") or f.get("facetParameter") for f in facets]
                print(f"[{key}] Total all jobs: {total} | Facets: {facet_names}")
                
                # Look for Country / Location facets
                for f in facets:
                    param = f.get("facetParameter")
                    desc = f.get("descriptor")
                    if any(w in str(desc).lower() or w in str(param).lower() for w in ["location", "country"]):
                        values = f.get("values", [])
                        india_values = [v for v in values if "india" in str(v.get("descriptor")).lower()]
                        print(f"  Facet {param} ({desc}): {len(values)} values. India values: {india_values}")
            else:
                print(f"[{key}] HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"[{key}] Error: {e}")

async def main():
    for k, v in companies.items():
        await inspect_company(k, v)
        await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(main())
