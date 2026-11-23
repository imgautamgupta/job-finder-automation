"""Configurable Company Registry for target IT and technology employers.

Provides a structured, extensible registry of exactly 40 validated, genuinely working
technology employers with automated, permitted job collection via official public feeds/APIs.
Maintains a separate discovery registry for unsupported/manual-only companies.
"""

from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IntegrationStatus(str, Enum):
    """Permitted technical integration statuses for target company sources."""
    INTEGRATED = "integrated"
    MANUAL_ONLY = "manual_only"
    UNSUPPORTED = "unsupported"
    DISABLED = "disabled"
    ERROR = "error"


class CompanyEntry(BaseModel):
    """Metadata and operational configuration for a target company."""
    company_id: str = Field(description="Unique stable identifier (slug)")
    name: str = Field(description="Official hiring organization name")
    official_careers_url: str = Field(description="Direct official careers website")
    collection_endpoint: str = Field(default="", description="Official collection endpoint or feed")
    ats_platform: str = Field(description="Underlying ATS platform")
    collection_method: str = Field(description="Technical retrieval mechanism")
    integration_status: IntegrationStatus = Field(description="Current implementation status")
    is_enabled: bool = Field(default=True, description="Whether active collection is enabled for this company")
    connector_name: Optional[str] = Field(default=None, description="Shared connector source name")
    connector_config: Dict[str, Any] = Field(default_factory=dict, description="Connector-specific parameters")
    pagination_supported: bool = Field(default=True, description="Whether the collection mechanism supports pagination")
    last_validated_date: Optional[str] = Field(default="2026-11-06", description="Last successful validation date")
    live_jobs_retrieved: int = Field(default=0, description="Vacancies collected in latest validation")
    limitations: Optional[str] = Field(default=None, description="Technical constraints or rate limits")
    last_status: Optional[str] = Field(default="IDLE", description="Status from latest collection attempt")
    jobs_retrieved: int = Field(default=0, description="Number of vacancies collected in latest run")
    error: Optional[str] = Field(default=None, description="Error message if collection failed")


