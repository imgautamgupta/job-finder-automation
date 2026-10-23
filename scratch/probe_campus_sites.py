import asyncio
import httpx

test_sites = [
    # Adobe
    ("adobe", "adobe.wd5.myworkdayjobs.com", "adobe", "external_campus"),
    ("adobe", "adobe.wd5.myworkdayjobs.com", "adobe", "Adobe_University"),
    ("adobe", "adobe.wd5.myworkdayjobs.com", "adobe", "Adobe_Intern"),
    ("adobe", "adobe.wd5.myworkdayjobs.com", "adobe", "University"),
    # Intel
    ("intel", "intel.wd1.myworkdayjobs.com", "intel", "Intel_Student"),
    ("intel", "intel.wd1.myworkdayjobs.com", "intel", "Student"),
    ("intel", "intel.wd1.myworkdayjobs.com", "intel", "Campus"),
    # NVIDIA
    ("nvidia", "nvidia.wd5.myworkdayjobs.com", "nvidia", "UniversityRecruiting"),
    ("nvidia", "nvidia.wd5.myworkdayjobs.com", "nvidia", "Campus"),
    ("nvidia", "nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIA_Students"),
    # Salesforce
    ("salesforce", "salesforce.wd12.myworkdayjobs.com", "salesforce", "Futureforce"),
    ("salesforce", "salesforce.wd12.myworkdayjobs.com", "salesforce", "Futureforce_Career_Site"),
    ("salesforce", "salesforce.wd12.myworkdayjobs.com", "salesforce", "University_Recruiting"),
    # Walmart
    ("walmart", "walmart.wd504.myworkdayjobs.com", "walmart", "Walmart_Campus"),
    ("walmart", "walmart.wd504.myworkdayjobs.com", "walmart", "CampusCareers"),
    # Mastercard
    ("mastercard", "mastercard.wd1.myworkdayjobs.com", "mastercard", "CampusCareers"),
    ("mastercard", "mastercard.wd1.myworkdayjobs.com", "mastercard", "University"),
    # Visa
    ("visa", "visa.wd5.myworkdayjobs.com", "visa", "visa_students"),
    ("visa", "visa.wd5.myworkdayjobs.com", "visa", "University"),
    # PayPal
    ("paypal", "paypal.wd1.myworkdayjobs.com", "paypal", "Campus"),
    ("paypal", "paypal.wd1.myworkdayjobs.com", "paypal", "University"),
]

async def check_sites():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for comp, host, tenant, site in test_sites:
            url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
            try:
                resp = await client.post(url, headers=headers, json={"limit": 1, "offset": 0, "searchText": ""})
                if resp.status_code == 200:
                    d = resp.json()
                    tot = d.get("total", 0)
                    print(f"[{comp}] REACHABLE: site='{site}' -> total jobs={tot}")
                else:
                    pass
            except Exception:
                pass
            await asyncio.sleep(0.2)

if __name__ == "__main__":
    asyncio.run(check_sites())
