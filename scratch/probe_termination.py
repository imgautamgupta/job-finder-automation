"""
Probe 2: Determine the effective API result cap and correct termination condition.
The API appears to cap totalHits at 10000 and returns results even at huge offsets (wrapping behavior).
We need a safe, practical stopping strategy.
"""
import json
import urllib.request
import urllib.parse
import sys

FINDJOBS_URL = "https://www.accenture.com/api/accenture/elastic/findjobs"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 JobFinderAutomation/1.0"
)

def fetch(keyword, start_index, page_size=10, timeout=15):
    payload = {
        "startIndex": str(start_index),
        "maxResultSize": str(page_size),
        "jobKeyword": keyword.strip(),
        "jobCountry": "India",
        "jobLanguage": "en",
        "countrySite": "in-en",
        "sortBy": "1",
        "searchType": "vectorSearch",
        "enableQueryBoost": "true",
        "minScore": "0.6",
        "getFeedbackJudgmentEnabled": "true",
        "useCleanEmbedding": "true",
        "score": "true",
        "totalHits": "true",
        "debugQuery": "false",
        "jobFilters": "[]",
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    headers = {
        "User-Agent": USER_AGENT,
        "Origin": "https://www.accenture.com",
        "Referer": "https://www.accenture.com/in-en/careers/jobsearch",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    req = urllib.request.Request(FINDJOBS_URL, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"  ERROR at startIndex={start_index}: {e}", file=sys.stderr)
        return {}

# Use a very specific keyword to get a small result set
keyword = "Python Developer Intern"
page_size = 5

print(f"=== Probing termination for keyword='{keyword}', page_size={page_size} ===\n")

all_seen_ids = set()
prev_ids = None
for start in range(0, 60, page_size):
    resp = fetch(keyword, start_index=start, page_size=page_size)
    items = resp.get("data", [])
    total = resp.get("totalHits", {})
    total_count = total.get("total", 0) if isinstance(total, dict) else 0
    ids = [j.get("requisitionId", "NO-ID") for j in items]
    new_ids = set(ids) - all_seen_ids
    repeated_ids = set(ids) & all_seen_ids

    print(f"startIndex={start:4d}: returned={len(items):2d} | total_reported={total_count} | new={len(new_ids):2d} | repeated={len(repeated_ids):2d} | ids={ids[:3]}")

    if ids == prev_ids:
        print("  *** SAME PAGE REPEATED — stop condition triggered ***")
        break
    if not items:
        print("  *** EMPTY PAGE — clean stop ***")
        break

    all_seen_ids.update(ids)
    prev_ids = ids

print(f"\nTotal unique IDs collected across all pages: {len(all_seen_ids)}")