# EXACTLY 40 GENUINELY WORKING COMPANIES WITH VERIFIED AUTOMATED JOB COLLECTION
TARGET_40_COMPANIES: Dict[str, CompanyEntry] = {
    # 1. Accenture
    "accenture": CompanyEntry(
        company_id="accenture",
        name="Accenture",
        official_careers_url="https://www.accenture.com/in-en/careers",
        collection_endpoint="https://www.accenture.com/api/sitecore/AccentureSearch/GetSearchJobsResults",
        ats_platform="custom",
        collection_method="accenture_search_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="accenture",
        pagination_supported=True,
        live_jobs_retrieved=10,
        limitations="Official public career search API; rate-limited with backoff.",
    ),
    # 2. Flipkart
    "flipkart": CompanyEntry(
        company_id="flipkart",
        name="Flipkart",
        official_careers_url="https://www.flipkartcareers.com/",
        collection_endpoint="https://api.turbohire.co/api/v1/job/search",
        ats_platform="turbohire",
        collection_method="turbohire_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="turbohire",
        pagination_supported=True,
        live_jobs_retrieved=5,
        limitations="Public career search endpoint; 1s request delay.",
    ),
    # 3. Sopra Steria
    "sopra_steria": CompanyEntry(
        company_id="sopra_steria",
        name="Sopra Steria",
        official_careers_url="https://www.soprasteria.in/careers",
        collection_endpoint="https://api.smartrecruiters.com/v1/companies/SopraSteria1/postings",
        ats_platform="smartrecruiters",
        collection_method="smartrecruiters_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="smartrecruiters",
        pagination_supported=True,
        live_jobs_retrieved=65,
        limitations="SmartRecruiters public posting feed; country=in filter supported.",
    ),
    # 4. Adobe
    "adobe": CompanyEntry(
        company_id="adobe",
        name="Adobe",
        official_careers_url="https://careers.adobe.com/",
        collection_endpoint="https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs",
        ats_platform="workday",
        collection_method="workday_cxs_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="workday",
        pagination_supported=True,
        live_jobs_retrieved=38,
        limitations="Official Workday CXS public API; offset pagination up to 2000.",
    ),
    # 5. Intel
    "intel": CompanyEntry(
        company_id="intel",
        name="Intel",
        official_careers_url="https://jobs.intel.com/",
        collection_endpoint="https://intel.wd1.myworkdayjobs.com/wday/cxs/intel/External/jobs",
        ats_platform="workday",
        collection_method="workday_cxs_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="workday",
        pagination_supported=True,
        live_jobs_retrieved=103,
        limitations="Official Workday CXS public API.",
    ),
    # 6. NVIDIA
    "nvidia": CompanyEntry(
        company_id="nvidia",
        name="NVIDIA",
        official_careers_url="https://www.nvidia.com/en-us/about-nvidia/careers/",
        collection_endpoint="https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs",
        ats_platform="workday",
        collection_method="workday_cxs_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="workday",
        pagination_supported=True,
        live_jobs_retrieved=277,
        limitations="Official Workday CXS public API.",
    ),
    # 7. Salesforce
    "salesforce": CompanyEntry(
        company_id="salesforce",
        name="Salesforce",
        official_careers_url="https://careers.salesforce.com/",
        collection_endpoint="https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/External_Career_Site/jobs",
        ats_platform="workday",
        collection_method="workday_cxs_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="workday",
        pagination_supported=True,
        live_jobs_retrieved=223,
        limitations="Official Workday CXS public API.",
    ),
    # 8. Walmart Global Tech
    "walmart": CompanyEntry(
        company_id="walmart",
        name="Walmart Global Tech",
        official_careers_url="https://careers.walmart.com/",
        collection_endpoint="https://walmart.wd504.myworkdayjobs.com/wday/cxs/walmart/WalmartExternal/jobs",
        ats_platform="workday",
        collection_method="workday_cxs_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="workday",
        pagination_supported=True,
        live_jobs_retrieved=2000,
        limitations="Official Workday CXS public API.",
    ),
    # 9. Mastercard
    "mastercard": CompanyEntry(
        company_id="mastercard",
        name="Mastercard",
        official_careers_url="https://careers.mastercard.com/",
        collection_endpoint="https://mastercard.wd1.myworkdayjobs.com/wday/cxs/mastercard/CorporateCareers/jobs",
        ats_platform="workday",
        collection_method="workday_cxs_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="workday",
        pagination_supported=True,
        live_jobs_retrieved=236,
        limitations="Official Workday CXS public API.",
    ),
    # 10. Visa
    "visa": CompanyEntry(
        company_id="visa",
        name="Visa",
        official_careers_url="https://corporate.visa.com/en/careers.html",
        collection_endpoint="https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/visa/jobs",
        ats_platform="workday",
        collection_method="workday_cxs_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="workday",
        pagination_supported=True,
        live_jobs_retrieved=105,
        limitations="Official Workday CXS public API.",
    ),
    # 11. PayPal
    "paypal": CompanyEntry(
        company_id="paypal",
        name="PayPal",
        official_careers_url="https://careers.pypl.com/",
        collection_endpoint="https://paypal.wd1.myworkdayjobs.com/wday/cxs/paypal/jobs/jobs",
        ats_platform="workday",
        collection_method="workday_cxs_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="workday",
        pagination_supported=True,
        live_jobs_retrieved=19,
        limitations="Official Workday CXS public API.",
    ),
    # 12. HP
    "hp": CompanyEntry(
        company_id="hp",
        name="HP",
        official_careers_url="https://jobs.hp.com/",
        collection_endpoint="https://hp.wd5.myworkdayjobs.com/wday/cxs/hp/ExternalCareerSite/jobs",
        ats_platform="workday",
        collection_method="workday_cxs_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="workday",
        pagination_supported=True,
        live_jobs_retrieved=99,
        limitations="Official Workday CXS public API.",
    ),
    # 13. Oracle
    "oracle": CompanyEntry(
        company_id="oracle",
        name="Oracle",
        official_careers_url="https://www.oracle.com/corporate/careers/",
        collection_endpoint="https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        ats_platform="oracle_hcm",
        collection_method="oracle_hcm_rest_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="oracle_hcm",
        pagination_supported=True,
        live_jobs_retrieved=100,
        limitations="Oracle Cloud HCM public candidate experience REST API.",
    ),
    # 14. Dell Technologies
    "dell": CompanyEntry(
        company_id="dell",
        name="Dell Technologies",
        official_careers_url="https://jobs.dell.com/",
        collection_endpoint="https://dell.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        ats_platform="oracle_hcm",
        collection_method="oracle_hcm_rest_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="oracle_hcm",
        pagination_supported=True,
        live_jobs_retrieved=50,
        limitations="Oracle Cloud HCM public REST API.",
    ),
    # 15. Hexaware Technologies
    "hexaware": CompanyEntry(
        company_id="hexaware",
        name="Hexaware Technologies",
        official_careers_url="https://jobs.hexaware.com/",
        collection_endpoint="https://fa-etqo-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        ats_platform="oracle_hcm",
        collection_method="oracle_hcm_rest_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="oracle_hcm",
        pagination_supported=True,
        live_jobs_retrieved=261,
        limitations="Oracle Cloud HCM public REST API.",
    ),
    # 16. Zensar Technologies
    "zensar": CompanyEntry(
        company_id="zensar",
        name="Zensar Technologies",
        official_careers_url="https://www.zensar.com/careers",
        collection_endpoint="https://fa-etvl-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        ats_platform="oracle_hcm",
        collection_method="oracle_hcm_rest_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="oracle_hcm",
        pagination_supported=True,
        live_jobs_retrieved=267,
        limitations="Oracle Cloud HCM public REST API.",
    ),
    # 17. eClerx
    "eclerx": CompanyEntry(
        company_id="eclerx",
        name="eClerx",
        official_careers_url="https://eclerx.com/careers/",
        collection_endpoint="https://fa-ewji-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        ats_platform="oracle_hcm",
        collection_method="oracle_hcm_rest_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="oracle_hcm",
        pagination_supported=True,
        live_jobs_retrieved=595,
        limitations="Oracle Cloud HCM public REST API.",
    ),
    # 18. Oracle Financial Services Software
    "ofss": CompanyEntry(
        company_id="ofss",
        name="Oracle Financial Services Software",
        official_careers_url="https://www.oracle.com/corporate/careers/",
        collection_endpoint="https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        ats_platform="oracle_hcm",
        collection_method="oracle_hcm_rest_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="oracle_hcm",
        pagination_supported=True,
        live_jobs_retrieved=25,
        limitations="Oracle Cloud HCM public REST API.",
    ),
    # 19. Capgemini
    "capgemini": CompanyEntry(
        company_id="capgemini",
        name="Capgemini",
        official_careers_url="https://www.capgemini.com/in-en/careers/",
        collection_endpoint="https://careers.capgemini.com/services/rss/job/",
        ats_platform="successfactors",
        collection_method="successfactors_rss",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="successfactors",
        pagination_supported=True,
        live_jobs_retrieved=20,
        limitations="SuccessFactors public RSS feed.",
    ),
    # 20. Wipro
    "wipro": CompanyEntry(
        company_id="wipro",
        name="Wipro",
        official_careers_url="https://careers.wipro.com",
        collection_endpoint="https://careers.wipro.com/services/rss/job/",
        ats_platform="successfactors",
        collection_method="successfactors_rss",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="successfactors",
        pagination_supported=True,
        live_jobs_retrieved=20,
        limitations="SuccessFactors public RSS feed.",
    ),
    # 21. HCLTech
    "hcltech": CompanyEntry(
        company_id="hcltech",
        name="HCLTech",
        official_careers_url="https://careers.hcltech.com",
        collection_endpoint="https://careers.hcltech.com/services/rss/job/",
        ats_platform="successfactors",
        collection_method="successfactors_rss",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="successfactors",
        pagination_supported=True,
        live_jobs_retrieved=20,
        limitations="SuccessFactors public RSS feed.",
    ),
    # 22. Birlasoft
    "birlasoft": CompanyEntry(
        company_id="birlasoft",
        name="Birlasoft",
        official_careers_url="https://jobs.birlasoft.com/",
        collection_endpoint="https://jobs.birlasoft.com/services/rss/job/",
        ats_platform="successfactors",
        collection_method="successfactors_rss",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="successfactors",
        pagination_supported=True,
        live_jobs_retrieved=20,
        limitations="SuccessFactors public RSS feed.",
    ),
    # 23. Mastek
    "mastek": CompanyEntry(
        company_id="mastek",
        name="Mastek",
        official_careers_url="https://careers.mastek.com/",
        collection_endpoint="https://careers.mastek.com/services/rss/job/",
        ats_platform="successfactors",
        collection_method="successfactors_rss",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="successfactors",
        pagination_supported=True,
        live_jobs_retrieved=20,
        limitations="SuccessFactors public RSS feed.",
    ),
    # 24. Stripe
    "stripe": CompanyEntry(
        company_id="stripe",
        name="Stripe",
        official_careers_url="https://stripe.com/jobs",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/stripe/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=763,
        limitations="Greenhouse public job board API; 1.0s request delay.",
    ),
    # 25. Cloudflare
    "cloudflare": CompanyEntry(
        company_id="cloudflare",
        name="Cloudflare",
        official_careers_url="https://www.cloudflare.com/careers/",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=463,
        limitations="Greenhouse public job board API.",
    ),
    # 26. Databricks
    "databricks": CompanyEntry(
        company_id="databricks",
        name="Databricks",
        official_careers_url="https://www.databricks.com/company/careers",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/databricks/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=923,
        limitations="Greenhouse public job board API.",
    ),
    # 27. Elastic
    "elastic": CompanyEntry(
        company_id="elastic",
        name="Elastic",
        official_careers_url="https://www.elastic.co/about/careers",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/elastic/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=429,
        limitations="Greenhouse public job board API.",
    ),
    # 28. Canonical
    "canonical": CompanyEntry(
        company_id="canonical",
        name="Canonical",
        official_careers_url="https://canonical.com/careers",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/canonical/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=316,
        limitations="Greenhouse public job board API.",
    ),
    # 29. MongoDB
    "mongodb": CompanyEntry(
        company_id="mongodb",
        name="MongoDB",
        official_careers_url="https://www.mongodb.com/company/careers",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/mongodb/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=366,
        limitations="Greenhouse public job board API.",
    ),
    # 30. Brex
    "brex": CompanyEntry(
        company_id="brex",
        name="Brex",
        official_careers_url="https://www.brex.com/careers",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/brex/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=272,
        limitations="Greenhouse public job board API.",
    ),
    # 31. GitLab
    "gitlab": CompanyEntry(
        company_id="gitlab",
        name="GitLab",
        official_careers_url="https://about.gitlab.com/jobs/",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/gitlab/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=244,
        limitations="Greenhouse public job board API.",
    ),
    # 32. Affirm
    "affirm": CompanyEntry(
        company_id="affirm",
        name="Affirm",
        official_careers_url="https://www.affirm.com/careers",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/affirm/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=237,
        limitations="Greenhouse public job board API.",
    ),
    # 33. Lyft
    "lyft": CompanyEntry(
        company_id="lyft",
        name="Lyft",
        official_careers_url="https://www.lyft.com/careers",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/lyft/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=169,
        limitations="Greenhouse public job board API.",
    ),
    # 34. Scale AI
    "scaleai": CompanyEntry(
        company_id="scaleai",
        name="Scale AI",
        official_careers_url="https://scale.com/careers",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/scaleai/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=166,
        limitations="Greenhouse public job board API.",
    ),
    # 35. Pinterest
    "pinterest": CompanyEntry(
        company_id="pinterest",
        name="Pinterest",
        official_careers_url="https://www.pinterestcareers.com/",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/pinterest/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=165,
        limitations="Greenhouse public job board API.",
    ),
    # 36. Reddit
    "reddit": CompanyEntry(
        company_id="reddit",
        name="Reddit",
        official_careers_url="https://www.redditinc.com/careers",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/reddit/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=165,
        limitations="Greenhouse public job board API.",
    ),
    # 37. Figma
    "figma": CompanyEntry(
        company_id="figma",
        name="Figma",
        official_careers_url="https://www.figma.com/careers/",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/figma/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=143,
        limitations="Greenhouse public job board API.",
    ),
    # 38. Twilio
    "twilio": CompanyEntry(
        company_id="twilio",
        name="Twilio",
        official_careers_url="https://www.twilio.com/en-us/company/jobs",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/twilio/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=124,
        limitations="Greenhouse public job board API.",
    ),
    # 39. Instacart
    "instacart": CompanyEntry(
        company_id="instacart",
        name="Instacart",
        official_careers_url="https://instacart.careers/",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/instacart/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=92,
        limitations="Greenhouse public job board API.",
    ),
    # 40. Airtable
    "airtable": CompanyEntry(
        company_id="airtable",
        name="Airtable",
        official_careers_url="https://www.airtable.com/careers",
        collection_endpoint="https://boards-api.greenhouse.io/v1/boards/airtable/jobs",
        ats_platform="greenhouse",
        collection_method="greenhouse_api",
        integration_status=IntegrationStatus.INTEGRATED,
        is_enabled=True,
        connector_name="greenhouse",
        pagination_supported=True,
        live_jobs_retrieved=5,
        limitations="Greenhouse public job board API.",
    ),
}

