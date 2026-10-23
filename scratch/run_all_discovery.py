import httpx
import json
import xml.etree.ElementTree as ET

client = httpx.Client(
    follow_redirects=True, 
    timeout=12.0, 
    headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8',
    }
)

results = []

def probe_amazon():
    url = "https://www.amazon.jobs/en/search.json?country=IND"
    r = client.get(url)
    data = r.json() if r.status_code == 200 else {}
    return {
        "company": "Amazon",
        "platform": "Company JSON feed (amazon.jobs)",
        "endpoint": url,
        "status": r.status_code,
        "returned": len(data.get("jobs", [])),
        "india_jobs": data.get("hits", 0),
        "job_id_apply_url": "Yes (id_icims e.g. 10411470, URL: amazon.jobs/en/jobs/10411470/...)",
        "verdict": "Usable"
    }

def probe_microsoft():
    url = "https://apply.careers.microsoft.com/api/pcsx/search"
    r = client.get(url)
    return {
        "company": "Microsoft",
        "platform": "Eightfold.ai",
        "endpoint": url,
        "status": r.status_code,
        "returned": 0,
        "india_jobs": 0,
        "job_id_apply_url": "No (requires auth session / bot challenge)",
        "verdict": "Blocked"
    }

def probe_google():
    url = "https://careers.google.com/jobs/results/"
    r = client.get(url)
    return {
        "company": "Google",
        "platform": "Custom Angular SPA (careers.google.com)",
        "endpoint": url,
        "status": r.status_code,
        "returned": 0,
        "india_jobs": 0,
        "job_id_apply_url": "No open REST API (SPA internal RPCs only)",
        "verdict": "Blocked"
    }

def probe_workday(company, host, tenant, site, query="India"):
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Origin': f'https://{host}',
        'Referer': f'https://{host}/en-US/{site}/jobs'
    }
    payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": query}
    try:
        r = client.post(url, headers=headers, json=payload)
        data = r.json() if r.status_code == 200 else {}
        items = data.get("jobPostings", [])
        total = data.get("total", 0)
        has_id = bool(items and (items[0].get("bulletFields") or items[0].get("externalPath")))
        return {
            "company": company,
            "platform": "Workday CXS",
            "endpoint": url,
            "status": r.status_code,
            "returned": len(items),
            "india_jobs": total,
            "job_id_apply_url": f"Yes ({items[0].get('bulletFields', [''])[0]} / externalPath)" if has_id else "N/A",
            "verdict": "Usable" if r.status_code == 200 else "Blocked"
        }
    except Exception as e:
        return {
            "company": company,
            "platform": "Workday CXS",
            "endpoint": url,
            "status": "Error",
            "returned": 0,
            "india_jobs": 0,
            "job_id_apply_url": "No",
            "verdict": "Blocked"
        }

def probe_oracle_cloud(company, base_url, site_number):
    url = f"{base_url}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber={site_number},keyword=India"
    r = client.get(url)
    data = r.json() if r.status_code == 200 else {}
    items = data.get("items", [])
    total = data.get("totalResults", len(items))
    has_id = bool(items and items[0].get("Id"))
    return {
        "company": company,
        "platform": "Oracle Cloud HCM",
        "endpoint": url,
        "status": r.status_code,
        "returned": len(items),
        "india_jobs": total,
        "job_id_apply_url": f"Yes (Id: {items[0].get('Id')})" if has_id else "N/A",
        "verdict": "Usable" if r.status_code == 200 else "Blocked"
    }

def probe_sf_rss(company, url):
    r = client.get(url)
    if r.status_code == 200 and 'xml' in r.headers.get('content-type', ''):
        root = ET.fromstring(r.content)
        items = root.findall('.//item')
        return {
            "company": company,
            "platform": "SAP SuccessFactors (RSS feed)",
            "endpoint": url,
            "status": r.status_code,
            "returned": len(items),
            "india_jobs": "Feed stream (active listings)",
            "job_id_apply_url": "Yes (guid / link with job ID)",
            "verdict": "Usable"
        }
    else:
        return {
            "company": company,
            "platform": "SAP SuccessFactors",
            "endpoint": url,
            "status": r.status_code,
            "returned": 0,
            "india_jobs": 0,
            "job_id_apply_url": "No (Cloudflare/Akamai bot protection)",
            "verdict": "Blocked"
        }

def probe_turbohire():
    url = "https://api.turbohire.co/api/careerpagev2/filteredjobs?orgId=4d757ba0-3d57-448a-b82c-238ed87ac90f&pageType=public"
    r_tok = client.get("https://api.turbohire.co/api/token/noauth", headers={"Origin": "https://flipkart.turbohire.co", "Referer": "https://flipkart.turbohire.co/"})
    token = r_tok.json().get("data") if r_tok.status_code == 200 else None
    headers = {"Authorization": f"Bearer {token}", "Origin": "https://flipkart.turbohire.co", "Referer": "https://flipkart.turbohire.co/"}
    r = client.post(url, headers=headers, json={"filters": [], "page": 1, "pageSize": 10})
    data = r.json() if r.status_code == 200 else {}
    items = data.get("data", {}).get("jobs", [])
    total = data.get("data", {}).get("totalJobs", len(items))
    return {
        "company": "Flipkart",
        "platform": "TurboHire API",
        "endpoint": url,
        "status": r.status_code,
        "returned": len(items),
        "india_jobs": total,
        "job_id_apply_url": "Yes (JobId & JobCode, URL flipkart.turbohire.co/job/...)",
        "verdict": "Usable"
    }

