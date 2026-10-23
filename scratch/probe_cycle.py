"""
Probe 3: Find the point where the API starts cycling/repeating results.
When all jobs on a page have already been seen, that's our safe stop condition.
"""
import json
import urllib.request
import urllib.parse
import sys
import time

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

# Test with a narrower keyword to find a realistic result set size faster
keyword = "SDE Intern"
page_size = 10
max_pages = 20  # test up to 200 results

print(f"=== Finding cycle/repeat point for keyword='{keyword}', page_size={page_size} ===\n")

all_seen_ids = set()
for page_num in range(max_pages):
    start = page_num * page_size
    resp = fetch(keyword, start_index=start, page_size=page_size)
    items = resp.get("data", [])
    ids = [j.get("requisitionId", "NO-ID") for j in items]
    id_set = set(ids)
    new_count = len(id_set - all_seen_ids)
    repeated_count = len(id_set & all_seen_ids)

    print(f"page={page_num} startIndex={start:4d}: returned={len(items):2d} | new={new_count:2d} | repeated={repeated_count:2d}")

    # Stop when all ids on this page are already seen (cycle detected)
    if id_set and id_set.issubset(all_seen_ids):
        print(f"\n*** ALL {len(id_set)} IDs ON THIS PAGE ALREADY SEEN — cycle detected at startIndex={start} ***")
        print(f"*** Safe stop here: {len(all_seen_ids)} unique results collected ***")
        break

    all_seen_ids.update(ids)

    if not items:
        print("*** Empty page — clean stop ***")
        break

    time.sleep(0.5)

print(f"\nConclusion: unique jobs collectible for '{keyword}' = {len(all_seen_ids)}")
