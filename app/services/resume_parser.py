"""Deterministic, local-first resume parsing and normalization service (Phase 10).

Parses local PDF, DOCX, TXT, and Markdown files safely without any external APIs,
cloud uploads, or LLM services. Normalizes technical skill variations deterministically.
"""

import logging
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple, Union

from app.models.resume import (
    CandidateExperience,
    CandidateProject,
    ResumeProfile,
)

logger = logging.getLogger(__name__)

# Canonical technical term normalization map
NORMALIZATION_MAP = {
    "fast api": "FastAPI",
    "fastapi": "FastAPI",
    "react.js": "React",
    "reactjs": "React",
    "react": "React",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mongo db": "MongoDB",
    "mongodb": "MongoDB",
    "scikit learn": "scikit-learn",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "machine learning": "Machine Learning",
    "artificial intelligence": "AI",
    "ai": "AI",
    "ml": "Machine Learning",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "vue.js": "Vue.js",
    "vuejs": "Vue.js",
    "angular.js": "Angular",
    "angularjs": "Angular",
    "angular": "Angular",
    "rest api": "REST API",
    "rest apis": "REST API",
    "restful": "REST API",
    "restful api": "REST API",
    "restful apis": "REST API",
    "opencv": "OpenCV",
    "open cv": "OpenCV",
    "nlp": "NLP",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "git hub": "GitHub",
    "github": "GitHub",
    "git": "Git",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "redis": "Redis",
    "graphql": "GraphQL",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "java": "Java",
    "c++": "C++",
    "c#": "C#",
    "sql": "SQL",
}

# Standard heading matchers
SECTION_PATTERNS = {
    "summary": r"^(?:summary|professional\s+summary|objective|about\s+me|profile)$",
    "skills": r"^(?:skills|technical\s+skills|core\s+competencies|technologies|tools\s+&\s+technologies|skills\s+&\s+tools)$",
    "experience": r"^(?:experience|work\s+experience|professional\s+experience|employment\s+history)$",
    "internships": r"^(?:internships?|internship\s+experience)$",
    "projects": r"^(?:projects|featured\s+projects|technical\s+projects|academic\s+projects|personal\s+projects)$",
    "education": r"^(?:education|academic\s+background|qualifications)$",
    "certifications": r"^(?:certifications?|credentials|licenses)$",
    "links": r"^(?:links|social\s+links|portfolio)$",
}


def normalize_skill_name(raw_name: str) -> str:
    """Normalize common skill variations deterministically."""
    clean = raw_name.strip()
    low = clean.lower()
    return NORMALIZATION_MAP.get(low, clean)