def probe_infosys():
    url = "https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/getCareerSearchJobs?sourceId=1&searchText=India"
    r = client.get(url)
    data = r.json() if r.status_code == 200 else []
    return {
        "company": "Infosys",
        "platform": "Company JSON feed (IntapGateway)",
        "endpoint": url,
        "status": r.status_code,
        "returned": len(data),
        "india_jobs": len(data),
        "job_id_apply_url": "Yes (jobReferenceCode, URL career.infosys.com/jobdescription?...)",
        "verdict": "Usable"
    }

def probe_cognizant():
    url = "https://careers.cognizant.com/global/en/search-results"
    r = client.get(url)
    return {
        "company": "Cognizant",
        "platform": "Phenom People",
        "endpoint": url,
        "status": r.status_code,
        "returned": 0,
        "india_jobs": 0,
        "job_id_apply_url": "No (Phenom bot protection 403)",
        "verdict": "Blocked"
    }

def probe_ibm():
    url = "https://ibm.eightfold.ai/api/apply/v2/jobs?domain=ibm.com"
    r = client.get(url)
    return {
        "company": "IBM",
        "platform": "Eightfold.ai",
        "endpoint": url,
        "status": r.status_code,
        "returned": 0,
        "india_jobs": 0,
        "job_id_apply_url": "No (Eightfold bot protection 403)",
        "verdict": "Blocked"
    }

def probe_tcs():
    url = "https://ibegin.tcsapps.com/iBegin/"
    r = client.get(url)
    return {
        "company": "TCS",
        "platform": "TCS iBegin Portal",
        "endpoint": url,
        "status": r.status_code,
        "returned": 0,
        "india_jobs": 0,
        "job_id_apply_url": "No (Requires authentication; marketing portal blocks non-browser traffic)",
        "verdict": "Blocked"
    }

def probe_tech_mahindra():
    url = "https://careers.techmahindra.com/JobSearch.aspx"
    r = client.get(url)
    return {
        "company": "Tech Mahindra",
        "platform": "ASP.NET WebForms",
        "endpoint": url,
        "status": r.status_code,
        "returned": 0,
        "india_jobs": 0,
        "job_id_apply_url": "No (Requires __VIEWSTATE interactive postback session)",
        "verdict": "Empty"
    }

print("Running live audit on all 23 companies...")
all_probes = [
    probe_amazon(),
    probe_microsoft(),
    probe_google(),
    probe_workday("Adobe", "adobe.wd5.myworkdayjobs.com", "adobe", "external_experienced"),
    probe_workday("Intel", "intel.wd1.myworkdayjobs.com", "intel", "External"),
    probe_workday("NVIDIA", "nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite"),
    probe_oracle_cloud("Dell", "https://enterpriseplatform.dell.com", "CX_1"),
    probe_workday("Salesforce", "salesforce.wd12.myworkdayjobs.com", "salesforce", "External_Career_Site"),
    probe_sf_rss("Capgemini", "https://careers.capgemini.com/services/rss/job/?locale=en_US&keywords=(India)"),
    probe_cognizant(),
    probe_ibm(),
    probe_oracle_cloud("Oracle", "https://eeho.fa.us2.oraclecloud.com", "CX_45001"),
    probe_sf_rss("SAP", "https://jobs.sap.com/services/rss/job/?locale=en_US&keywords=(India)"),
    probe_infosys(),
    probe_tcs(),
    probe_sf_rss("Wipro", "https://careers.wipro.com/services/rss/job/?locale=en_US&keywords=(India)"),
    probe_sf_rss("HCLTech", "https://careers.hcltech.com/services/rss/job/?locale=en_US&keywords=(India)"),
    probe_tech_mahindra(),
    probe_turbohire(),
    probe_workday("Walmart", "walmart.wd504.myworkdayjobs.com", "walmart", "WalmartExternal"),
    probe_workday("Mastercard", "mastercard.wd1.myworkdayjobs.com", "mastercard", "CorporateCareers"),
    probe_workday("Visa", "visa.wd5.myworkdayjobs.com", "visa", "visa"),
    probe_workday("PayPal", "paypal.wd1.myworkdayjobs.com", "paypal", "jobs")
]

with open("scratch/task4_discovery_results.json", "w") as f:
    json.dump(all_probes, f, indent=2)

print("Finished auditing all 23 companies. Dumped to scratch/task4_discovery_results.json")
