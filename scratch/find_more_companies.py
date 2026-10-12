"""Broad scan to discover active Lever and Greenhouse boards for India / Remote tech companies."""

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

from candidate_auditor import (
    probe_greenhouse,
    probe_lever,
    is_india_loc,
    is_remote_loc,
    is_engineering_job,
    is_potentially_relevant,
)

CANDIDATES = [
    # Indian startups / unicorns / tech
    "zepto", "blinkit", "zomato", "swiggy", "rapido", "spinny", "cars24",
    "pocketfm", "unacademy", "scaler", "interviewbit", "hackerrank",
    "cleartax", "khatabook", "leadsquared", "exotel", "sprinklr",
    "thoughtspot", "druva", "juspay", "fampay", "epifi", "slice",
    "navi", "indmoney", "smallcase", "acko", "godigit", "dealshare",
    "airmeet", "yellowai", "gupshup", "shiprocket", "delhivery", "shadowfax",
    "blackbuck", "inframarket", "lenskart", "nykaa", "urbancompany", "urbanclap",
    "curefit", "cultfit", "mpl", "loconav", "classplus", "browserstack",
    "clevertap", "freshworks", "chargebee", "hasura", "postman", "getpostman",
    "razorpay", "cred", "udaan", "inmobi", "meesho", "paytm", "zeta",
    
    # Global / Remote tech & AI
    "openai", "anthropic", "scale", "scaleapi", "perplexity", "cohere",
    "databricks", "snowflake", "confluent", "sentry", "launchdarkly",
    "circleci", "harness", "jfrog", "snyk", "wiz", "pagerduty",
    "automattic", "duckduckgo", "mozilla", "brave", "sumologic",
    "newrelic", "elastic", "stripe", "gitlab", "airbnb", "datadog",
    "mongodb", "instawork", "twilio", "okta", "coinbase", "samsara",
    "rubrik", "gusto", "canonical", "cloudflare", "deliveroo",
    "sourcegraph", "zapier", "docker", "dbtlabs", "prefect", "astronomer",
    "flyio", "fly-io", "render", "supabase", "vercel", "linear",
    "replit", "wandb", "modal", "langchain", "deepgram", "groq"
]


def main():
    print(f"Scanning {len(CANDIDATES)} candidates on both Greenhouse and Lever...")
    gh_valid = []
    lever_valid = []

    for name in CANDIDATES:
        # Check Greenhouse
        try:
            gh_res = probe_greenhouse(name)
            if gh_res["http_status"] == 200 and gh_res["available"] > 0:
                print(f"[GH 200] {name:15} Avail: {gh_res['available']:4} | India: {gh_res['india_jobs']:3} | Remote: {gh_res['remote_jobs']:3} | Eng: {gh_res['engineering_jobs']:3} | Rel: {gh_res['potentially_relevant']:2}")
                gh_valid.append(gh_res)
        except Exception:
            pass

        # Check Lever
        try:
            lever_res = probe_lever(name)
            if lever_res["http_status"] == 200 and lever_res["available"] > 0:
                print(f"[LV 200] {name:15} Avail: {lever_res['available']:4} | India: {lever_res['india_jobs']:3} | Remote: {lever_res['remote_jobs']:3} | Eng: {lever_res['engineering_jobs']:3} | Rel: {lever_res['potentially_relevant']:2}")
                lever_valid.append(lever_res)
        except Exception:
            pass

        time.sleep(0.2)

    with open("scratch/gh_valid_discovered.json", "w", encoding="utf-8") as f:
        json.dump(gh_valid, f, indent=2)

    with open("scratch/lever_valid_discovered.json", "w", encoding="utf-8") as f:
        json.dump(lever_valid, f, indent=2)

    print(f"\nDone! Discovered {len(gh_valid)} active Greenhouse boards and {len(lever_valid)} active Lever boards.")


if __name__ == "__main__":
    main()
