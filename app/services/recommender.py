"""Deterministic, explainable job recommendation and application workflow service (Phase 9).

Calculates Application Readiness Scores, Application Priority, Skill-Gap Analysis,
Profile Alignment, Match Explanations, Risk Reasons, and Application Checklists.
"""

import logging
import re
from typing import List, Optional, Set, Tuple
from urllib.parse import urlparse

from app.models.job import ApplicationPriority, Job, JobStatus
from app.models.profile import JobProfile
from app.models.recommendation import ApplicationRecommendation
from app.services.matcher import is_india_eligible_remote

logger = logging.getLogger(__name__)

# Known application platforms
KNOWN_SOURCES = {
    "lever",
    "greenhouse",
    "naukri",
    "linkedin",
    "ashby",
    "workable",
    "smartrecruiters",
    "bamboohr",
    "icims",
}

# Technical Skills Ontology for Gap Analysis
TECH_SKILLS_ONTOLOGY = {
    # Core Backend & Languages
    "Java": {"category": "critical", "patterns": [r"\bjava\b(?!script)"]},
    "Spring Boot": {"category": "critical", "patterns": [r"\bspring\s*boot\b", r"\bspring\s*framework\b"]},
    "C++": {"category": "critical", "patterns": [r"\bc\+\+\b"]},
    "C#": {"category": "critical", "patterns": [r"\bc#\b", r"\bc\s*sharp\b"]},
    ".NET": {"category": "critical", "patterns": [r"\b\.net\b", r"\basp\.net\b"]},
    "Go / Golang": {"category": "critical", "patterns": [r"\bgolang\b", r"\bgo\s+language\b"]},
    "Rust": {"category": "critical", "patterns": [r"\brust\b"]},
    "Ruby": {"category": "critical", "patterns": [r"\bruby\b", r"\bruby\s+on\s+rails\b", r"\brails\b"]},
    "PHP": {"category": "critical", "patterns": [r"\bphp\b", r"\blaravel\b"]},
    "Kotlin": {"category": "critical", "patterns": [r"\bkotlin\b"]},
    "Swift": {"category": "critical", "patterns": [r"\bswift\b(?!ui)"]},

    # Modern Frontend / Fullstack
    "Angular": {"category": "moderate", "patterns": [r"\bangular\b(?:\s*js)?"]},
    "Vue.js": {"category": "moderate", "patterns": [r"\bvue(?:\.js)?\b"]},
    "Node.js": {"category": "moderate", "patterns": [r"\bnode(?:\.js)?\b"]},
    "Express.js": {"category": "moderate", "patterns": [r"\bexpress(?:\.js)?\b"]},
    "NestJS": {"category": "moderate", "patterns": [r"\bnest(?:\.js)?\b"]},

    # Databases, Caching & Streaming
    "Redis": {"category": "moderate", "patterns": [r"\bredis\b"]},
    "Kafka": {"category": "moderate", "patterns": [r"\bkafka\b", r"\bapache\s+kafka\b"]},
    "RabbitMQ": {"category": "moderate", "patterns": [r"\brabbitmq\b"]},
    "Elasticsearch": {"category": "moderate", "patterns": [r"\belasticsearch\b", r"\belastic\s+search\b"]},
    "Cassandra": {"category": "moderate", "patterns": [r"\bcassandra\b"]},
    "DynamoDB": {"category": "moderate", "patterns": [r"\bdynamodb\b"]},

    # Cloud, Containers & Architecture
    "Docker": {"category": "moderate", "patterns": [r"\bdocker\b", r"\bcontainerization\b"]},
    "Kubernetes": {"category": "moderate", "patterns": [r"\bkubernetes\b", r"\bk8s\b"]},
    "AWS": {"category": "moderate", "patterns": [r"\baws\b", r"\bamazon\s+web\s+services\b"]},
    "Azure": {"category": "moderate", "patterns": [r"\bazure\b", r"\bmicrosoft\s+azure\b"]},
    "GCP": {"category": "moderate", "patterns": [r"\bgcp\b", r"\bgoogle\s+cloud\b"]},
    "GraphQL": {"category": "moderate", "patterns": [r"\bgraphql\b"]},
    "Microservices": {"category": "moderate", "patterns": [r"\bmicroservices?\b", r"\bmicro-services?\b"]},
    "System Design": {"category": "moderate", "patterns": [r"\bsystem\s+design\b", r"\bdistributed\s+systems\b"]},

    # Tooling & Supporting Skills
    "CI/CD": {"category": "minor", "patterns": [r"\bci[/-]cd\b", r"\bcontinuous\s+integration\b"]},
    "Terraform": {"category": "minor", "patterns": [r"\bterraform\b"]},
    "Linux": {"category": "minor", "patterns": [r"\blinux\b", r"\bunix\b"]},
    "Jenkins": {"category": "minor", "patterns": [r"\bjenkins\b"]},
    "GitLab CI": {"category": "minor", "patterns": [r"\bgitlab\s+ci\b"]},
    "Agile": {"category": "minor", "patterns": [r"\bagile\b", r"\bscrum\b"]},
}

