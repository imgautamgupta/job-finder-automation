"""Job filtering service matching jobs against user preferences."""

import logging
import re
from typing import List
import unicodedata

from app.models.profile import JobProfile
from app.models.job import Job
from app.services.matcher import has_explicit_seniority_experience, is_india_eligible_remote

logger = logging.getLogger(__name__)


class JobFilter:
    """Filters job listings based on defined profile rules and criteria."""

    def __init__(self, profile: JobProfile):
        self.profile = profile

    def is_match(self, job: Job) -> bool:
        """Evaluate if a single Job listing satisfies user preferences."""
        title_lower = (job.title or "").lower()
        desc_lower = (job.description or "").lower()
        exp_lower = (job.experience_required or "").lower()
        location_raw = job.location or ""
        location_norm = unicodedata.normalize("NFC", location_raw)
        location_lower = location_norm.lower()

        # 1. Negative keyword exclusion
        for neg_kw in self.profile.negative_keywords:
            neg_lower = neg_kw.lower().strip()
            if not neg_lower:
                continue

            pattern = r"\b" + re.escape(neg_lower) + r"\b" if neg_lower.isalnum() else re.escape(neg_lower)

            # Check title (primary seniority signal: Senior, Lead, Staff, Manager, etc.)
            if re.search(pattern, title_lower):
                logger.debug(
                    "Job '%s' excluded by title negative keyword: '%s'", job.title, neg_kw
                )
                return False

            # Check explicit structured experience field
            if exp_lower and re.search(pattern, exp_lower):
                logger.debug(
                    "Job '%s' excluded by experience field negative keyword: '%s'", job.title, neg_kw
                )
                return False

            # Check explicit experience requirements in description (e.g. 5+ years required)
            if neg_lower in ("5+ years", "7+ years", "10+ years") and has_explicit_seniority_experience(desc_lower):
                logger.debug(
                    "Job '%s' excluded by explicit experience requirement in description: '%s'", job.title, neg_kw
                )
                return False

        # 2. Remote check (India-eligible remote)
        is_job_remote = is_india_eligible_remote(location_norm)
        if self.profile.remote_only and not is_job_remote:
            logger.debug("Job '%s' excluded because not India-eligible remote", job.title)
            return False

        if not self.profile.preferences.remote_allowed and is_job_remote:
            logger.debug("Job '%s' excluded because remote is not allowed", job.title)
            return False

        # 3. Internship check
        is_internship = "intern" in title_lower or "internship" in title_lower
        if is_internship and not self.profile.preferences.internship_allowed:
            logger.debug("Job '%s' excluded because internships are not allowed", job.title)
            return False

        # 4. Target role match (title contains any role token/term with word boundary awareness)
        if self.profile.target_roles:
            role_matched = False
            for role in self.profile.target_roles:
                role_clean = role.strip()
                if not role_clean:
                    continue
                role_lower = role_clean.lower()

                # Check 1: Exact phrase with word boundaries
                if re.search(r"\b" + re.escape(role_lower) + r"\b", title_lower):
                    role_matched = True
                    break

                # Check 2: All constituent tokens appear with word boundaries
                role_tokens = [t for t in re.split(r"[\s\-_/]+", role_lower) if t]
                if len(role_tokens) > 1 and all(
                    re.search(r"\b" + re.escape(t) + r"\b", title_lower) for t in role_tokens
                ):
                    role_matched = True
                    break

            if not role_matched:
                logger.debug("Job '%s' does not match any target roles", job.title)
                return False

        # 5. Location match (if locations specified)
        if self.profile.preferred_locations and not (self.profile.remote_only and is_job_remote):
            is_loc_matched = False
            # Check if remote matches allowed remote and is India-eligible
            if is_job_remote and self.profile.preferences.remote_allowed:
                is_loc_matched = True
            elif location_lower and location_lower not in ("unknown", "none", "n/a", "not specified"):
                unrelated_cities = {
                    "mumbai", "pune", "hyderabad", "chennai", "kolkata", "jaipur",
                    "lucknow", "chandigarh", "kochi", "indore", "bhopal", "gurgaon",
                    "gurugram", "nagpur", "patna", "bhubaneswar", "visakhapatnam",
                    "trivandrum", "coimbatore", "surat", "vadodara", "london", "singapore",
                    "new york", "berlin", "tokyo", "sydney", "dubai", "toronto"
                }
                has_unrelated_city = any(re.search(r"\b" + re.escape(c) + r"\b", location_lower) for c in unrelated_cities)

                for pref_loc in self.profile.preferred_locations:
                    p_low = pref_loc.lower().strip()
                    if p_low == "remote":
                        continue
                    if p_low in ("bangalore", "bengaluru") and ("bangalore" in location_lower or "bengaluru" in location_lower):
                        is_loc_matched = True
                        break
                    if p_low == "india":
                        if not has_unrelated_city and re.search(r"\b(india|pan[- ]india|all[- ]india)\b", location_lower):
                            is_loc_matched = True
                            break
                    elif re.search(r"\b" + re.escape(p_low) + r"\b", location_lower):
                        is_loc_matched = True
                        break

            if not is_loc_matched:
                logger.debug(
                    "Job '%s' location '%s' does not match preferred locations",
                    job.title,
                    job.location,
                )
                return False

        # 6. Employment type check if available on the job
        if job.employment_type and self.profile.employment_types:
            job_emp_type = job.employment_type.lower()
            emp_matched = any(
                emp.lower() in job_emp_type for emp in self.profile.employment_types
            )
            if not emp_matched:
                logger.debug(
                    "Job '%s' employment type '%s' does not match preferences",
                    job.title,
                    job.employment_type,
                )
                return False

        return True

    def filter_jobs(self, jobs: List[Job]) -> List[Job]:
        """Filter a list of Job instances according to profile rules."""
        matched_jobs: List[Job] = []
        for job in jobs:
            if self.is_match(job):
                matched_jobs.append(job)
        logger.info(
            "Filtered %d listings down to %d matching jobs",
            len(jobs),
            len(matched_jobs),
        )
        return matched_jobs
