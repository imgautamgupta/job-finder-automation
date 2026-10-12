"""Deterministic Interview Preparation Engine.

Analyzes job requirements, candidate profile, and technical ontology to generate
tailored technical topics, role-specific questions, real project discussion points,
skill gap revision advisories, behavioral questions, and employer questions.

Zero external APIs. 100% deterministic and local-first.
All questions are transparently labeled as based on the job description or general questions.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
import re

from app.models.job import Job
from app.models.profile import JobProfile
from app.models.interview import (
    InterviewPreparationPackage,
    TechnicalTopic,
    ProjectQuestionSet,
)
from app.services.resume_parser import normalize_skill_name


# Technical knowledge ontology mapping skills to interview focus areas & conceptual questions
SKILL_INTERVIEW_ONTOLOGY: Dict[str, Dict[str, Any]] = {
    "Python": {
        "category": "Core Language",
        "focus_points": [
            "OOP principles: inheritance, encapsulation, polymorphism, abstract base classes",
            "Decorators, closures, and generator functions (yield vs return)",
            "Data structures & built-in collections: lists, dicts (hash maps), sets, tuples",
            "Memory management: reference counting, garbage collection, and GIL (Global Interpreter Lock)",
            "Exception handling best practices and context managers (with statement)",
            "Type hints and typing module for clean code documentation",
        ],
        "sample_questions": [
            "Explain how Python decorators work under the hood and when you would implement a custom decorator.",
            "What is the difference between a list, a tuple, and a set in Python regarding mutability and memory complexity?",
            "How does the Global Interpreter Lock (GIL) affect multithreading in CPU-bound vs I/O-bound tasks in Python?",
            "Explain the difference between deepcopy and shallow copy in Python.",
        ],
    },
    "FastAPI": {
        "category": "Backend Framework",
        "focus_points": [
            "Route declaration and HTTP method handlers with status codes",
            "Pydantic data schemas: request body validation, response models, serialization",
            "Dependency injection system (Depends) for database sessions and authentication",
            "Asynchronous programming: async/await and event loops in ASGI (Uvicorn)",
            "Middleware implementation, CORS headers, and exception handlers",
            "Automated OpenAPI (Swagger) and ReDoc documentation generation",
        ],
        "sample_questions": [
            "How does FastAPI utilize Pydantic for request validation and response serialization?",
            "How does dependency injection work in FastAPI and how do you use it for database connection sessions?",
            "What is the difference between synchronous (def) and asynchronous (async def) route handlers in FastAPI?",
            "How do you handle custom exceptions and error responses cleanly across FastAPI endpoints?",
        ],
    },
    "React": {
        "category": "Frontend Framework",
        "focus_points": [
            "Functional components vs class components and JSX syntax",
            "Core hooks: useState, useEffect, useMemo, useCallback, useRef",
            "Component lifecycle, virtual DOM reconciliation, and rendering optimization",
            "State management: local state vs Context API vs global store",
            "Props drilling, composition patterns, and custom hooks creation",
            "Asynchronous data fetching, loading states, and error boundary handling",
        ],
        "sample_questions": [
            "Explain the difference between useEffect, useMemo, and useCallback hooks with practical use cases.",
            "How does React's virtual DOM reconciliation algorithm detect changes and update the UI?",
            "What causes unnecessary re-renders in React components and how do you prevent them?",
            "Explain props vs state and when to lift state up in a component hierarchy.",
        ],
    },
    "Next.js": {
        "category": "Full Stack Framework",
        "focus_points": [
            "Rendering strategies: Server-Side Rendering (SSR), Static Site Generation (SSG), Incremental Static Regeneration (ISR)",
            "App Router vs Pages Router architecture and layouts",
            "Server Components vs Client Components ('use client')",
            "API routes and server actions for backend logic",
            "Image optimization, dynamic routing, and SEO metadata configuration",
        ],
        "sample_questions": [
            "What is the difference between Server-Side Rendering (SSR) and Static Site Generation (SSG) in Next.js?",
            "When should you use a Server Component versus a Client Component in Next.js App Router?",
            "How does Incremental Static Regeneration (ISR) allow static pages to be updated without rebuilding the entire app?",
        ],
    },
    "JavaScript": {
        "category": "Core Language",
        "focus_points": [
            "Event loop, call stack, microtask queue (Promises) and macrotask queue (setTimeout)",
            "Closures, lexical scoping, and 'this' keyword binding",
            "Asynchronous patterns: callbacks, Promises, async/await",
            "ES6+ features: destructuring, spread/rest, modules, arrow functions",
            "DOM manipulation, event delegation, and bubbling vs capturing",
        ],
        "sample_questions": [
            "Explain how the JavaScript event loop handles synchronous code, microtasks, and macrotasks.",
            "What is a closure in JavaScript and can you describe a practical scenario where you used one?",
            "What is the difference between == and ===, and how does type coercion work in JavaScript?",
            "Explain the difference between let, const, and var regarding hoisting and scoping.",
        ],
    },
    "TypeScript": {
        "category": "Core Language",
        "focus_points": [
            "Static typing: primitives, interfaces vs type aliases, unions, and intersections",
            "Generics for reusable and type-safe functions and components",
            "Utility types: Partial, Pick, Omit, Record, Readonly",
            "Type narrowing, type guards (typeof, instanceof), and assertion signatures",
            "Strict mode compiler options and avoiding 'any'",
        ],
        "sample_questions": [
            "What is the difference between an interface and a type alias in TypeScript?",
            "Explain TypeScript generics and provide an example of a generic API response wrapper.",
            "What are utility types like Partial, Pick, and Omit, and how do they improve code safety?",
        ],
    },
    "SQL": {
        "category": "Database",
        "focus_points": [
            "JOIN operations: INNER JOIN, LEFT OUTER JOIN, RIGHT JOIN, FULL OUTER JOIN, CROSS JOIN",
            "Aggregation: GROUP BY, HAVING, COUNT, SUM, AVG, and window functions (ROW_NUMBER, RANK)",
            "Database normalization (1NF, 2NF, 3NF) and schema design",
            "Transactions and ACID properties: Atomicity, Consistency, Isolation, Durability",
            "Indexing strategies: B-Tree indexes, compound indexes, and query execution plans",
        ],
        "sample_questions": [
            "Explain the difference between WHERE and HAVING clauses in SQL queries.",
            "What is the difference between an INNER JOIN and a LEFT JOIN, and how do NULL values behave?",
            "How do indexes speed up SELECT queries, and what is the trade-off with INSERT/UPDATE operations?",
            "Explain the ACID properties of relational database transactions.",
        ],
    },
    "PostgreSQL": {
        "category": "Database",
        "focus_points": [
            "PostgreSQL-specific types: JSONB, UUID, ARRAY, ENUM",
            "Query profiling with EXPLAIN and EXPLAIN ANALYZE",
            "Indexing: B-tree, GIN (for JSONB/full-text), GiST",
            "Connection pooling (PgBouncer) and concurrent connection limits",
            "Foreign keys, cascading updates/deletes, and constraint enforcement",
        ],
        "sample_questions": [
            "How does JSONB in PostgreSQL differ from standard JSON, and how do you query nested fields?",
            "How do you interpret the output of EXPLAIN ANALYZE to identify a sequential scan or slow join?",
            "When would you create a GIN index instead of a B-tree index in PostgreSQL?",
        ],
    },
    "MongoDB": {
        "category": "Database",
        "focus_points": [
            "Document-oriented data model, BSON types, and embedded vs referenced relationships",
            "Aggregation framework: $match, $group, $project, $unwind, $lookup",
            "Indexing: single field, compound, multikey, and text indexes",
            "CRUD operations and atomic document updates ($set, $push, $pull)",
            "Replica sets, high availability, and sharding basics",
        ],
        "sample_questions": [
            "When is it better to embed documents versus referencing them by ID in MongoDB schema design?",
            "Explain the stages of the MongoDB aggregation pipeline with an example ($match and $group).",
            "How do indexes work in MongoDB and how do you check if a query uses an index?",
        ],
    },
    "REST API": {
        "category": "Architecture & Networking",
        "focus_points": [
            "REST architectural constraints: client-server, statelessness, uniform interface",
            "HTTP methods & semantics: GET, POST, PUT, PATCH, DELETE",
            "Idempotency: why GET/PUT/DELETE are idempotent and POST is not",
            "HTTP status codes: 200, 201, 204, 400, 401, 403, 404, 422, 500",
            "API design: resource naming, pagination, filtering, versioning (/v1/)",
            "Authentication: Bearer tokens, JWT, API keys, OAuth2 flows",
        ],
        "sample_questions": [
            "What makes a REST API endpoint idempotent, and what is the difference between PUT and PATCH?",
            "What is the difference between HTTP 401 Unauthorized and HTTP 403 Forbidden?",
            "How do you design pagination, sorting, and filtering for an endpoint returning large collections?",
        ],
    },
    "Machine Learning": {
        "category": "Data Science & AI",
        "focus_points": [
            "Supervised vs Unsupervised vs Reinforcement learning paradigms",
            "Evaluation metrics: Accuracy, Precision, Recall, F1-Score, ROC-AUC, Confusion Matrix",
            "Bias-Variance tradeoff, overfitting, and underfitting indicators",
            "Regularization techniques: L1 (Lasso) vs L2 (Ridge) vs Dropout",
            "Data preprocessing: handling missing values, encoding categoricals, normalization/scaling",
            "Cross-validation techniques (k-fold, stratified k-fold) to avoid data leakage",
        ],
        "sample_questions": [
            "Explain the difference between Precision and Recall. Which metric would you prioritize for medical diagnosis or fraud detection?",
            "What is the Bias-Variance tradeoff, and how do you diagnose whether a model suffers from high bias or high variance?",
            "What is data leakage and how do you ensure the test set remains strictly isolated during feature engineering?",
        ],
    },
    "scikit-learn": {
        "category": "Data Science & AI",
        "focus_points": [
            "Scikit-learn API design: Estimators, Transformers, Predictors (fit, transform, predict)",
            "Scikit-learn Pipelines (Pipeline, ColumnTransformer) for clean reproducible modeling",
            "Model selection: GridSearchCV, RandomizedSearchCV for hyperparameter tuning",
            "Classifiers: LogisticRegression, DecisionTree, RandomForest, GradientBoosting",
            "Evaluation tools: classification_report, confusion_matrix, cross_val_score",
        ],
        "sample_questions": [
            "Why is it recommended to use a Scikit-learn Pipeline rather than applying transformers manually before model training?",
            "How does Random Forest reduce variance compared to an individual Decision Tree?",
            "How does StratifiedKFold differ from standard KFold cross-validation and why is it essential for imbalanced datasets?",
        ],
    },
    "OpenCV": {
        "category": "Computer Vision",
        "focus_points": [
            "Image representation: NumPy ndarrays, BGR vs RGB color spaces",
            "Image preprocessing: grayscale conversion, Gaussian blur, thresholding (Otsu)",
            "Edge detection (Canny) and contour extraction (findContours, drawContours)",
            "Geometric transformations: resizing, affine transformations, perspective warp",
            "Bounding box detection, aspect ratio filtering, and ROI (Region of Interest) cropping",
        ],
        "sample_questions": [
            "Why does OpenCV load images in BGR format by default instead of RGB, and how do you convert them?",
            "Explain the steps in Canny edge detection and how gradient magnitude is computed.",
            "How do you locate and crop a document or region of interest from an image using contours and perspective transform?",
        ],
    },
    "Git": {
        "category": "Development Tools",
        "focus_points": [
            "Version control workflow: working directory, staging area, local repository, remote",
            "Branching strategies: feature branches, PR reviews, main/develop branches",
            "Merge vs Rebase: understanding linear history vs preserving merge commits",
            "Resolving merge conflicts methodically and inspecting git diff",
            "Undoing changes: git revert (safe/public) vs git reset (rewriting local history)",
        ],
        "sample_questions": [
            "What is the fundamental difference between git merge and git rebase?",
            "What is the difference between git reset --soft, git reset --mixed, and git reset --hard?",
            "How do you inspect differences between branches or commits using git log and git diff?",
        ],
    },
}

# Role categories and interview guides
ROLE_INTERVIEW_GUIDES: Dict[str, Dict[str, Any]] = {
    "Python Developer": {
        "role_category": "Python Software Engineering",
        "focus_areas": [
            "Clean code, PEP 8 standards, and type hints",
            "Asynchronous I/O and concurrent task handling",
            "Backend API development, routing, and data serialization",
            "Database integration using ORMs or raw SQL connectors",
            "Unit testing with pytest, mocking, and test coverage",
        ],
        "conceptual_questions": [
            "How do you organize a scalable Python backend project structure?",
            "What testing strategies and pytest fixtures do you implement for backend services?",
        ],
    },
    "Backend Developer": {
        "role_category": "Backend & API Engineering",
        "focus_areas": [
            "RESTful API design conventions and clean endpoint architectures",
            "Database schema modeling, indexing, and transaction management",
            "Authentication, session management, and JWT token lifecycle",
            "Error handling, structured logging, and observability",
            "API security: rate limiting, input validation, SQL injection prevention",
        ],
        "conceptual_questions": [
            "How would you architect a backend service to handle unexpected spikes in traffic?",
            "Explain how you design database transactions to prevent partial updates or data corruption.",
        ],
    },
    "Full Stack Developer": {
        "role_category": "Full Stack Web Development",
        "focus_areas": [
            "End-to-end data flow: client UI -> API layer -> database -> response",
            "State management, optimistic UI updates, and caching",
            "CORS configuration and secure token storage (HTTP-only cookies vs localStorage)",
            "Responsive layout design, component modularity, and accessibility",
            "Continuous deployment and full stack build tools",
        ],
        "conceptual_questions": [
            "How do you structure the boundary between frontend state and backend persistence?",
            "What security considerations do you take into account when communicating between React and a FastAPI backend?",
        ],
    },
    "AI Engineer": {
        "role_category": "AI / Machine Learning Engineering",
        "focus_areas": [
            "End-to-end ML lifecycle: data collection, cleaning, feature engineering, model training, evaluation, deployment",
            "Handling real-world noisy or imbalanced datasets",
            "Model packaging and serving via lightweight REST APIs (FastAPI)",
            "Computer vision pipelines: document OCR, image classification, contour analysis",
            "Monitoring model performance, drift, and latency in production",
        ],
        "conceptual_questions": [
            "How do you evaluate and deploy a machine learning model to serve real-time predictions via an API?",
            "How do you handle class imbalance in classification problems?",
        ],
    },
    "Software Engineer": {
        "role_category": "General Software Engineering",
        "focus_areas": [
            "Data structures and algorithmic efficiency (time and space complexity)",
            "Object-oriented design and SOLID principles",
            "Code quality, code review standards, and automated testing",
            "Debugging methodologies and root-cause analysis",
            "System reliability, graceful degradation, and error boundaries",
        ],
        "conceptual_questions": [
            "Explain the SOLID principles with an example from a project you built.",
            "Walk through how you debug a production error when you only have log files.",
        ],
    },
}

# Standard HR & Behavioral questions
GENERAL_HR_QUESTIONS: List[str] = [
    "Tell me about yourself, your educational background, and your journey into software development.",
    "Why are you interested in this specific role and what attracted you to our team?",
    "Describe a challenging bug or technical roadblock you faced in a project and how you solved it.",
    "Tell me about a time you had to learn a completely new technology or tool under a tight deadline.",
    "How do you handle ambiguous project requirements or changing specifications during development?",
    "What are your greatest technical strengths, and what is one area you are actively working to improve?",
    "Where do you see yourself technically in the next 1 to 2 years?",
]

# Thoughtful questions candidate can ask the interviewer
QUESTIONS_FOR_EMPLOYER: List[str] = [
    "What does success look like in this role during the first 30, 60, and 90 days?",
    "What does the development workflow look like from feature ticket to production deployment?",
    "What is the biggest technical or architectural challenge the engineering team is currently tackling?",
    "How does the team handle code reviews, automated testing, and knowledge sharing?",
    "What opportunities are available for mentorship, learning new technologies, and technical growth?",
]

# 10-step interview preparation checklist
INTERVIEW_CHECKLIST_TEMPLATE: List[str] = [
    "Review the full job posting, required qualifications, and core company domain",
    "Prepare a concise 90-second self-introduction highlighting matching technical skills",
    "Review technical focus topics for primary languages, frameworks, and databases",
    "Brush up on any missing or unfamiliar skills to address them transparently",
    "Rehearse talking points for the featured candidate project using the STAR method",
    "Practice answers for likely technical concept questions based on the job description",
    "Review general behavioral and HR questions with concrete project examples",
    "Select 2-3 thoughtful questions to ask the interviewer about the role and team",
    "Review resume bullet points to ensure accurate and confident alignment",
    "Test your interview setup, camera/mic, IDE, and internet connection ahead of time",
]


class InterviewPreparationService:
    """Service generating deterministic, explainable interview preparation packages."""

    def __init__(self, profile: Optional[JobProfile] = None):
        self.profile = profile or JobProfile()

    def generate_package(self, job: Job, profile: Optional[JobProfile] = None) -> InterviewPreparationPackage:
        """Alias for generate_preparation_package supporting dynamic profile injection."""
        if profile is not None:
            self.profile = profile
        return self.generate_preparation_package(job)

    def generate_preparation_package(self, job: Job) -> InterviewPreparationPackage:
        """Build comprehensive deterministic preparation package for a job."""
        company_name = job.company or "Hiring Company"
        job_title = job.title or "Software Engineer"
        desc_text = (job.description or "").lower()
        title_text = (job.title or "").lower()
        full_text = f"{title_text} {desc_text}"

        # 1. Match reasons (deterministic from job match scores and matched items)
        match_reasons = list(job.recommendation_reasons) if job.recommendation_reasons else []
        if not match_reasons:
            if job.matched_roles:
                match_reasons.append(f"Target role matches: {', '.join(job.matched_roles)}")
            if job.matched_skills:
                match_reasons.append(f"Demonstrated skills: {', '.join(job.matched_skills[:5])}")
            if job.experience_match:
                match_reasons.append("Experience requirements align with junior/entry-level profile")

        # 2. Extract technical topics
        technical_topics, all_identified_skills = self._extract_technical_topics(job, full_text)

        # 3. Extract role-specific topics
        role_topics = self._extract_role_topics(job, title_text)

        # 4. Project discussion points (based on candidate's real projects)
        project_questions = self._build_project_question_set(job, full_text)

        # 5. Likely technical questions (strictly labeled: based on job description)
        likely_tech_questions = self._extract_likely_technical_questions(technical_topics, role_topics)

        # 6. Skill gap preparation
        matched_skills, revise_skills, missing_skills = self._categorize_skill_gaps(
            job, all_identified_skills
        )

        # 7. Preparation Checklist
        checklist = list(INTERVIEW_CHECKLIST_TEMPLATE)

        # 8. Tracking fields from job
        interview_date = getattr(job, "interview_date", None)
        interview_stage = getattr(job, "interview_stage", None)
        interview_status = getattr(job, "interview_status", None) or "NOT_SCHEDULED"
        interview_notes = getattr(job, "interview_notes", None)
        interview_prep_status = getattr(job, "interview_preparation_status", None) or "NOT_STARTED"

        status_str = (
            job.status.value
            if hasattr(job.status, "value")
            else str(job.status or "NEW")
        )

        return InterviewPreparationPackage(
            job_id=job.id or 0,
            company=company_name,
            title=job_title,
            location=job.location,
            source=job.source,
            url=job.url,
            match_score=job.match_score,
            readiness_score=job.application_readiness_score,
            resume_alignment_score=job.resume_alignment_score,
            status=status_str,
            match_reasons=match_reasons,
            technical_topics=technical_topics,
            role_topics=role_topics,
            project_questions=project_questions,
            likely_technical_questions=likely_tech_questions,
            hr_behavioral_questions=list(GENERAL_HR_QUESTIONS),
            matched_skills=matched_skills,
            skills_to_revise=revise_skills,
            missing_skills=missing_skills,
            questions_to_ask_employer=list(QUESTIONS_FOR_EMPLOYER),
            checklist=checklist,
            interview_date=interview_date,
            interview_stage=interview_stage,
            interview_status=interview_status,
            interview_notes=interview_notes,
            interview_preparation_status=interview_prep_status,
        )

    def _extract_technical_topics(
        self, job: Job, full_text: str
    ) -> Tuple[List[TechnicalTopic], Set[str]]:
        """Identify relevant technical skills and attach interview focus areas."""
        detected_topics: List[TechnicalTopic] = []
        all_identified: Set[str] = set()

        # Check job matched skills first
        matched_job_skills = job.matched_skills or []
        for s in matched_job_skills:
            clean = normalize_skill_name(s)
            all_identified.add(clean)

        # Scan text for skills in ontology
        for skill_name, info in SKILL_INTERVIEW_ONTOLOGY.items():
            pattern = r"\b" + re.escape(skill_name.lower()) + r"\b"
            if re.search(pattern, full_text) or skill_name in all_identified:
                all_identified.add(skill_name)
                detected_topics.append(
                    TechnicalTopic(
                        skill=skill_name,
                        category=info.get("category", "Core Skill"),
                        focus_points=info.get("focus_points", []),
                    )
                )

        return detected_topics, all_identified

    def _extract_role_topics(self, job: Job, title_text: str) -> List[Dict[str, Any]]:
        """Extract role-based interview topics based on target roles and title."""
        topics: List[Dict[str, Any]] = []

        for role_name, guide in ROLE_INTERVIEW_GUIDES.items():
            pattern = r"\b" + re.escape(role_name.lower().replace("developer", "").replace("engineer", "").strip()) + r"\b"
            if role_name.lower() in title_text or (job.matched_roles and any(role_name.lower() in r.lower() for r in job.matched_roles)):
                topics.append({
                    "role_title": role_name,
                    "category": guide["role_category"],
                    "focus_areas": guide["focus_areas"],
                    "conceptual_questions": guide["conceptual_questions"],
                })

        # Default fallback to Software Engineer if none explicitly matched
        if not topics:
            default_guide = ROLE_INTERVIEW_GUIDES["Software Engineer"]
            topics.append({
                "role_title": "Software Engineer",
                "category": default_guide["role_category"],
                "focus_areas": default_guide["focus_areas"],
                "conceptual_questions": default_guide["conceptual_questions"],
            })

        return topics

    def _build_project_question_set(
        self, job: Job, full_text: str
    ) -> Optional[ProjectQuestionSet]:
        """Select candidate's real project matching the job and generate project discussion questions."""
        projects = self.profile.projects or []
        if not projects:
            return None

        # Score candidate projects based on technology overlap with job
        best_proj = None
        best_score = -1
        best_matched_skills: List[str] = []

        for p in projects:
            p_name = p.get("name", "Candidate Project")
            p_skills = p.get("skills", [])
            overlap = [
                s for s in p_skills
                if re.search(r"\b" + re.escape(s.lower()) + r"\b", full_text)
            ]
            score = len(overlap) * 10
            if score > best_score:
                best_score = score
                best_proj = p
                best_matched_skills = overlap

        if not best_proj and projects:
            best_proj = projects[0]
            best_matched_skills = best_proj.get("skills", [])[:3]

        proj_name = best_proj.get("name", "Candidate Project")
        desc = best_proj.get("description", "")

        # Generate realistic project talking points and questions without inventing project features
        discussion_points = [
            f"Explain the motivation and architecture of '{proj_name}'. What problem does it solve?",
            f"Why did you choose {', '.join(best_matched_skills[:3]) if best_matched_skills else 'these technologies'} for this project?",
            "What was the biggest technical challenge or bug you faced during implementation, and how did you resolve it?",
            "How did you validate correctness and measure system performance or accuracy?",
            "If you were deploying this project into high-availability production, what architectural improvements would you make?",
        ]

        # Role-specific enhancement for AI/ML project
        if "fraud" in proj_name.lower() or "ai" in proj_name.lower():
            discussion_points.append(
                "How does the OCR and computer vision pipeline extract and verify text from source documents?"
            )
        elif "notes" in proj_name.lower() or "nest" in proj_name.lower():
            discussion_points.append(
                "How is state managed between the frontend and database for real-time note and bookmark updates?"
            )

        why_text = (
            f"Directly showcases hands-on experience with {', '.join(best_matched_skills)}"
            if best_matched_skills
            else "Demonstrates full-stack problem-solving and software development capabilities"
        )

        return ProjectQuestionSet(
            project_name=proj_name,
            why_recommended=why_text,
            technologies=best_matched_skills or best_proj.get("skills", []),
            discussion_points=discussion_points,
        )

    def _extract_likely_technical_questions(
        self, technical_topics: List[TechnicalTopic], role_topics: List[Dict[str, Any]]
    ) -> List[str]:
        """Aggregate likely questions strictly derived from identified job technologies."""
        questions: List[str] = []

        # Pull from technical ontology
        for topic in technical_topics:
            info = SKILL_INTERVIEW_ONTOLOGY.get(topic.skill, {})
            sample_qs = info.get("sample_questions", [])
            for q in sample_qs[:2]:  # Top 2 per skill
                if q not in questions:
                    questions.append(q)

        # Pull from role guides
        for r in role_topics:
            for q in r.get("conceptual_questions", []):
                if q not in questions:
                    questions.append(q)

        # Cap at 8 questions for readability
        return questions[:8]

    def _categorize_skill_gaps(
        self, job: Job, identified_skills: Set[str]
    ) -> Tuple[List[str], List[str], List[str]]:
        """Categorize skills into matched, revise, and missing."""
        candidate_skills = {normalize_skill_name(s).lower(): s for s in (self.profile.skills or [])}

        matched: List[str] = []
        revise: List[str] = []
        missing: List[str] = []

        # Job's matched skills (candidate has them and job requires them)
        for s in job.matched_skills or []:
            clean = normalize_skill_name(s)
            if clean not in matched:
                matched.append(clean)

        # Skills in identified set:
        for s in identified_skills:
            clean = normalize_skill_name(s)
            clean_lower = clean.lower()
            if clean_lower in candidate_skills:
                if clean not in matched and clean not in revise:
                    revise.append(clean)
            else:
                if clean not in missing and clean not in matched:
                    missing.append(clean)

        # Add any explicit missing skills from Phase 9/10
        for s in job.missing_skills or []:
            clean = normalize_skill_name(s)
            if clean not in missing and clean.lower() not in candidate_skills:
                missing.append(clean)

        return matched, revise, missing
