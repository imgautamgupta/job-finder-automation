"""
Live API probe: verify startIndex pagination behavior on Accenture findjobs endpoint.
Fetches page 0 and page 1 for a keyword, checks whether different jobs are returned.
This is a one-time verification script — NOT a unit test.
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


def fetch(keyword, start_index, page_size=10, timeout=20):
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
        print(f"  ERROR: {e}", file=sys.stderr)
        return {}


keyword = "Software Engineer"
page_size = 10

print(f"=== Probing Accenture findjobs API with keyword='{keyword}', page_size={page_size} ===\n")

# Page 0
p0 = fetch(keyword, start_index=0, page_size=page_size)
total = p0.get("totalHits", {})
total_count = total.get("total", 0) if isinstance(total, dict) else 0
page0_ids = [j.get("requisitionId", "NO-ID") for j in p0.get("data", [])]
print(f"Page 0 (startIndex=0):")
print(f"  totalHits.total = {total_count}")
print(f"  Jobs returned   = {len(p0.get('data', []))}")
print(f"  Job IDs         = {page0_ids}")

# Page 1
p1 = fetch(keyword, start_index=page_size, page_size=page_size)
page1_ids = [j.get("requisitionId", "NO-ID") for j in p1.get("data", [])]
print(f"\nPage 1 (startIndex={page_size}):")
print(f"  Jobs returned   = {len(p1.get('data', []))}")
print(f"  Job IDs         = {page1_ids}")

# Page 2
p2 = fetch(keyword, start_index=2 * page_size, page_size=page_size)
page2_ids = [j.get("requisitionId", "NO-ID") for j in p2.get("data", [])]
print(f"\nPage 2 (startIndex={2*page_size}):")
print(f"  Jobs returned   = {len(p2.get('data', []))}")
print(f"  Job IDs         = {page2_ids}")

# Beyond total — verify empty termination
beyond_start = total_count + 10 if total_count > 0 else 9999
pb = fetch(keyword, start_index=beyond_start, page_size=page_size)
page_beyond_ids = [j.get("requisitionId", "NO-ID") for j in pb.get("data", [])]
print(f"\nBeyond total (startIndex={beyond_start}):")
print(f"  Jobs returned   = {len(pb.get('data', []))}")
print(f"  Job IDs         = {page_beyond_ids}")

print("\n=== Pagination Analysis ===")
overlap_01 = set(page0_ids) & set(page1_ids)
overlap_12 = set(page1_ids) & set(page2_ids)
print(f"Overlap page0 vs page1: {overlap_01} (should be empty for correct pagination)")
print(f"Overlap page1 vs page2: {overlap_12} (should be empty for correct pagination)")
print(f"Pagination advances correctly: {not overlap_01 and len(page1_ids) > 0}")
print(f"Empty-page termination works: {len(page_beyond_ids) == 0}")

# Also check what fields exist in a raw record
if p0.get("data"):
    print("\n=== Response keys in first job record ===")
    print(sorted(p0["data"][0].keys()))
