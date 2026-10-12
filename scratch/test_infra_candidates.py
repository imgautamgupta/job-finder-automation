"""Test more global tech and infrastructure startups on Lever."""

import json
import time
from candidate_auditor import probe_lever, probe_greenhouse

CANDIDATES = [
    "digitalocean", "box", "squarespace", "vimeo", "quizlet", "duolingo",
    "coursera", "udacity", "khanacademy", "medium", "quora", "stackoverflow",
    "hackerone", "bugcrowd", "fastly", "algolia", "influxdata", "timescale",
    "cockroachlabs", "yugabyte", "clickhouse", "pinecone", "weaviate",
    "qdrant", "zilliz", "auth0", "kong", "postman"
]

def main():
    print("Testing dev tools / infra on Lever and Greenhouse...")
    for c in CANDIDATES:
        try:
            r = probe_lever(c)
            if r["http_status"] == 200 and r["available"] > 0:
                print(f"[LV 200] {c:18} Avail: {r['available']:4} | India: {r['india_jobs']:3} | Remote: {r['remote_jobs']:3} | Eng: {r['engineering_jobs']:3} | Rel: {r['potentially_relevant']:2}")
        except Exception:
            pass

        try:
            r = probe_greenhouse(c)
            if r["http_status"] == 200 and r["available"] > 0:
                print(f"[GH 200] {c:18} Avail: {r['available']:4} | India: {r['india_jobs']:3} | Remote: {r['remote_jobs']:3} | Eng: {r['engineering_jobs']:3} | Rel: {r['potentially_relevant']:2}")
        except Exception:
            pass
        time.sleep(0.12)

if __name__ == "__main__":
    main()
