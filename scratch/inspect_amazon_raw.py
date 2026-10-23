import httpx
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
url = "https://www.amazon.jobs/en/search.json?query=10572929"
resp = httpx.get(url, headers=headers)
data = resp.json()
jobs = data.get("jobs", [])
print(f"Total jobs returned for 10572929: {len(jobs)}")
if jobs:
    j = jobs[0]
    print("Keys:", list(j.keys()))
    print("\n--- basic_qualifications ---")
    print(j.get("basic_qualifications"))
    print("\n--- preferred_qualifications ---")
    print(j.get("preferred_qualifications"))
    print("\n--- description snippet ---")
    print(j.get("description", "")[:400])
