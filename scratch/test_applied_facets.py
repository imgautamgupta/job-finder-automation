import asyncio
import httpx
import json

from inspect_workday_facets import companies

FACET_CONFIGS = {
    "adobe": {
        "appliedFacets": {"locationCountry": ["c4f78be1a8f14da0ab49ce1162348a5e"]},
    },
    "intel": {
        "appliedFacets": {"locations": ["1e4a4eb3adf101f44070f976bf8184cf", "fabab36f05f51000ba74e9448dc20000"]},
    },
    "nvidia": {
        "appliedFacets": {"locationHierarchy1": ["2fcb99c455831013ea52b82135ba3266"]},
    },
    "salesforce": {
        "appliedFacets": {"CF_-_REC_-_LRV_-_Job_Posting_Anchor_-_Country_from_Job_Posting_Location_Extended": ["c4f78be1a8f14da0ab49ce1162348a5e"]},
    },
    "walmart": {
        "appliedFacets": {"locationCountry": ["c4f78be1a8f14da0ab49ce1162348a5e"]},
    },
    "mastercard": {
        "appliedFacets": {"locations": [
            "8eab563831bf10acbc722e4859721571", # Pune
            "8eab563831bf10acb97b7fba5feff76e", # Gurgaon
            "28905a74db1b10019f5bb16c36030000", # Navi Mumbai
            "8eab563831bf10acb9d6f1103d78fa67", # Hyderabad
            "85a5bdf4e1831035984400a2fb698c94", # Vadodara
            "8eab563831bf10acb5d384310bb7d5ec", # Bangalore
            "8eab563831bf10acbb7b5bf86d570af1", # Mumbai
        ]},
    },
    "visa": {
        "appliedFacets": {"locationCountry": ["c4f78be1a8f14da0ab49ce1162348a5e"]},
    },
    "paypal": {
        "appliedFacets": {"locations": [
            "bcdc9518960a0115db738aaa2d241899", # Bangalore
            "bcdc9518960a01a46ac477aa2d240c99", # Chennai
        ]},
    },
}

async def test_facets():
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for key, fc in FACET_CONFIGS.items():
            cfg = companies[key]
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
            payload = {
                "appliedFacets": fc["appliedFacets"],
                "limit": 5,
                "offset": 0,
                "searchText": "",
            }
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    tot = data.get("total", 0)
                    postings = data.get("jobPostings", [])
                    print(f"[{key}] SUCCESS: total India jobs = {tot}")
                    for p in postings[:2]:
                        print(f"   -> {p.get('title')} | {p.get('locationsText')}")
                else:
                    print(f"[{key}] FAILED: HTTP {resp.status_code} - {resp.text[:100]}")
            except Exception as e:
                print(f"[{key}] ERROR: {e}")
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(test_facets())