class ResumeParser:
    """Deterministic local parser for resume files."""

    def __init__(self):
        pass

    def extract_text(self, file_path: Union[str, Path]) -> Tuple[str, Optional[str]]:
        """Extract raw plain text from a local file.

        Returns:
            Tuple of (extracted_text, error_message)
        """
        path = Path(file_path)
        if not path.exists():
            return "", f"File not found: {path.name}"

        suffix = path.suffix.lower()

        try:
            if suffix in (".txt", ".md"):
                text = path.read_text(encoding="utf-8", errors="replace")
                return text, None

            elif suffix == ".pdf":
                try:
                    import pypdf
                    reader = pypdf.PdfReader(str(path))
                    pages_text = []
                    for page in reader.pages:
                        extracted = page.extract_text()
                        if extracted:
                            pages_text.append(extracted)
                    full_text = "\n".join(pages_text)
                    return full_text, None
                except Exception as pdf_err:
                    logger.warning("PDF extraction failed for %s: %s", path.name, pdf_err)
                    return "", f"Failed to parse PDF file: {pdf_err}"

            elif suffix in (".docx", ".doc"):
                try:
                    import docx
                    doc = docx.Document(str(path))
                    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                    for table in doc.tables:
                        for row in table.rows:
                            for cell in row.cells:
                                if cell.text.strip():
                                    paragraphs.append(cell.text.strip())
                    return "\n".join(paragraphs), None
                except Exception as docx_err:
                    logger.warning("DOCX extraction failed for %s: %s", path.name, docx_err)
                    return "", f"Failed to parse DOCX file: {docx_err}"

            else:
                return "", f"Unsupported file extension: {suffix}"

        except Exception as e:
            logger.warning("Error reading file %s: %s", path.name, e)
            return "", str(e)

    def parse_text_to_sections(self, text: str) -> Dict[str, List[str]]:
        """Segment raw text into structured section blocks by matching headings."""
        lines = [line.strip() for line in text.splitlines()]
        sections: Dict[str, List[str]] = {
            "header": [],
            "summary": [],
            "skills": [],
            "experience": [],
            "internships": [],
            "projects": [],
            "education": [],
            "certifications": [],
            "links": [],
            "other": [],
        }

        current_section = "header"

        for line in lines:
            if not line:
                continue

            # Check if line looks like a section header (short line, title-like)
            clean_line = line.strip().strip(":").strip("#").strip("-").strip()
            clean_lower = clean_line.lower()

            matched_sec = None
            if len(clean_line) <= 40:
                for sec_name, pat in SECTION_PATTERNS.items():
                    if re.match(pat, clean_lower, re.IGNORECASE):
                        matched_sec = sec_name
                        break

            if matched_sec:
                current_section = matched_sec
                continue

            sections[current_section].append(line)

        return sections

    def parse_file(self, file_path: Union[str, Path], label: Optional[str] = None) -> ResumeProfile:
        """Parse a single resume file into a structured ResumeProfile."""
        path = Path(file_path)
        source_label = label or path.name

        text, error = self.extract_text(path)
        if error or not text.strip():
            logger.info("Resume file '%s' could not be parsed (%s). Using fallback profile.", path.name, error)
            return ResumeProfile(
                source_file=source_label,
                is_fallback=True,
            )

        sections = self.parse_text_to_sections(text)

        # Extract skills
        skills: List[str] = []
        skills_text = " ".join(sections.get("skills", []))
        if skills_text:
            # Split by commas, bullets, pipes, or newlines
            raw_tokens = re.split(r"[,•|\n;/\\]", skills_text)
            for tok in raw_tokens:
                clean_tok = tok.strip().strip("-").strip()
                if clean_tok and len(clean_tok) <= 30 and not clean_tok.startswith("http"):
                    norm = normalize_skill_name(clean_tok)
                    if norm not in skills:
                        skills.append(norm)

        # Also search entire text for known normalization technologies if skills section was sparse
        for raw_k, canon in NORMALIZATION_MAP.items():
            if canon not in skills:
                # Word boundary search
                pattern = r"\b" + re.escape(raw_k) + r"\b"
                if re.search(pattern, text, re.IGNORECASE):
                    skills.append(canon)

        # Extract projects
        projects: List[CandidateProject] = []
        proj_lines = sections.get("projects", [])
        if proj_lines:
            curr_proj_name = None
            curr_proj_skills: List[str] = []
            curr_proj_bullets: List[str] = []

            for pl in proj_lines:
                if (pl.startswith("-") or pl.startswith("•") or pl.startswith("*")) and curr_proj_name:
                    curr_proj_bullets.append(pl.lstrip("-•* ").strip())
                elif len(pl) < 60 and not pl.startswith("http"):
                    if curr_proj_name:
                        projects.append(
                            CandidateProject(
                                name=curr_proj_name,
                                skills=curr_proj_skills,
                                highlights=curr_proj_bullets,
                            )
                        )
                    curr_proj_name = pl
                    curr_proj_skills = [
                        s for s in skills if re.search(r"\b" + re.escape(s) + r"\b", pl, re.IGNORECASE)
                    ]
                    curr_proj_bullets = []
                else:
                    if curr_proj_name:
                        curr_proj_bullets.append(pl)

            if curr_proj_name:
                projects.append(
                    CandidateProject(
                        name=curr_proj_name,
                        skills=curr_proj_skills,
                        highlights=curr_proj_bullets,
                    )
                )

        # Extract experiences
        experiences: List[CandidateExperience] = []
        exp_lines = sections.get("experience", [])
        if exp_lines:
            curr_exp_title = None
            curr_exp_bullets: List[str] = []
            for el in exp_lines:
                if (el.startswith("-") or el.startswith("•") or el.startswith("*")) and curr_exp_title:
                    curr_exp_bullets.append(el.lstrip("-•* ").strip())
                elif len(el) < 60:
                    if curr_exp_title:
                        experiences.append(
                            CandidateExperience(
                                title=curr_exp_title,
                                experience_type="work",
                                highlights=curr_exp_bullets,
                            )
                        )
                    curr_exp_title = el
                    curr_exp_bullets = []
                else:
                    if curr_exp_title:
                        curr_exp_bullets.append(el)
            if curr_exp_title:
                experiences.append(
                    CandidateExperience(
                        title=curr_exp_title,
                        experience_type="work",
                        highlights=curr_exp_bullets,
                    )
                )

        # Extract internships
        internships: List[CandidateExperience] = []
        intern_lines = sections.get("internships", [])
        if intern_lines:
            curr_int_title = None
            curr_int_bullets: List[str] = []
            for il in intern_lines:
                if (il.startswith("-") or il.startswith("•") or il.startswith("*")) and curr_int_title:
                    curr_int_bullets.append(il.lstrip("-•* ").strip())
                elif len(il) < 60:
                    if curr_int_title:
                        internships.append(
                            CandidateExperience(
                                title=curr_int_title,
                                experience_type="internship",
                                highlights=curr_int_bullets,
                            )
                        )
                    curr_int_title = il
                    curr_int_bullets = []
                else:
                    if curr_int_title:
                        curr_int_bullets.append(il)
            if curr_int_title:
                internships.append(
                    CandidateExperience(
                        title=curr_int_title,
                        experience_type="internship",
                        highlights=curr_int_bullets,
                    )
                )

        summary_text = " ".join(sections.get("summary", [])) or None

        profile = ResumeProfile(
            name=sections.get("header", [""])[0] if sections.get("header") else None,
            summary=summary_text,
            skills=skills,
            experience=experiences,
            internships=internships,
            projects=projects,
            education=sections.get("education", []),
            certifications=sections.get("certifications", []),
            links=sections.get("links", []),
            source_file=source_label,
            is_fallback=False,
        )
        return profile

    def load_resumes(
        self, configured_path: Optional[Union[str, Path]]
    ) -> Dict[str, ResumeProfile]:
        """Detect and load one or multiple resume files.

        Returns:
            Dictionary mapping label (e.g. 'Primary Resume', 'Backend Resume') to ResumeProfile.
            If no resume configured or found, returns {'Profile Fallback': ResumeProfile(is_fallback=True)}.
        """
        if not configured_path or not str(configured_path).strip():
            logger.info("Resume file not configured — using profile data for preparation analysis.")
            return {"Profile Fallback": ResumeProfile(source_file="profile.json fallback", is_fallback=True)}

        target_path = Path(str(configured_path).strip())

        if not target_path.exists():
            logger.warning(
                "Configured resume path '%s' does not exist. Using profile data for preparation analysis.",
                target_path,
            )
            return {"Profile Fallback": ResumeProfile(source_file="profile.json fallback", is_fallback=True)}

        results: Dict[str, ResumeProfile] = {}

        if target_path.is_file():
            profile = self.parse_file(target_path, label="Primary Resume")
            results["Primary Resume"] = profile
            return results

        if target_path.is_dir():
            # Discover supported files
            valid_extensions = {".pdf", ".docx", ".txt", ".md"}
            files = [
                f for f in sorted(target_path.iterdir())
                if f.is_file() and f.suffix.lower() in valid_extensions and not f.name.startswith("~")
            ]

            if not files:
                logger.info(
                    "No resume files found in directory '%s'. Using profile data fallback.",
                    target_path,
                )
                return {"Profile Fallback": ResumeProfile(source_file="profile.json fallback", is_fallback=True)}

            for f in files:
                # Generate clean label e.g. resume_backend.pdf -> Backend Resume
                stem = f.stem.replace("resume_", "").replace("resume-", "").replace("_resume", "").replace("cv_", "")
                words = stem.replace("_", " ").replace("-", " ").strip().title()
                label = f"{words} Resume" if words and "resume" not in words.lower() else (words or f.name)
                profile = self.parse_file(f, label=label)
                results[label] = profile

            return results

        return {"Profile Fallback": ResumeProfile(source_file="profile.json fallback", is_fallback=True)}
