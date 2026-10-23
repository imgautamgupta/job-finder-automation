"""Debug the two failing search intelligence tests to trace why MONITOR is returned instead of expected values."""
import sys
sys.path.insert(0, ".")

from datetime import datetime
from app.database.database import DatabaseManager
from app.models.job import ApplicationPriority, Job, JobStatus
from app.models.profile import JobProfile
from app.models.search_intelligence import DataConfidence, RecommendationPriority, SourceActionRecommendation
from app.services.search_intelligence import SearchIntelligenceService
import tempfile, os

def make_db():
    tmp = tempfile.mkdtemp()
    db_file = os.path.join(tmp, "debug.db")
    db = DatabaseManager(str(db_file))
    db.initialize()
    return db

def create_mock_job(title="Software Engineer", company="TechCorp", location="Bangalore, India",
                    source="greenhouse", match_score=80, readiness_score=75, resume_score=70,
                    priority=ApplicationPriority.HIGH, status=JobStatus.NEW):
    return Job(
        title=title, company=company, location=location, source=source,
        url=f"https://example.com/job/{datetime.now().timestamp()}_{title.replace(' ','_')}",
        description=f"Job listing for {title}",
        match_score=match_score,
        application_readiness_score=readiness_score,
        resume_alignment_score=resume_score,
        application_priority=priority,
        status=status,
        matched_roles=[title],
        matched_locations=["Bangalore"],
    )

sample_profile = JobProfile(
    target_roles=["Python Developer","Backend Developer","Software Engineer",
                  "Full Stack Developer","Web Developer","ML Engineer","AI Engineer","SDE Intern"],
    preferred_locations=["Bangalore","Bengaluru","Delhi","Noida","Ahmedabad","Remote","India"],
    skills=["Python","FastAPI","React","SQL","Git"],
)

# === Test 1 debug ===
print("=== Test 1: test_source_intelligence_aggregation_and_relevance ===")
db = make_db()
for i in range(7):
    db.save_job(create_mock_job(title=f"Software Engineer {i}", source="greenhouse",
                                location="Bangalore, India", match_score=85, priority=ApplicationPriority.HIGH))
for i in range(3):
    db.save_job(create_mock_job(title=f"Senior Director {i}", source="greenhouse",
                                location="Berlin, Germany", match_score=45, priority=ApplicationPriority.SKIP))

service = SearchIntelligenceService(db=db, profile=sample_profile)
raw_jobs = db.get_all_jobs_raw()
print(f"  raw_jobs count: {len(raw_jobs)}")
print(f"  greenhouse jobs: {[j.get('location') for j in raw_jobs if j.get('source')=='greenhouse']}")

# manually compute what the service would compute
gh_jobs = [j for j in raw_jobs if (j.get("source") or "").lower() == "greenhouse"]
found = len(gh_jobs)
relevant = sum(1 for j in gh_jobs if (j.get("match_score") or 0) >= 60)
print(f"  found={found}, relevant={relevant}")
pref_loc_count = sum(1 for j in gh_jobs if service._is_preferred_location(j.get("location")))
pref_loc_rate = round((pref_loc_count / found) * 100.0, 1) if found > 0 else None
india_count = sum(1 for j in gh_jobs if "bangalore" in (j.get("location") or "").lower())
india_rate = round((india_count / found) * 100.0, 1) if found > 0 else None
rel_rate = round((relevant / found) * 100.0, 1) if found > 0 else None
print(f"  pref_loc_count={pref_loc_count}, pref_loc_rate={pref_loc_rate}")
print(f"  india_count={india_count}, india_rate={india_rate}")
print(f"  rel_rate={rel_rate}")

from app.models.search_intelligence import DataConfidence
confidence_val = service._evaluate_confidence(found)
print(f"  confidence={confidence_val}")

quality_score, quality_label = service.analytics_service.compute_source_quality_score(
    found, relevant, 0, 0, 0, 0
)
print(f"  quality_score={quality_score}, quality_label={quality_label}")

condition = ((quality_score or 0) >= 60.0 or (rel_rate or 0) >= 50.0) and ((pref_loc_rate or 0) >= 30.0 or (india_rate or 0) >= 50.0)
print(f"  INCREASE_SEARCH_DEPTH condition: {condition}")
print()

report = service.get_search_intelligence_report()
gh = next((s for s in report.sources if s.source.lower() == "greenhouse"), None)
print(f"  Actual recommendation: {gh.recommendation}")
print(f"  Actual rec_priority: {gh.recommendation_priority}")
print(f"  Expected: INCREASE_SEARCH_DEPTH")

# === Test 2 debug ===
print()
print("=== Test 2: test_small_data_protection_and_insufficient_data ===")
db2 = make_db()
db2.save_job(create_mock_job(title="Software Engineer", source="lever", match_score=90))
db2.save_job(create_mock_job(title="Backend Developer", source="lever", match_score=85))

service2 = SearchIntelligenceService(db=db2, profile=sample_profile)
report2 = service2.get_search_intelligence_report()
lev = next((s for s in report2.sources if s.source.lower() == "lever"), None)
print(f"  jobs_found={lev.jobs_found}, confidence={lev.confidence}")
print(f"  recommendation={lev.recommendation}")
print(f"  recommendation_reason={lev.recommendation_reason!r}")
print(f"  Expected: INSUFFICIENT_DATA")
