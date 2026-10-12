"""Test Indian fintechs, startups, and tech companies on Lever and Greenhouse."""

import json
import time
from candidate_auditor import probe_lever, probe_greenhouse

CANDIDATES = [
    "cashfree", "simpl", "fibe", "earlysalary", "kreditbee", "navi-technologies",
    "openfinancial", "goniyo", "niyo", "rupeek", "moneyview", "scapia",
    "uni-cards", "onecard", "fpl-technologies", "upstox", "angelone",
    "dhan", "myjar", "jar", "decentro", "setu", "signzy", "idfy",
    "hyperverge", "leegality", "games24x7", "dream11", "dreamsports",
    "redbus", "makemytrip", "ixigo", "oyo", "oyorooms", "porter",
    "rapido", "spinny", "cars24", "bluedart", "rivigo", "mobikwik",
    "one97", "billdesk", "perfios", "finbox", "invoid", "treebo",
    "cleartrip", "yatra", "shadowfax", "delhivery", "blackbuck"
]

def main():
    print("Testing fintechs and startups...")
    found_lever = []
    found_gh = []
    for c in CANDIDATES:
        try:
            r = probe_lever(c)
            if r["http_status"] == 200 and r["available"] > 0:
                print(f"[LV 200] {c:20} Avail: {r['available']:4} | India: {r['india_jobs']:3} | Remote: {r['remote_jobs']:3} | Eng: {r['engineering_jobs']:3} | Rel: {r['potentially_relevant']:2}")
                found_lever.append(r)
        except Exception:
            pass

        try:
            r = probe_greenhouse(c)
            if r["http_status"] == 200 and r["available"] > 0:
                print(f"[GH 200] {c:20} Avail: {r['available']:4} | India: {r['india_jobs']:3} | Remote: {r['remote_jobs']:3} | Eng: {r['engineering_jobs']:3} | Rel: {r['potentially_relevant']:2}")
                found_gh.append(r)
        except Exception:
            pass
        time.sleep(0.12)

    with open("scratch/fintech_discovered.json", "w", encoding="utf-8") as f:
        json.dump({"lever": found_lever, "greenhouse": found_gh}, f, indent=2)

if __name__ == "__main__":
    main()
