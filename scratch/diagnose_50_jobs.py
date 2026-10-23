"""Diagnose the 50 jobs collected by AccentureJobSource under current settings."""
import asyncio
import json
import re
import sys

sys.path.insert(0, ".")

from app.config.settings import get_settings
from app.services.filter import JobFilter
from app.services.matcher import JobMatcher, has_explicit_seniority_experience
from app.sources.accenture import AccentureJobSource, determine_accenture_eligibility

async def diagnose():
    settings = get_settings()
    profile = settings.load_profile()
    source = AccentureJobSource(is_enabled=True, settings=settings)

    print("Collecting 50 jobs from Accenture using current settings...")
    jobs = await source.collect_jobs(
        roles=profile.target_roles,
        locations=profile.preferred_locations,
        max_results=50,
    )
    print(f"Collected {len(jobs)} jobs.\n")

    job_filter = JobFilter(profile=profile)
    matcher = JobMatcher(profile=profile)

    diagnosis_results = []

    for idx, job in enumerate(jobs, 1):
        job_id = job.source_job_id or "UNAVAILABLE"
        title = job.title or "Untitled"
        location = job.location or "Unspecified"
        exp_req = job.experience_required or "Unspecified"
        desc = job.description or ""
        eligibility = job.extra_metadata.get("eligibility", "Unknown")

        # Evaluate each filter gate
        rejection_reasons = []

        # 1. Negative keywords
        for neg in profile.negative_keywords:
            neg_low = neg.lower().strip()
            if not neg_low:
                continue
            pat = r"\b" + re.escape(neg_low) + r"\b" if neg_low.isalnum() else re.escape(neg_low)
            if re.search(pat, title.lower()):
                rejection_reasons.append(f"Title negative keyword: '{neg}'")
            if exp_req != "Unspecified" and re.search(pat, exp_req.lower()):
                rejection_reasons.append(f"Experience negative keyword: '{neg}'")
            if neg_low in ("5+ years", "7+ years", "10+ years") and has_explicit_seniority_experience(desc.lower()):
                rejection_reasons.append(f"Description explicit seniority: '{neg}'")

        # 2. Target role
        role_matched = False
        matched_role_name = None
        for role in profile.target_roles:
            role_low = role.lower().strip()
            if re.search(r"\b" + re.escape(role_low) + r"\b", title.lower()):
                role_matched = True
                matched_role_name = role
                break
            tokens = [t for t in re.split(r"[\s\-_/]+", role_low) if t]
            if len(tokens) > 1 and all(re.search(r"\b" + re.escape(t) + r"\b", title.lower()) for t in tokens):
                role_matched = True
                matched_role_name = role
                break
        if not role_matched:
            rejection_reasons.append(f"Role mismatch: title '{title}' does not match any profile target role")

        # 3. Location match
        unapproved = ["mumbai", "pune", "hyderabad", "chennai", "kolkata", "gurugram", "gurgaon"]
        loc_low = location.lower()
        unapproved_found = [c for c in unapproved if c in loc_low]
        if unapproved_found:
            rejection_reasons.append(f"Excluded location: contains {unapproved_found}")
        else:
            allowed = any(p.lower() in loc_low for p in ["bangalore", "bengaluru", "delhi", "noida", "ahmedabad", "remote"])
            if not allowed:
                rejection_reasons.append(f"Location not in preferred list: '{location}'")

        # 4. Experience assessment
        desc_min_exp = None
        m_exp = re.search(r"minimum\s*(\d+)\s*year", desc.lower())
        if m_exp:
            desc_min_exp = f"Minimum {m_exp.group(1)} years"

        # Classification
        is_filter_match = job_filter.is_match(job)

        # Assessment of rejection
        # Is it a true rejection (correct), false rejection (incorrectly excluded), or uncertain?
        if not role_matched:
            assessment = "CORRECT_REJECTION (Irrelevant role)"
        elif unapproved_found:
            assessment = "CORRECT_REJECTION (Excluded location)"
        elif eligibility == "Ineligible" or "5-10" in exp_req or (desc_min_exp and "5" in desc_min_exp):
            assessment = "CORRECT_REJECTION (Senior experience >= 5 yrs)"
        elif "0-2" in exp_req or "0-1" in exp_req or eligibility == "Eligible":
            if not is_filter_match:
                assessment = "FALSE_REJECTION (Eligible fresher/0-2 yrs but filtered out)"
            else:
                assessment = "MATCH"
        elif eligibility == "Needs Review" or exp_req == "Unspecified":
            assessment = "UNCERTAIN / NEEDS_REVIEW"
        else:
            assessment = "CORRECT_REJECTION"

        result = {
            "index": idx,
            "job_id": job_id,
            "title": title,
            "location": location,
            "experience_required": exp_req,
            "desc_min_exp": desc_min_exp,
            "eligibility": eligibility,
            "rejection_reasons": rejection_reasons,
            "is_filter_match": is_filter_match,
            "assessment": assessment,
        }
        diagnosis_results.append(result)

        print(f"[{idx:02d}] {job_id} | {title} | {location} | Exp: {exp_req}")
        print(f"     Eligibility: {eligibility} | Filter Match: {is_filter_match}")
        print(f"     Reasons: {'; '.join(rejection_reasons) if rejection_reasons else 'None (Passed)'}")
        print(f"     Assessment: {assessment}\n")

    # Summary
    assessments_count = {}
    for r in diagnosis_results:
        a = r["assessment"].split(" ")[0]
        assessments_count[a] = assessments_count.get(a, 0) + 1
    print("=== DIAGNOSIS SUMMARY ===")
    for k, v in assessments_count.items():
        print(f"  {k}: {v}")

    with open("scratch/diagnosis_50_jobs.json", "w", encoding="utf-8") as f:
        json.dump(diagnosis_results, f, indent=2)
    print("\nSaved diagnosis to scratch/diagnosis_50_jobs.json")

if __name__ == "__main__":
    asyncio.run(diagnose())