# Regex patterns identifying requirement/qualification sections
REQUIREMENT_HEADER_PATTERNS = [
    r"(?:requirements|qualifications|must\s+have|what\s+you'll\s+need|what\s+you\s+need|who\s+you\s+are|we're\s+looking\s+for|what\s+we\s+look\s+for|minimum\s+qualifications|basic\s+qualifications|key\s+skills)",
]

# High-seniority experience indicator regexes
SENIORITY_EXP_PATTERNS = [
    r"\b(?:minimum|min|at least|requires?|requiring)?\s*(?:[3-9]|1\d)\+?\s*(?:to|-|\+)?\s*(?:\d+)?\s*years?(?:\s+of)?\s*(?:experience|required)?\b",
    r"\b(?:[3-9]|1\d)\+\s*years?\b",
    r"\b(?:senior|lead|principal|staff|director|architect|head\s+of|sde\s*[-_]?\s*(?:iii|iv|3|4)|software\s+engineer\s*[-_]?\s*(?:iii|iv|3|4))\b",
]

# Fresher / Entry-level patterns
ENTRY_EXP_PATTERNS = [
    r"\b(?:0\s*-\s*[12]|0\s*to\s*[12]|1\s*-\s*2|1\s*to\s*2|up\s*to\s*2|upto\s*2)\s*years(?:\s+of)?\s*(?:experience)?\b",
    r"\b(?:fresher|intern|internship|entry[- ]level|college\s+grad|new\s+grad|trainee)\b",
]


