import asyncio
import httpx
from datetime import datetime, timezone
import json

async def probe():
    results = {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
        # 1. Test Workday
        workday_tests = {
            "adobe": ("https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs", {"appliedFacets": {"locationCountry": ["c4f78be1a8f14da0ab49ce1162348a5e"]}, "limit": 5, "offset": 0}),
            "intel": ("https://intel.wd1.myworkdayjobs.com/wday/cxs/intel/External/jobs", {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": "India"}),
            "nvidia": ("https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs", {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": "India"}),
            "salesforce": ("https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/External_Career_Site/jobs", {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": "India"}),
            "walmart": ("https://walmart.wd504.myworkdayjobs.com/wday/cxs/walmart/WalmartExternal/jobs", {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": "India"}),
            "mastercard": ("https://mastercard.wd1.myworkdayjobs.com/wday/cxs/mastercard/CorporateCareers/jobs", {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": "India"}),
            "visa": ("https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/visa/jobs", {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": "India"}),
            "paypal": ("https://paypal.wd1.myworkdayjobs.com/wday/cxs/paypal/jobs/jobs", {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": "India"}),
            "hp": ("https://hp.wd5.myworkdayjobs.com/wday/cxs/hp/ExternalCareerSite/jobs", {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": "India"}),
            "netapp": ("https://netapp.wd1.myworkdayjobs.com/wday/cxs/netapp/Careers/jobs", {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": "India"}),
            "hpe": ("https://hpe.wd5.myworkdayjobs.com/wday/cxs/hpe/ExternalCareerSite/jobs", {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": "India"}),
        }

        for name, (url, payload) in workday_tests.items():
            try:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    total = data.get("total", 0)
                    items = data.get("jobPostings", [])
                    results[f"workday_{name}"] = {"status": "OK", "count": total, "sample": items[0].get("title") if items else None}
                else:
                    results[f"workday_{name}"] = {"status": f"HTTP_{res.status_code}"}
            except Exception as e:
                results[f"workday_{name}"] = {"status": "ERR", "msg": str(e)}

        # 2. Test Greenhouse
        greenhouse_tokens = [
            "cloudflare", "stripe", "figma", "databricks", "elastic",
            "canonical", "github", "gitlab", "reddit", "twilio",
            "grammarly", "mongodb", "automattic", "brex", "doordash", "affirm",
            "atlassian", "airtable", "dbtlabs", "hashicorp", "instacart", "lyft", "pinterest", "scaleai", "snap", "uber"
        ]

        for token in greenhouse_tokens:
            url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    jobs = data.get("jobs", [])
                    results[f"greenhouse_{token}"] = {"status": "OK", "count": len(jobs), "sample": jobs[0].get("title") if jobs else None}
                else:
                    results[f"greenhouse_{token}"] = {"status": f"HTTP_{res.status_code}"}
            except Exception as e:
                results[f"greenhouse_{token}"] = {"status": "ERR", "msg": str(e)}

        # 3. Test SmartRecruiters
        sr_companies = ["SopraSteria1", "bosch", "AveryDennison", "Square", "Ubisoft", "Criteo", "Kinaxis", "Visa", "Twitter"]
        for c in sr_companies:
            url = f"https://api.smartrecruiters.com/v1/companies/{c}/postings"
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    total = data.get("totalFound", 0)
                    items = data.get("content", [])
                    results[f"smartrecruiters_{c}"] = {"status": "OK", "count": total, "sample": items[0].get("name") if items else None}
                else:
                    results[f"smartrecruiters_{c}"] = {"status": f"HTTP_{res.status_code}"}
            except Exception as e:
                results[f"smartrecruiters_{c}"] = {"status": "ERR", "msg": str(e)}

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(probe())

