"""Test Lever boards discovered from search."""

import json
import time
from candidate_auditor import probe_lever, probe_greenhouse

LEVER_NAMES = [
    "curai", "olx", "jumpcloud", "invisible", "fullstory", "kraken",
    "buffer", "articulate", "gitbook", "segment", "thoughtworks",
    "hotstar", "invideo", "browserstack", "browserstack-careers",
    "atlassian", "postman", "postman-inc", "getpostman", "udaan",
    "inmobi", "clevertap", "zeta", "paytm", "fampay", "meesho",
    "epifi", "cred", "pocketfm", "zerodha", "cleartax", "khatabook",
    "groww", "upstox", "indmoney", "smallcase", "bharatpe", "phonepe",
    "cars24", "spinny", "delhivery", "shadowfax", "shiprocket"
]

def main():
    print("Testing Lever candidates...")
    results = []
    for name in LEVER_NAMES:
        r = probe_lever(name)
        if r["http_status"] == 200 and r["available"] > 0:
            print(f"[LV 200] {name:20} Avail: {r['available']:4} | India: {r['india_jobs']:3} | Remote: {r['remote_jobs']:3} | Eng: {r['engineering_jobs']:3} | Rel: {r['potentially_relevant']:2}")
            results.append(r)
        time.sleep(0.15)

    with open("scratch/lever_search_test.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