class JobRecommender:
    """Deterministic, explainable recommendation and workflow engine."""

    def __init__(self, profile: JobProfile):
        self.profile = profile
        # Pre-normalize profile skills
        self.profile_skills_lower = {s.strip().lower() for s in profile.skills if s.strip()}

    def recommend(self, job: Job) -> ApplicationRecommendation:
        """Generate comprehensive application recommendation analysis for a job."""
        readiness_score = self.calculate_application_readiness(job)
        priority = self.determine_application_priority(job, readiness_score)
        missing_skills, critical_gaps, moderate_gaps, minor_gaps = self.analyze_skill_gaps(job)
        profile_alignment = self.get_profile_alignment(job)
        match_reasons = self.generate_match_reasons(job)
        risk_reasons = self.generate_risk_reasons(job, critical_gaps, moderate_gaps)
        checklist = self.build_application_checklist(job)

        rec = ApplicationRecommendation(
            job_id=job.id,
            match_score=job.match_score or 0,
            match_category=job.match_category or "Not Relevant",
            application_readiness_score=readiness_score,
            application_priority=priority,
            matched_skills=job.matched_skills,
            missing_skills=missing_skills,
            critical_gaps=critical_gaps,
            moderate_gaps=moderate_gaps,
            minor_gaps=minor_gaps,
            recommendation_reasons=match_reasons,
            risk_reasons=risk_reasons,
            profile_alignment=profile_alignment,
            checklist=checklist,
        )
        return rec

    def calculate_application_readiness(self, job: Job) -> int:
        """Calculate deterministic Application Readiness Score (0-100).

        Formula Breakdown:
        1. Existing Match Quality: 50 points (match_score * 0.50)
        2. Application Accessibility: 15 points
           - Valid direct job URL: 10 points
           - Known/verified application board structure: +5 points
        3. Experience Fit: 15 points
           - Explicit fresher/entry/0-1/0-2 requirement or experience match: 15 points
           - Missing/unspecified experience: 8 points
           - Explicit higher experience requirement (3+ yrs): 0 points
        4. Skill Coverage: 10 points
           - 5+ matched skills: 10 points
           - 3-4 matched skills: 7 points
           - 1-2 matched skills: 4 points
           - 0 matched skills: 0 points
        5. Readiness Signals: 10 points (5 signals @ 2 pts each)
           - Direct apply URL available
           - Company and source known
           - Detailed description available (>= 50 chars)
           - Location specified
           - Job title clearly identified
        """
        # 1. Match Quality (50 pts)
        match_score = job.match_score or 0
        match_points = round(match_score * 0.50)

        # 2. Application Accessibility (15 pts)
        access_points = 0
        if job.url and job.url.strip():
            parsed = urlparse(job.url.strip())
            if parsed.scheme in ("http", "https") and parsed.netloc:
                access_points += 10
                # Check known platform / verified direct posting structure
                source_norm = (job.source or "").lower().strip()
                if source_norm in KNOWN_SOURCES or any(p in job.url.lower() for p in ["/jobs/", "/postings/", "/apply", "/careers"]):
                    access_points += 5

        # 3. Experience Fit (15 pts)
        exp_text = f"{job.experience_required or ''} {job.title or ''}".lower()
        desc_text = (job.description or "").lower()

        has_senior = any(re.search(pat, exp_text) for pat in SENIORITY_EXP_PATTERNS) or any(
            re.search(pat, desc_text[:400]) for pat in SENIORITY_EXP_PATTERNS
        )
        has_entry = any(re.search(pat, exp_text) for pat in ENTRY_EXP_PATTERNS) or job.experience_match

        if has_senior and not has_entry:
            exp_points = 0
        elif has_entry:
            exp_points = 15
        elif not job.experience_required or not job.experience_required.strip():
            exp_points = 8
        else:
            exp_points = 8

        # 4. Skill Coverage (10 pts)
        matched_count = len(job.matched_skills)
        if matched_count >= 5:
            skill_points = 10
        elif matched_count >= 3:
            skill_points = 7
        elif matched_count >= 1:
            skill_points = 4
        else:
            skill_points = 0

        # 5. Readiness Signals (10 pts: 5 signals x 2 pts)
        signals = 0
        # Signal 1: Direct apply URL available
        if access_points >= 10:
            signals += 1
        # Signal 2: Company and source known
        if bool(job.company and job.company.strip() and job.source and job.source.strip()):
            signals += 1
        # Signal 3: Job description available
        if bool(job.description and len(job.description.strip()) >= 50):
            signals += 1
        # Signal 4: Location specified
        if bool(job.location and job.location.strip() and job.location.strip().lower() not in ("unknown", "n/a", "none")):
            signals += 1
        # Signal 5: Job title clearly identified
        if bool(job.title and job.title.strip()):
            signals += 1

        signal_points = signals * 2

        # Sum and clamp between 0 and 100
        total = match_points + access_points + exp_points + skill_points + signal_points
        return max(0, min(100, int(round(total))))

    def determine_application_priority(
        self, job: Job, readiness_score: int
    ) -> ApplicationPriority:
        """Map readiness and match score to an ApplicationPriority level."""
        match_score = job.match_score or 0
        is_inactive = job.status in (
            JobStatus.APPLIED,
            JobStatus.REJECTED,
            JobStatus.NOT_INTERESTED,
            JobStatus.INTERVIEW,
            JobStatus.OFFER,
        )

        # URGENT: High readiness, high match score, actionable status
        if readiness_score >= 85 and match_score >= 80 and not is_inactive:
            return ApplicationPriority.URGENT

        # HIGH: Readiness >= 75 OR Match Score >= 80
        if readiness_score >= 75 or match_score >= 80:
            return ApplicationPriority.HIGH

        # NORMAL: Readiness >= 60
        if readiness_score >= 60:
            return ApplicationPriority.NORMAL

        # LOW: Readiness >= 45
        if readiness_score >= 45:
            return ApplicationPriority.LOW

        # SKIP: Readiness < 45
        return ApplicationPriority.SKIP

    def analyze_skill_gaps(
        self, job: Job
    ) -> Tuple[List[str], List[str], List[str], List[str]]:
        """Identify missing skills required by the job and categorize into severity gaps.

        Returns:
            Tuple of (all_missing_skills, critical_gaps, moderate_gaps, minor_gaps)
        """
        desc = (job.description or "") + " " + (job.title or "")
        desc_lower = desc.lower()

        # Extract requirements/must-have section if available
        req_text_lower = desc_lower
        for pat in REQUIREMENT_HEADER_PATTERNS:
            match = re.search(pat, desc_lower)
            if match:
                # Use text starting from requirements section
                req_text_lower = desc_lower[match.start():]
                # Truncate if followed by nice-to-have / bonus section
                opt_match = re.search(r"\n\s*(?:nice\s+to\s+have|preferred|bonus|optional)", req_text_lower)
                if opt_match and opt_match.start() > 0:
                    req_text_lower = req_text_lower[:opt_match.start()]
                break

        missing: List[str] = []
        critical: List[str] = []
        moderate: List[str] = []
        minor: List[str] = []

        # Check skills in ontology
        for skill_name, info in TECH_SKILLS_ONTOLOGY.items():
            # If skill is already present in profile, it is NOT missing
            if skill_name.lower() in self.profile_skills_lower:
                continue

            patterns = info["patterns"]
            # Check if mentioned in job
            found_in_all = any(re.search(p, desc_lower) for p in patterns)
            if not found_in_all:
                continue

            found_in_reqs = any(re.search(p, req_text_lower) for p in patterns)
            category = info["category"]

            missing.append(skill_name)
            if category == "critical":
                critical.append(skill_name)
            elif category == "moderate":
                moderate.append(skill_name)
            else:
                minor.append(skill_name)

        return missing, critical, moderate, minor

    def get_profile_alignment(self, job: Job) -> str:
        """Deterministic qualitative profile alignment classification."""
        match_score = job.match_score or 0
        if match_score >= 80:
            return "Strong alignment"
        elif match_score >= 65:
            return "Good alignment"
        elif match_score >= 45:
            return "Partial alignment"
        else:
            return "Weak alignment"

    def generate_match_reasons(self, job: Job) -> List[str]:
        """Generate explainable, data-backed reasons why this job matches."""
        reasons: List[str] = []

        # Role match
        if job.matched_roles:
            roles_str = ", ".join(job.matched_roles[:2])
            reasons.append(f"✓ '{roles_str}' matches your target role")

        # Skills match
        if job.matched_skills:
            skills_sample = ", ".join(job.matched_skills[:4])
            count_suffix = f" (+{len(job.matched_skills) - 4} more)" if len(job.matched_skills) > 4 else ""
            reasons.append(f"✓ Matched technical skills: {skills_sample}{count_suffix}")

        # Location / Remote
        if job.matched_locations:
            locs_str = ", ".join(job.matched_locations[:2])
            reasons.append(f"✓ {locs_str} is a preferred location")
        elif is_india_eligible_remote(job.location):
            reasons.append("✓ Remote/India eligible")

        # Experience fit
        if job.experience_match:
            reasons.append("✓ Entry-level experience requirement")

        # Overall score
        if (job.match_score or 0) >= 80:
            reasons.append(f"✓ High deterministic match score ({job.match_score}/100 - {job.match_category})")

        return reasons

    def generate_risk_reasons(
        self, job: Job, critical_gaps: List[str], moderate_gaps: List[str]
    ) -> List[str]:
        """Generate deterministic warnings for potential application friction."""
        risks: List[str] = []

        # Direct application URL missing
        if not job.url or not job.url.strip():
            risks.append("Possible concern: Direct application URL is missing or invalid")

        # Critical skill gaps
        if critical_gaps:
            gaps_str = ", ".join(critical_gaps[:3])
            risks.append(f"Possible concern: {gaps_str} is listed as a required skill")

        # Experience requirement
        desc = (job.description or "").lower()
        if not job.experience_match and (has_senior_req := any(re.search(pat, desc[:500]) for pat in SENIORITY_EXP_PATTERNS)):
            exp_display = job.experience_required or "Higher experience indicated"
            risks.append(f"Possible concern: Job asks for higher experience ({exp_display})")

        # Location alignment
        if not job.matched_locations and not is_india_eligible_remote(job.location):
            loc_val = job.location or "Unspecified location"
            risks.append(f"Possible concern: Location preference is weaker or outside primary hubs ({loc_val})")

        # Multiple moderate skill gaps
        if len(moderate_gaps) >= 3:
            mod_sample = ", ".join(moderate_gaps[:3])
            risks.append(f"Possible concern: Several required skills are missing ({mod_sample})")

        # Sparse description
        if not job.description or len(job.description.strip()) < 100:
            risks.append("Possible concern: Job description is brief with limited technical requirements")

        return risks

    def build_application_checklist(self, job: Job) -> List[str]:
        """Generate standardized informational application checklist."""
        exp_note = job.experience_required or "Entry / Fresher"
        url_display = job.url if len(job.url) <= 50 else (job.url[:47] + "...")

        return [
            "Review full job description and company overview",
            "Confirm location eligibility and remote / hybrid policy",
            f"Verify experience expectations ({exp_note})",
            "Review skill-gap analysis and note any required tooling",
            "Tailor resume emphasizing matching skills and relevant projects",
            "Prepare portfolio, GitHub repository, and live demo links",
            f"Open application URL ({url_display})",
            "Submit application manually through employer career portal",
            "Update dashboard tracking status to APPLIED",
            "Record follow-up date and recruiter/submission notes",
        ]
