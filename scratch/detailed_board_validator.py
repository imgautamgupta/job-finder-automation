"""Detailed validator script for all discovered candidates to generate comprehensive metrics.

Checks specific role keywords (Python, Backend, Full Stack, AI/ML, Intern/Entry)
and specific locations (Delhi, Noida, Bengaluru, Ahmedabad, India, Remote).
"""

import json
import re
import urllib.request
import urllib.error
from typing import Any, Dict, List

HEADERS = {
    "User-Agent": "JobFinderAutomation/1.0 (Candidate Board Validator; polite crawler)",
    "Accept": "application/json",
}

def analyze_jobs(platform: str, company: str, jobs_raw: List[Dict[str, Any]]) -> Dict[str, Any]:
    metrics = {
        "company": company,
        "platform": platform,
        "board_identifier": company,
        "available_postings": len(jobs_raw),
        "india_jobs": 0,
        "bengaluru_jobs": 0,
        "delhi_jobs": 0,
        "noida_jobs": 0,
        "remote_jobs": 0,
        "ahmedabad_jobs": 0,
        "software_eng_jobs": 0,
        "python_jobs": 0,
        "backend_jobs": 0,
        "fullstack_jobs": 0,
        "aiml_jobs": 0,
        "intern_entry_jobs": 0,
        "potentially_relevant": 0,
        "sample_relevant_titles": [],
        "sample_rejected_titles": [],
    }

    senior_negatives = ["senior", "lead", "principal", "staff", "manager", "director", "architect", "vp", "head of"]

    for j in jobs_raw:
        if platform == "Lever":
            title = (j.get("text") or "").strip()
            cats = j.get("categories") or {}
            loc = (cats.get("location") or "").strip()
            dept = (cats.get("department") or "").strip()
            workplace = (j.get("workplaceType") or "").strip()
            full_loc = f"{loc} {workplace}".strip()
            content = j.get("descriptionPlain") or ""
        else: # Greenhouse
            title = (j.get("title") or "").strip()
            loc_obj = j.get("location") or {}
            loc = (loc_obj.get("name") if isinstance(loc_obj, dict) else str(loc_obj)) or ""
            departments = [d.get("name", "") for d in j.get("departments", []) if isinstance(d, dict)]
            dept = " ".join(departments)
            full_loc = loc
            content = j.get("content") or ""

        t_lower = title.lower()
        l_lower = full_loc.lower()
        c_lower = (content or "").lower()
        full_text = f"{t_lower} {c_lower}"

        is_ind = any(k in l_lower for k in ["india", "bangalore", "bengaluru", "delhi", "noida", "gurgaon", "gurugram", "mumbai", "pune", "hyderabad", "chennai", "ahmedabad"])
        is_rem = "remote" in l_lower or "anywhere" in l_lower or "distributed" in l_lower or "work from home" in l_lower

        if is_ind:
            metrics["india_jobs"] += 1
            if "bangalore" in l_lower or "bengaluru" in l_lower:
                metrics["bengaluru_jobs"] += 1
            if "delhi" in l_lower or "gurgaon" in l_lower or "gurugram" in l_lower:
                metrics["delhi_jobs"] += 1
            if "noida" in l_lower:
                metrics["noida_jobs"] += 1
            if "ahmedabad" in l_lower:
                metrics["ahmedabad_jobs"] += 1
        if is_rem:
            metrics["remote_jobs"] += 1

        is_eng = any(k in f"{t_lower} {dept.lower()}" for k in ["engineer", "developer", "software", "backend", "frontend", "full stack", "fullstack", "data", "ml", "ai", "sde", "technology"])
        if is_eng:
            metrics["software_eng_jobs"] += 1

        is_py = "python" in t_lower or "python" in full_text
        if is_py and is_eng:
            metrics["python_jobs"] += 1

        is_be = "backend" in t_lower or "back-end" in t_lower or "back end" in t_lower
        if is_be:
            metrics["backend_jobs"] += 1

        is_fs = "full stack" in t_lower or "fullstack" in t_lower or "full-stack" in t_lower
        if is_fs:
            metrics["fullstack_jobs"] += 1

        is_ai = any(k in t_lower for k in ["machine learning", "ml ", "ml engineer", "ai ", "ai engineer", "artificial intelligence", "nlp", "computer vision", "deep learning"])
        if is_ai:
            metrics["aiml_jobs"] += 1

        is_intern = any(k in t_lower for k in ["intern", "internship", "fresher", "entry level", "entry-level", "graduate", "junior", "associate", "trainee", "apprentice"])
        if is_intern:
            metrics["intern_entry_jobs"] += 1

        # Check potential relevance for our profile
        if (is_ind or is_rem) and is_eng:
            has_senior = any(re.search(r"\b" + re.escape(neg) + r"\b", t_lower) for neg in senior_negatives)
            target_role_match = any(r in t_lower for r in [
                "software engineer", "developer", "backend", "full stack", "fullstack",
                "python", "web", "machine learning", "ml", "ai", "sde", "intern"
            ])
            if target_role_match and not has_senior:
                metrics["potentially_relevant"] += 1
                if len(metrics["sample_relevant_titles"]) < 4:
                    metrics["sample_relevant_titles"].append(f"{title} [{full_loc}]")
            else:
                if len(metrics["sample_rejected_titles"]) < 2:
                    metrics["sample_rejected_titles"].append(f"{title} (Excluded/Non-target)")

    return metrics


def main():
    lever_companies = [
        "paytm", "meesho", "jumpcloud", "fampay", "zeta", "cred", "epifi", "pocketfm", "curai", "palantir"
    ]
    gh_companies = [
        "gitlab", "stripe", "mongodb", "instawork", "twilio", "samsara", "rubrik",
        "glance", "hackerrank", "inmobi", "launchdarkly", "databricks", "airbnb",
        "elastic", "cloudflare", "affirm", "gusto", "canonical", "deliveroo"
    ]

    all_metrics = []

    print("=== Fetching & Evaluating Lever Candidates ===")
    for c in lever_companies:
        url = f"https://api.lever.co/v0/postings/{c}?mode=json"
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                m = analyze_jobs("Lever", c, data)
                all_metrics.append(m)
                print(f"[Lever] {c:12} | Avail: {m['available_postings']:3} | Ind: {m['india_jobs']:3} (Blr:{m['bengaluru_jobs']:2}, Del:{m['delhi_jobs']:2}, Noi:{m['noida_jobs']:2}) | Rem: {m['remote_jobs']:3} | Eng: {m['software_eng_jobs']:3} | Rel: {m['potentially_relevant']:2}")
        except Exception as e:
            print(f"[Lever] {c} Error: {e}")

    print("\n=== Fetching & Evaluating Greenhouse Candidates ===")
    for c in gh_companies:
        url = f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs?content=true"
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                jobs = data.get("jobs", [])
                m = analyze_jobs("Greenhouse", c, jobs)
                all_metrics.append(m)
                print(f"[GH]    {c:12} | Avail: {m['available_postings']:3} | Ind: {m['india_jobs']:3} (Blr:{m['bengaluru_jobs']:2}, Del:{m['delhi_jobs']:2}, Noi:{m['noida_jobs']:2}) | Rem: {m['remote_jobs']:3} | Eng: {m['software_eng_jobs']:3} | Rel: {m['potentially_relevant']:2}")
        except Exception as e:
            print(f"[GH]    {c} Error: {e}")

    with open("scratch/detailed_validation_metrics.json", "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2)

    print("\nDone! Saved detailed metrics to scratch/detailed_validation_metrics.json")

if __name__ == "__main__":
    main()
