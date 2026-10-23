import httpx
import json

companies = {
    "adobe": {"name": "Adobe", "host": "adobe.wd5.myworkdayjobs.com", "tenant": "adobe", "site": "external_experienced"},
    "intel": {"name": "Intel", "host": "intel.wd1.myworkdayjobs.com", "tenant": "intel", "site": "External"},
    "nvidia": {"name": "NVIDIA", "host": "nvidia.wd5.myworkdayjobs.com", "tenant": "nvidia", "site": "NVIDIAExternalCareerSite"},
    "salesforce": {"name": "Salesforce", "host": "salesforce.wd12.myworkdayjobs.com", "tenant": "salesforce", "site": "External_Career_Site"},
    "walmart": {"name": "Walmart", "host": "walmart.wd504.myworkdayjobs.com", "tenant": "walmart", "site": "WalmartExternal"},
    "mastercard": {"name": "Mastercard", "host": "mastercard.wd1.myworkdayjobs.com", "tenant": "mastercard", "site": "CorporateCareers"},
    "visa": {"name": "Visa", "host": "visa.wd5.myworkdayjobs.com", "tenant": "visa", "site": "visa"},
    "paypal": {"name": "PayPal", "host": "paypal.wd1.myworkdayjobs.com", "tenant": "paypal", "site": "jobs"},
}

for key, c in companies.items():
    client = httpx.Client(timeout=10.0, follow_redirects=True)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Origin': f"https://{c['host']}",
        'Referer': f"https://{c['host']}/en-US/{c['site']}/jobs",
    }
    try:
        # Establish session
        client.get(f"https://{c['host']}/en-US/{c['site']}/jobs", headers={'User-Agent': headers['User-Agent']})
        # Search jobs
        url = f"https://{c['host']}/wday/cxs/{c['tenant']}/{c['site']}/jobs"
        payload = {'appliedFacets': {}, 'limit': 5, 'offset': 0, 'searchText': 'India'}
        r = client.post(url, headers=headers, json=payload)
        data = r.json() if r.status_code == 200 else {}
        total = data.get('total', 0)
        postings = data.get('jobPostings', [])
        sample_title = postings[0].get('title') if postings else 'None'
        print(f"[{c['name']}] Status: {r.status_code} | Total: {total} | Fetched: {len(postings)} | Sample: {sample_title}")
    except Exception as e:
        print(f"[{c['name']}] Exception: {e}")