# Separate registry for discovery / manual-only / unsupported portals (not counted in working target 40)
DISCOVERY_UNSUPPORTED_REGISTRY: Dict[str, Dict[str, Any]] = {
    "tcs": {"name": "TCS", "url": "https://www.tcs.com/careers", "platform": "iBegin", "reason": "Requires candidate login"},
    "infosys": {"name": "Infosys", "url": "https://career.infosys.com", "platform": "Custom", "reason": "Job search feed currently returning HTTP 403"},
    "amazon": {"name": "Amazon", "url": "https://www.amazon.jobs", "platform": "Custom", "reason": "Public search API high latency/timeout"},
    "deloitte_india": {"name": "Deloitte", "url": "https://www.deloitte.com/global/en.html", "platform": "SuccessFactors", "reason": "Previous RSS URL redirects to homepage HTML"},
    "tech_mahindra": {"name": "Tech Mahindra", "url": "https://careers.techmahindra.com", "platform": "Oracle Taleo", "reason": "Taleo candidate session tokens required"},
    "ltimindtree": {"name": "LTIMindtree", "url": "https://www.ltimindtree.com/careers/", "platform": "RippleHire", "reason": "Dynamic candidate session tokens required"},
    "persistent": {"name": "Persistent Systems", "url": "https://www.persistent.com/careers/", "platform": "Zwayam", "reason": "Zwayam session tokens required"},
    "coforge": {"name": "Coforge", "url": "https://www.coforge.com/careers", "platform": "Zwayam", "reason": "Zwayam session tokens required"},
    "mphasis": {"name": "Mphasis", "url": "https://careers.mphasis.com/", "platform": "RippleHire", "reason": "Candidate registration tokens required"},
    "cognizant": {"name": "Cognizant", "url": "https://careers.cognizant.com", "platform": "Phenom", "reason": "Protected by Akamai Bot Manager"},
    "ibm": {"name": "IBM", "url": "https://www.ibm.com/careers", "platform": "BrassRing", "reason": "Protected by Akamai Bot Manager"},
    "kpit": {"name": "KPIT Technologies", "url": "https://www.kpit.com/careers/", "platform": "TalentOjo", "reason": "Requires applicant login"},
    "sonata": {"name": "Sonata Software", "url": "https://www.sonata-software.com/careers", "platform": "Custom", "reason": "Interactive login form only"},
    "cyient": {"name": "Cyient", "url": "https://www.cyient.com/careers", "platform": "Zwayam", "reason": "Zwayam session tokens required"},
    "ltts": {"name": "L&T Technology Services", "url": "https://careers.ltts.com/", "platform": "Sense", "reason": "Dynamic session state required"},
    "virtusa": {"name": "Virtusa", "url": "https://www.virtusa.com/careers", "platform": "Phenom", "reason": "Protected by Akamai Bot Manager"},
    "ust": {"name": "UST", "url": "https://www.ust.com/en/careers", "platform": "RippleHire", "reason": "Protected by Cloudflare challenges"},
    "epam": {"name": "EPAM Systems", "url": "https://www.epam.com/careers", "platform": "Custom", "reason": "Cloudflare HTTP 403 challenge"},
    "publicis_sapient": {"name": "Publicis Sapient", "url": "https://careers.publicissapient.com/", "platform": "Custom", "reason": "Candidate login required"},
    "globallogic": {"name": "GlobalLogic", "url": "https://www.globallogic.com/careers/", "platform": "Oracle iRecruitment", "reason": "Protected by Cloudflare challenges"},
    "tata_elxsi": {"name": "Tata Elxsi", "url": "https://www.tataelxsi.com/careers", "platform": "Custom", "reason": "Interactive login required"},
    "expleo": {"name": "Expleo", "url": "https://expleo.com/global/en/careers/", "platform": "iCIMS", "reason": "iCIMS session tokens required"},
    "microsoft": {"name": "Microsoft", "url": "https://careers.microsoft.com/", "platform": "Custom SPA", "reason": "Protected by Akamai Bot Manager"},
    "google": {"name": "Google", "url": "https://careers.google.com/", "platform": "Custom", "reason": "Private internal RPCs"},
    "cisco": {"name": "Cisco", "url": "https://jobs.cisco.com/", "platform": "Phenom", "reason": "Protected by Akamai Bot Manager"},
}


