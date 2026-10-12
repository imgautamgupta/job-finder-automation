"""Deterministic Resume Intelligence and Application Preparation Service (Phase 10).

Calculates Resume Alignment Score (0-100), Skills to Emphasize, Keyword Coverage,
Project Recommendations, Experience Emphasis, Potential Concerns, and Suggested Focus.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.job import Job
from app.models.profile import JobProfile
from app.models.resume import (
    CandidateExperience,
    CandidateProfile,
    CandidateProject,
    PreparationStatus,
    ResumePreparationAnalysis,
    ResumeProfile,
)
from app.services.recommender import (
    ENTRY_EXP_PATTERNS,
    REQUIREMENT_HEADER_PATTERNS,
    SENIORITY_EXP_PATTERNS,
    TECH_SKILLS_ONTOLOGY,
)
from app.services.resume_parser import NORMALIZATION_MAP, ResumeParser, normalize_skill_name

logger = logging.getLogger(__name__)

# Keyword priority section headers
HIGH_PRIORITY_HEADERS = [
    r"(?:requirements|qualifications|must\s+have|what\s+you'll\s+need|what\s+you\s+need|who\s+you\s+are|we're\s+looking\s+for|minimum\s+qualifications|basic\s+qualifications|key\s+skills)",
]

MEDIUM_PRIORITY_HEADERS = [
    r"(?:responsibilities|what\s+you'll\s+do|what\s+you\s+do|duties|skills|preferred\s+qualifications|desired\s+skills)",
]

LOW_PRIORITY_HEADERS = [
    r"(?:nice\s+to\s+have|bonus|optional|good\s+to\s+have|plus)",
]


class ResumeIntelligenceService:
    """Deterministic, explainable resume intelligence and application preparation service."""

    def __init__(
        self,
        profile: JobProfile,
        resume_profiles: Optional[Dict[str, ResumeProfile]] = None,
        resume_parser: Optional[ResumeParser] = None,
    ):
        self.job_profile = profile
        self.parser = resume_parser or ResumeParser()
        self.resume_profiles = resume_profiles or {
            "Profile Fallback": ResumeProfile(source_file="profile.json fallback", is_fallback=True)
        }

        # Build primary candidate representation
        self.primary_resume_label, self.primary_resume = self._select_primary_resume()
        self.candidate_profile = self._build_candidate_profile(self.job_profile, self.primary_resume)

    def _select_primary_resume(self) -> Tuple[str, ResumeProfile]:
        """Select primary resume profile for candidate representation."""
        if "Primary Resume" in self.resume_profiles:
            return "Primary Resume", self.resume_profiles["Primary Resume"]
        # Return first item in dictionary
        first_label = next(iter(self.resume_profiles))
        return first_label, self.resume_profiles[first_label]

    def _build_candidate_profile(
        self, job_profile: JobProfile, resume: ResumeProfile
    ) -> CandidateProfile:
        """Combine profile.json and resume into a unified truthful CandidateProfile."""
        # 1. Candidate skills: start with explicit profile.json skills (Priority 1)
        all_skills: List[str] = []
        seen_skills_lower: Set[str] = set()

        for s in job_profile.skills:
            clean = normalize_skill_name(s)
            if clean.lower() not in seen_skills_lower:
                seen_skills_lower.add(clean.lower())
                all_skills.append(clean)

        # 2. Add resume-derived skills if present
        resume_skills_visible: List[str] = []
        for s in resume.skills:
            clean = normalize_skill_name(s)
            if clean.lower() not in seen_skills_lower:
                seen_skills_lower.add(clean.lower())
                all_skills.append(clean)
            if clean not in resume_skills_visible:
                resume_skills_visible.append(clean)

        # 3. Candidate projects: from resume first, or fallback to profile.json projects
        projects: List[CandidateProject] = []
        if resume.projects:
            projects = list(resume.projects)
        elif hasattr(job_profile, "projects") and job_profile.projects:
            for p in job_profile.projects:
                if isinstance(p, dict) and "name" in p:
                    projects.append(
                        CandidateProject(
                            name=p.get("name", "Project"),
                            description=p.get("description"),
                            skills=p.get("skills", []),
                            highlights=p.get("highlights", []),
                        )
                    )

        # 4. Candidate experience: from resume first, or fallback to profile.json experience
        experience: List[CandidateExperience] = []
        internships: List[CandidateExperience] = []

        if resume.experience:
            experience = list(resume.experience)
        elif hasattr(job_profile, "experience") and job_profile.experience:
            for exp in job_profile.experience:
                if isinstance(exp, dict) and "title" in exp:
                    exp_type = exp.get("experience_type", "work")
                    item = CandidateExperience(
                        title=exp.get("title", ""),
                        company=exp.get("company"),
                        experience_type=exp_type,
                        description=exp.get("description"),
                        skills=exp.get("skills", []),
                        highlights=exp.get("highlights", []),
                    )
                    if exp_type.lower() == "internship":
                        internships.append(item)
                    else:
                        experience.append(item)

        if resume.internships:
            internships.extend(resume.internships)

        source_desc = resume.source_file or ("data/profile.json" if resume.is_fallback else "Resume")

        return CandidateProfile(
            skills=all_skills,
            target_roles=job_profile.target_roles,
            preferred_locations=job_profile.preferred_locations,
            projects=projects,
            experience=experience,
            internships=internships,
            resume_profile=resume,
            source_description=source_desc,
            resume_skills_set=resume_skills_visible,
        )

    def analyze(self, job: Job) -> ResumePreparationAnalysis:
        """Generate comprehensive, explainable Phase 10 preparation analysis for a job."""
        # 1. Multi-resume evaluation: evaluate each configured resume version to recommend the best fit
        best_resume_label = self.primary_resume_label
        best_score = -1
        best_breakdown: Optional[Dict[str, Any]] = None

        for label, r_prof in self.resume_profiles.items():
            cand_repr = self._build_candidate_profile(self.job_profile, r_prof)
            score, breakdown = self.calculate_resume_alignment_score(job, cand_repr, r_prof)
            if score > best_score:
                best_score = score
                best_resume_label = label
                best_breakdown = breakdown

        active_resume = self.resume_profiles[best_resume_label]
        active_candidate = self._build_candidate_profile(self.job_profile, active_resume)
        alignment_score, _ = self.calculate_resume_alignment_score(job, active_candidate, active_resume)

        # 2. Alignment Category
        category = self.get_alignment_category(alignment_score)

        # 3. Skills to Emphasize
        skills_to_emphasize = self.extract_skills_to_emphasize(job, active_candidate, active_resume)

        # 4. Keyword Analysis (Covered vs Missing / Not Prominent)
        matched_keywords, missing_keywords = self.analyze_keywords(job, active_candidate, active_resume)

        # 5. Project Recommendation
        rec_project_name, rec_project_details = self.recommend_project(job, active_candidate)

        # 6. Experience Recommendation
        rec_exp_title, rec_exp_details = self.recommend_experience(job, active_candidate)

        # 7. Potential Concerns
        concerns = self.generate_resume_concerns(
            job, active_candidate, active_resume, missing_keywords, skills_to_emphasize
        )

        # 8. Suggested Focus
        suggestions = self.generate_resume_suggestions(
            job, skills_to_emphasize, rec_project_name, rec_exp_title, missing_keywords, active_resume
        )

        # 9. Application Checklist
        checklist = self.build_preparation_checklist(job, active_resume)

        # 10. Status and Notes preserved if already present on job
        prep_status = (
            job.preparation_status
            if hasattr(job, "preparation_status") and job.preparation_status
            else PreparationStatus.NOT_REVIEWED
        )
        if isinstance(prep_status, str):
            try:
                prep_status = PreparationStatus(prep_status)
            except Exception:
                prep_status = PreparationStatus.NOT_REVIEWED

        prep_notes = getattr(job, "preparation_notes", None)

        return ResumePreparationAnalysis(
            job_id=job.id,
            resume_alignment_score=alignment_score,
            resume_alignment_category=category,
            skills_to_emphasize=skills_to_emphasize,
            resume_matched_keywords=matched_keywords,
            resume_missing_keywords=missing_keywords,
            recommended_project=rec_project_name,
            recommended_project_details=rec_project_details,
            recommended_experience=rec_exp_title,
            recommended_experience_details=rec_exp_details,
            resume_concerns=concerns,
            resume_suggestions=suggestions,
            recommended_resume=best_resume_label,
            preparation_status=prep_status,
            preparation_notes=prep_notes,
            checklist=checklist,
        )

    def calculate_resume_alignment_score(
        self, job: Job, candidate: CandidateProfile, resume: ResumeProfile
    ) -> Tuple[int, Dict[str, Any]]:
        """Calculate deterministic Resume Alignment Score (0-100).

        Formula Breakdown (Section 8 of prompt):
        1. Role Alignment: 30 points
           - Target role matching job title: up to 15 points
           - Resume experience / projects matching role: up to 15 points
        2. Skill Alignment: 35 points
           - Based on job skills, resume skills, and candidate profile skills
        3. Experience Alignment: 15 points
           - Internship, projects, and experience vs job experience requirement
        4. Project Alignment: 10 points
           - Candidate has relevant project(s) matching job technologies
        5. Keyword Coverage: 10 points
           - Important job keywords appearing in resume / candidate profile
        Total Maximum: 100 points
        """
        # 1. Role Alignment (30 pts)
        role_pts = 0
        job_title_lower = (job.title or "").lower()

        # Component 1A: Target role match (up to 15 pts)
        if job.matched_roles:
            role_pts += 15
        elif any(r.lower() in job_title_lower for r in candidate.target_roles):
            role_pts += 15
        elif any(
            w in job_title_lower
            for w in ["developer", "engineer", "software", "backend", "intern", "trainee", "ai", "ml"]
        ):
            role_pts += 10
        else:
            role_pts += 5

        # Component 1B: Experience/Project role keywords (up to 15 pts)
        cand_exp_text = " ".join(
            [e.title + " " + (e.description or "") for e in candidate.experience + candidate.internships]
            + [p.name + " " + (p.description or "") for p in candidate.projects]
        ).lower()

        matched_role_words = sum(
            1 for w in ["developer", "engineer", "software", "backend", "ai", "machine learning", "intern"]
            if w in cand_exp_text and w in job_title_lower
        )
        if matched_role_words >= 2:
            role_pts += 15
        elif matched_role_words == 1:
            role_pts += 10
        elif candidate.projects or candidate.experience:
            role_pts += 7
        else:
            role_pts += 4

        role_pts = min(30, role_pts)

        # 2. Skill Alignment (35 pts)
        # Based on how well candidate/resume skills cover all technical skills identified in the job
        skill_pts = 0
        matched_kw, missing_kw = self.analyze_keywords(job, candidate, resume)
        all_job_skills = list(set((job.matched_skills or []) + matched_kw + missing_kw))
        resume_skills_lower = {s.lower() for s in (resume.skills if not resume.is_fallback else candidate.skills)}

        if all_job_skills:
            covered_in_resume = sum(1 for s in all_job_skills if s.lower() in resume_skills_lower)
            ratio = covered_in_resume / len(all_job_skills)
            if ratio >= 0.80:
                skill_pts = 35
            elif ratio >= 0.60:
                skill_pts = 28
            elif ratio >= 0.40:
                skill_pts = 20
            elif ratio >= 0.20:
                skill_pts = 14
            elif ratio > 0:
                skill_pts = 8
            else:
                skill_pts = 4
        else:
            # If job didn't have parsed matched skills, evaluate candidate skills against description
            desc_lower = (job.description or "").lower()
            found_count = sum(1 for s in candidate.skills if re.search(r"\b" + re.escape(s.lower()) + r"\b", desc_lower))
            if found_count >= 5:
                skill_pts = 32
            elif found_count >= 3:
                skill_pts = 24
            elif found_count >= 1:
                skill_pts = 16
            else:
                skill_pts = 6

        skill_pts = min(35, skill_pts)

        # 3. Experience Alignment (15 pts)
        exp_pts = 0
        desc_text = (job.description or "").lower()
        title_text = (job.title or "").lower()
        exp_text = f"{job.experience_required or ''} {title_text}".lower()

        has_senior = any(re.search(p, exp_text) for p in SENIORITY_EXP_PATTERNS) or any(
            re.search(p, desc_text[:400]) for p in SENIORITY_EXP_PATTERNS
        )
        has_entry = any(re.search(p, exp_text) for p in ENTRY_EXP_PATTERNS) or job.experience_match

        has_cand_intern = len(candidate.internships) > 0
        has_cand_exp = len(candidate.experience) > 0 or len(candidate.projects) > 0

        if has_entry and (has_cand_intern or has_cand_exp):
            exp_pts = 15
        elif has_entry:
            exp_pts = 12
        elif not has_senior and (has_cand_intern or has_cand_exp):
            exp_pts = 12
        elif not has_senior:
            exp_pts = 8
        else:
            # Job asks for senior experience
            exp_pts = 4

        exp_pts = min(15, exp_pts)

        # 4. Project Alignment (10 pts)
        proj_pts = 0
        best_proj_match_count = 0
        for proj in candidate.projects:
            proj_skills = {s.lower() for s in proj.skills}
            overlap = sum(1 for js in (job.matched_skills or candidate.skills) if js.lower() in proj_skills)
            best_proj_match_count = max(best_proj_match_count, overlap)

        if best_proj_match_count >= 3:
            proj_pts = 10
        elif best_proj_match_count >= 2:
            proj_pts = 8
        elif best_proj_match_count >= 1:
            proj_pts = 6
        elif len(candidate.projects) > 0:
            proj_pts = 4
        else:
            proj_pts = 0

        proj_pts = min(10, proj_pts)

        # 5. Keyword Coverage (10 pts)
        kw_pts = 0
        matched_kw, missing_kw = self.analyze_keywords(job, candidate, resume)
        total_kw = len(matched_kw) + len(missing_kw)
        if total_kw > 0:
            ratio = len(matched_kw) / total_kw
            kw_pts = round(ratio * 10)
        else:
            kw_pts = 7

        kw_pts = min(10, kw_pts)

        total_score = max(0, min(100, role_pts + skill_pts + exp_pts + proj_pts + kw_pts))

        breakdown = {
            "role_points": role_pts,
            "skill_points": skill_pts,
            "experience_points": exp_pts,
            "project_points": proj_pts,
            "keyword_points": kw_pts,
        }
        return total_score, breakdown

    def get_alignment_category(self, score: int) -> str:
        """Deterministic categorical rating for resume alignment score."""
        if score >= 80:
            return "Strong Alignment"
        elif score >= 65:
            return "Good Alignment"
        elif score >= 50:
            return "Partial Alignment"
        else:
            return "Low Alignment"

    def extract_skills_to_emphasize(
        self, job: Job, candidate: CandidateProfile, resume: ResumeProfile
    ) -> List[str]:
        """Identify candidate skills that directly align with the job to emphasize.

        Rule: NEVER invent skills. Only include skills genuinely possessed by candidate
        and mentioned / relevant to the job.
        Prioritization:
        1. Required skills (found in requirements)
        2. Strongly relevant skills (in job.matched_skills)
        3. Skills appearing in both resume and job
        4. Skills appearing in profile and job
        """
        desc_lower = ((job.description or "") + " " + (job.title or "")).lower()

        # Candidate skills set
        candidate_skills = candidate.skills
        resume_skills_lower = {s.lower() for s in (resume.skills if not resume.is_fallback else candidate.skills)}

        # Extract requirements section text
        req_text = desc_lower
        for pat in HIGH_PRIORITY_HEADERS:
            match = re.search(pat, desc_lower)
            if match:
                req_text = desc_lower[match.start():]
                break

        ranked_skills: List[Tuple[int, str]] = []

        for skill in candidate_skills:
            skill_clean = normalize_skill_name(skill)
            skill_lower = skill_clean.lower()

            # Check if mentioned in job
            in_job = re.search(r"\b" + re.escape(skill_lower) + r"\b", desc_lower) is not None
            if not in_job:
                # Check ontology patterns
                if skill_clean in TECH_SKILLS_ONTOLOGY:
                    patterns = TECH_SKILLS_ONTOLOGY[skill_clean]["patterns"]
                    in_job = any(re.search(p, desc_lower) for p in patterns)

            if not in_job:
                continue

            # Prioritization scoring
            priority = 0
            # 1. Required skills
            in_req = re.search(r"\b" + re.escape(skill_lower) + r"\b", req_text) is not None
            if in_req:
                priority += 40

            # 2. In job.matched_skills
            if job.matched_skills and any(ms.lower() == skill_lower for ms in job.matched_skills):
                priority += 30

            # 3. Visible in resume
            if skill_lower in resume_skills_lower:
                priority += 20
            else:
                priority += 10

            ranked_skills.append((priority, skill_clean))

        # Sort descending by priority, preserve deduplication
        ranked_skills.sort(key=lambda x: x[0], reverse=True)

        result: List[str] = []
        for _, s in ranked_skills:
            if s not in result:
                result.append(s)

        return result

    def analyze_keywords(
        self, job: Job, candidate: CandidateProfile, resume: ResumeProfile
    ) -> Tuple[List[str], List[str]]:
        """Deterministic keyword coverage analysis.

        Categorizes terms into High/Medium/Low priority from job,
        then checks whether each is visible in the resume.
        """
        desc = (job.description or "") + " " + (job.title or "")
        desc_lower = desc.lower()

        # 1. Identify keywords from ontology and candidate domain
        candidate_skills_lower = {s.lower(): s for s in candidate.skills}
        resume_text_lower = (
            " ".join(resume.skills + [e.title for e in resume.experience] + [p.name for p in resume.projects]).lower()
            if not resume.is_fallback
            else " ".join(candidate.skills).lower()
        )

        all_candidate_terms = dict(candidate_skills_lower)
        for canon, val in TECH_SKILLS_ONTOLOGY.items():
            all_candidate_terms[canon.lower()] = canon

        job_detected_terms: List[Tuple[str, str]] = []  # (term_name, priority_level)

        # Check sections
        req_match = None
        for p in HIGH_PRIORITY_HEADERS:
            m = re.search(p, desc_lower)
            if m:
                req_match = m
                break

        med_match = None
        for p in MEDIUM_PRIORITY_HEADERS:
            m = re.search(p, desc_lower)
            if m:
                med_match = m
                break

        for raw_k, canon_name in all_candidate_terms.items():
            pattern = r"\b" + re.escape(raw_k) + r"\b"
            m = re.search(pattern, desc_lower)
            if not m:
                continue

            pos = m.start()
            if req_match and pos >= req_match.start():
                prio = "HIGH"
            elif med_match and pos >= med_match.start():
                prio = "MEDIUM"
            else:
                prio = "HIGH" if (job.matched_skills and canon_name in job.matched_skills) else "MEDIUM"

            job_detected_terms.append((canon_name, prio))

        # Compare with resume
        covered: List[str] = []
        missing: List[str] = []

        for name, prio in job_detected_terms:
            name_lower = name.lower()
            pattern = r"\b" + re.escape(name_lower) + r"\b"
            is_visible = re.search(pattern, resume_text_lower) is not None

            if is_visible:
                if name not in covered:
                    covered.append(name)
            else:
                if name not in missing:
                    missing.append(name)

        return covered, missing

    def recommend_project(
        self, job: Job, candidate: CandidateProfile
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Select top relevant candidate project using deterministic skill overlap."""
        if not candidate.projects:
            return None, None

        job_text = ((job.description or "") + " " + (job.title or "")).lower()
        job_skills = {s.lower() for s in (job.matched_skills or candidate.skills)}

        scored_projects: List[Tuple[int, CandidateProject, List[str]]] = []

        for proj in candidate.projects:
            overlap_skills: List[str] = []
            score = 0

            for ps in proj.skills:
                ps_clean = normalize_skill_name(ps)
                if ps_clean.lower() in job_skills or re.search(r"\b" + re.escape(ps_clean.lower()) + r"\b", job_text):
                    overlap_skills.append(ps_clean)
                    score += 10

            # Role keywords in project name/description
            proj_full = (proj.name + " " + (proj.description or "")).lower()
            for role_term in ["backend", "api", "ai", "machine learning", "fraud", "notes", "web"]:
                if role_term in job_text and role_term in proj_full:
                    score += 5

            scored_projects.append((score, proj, overlap_skills))

        # Sort descending by score
        scored_projects.sort(key=lambda x: x[0], reverse=True)

        if not scored_projects:
            return None, None

        best_score, best_proj, best_overlap = scored_projects[0]
        details = {
            "name": best_proj.name,
            "description": best_proj.description or "",
            "matched_skills": best_overlap,
            "score": best_score,
            "why": f"Demonstrates hands-on implementation of {', '.join(best_overlap[:4])}"
            if best_overlap
            else "Relevant domain project matching core technical responsibilities.",
        }
        return best_proj.name, details

    def recommend_experience(
        self, job: Job, candidate: CandidateProfile
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Select top relevant candidate work experience or internship to emphasize."""
        all_exp = candidate.internships + candidate.experience
        if not all_exp:
            return None, None

        job_text = ((job.description or "") + " " + (job.title or "")).lower()
        job_skills = {s.lower() for s in (job.matched_skills or candidate.skills)}

        scored_exp: List[Tuple[int, CandidateExperience, List[str]]] = []

        for exp in all_exp:
            overlap_skills: List[str] = []
            score = 0

            for s in exp.skills:
                s_clean = normalize_skill_name(s)
                if s_clean.lower() in job_skills or re.search(r"\b" + re.escape(s_clean.lower()) + r"\b", job_text):
                    overlap_skills.append(s_clean)
                    score += 10

            exp_full = (exp.title + " " + (exp.description or "") + " " + (exp.company or "")).lower()
            for kw in ["ai", "machine learning", "backend", "software", "intern", "developer"]:
                if kw in job_text and kw in exp_full:
                    score += 5

            scored_exp.append((score, exp, overlap_skills))

        scored_exp.sort(key=lambda x: x[0], reverse=True)
        if not scored_exp:
            return None, None

        best_score, best_exp, best_overlap = scored_exp[0]
        title_display = f"{best_exp.title}" + (f" ({best_exp.company})" if best_exp.company else "")
        details = {
            "title": title_display,
            "experience_type": best_exp.experience_type,
            "matched_skills": best_overlap,
            "why": f"Direct practical experience utilizing {', '.join(best_overlap[:4])}"
            if best_overlap
            else "Hands-on experience directly aligned with primary role objectives.",
        }
        return title_display, details

    def generate_resume_concerns(
        self,
        job: Job,
        candidate: CandidateProfile,
        resume: ResumeProfile,
        missing_keywords: List[str],
        skills_to_emphasize: List[str],
    ) -> List[str]:
        """Generate deterministic, constructive warnings for resume alignment.

        Language rule: Never say 'Your resume is bad'. Use 'Potential concern'
        or 'Could be emphasized'.
        """
        concerns: List[str] = []
        resume_skills_lower = {s.lower() for s in (resume.skills if not resume.is_fallback else candidate.skills)}

        # 1. Candidate skills that are in profile but not prominent in resume
        for s in skills_to_emphasize[:3]:
            if s.lower() not in resume_skills_lower and not resume.is_fallback:
                concerns.append(f"Potential concern: Job emphasizes {s}, but it is not prominent in the resume.")

        # 2. Critical missing keywords from job that candidate does NOT possess
        desc_lower = (job.description or "").lower()
        for missing_kw in missing_keywords[:3]:
            if missing_kw.lower() not in {cs.lower() for cs in candidate.skills}:
                concerns.append(
                    f"Potential concern: Job asks for {missing_kw}, which is not present in your candidate profile. "
                    "Do not add it unless you genuinely have this experience."
                )

        # 3. Role focus mismatch
        title_lower = (job.title or "").lower()
        if "backend" in title_lower and not any("backend" in s.lower() for s in skills_to_emphasize):
            concerns.append(
                "Potential concern: Job focuses heavily on backend architecture; ensure backend API work is prominently featured."
            )
        elif ("ai" in title_lower or "machine learning" in title_lower) and not any(
            "learn" in s.lower() or "ai" in s.lower() or "python" in s.lower() for s in skills_to_emphasize
        ):
            concerns.append(
                "Potential concern: Job is centered on AI/ML; ensure machine learning projects and models are front and center."
            )

        # 4. Fallback profile notice
        if resume.is_fallback:
            concerns.append(
                "Notice: Resume file not configured — using profile.json data for preparation analysis."
            )

        return concerns

    def generate_resume_suggestions(
        self,
        job: Job,
        skills_to_emphasize: List[str],
        recommended_project: Optional[str],
        recommended_experience: Optional[str],
        missing_keywords: List[str],
        resume: ResumeProfile,
    ) -> List[str]:
        """Generate actionable, truthful resume preparation suggestions."""
        suggestions: List[str] = []
        step = 1

        # 1. Top skills placement
        if skills_to_emphasize:
            top_skills_str = ", ".join(skills_to_emphasize[:3])
            suggestions.append(f"{step}. Position {top_skills_str} high in the technical skills section.")
            step += 1

        # 2. Recommended project
        if recommended_project:
            suggestions.append(
                f"{step}. Highlight '{recommended_project}' as your primary featured project with metrics and technologies."
            )
            step += 1

        # 3. Relevant experience
        if recommended_experience:
            suggestions.append(f"{step}. Emphasize '{recommended_experience}' with bullets focused on matching responsibilities.")
            step += 1

        # 4. Missing keywords truthful note
        if missing_keywords:
            sample = ", ".join(missing_keywords[:2])
            suggestions.append(
                f"{step}. If you genuinely possess experience with {sample}, consider highlighting it; otherwise, focus on your core strengths."
            )
            step += 1

        # 5. General alignment
        suggestions.append(f"{step}. Keep resume concise, tailored, and strictly aligned with this role's primary requirements.")

        return suggestions

    def build_preparation_checklist(self, job: Job, resume: ResumeProfile) -> List[str]:
        """Generate interactive application preparation checklist."""
        company_name = job.company or "Employer"
        role_name = job.title or "Position"

        return [
            f"Review full {company_name} - {role_name} posting",
            "Verify resume version and prominent skill ordering",
            "Confirm portfolio and GitHub project demo links are active",
            "Check direct application URL accessibility",
            "Review interview preparation topics for highlighted skills",
            "Submit application manually through employer career portal",
            "Record application date and update dashboard status to APPLIED",
        ]
