"""Lightweight audit script to probe and validate candidate companies on Lever and Greenhouse.

Respects rate limits and uses only public endpoints.
"""

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

LEVER_URL_FMT = "https://api.lever.co/v0/postings/{company}?mode=json"
GREENHOUSE_URL_FMT = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"

HEADERS = {
    "User-Agent": "JobFinderAutomation/1.0 (Candidate Board Validator; polite crawler)",
    "Accept": "application/json",
}

INDIA_LOC_KEYWORDS = [
    "india", "delhi", "new delhi", "noida", "gurgaon", "gurugram",
    "bangalore", "bengaluru", "ahmedabad", "mumbai", "pune", "hyderabad", "chennai"
]
TARGET_ROLE_KEYWORDS = [
    "python", "backend", "software engineer", "software development",
    "full stack", "fullstack", "web developer", "web development",
    "ml engineer", "machine learning", "ai engineer", "artificial intelligence",
    "sde", "intern", "internship", "fresher", "entry level", "graduate"
]
EXCLUDED_KEYWORDS = [
    "senior", "lead", "principal", "staff", "manager", "director",
    "architect", "vp", "head of", "5+ years", "7+ years", "10+ years"
]


def is_india_loc(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(loc in t for loc in INDIA_LOC_KEYWORDS)


def is_remote_loc(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return "remote" in t or "anywhere" in t or "distributed" in t or "work from home" in t


def is_engineering_job(title: str, dept: str = "") -> bool:
    combined = f"{title} {dept}".lower()
    eng_keywords = [
        "engineer", "engineering", "developer", "development",
        "software", "backend", "frontend", "full stack", "fullstack",
        "python", "data", "machine learning", "ml", "ai", "sde", "tech"
    ]
    return any(kw in combined for kw in eng_keywords)


def is_potentially_relevant(title: str, loc: str) -> Tuple[bool, str]:
    t_lower = title.lower()
    l_lower = (loc or "").lower()

    # Check location: must be India or Remote
    loc_match = is_india_loc(l_lower) or is_remote_loc(l_lower)
    if not loc_match:
        return False, "Non-target location"

    # Check negative title keywords
    for neg in EXCLUDED_KEYWORDS:
        if re.search(r"\b" + re.escape(neg) + r"\b", t_lower):
            return False, f"Excluded keyword: {neg}"

    # Check positive target role keywords
    matched_role = None
    for rk in TARGET_ROLE_KEYWORDS:
        if rk in t_lower:
            matched_role = rk
            break
    if not matched_role:
        return False, "Role not in target list"

    return True, f"Matched: {matched_role}"


def probe_lever(company: str) -> Dict[str, Any]:
    url = LEVER_URL_FMT.format(company=company.strip().lower())
    req = urllib.request.Request(url, headers=HEADERS)
    res = {
        "company": company,
        "platform": "Lever",
        "endpoint": url,
        "http_status": 0,
        "available": 0,
        "india_jobs": 0,
        "bengaluru_jobs": 0,
        "delhi_jobs": 0,
        "noida_jobs": 0,
        "remote_jobs": 0,
        "ahmedabad_jobs": 0,
        "engineering_jobs": 0,
        "potentially_relevant": 0,
        "sample_relevant": [],
        "sample_titles": [],
        "error": None,
    }
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res["http_status"] = response.status
            data = json.loads(response.read().decode("utf-8"))
            if isinstance(data, list):
                res["available"] = len(data)
                for item in data:
                    title = item.get("text", "")
                    cats = item.get("categories", {}) or {}
                    loc = cats.get("location", "") or ""
                    workplace = item.get("workplaceType", "") or ""
                    full_loc = f"{loc} {workplace}".strip()
                    dept = cats.get("department", "") or ""

                    if len(res["sample_titles"]) < 5:
                        res["sample_titles"].append(f"{title} ({full_loc})")

                    if is_india_loc(full_loc):
                        res["india_jobs"] += 1
                        fl_lower = full_loc.lower()
                        if "bangalore" in fl_lower or "bengaluru" in fl_lower:
                            res["bengaluru_jobs"] += 1
                        if "delhi" in fl_lower:
                            res["delhi_jobs"] += 1
                        if "noida" in fl_lower:
                            res["noida_jobs"] += 1
                        if "ahmedabad" in fl_lower:
                            res["ahmedabad_jobs"] += 1

                    if is_remote_loc(full_loc):
                        res["remote_jobs"] += 1

                    if is_engineering_job(title, dept):
                        res["engineering_jobs"] += 1

                    is_rel, reason = is_potentially_relevant(title, full_loc)
                    if is_rel:
                        res["potentially_relevant"] += 1
                        if len(res["sample_relevant"]) < 5:
                            res["sample_relevant"].append(f"{title} [{full_loc}]")
    except urllib.error.HTTPError as he:
        res["http_status"] = he.code
        res["error"] = f"HTTP {he.code}"
    except Exception as e:
        res["error"] = str(e)
    return res


def probe_greenhouse(company: str) -> Dict[str, Any]:
    url = GREENHOUSE_URL_FMT.format(company=company.strip().lower())
    req = urllib.request.Request(url, headers=HEADERS)
    res = {
        "company": company,
        "platform": "Greenhouse",
        "endpoint": url,
        "http_status": 0,
        "available": 0,
        "india_jobs": 0,
        "bengaluru_jobs": 0,
        "delhi_jobs": 0,
        "noida_jobs": 0,
        "remote_jobs": 0,
        "ahmedabad_jobs": 0,
        "engineering_jobs": 0,
        "potentially_relevant": 0,
        "sample_relevant": [],
        "sample_titles": [],
        "error": None,
    }
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res["http_status"] = response.status
            data = json.loads(response.read().decode("utf-8"))
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            res["available"] = len(jobs)
            for item in jobs:
                title = item.get("title", "")
                loc_obj = item.get("location", {}) or {}
                loc = loc_obj.get("name", "") if isinstance(loc_obj, dict) else str(loc_obj)
                departments = [d.get("name", "") for d in item.get("departments", []) if isinstance(d, dict)]
                dept_str = " ".join(departments)

                if len(res["sample_titles"]) < 5:
                    res["sample_titles"].append(f"{title} ({loc})")

                if is_india_loc(loc):
                    res["india_jobs"] += 1
                    l_lower = loc.lower()
                    if "bangalore" in l_lower or "bengaluru" in l_lower:
                        res["bengaluru_jobs"] += 1
                    if "delhi" in l_lower:
                        res["delhi_jobs"] += 1
                    if "noida" in l_lower:
                        res["noida_jobs"] += 1
                    if "ahmedabad" in l_lower:
                        res["ahmedabad_jobs"] += 1

                if is_remote_loc(loc):
                    res["remote_jobs"] += 1

                if is_engineering_job(title, dept_str):
                    res["engineering_jobs"] += 1

                is_rel, reason = is_potentially_relevant(title, loc)
                if is_rel:
                    res["potentially_relevant"] += 1
                    if len(res["sample_relevant"]) < 5:
                        res["sample_relevant"].append(f"{title} [{loc}]")
    except urllib.error.HTTPError as he:
        res["http_status"] = he.code
        res["error"] = f"HTTP {he.code}"
    except Exception as e:
        res["error"] = str(e)
    return res


def main():
    greenhouse_candidates = [
        "elastic", "stripe", "gitlab", "airbnb", "razorpay", "cred", "swiggy",
        "groww", "postman", "browserstack", "clevertap", "atlassian", "gusto",
        "hashicorp", "datadog", "mongodb", "instawork", "urbancompany", "curefit",
        "inmobi", "chargebee", "freshworks", "zeta", "canonical", "cloudflare",
        "deliveroo", "grab", "gojek", "cars24", "twilio", "okta", "uber",
        "github", "coinbase", "samsara", "rubrik", "cohesity", "nutanix"
    ]

    lever_candidates = [
        "palantir", "meesho", "inmobi", "udaan", "sourcegraph", "cohere",
        "zapier", "docker", "instamojo", "clevertap", "zeta", "razorpay",
        "cred", "dunzo", "paytm", "bharatpe", "phonepe", "replit",
        "scaleapi", "scale", "togetherai", "groq", "mistral", "perplexity",
        "deepgram", "weightsandbiases", "wandb", "modal", "huggingface",
        "langchain", "snorkel", "anthropic", "anyscale", "cursor",
        "anysphere", "vercel", "linear", "fly-io", "render", "supabase",
        "hasura", "prefect", "astronomer", "dbtlabs"
    ]

    results = []
    print("=== Auditing Greenhouse Candidates ===")
    for c in greenhouse_candidates:
        r = probe_greenhouse(c)
        results.append(r)
        status = r["http_status"]
        if status == 200:
            print(f"[GH 200] {c:15} Avail: {r['available']:4} | India: {r['india_jobs']:3} | Remote: {r['remote_jobs']:3} | Eng: {r['engineering_jobs']:3} | Potentially Rel: {r['potentially_relevant']:2}")
        else:
            print(f"[GH {status}] {c:15} Error: {r.get('error')}")
        time.sleep(0.3)

    print("\n=== Auditing Lever Candidates ===")
    for c in lever_candidates:
        r = probe_lever(c)
        results.append(r)
        status = r["http_status"]
        if status == 200:
            print(f"[LEVER 200] {c:15} Avail: {r['available']:4} | India: {r['india_jobs']:3} | Remote: {r['remote_jobs']:3} | Eng: {r['engineering_jobs']:3} | Potentially Rel: {r['potentially_relevant']:2}")
        else:
            print(f"[LEVER {status}] {c:15} Error: {r.get('error')}")
        time.sleep(0.3)

    with open("scratch/audit_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nAudit saved to scratch/audit_results.json")


if __name__ == "__main__":
    main()