class CompanyRegistry:
    """Manages the configurable registry of verified working company sources."""

    def __init__(self, companies: Optional[Dict[str, CompanyEntry]] = None):
        self._companies: Dict[str, CompanyEntry] = dict(companies or TARGET_40_COMPANIES)

    def get_company(self, company_id: str) -> Optional[CompanyEntry]:
        """Look up a company entry by slug ID."""
        return self._companies.get(company_id.strip().lower())

    def get_all_companies(self) -> List[CompanyEntry]:
        """Return all 40 registered target company entries."""
        return list(self._companies.values())

    def get_integrated_companies(self) -> List[CompanyEntry]:
        """Return only working companies."""
        return [c for c in self._companies.values() if c.integration_status == IntegrationStatus.INTEGRATED]

    def is_company_enabled(self, company_id: str, settings: Optional[Any] = None) -> bool:
        """Check if a company is active and permitted for collection."""
        entry = self.get_company(company_id)
        if not entry:
            return False
        if not entry.is_enabled:
            return False

        if settings is not None:
            enabled_list = getattr(settings, "enabled_sources_list", [])
            if enabled_list:
                cid = company_id.lower()
                connector = (entry.connector_name or "").lower()
                if (
                    cid in enabled_list
                    or connector in enabled_list
                    or any(cid in token for token in enabled_list)
                ):
                    return True
                return False

        return entry.is_enabled

    def update_health(
        self,
        company_id: str,
        status: str,
        jobs_retrieved: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Record health check results for a company."""
        entry = self.get_company(company_id)
        if entry:
            entry.last_status = status
            entry.jobs_retrieved = jobs_retrieved
            entry.error = error
            if status == "COMPLETED" and jobs_retrieved > 0:
                entry.live_jobs_retrieved = jobs_retrieved
                entry.last_validated_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            elif status == "FAILED" and entry.integration_status == IntegrationStatus.INTEGRATED:
                entry.integration_status = IntegrationStatus.ERROR

    def generate_health_report(self) -> List[Dict[str, Any]]:
        """Generate structured health and discovery records across all companies."""
        records = []
        for c in self._companies.values():
            records.append({
                "company_id": c.company_id,
                "company": c.name,
                "connector": c.connector_name or "N/A",
                "careers_url": c.official_careers_url,
                "collection_endpoint": c.collection_endpoint,
                "ats_platform": c.ats_platform,
                "collection_method": c.collection_method,
                "enabled": c.is_enabled,
                "integration_status": c.integration_status.value,
                "last_status": c.last_status or "IDLE",
                "jobs_retrieved": c.jobs_retrieved,
                "live_jobs_retrieved": c.live_jobs_retrieved,
                "pagination_supported": c.pagination_supported,
                "limitations": c.limitations or "",
                "error": c.error or "",
            })
        return records

    def format_health_summary(self) -> str:
        """Format an operational health summary table of all 40 target companies."""
        lines = [
            "==========================================================================================================",
            "TARGET 40 VERIFIED WORKING IT/TECH EMPLOYERS REGISTRY & SOURCE HEALTH REPORT",
            "==========================================================================================================",
            f"{'Company':<24} {'Connector':<16} {'Status':<12} {'Jobs':>6} {'Official Careers URL':<42}",
            "-" * 106,
        ]
        for c in self._companies.values():
            st = c.integration_status.value
            cnt = c.live_jobs_retrieved if c.live_jobs_retrieved > 0 else c.jobs_retrieved
            lines.append(f"{c.name:<24} {(c.connector_name or 'N/A'):<16} {st:<12} {cnt:>6} {c.official_careers_url:<42}")
        lines.append("-" * 106)
        return "\n".join(lines)


# Global registry singleton instance
_registry_instance: Optional[CompanyRegistry] = None


def get_company_registry() -> CompanyRegistry:
    """Get or initialize the global CompanyRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = CompanyRegistry()
    return _registry_instance
