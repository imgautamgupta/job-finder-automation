import httpx

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
target_ids = ['10572929', '10531567', '10551515', '10495277', '10528516']
for tid in target_ids:
    url = f"https://www.amazon.jobs/en/jobs/{tid}.json"
    resp = httpx.get(url, headers=headers, follow_redirects=True)
    if resp.status_code == 200:
        j = resp.json().get("job", {})
        print(f"=== JOB {tid} ===")
        print("Title:", j.get("title"))
        print("Basic Qualifications:\n", j.get("basic_qualifications"))
        print("Preferred Qualifications:\n", j.get("preferred_qualifications"))
        print("Description snippet:\n", j.get("description", "")[:200])
    else:
        print(f"Job {tid} returned status {resp.status_code}")
