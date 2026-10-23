import httpx
import json
from pathlib import Path

samples_dir = Path("tests/samples")
samples_dir.mkdir(parents=True, exist_ok=True)

companies = {
    "adobe": {"name": "Adobe", "host": "adobe.wd5.myworkdayjobs.com", "tenant": "adobe", "site": "external_experienced"},
    "salesforce": {"name": "Salesforce", "host": "salesforce.wd12.myworkdayjobs.com", "tenant": "salesforce", "site": "External_Career_Site"},
    "visa": {"name": "Visa", "host": "visa.wd5.myworkdayjobs.com", "tenant": "visa", "site": "visa"},
}

client = httpx.Client(timeout=10.0, follow_redirects=True)

for key, c in companies.items():
    client.get(f"https://{c['host']}/en-US/{c['site']}/jobs", headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    url = f"https://{c['host']}/wday/cxs/{c['tenant']}/{c['site']}/jobs"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Origin': f"https://{c['host']}",
        'Referer': f"https://{c['host']}/en-US/{c['site']}/jobs",
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    payload = {'appliedFacets': {}, 'limit': 5, 'offset': 0, 'searchText': 'India'}
    r = client.post(url, headers=headers, json=payload)
    if r.status_code == 200:
        sample_path = samples_dir / f"workday_{key}_sample.json"
        with open(sample_path, "w", encoding="utf-8") as f:
            json.dump(r.json(), f, indent=2)
        print(f"Saved {sample_path}")
