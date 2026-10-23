"""Live probe script for Task 10 endpoints:
- Amazon (amazon.jobs search.json)
- Infosys (intapgateway.infosysapps.com getCareerSearchJobs)
- Capgemini, Wipro, HCLTech (SuccessFactors RSS feeds)
- Oracle, Dell (Oracle Cloud HCM recruitingCEJobRequisitions)
- Flipkart (TurboHire API)
"""
import httpx
import json
import xml.etree.ElementTree as ET

client = httpx.Client(timeout=15.0, follow_redirects=True, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
})

def probe_amazon():
    print("=== PROBING AMAZON ===")
    # Amazon search.json
    url = "https://www.amazon.jobs/en/search.json?country=IND&facets[]=normalized_country_code%3A%3AIND"
    r = client.get(url)
    print("Amazon status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        print("Amazon total hits:", data.get("hits"))
        jobs = data.get("jobs", [])
        print("Returned jobs:", len(jobs))
        if jobs:
            j = jobs[0]
            print("Sample job keys:", list(j.keys()))
            print("Title:", j.get("title"))
            print("Job ID / id_icims:", j.get("id_icims"), j.get("id"))
            print("Location:", j.get("location"), j.get("city"), j.get("country_code"))
            print("URL:", f"https://www.amazon.jobs{j.get('job_path')}")
            print("Posting date:", j.get("posted_date"))

def probe_infosys():
    print("\n=== PROBING INFOSYS ===")
    url = "https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/getCareerSearchJobs?sourceId=1&searchText=India"
    r = client.get(url)
    print("Infosys status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        # Look for structure
        if isinstance(data, dict):
            print("Infosys dict keys:", list(data.keys()))
            jobs = data.get("jobSearchResult") or data.get("jobs") or data.get("jobList") or []
            print("Total jobs or list len:", len(jobs), "Total count key:", data.get("totalCount"))
            if jobs:
                j = jobs[0]
                print("Sample keys:", list(j.keys()))
                print("Title:", j.get("jobTitle") or j.get("title"))
                print("Ref Code / ID:", j.get("jobReferenceCode") or j.get("jobId"))
                print("Location:", j.get("jobLocation") or j.get("location"))
                print("Posting date:", j.get("postingDate") or j.get("postedDate"))
                print("URL/Link:", j.get("jobUrl") or j.get("applyUrl"))
        elif isinstance(data, list):
            print("Infosys list len:", len(data))
            if data:
                print("Sample keys:", list(data[0].keys()))

def probe_successfactors_rss():
    print("\n=== PROBING SUCCESSFACTORS RSS (Capgemini, Wipro, HCLTech) ===")
    rss_urls = {
        "Capgemini": "https://careers.capgemini.com/services/rss/job/?locale=en_US&keywords=(India)",
        "Wipro": "https://careers.wipro.com/services/rss/job/?locale=en_US&keywords=(India)",
        "HCLTech": "https://careers.hcltech.com/services/rss/job/?locale=en_US&keywords=(India)",
    }
    for comp, url in rss_urls.items():
        r = client.get(url)
        print(f"\n{comp} RSS status: {r.status_code}, length: {len(r.text)}")
        if r.status_code == 200:
            try:
                root = ET.fromstring(r.content)
                channel = root.find("channel")
                items = channel.findall("item") if channel is not None else []
                print(f"{comp} RSS items count: {len(items)}")
                if items:
                    it = items[0]
                    title = it.findtext("title")
                    link = it.findtext("link")
                    guid = it.findtext("guid")
                    pubDate = it.findtext("pubDate")
                    desc = it.findtext("description")
                    print(f"Sample item -> Title: {title}, Link: {link}, GUID: {guid}, Date: {pubDate}")
            except Exception as e:
                print(f"XML parse error for {comp}: {e}")

def probe_oracle_cloud_hcm():
    print("\n=== PROBING ORACLE CLOUD HCM (Oracle, Dell) ===")
    hcm_urls = {
        "Oracle": "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber=CX_45001,keyword=India",
        "Dell": "https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber=CX_1,keyword=India",
    }
    for comp, url in hcm_urls.items():
        r = client.get(url)
        print(f"\n{comp} HCM status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            print(f"{comp} HCM items len: {len(items)}")
            if items:
                req_list = items[0].get("requisitionList", [])
                print(f"{comp} requisitionList len: {len(req_list)}")
                print(f"{comp} TotalJobs: {items[0].get('TotalJobs')}")
                if req_list:
                    j = req_list[0]
                    print("Sample req keys:", list(j.keys()))
                    print("Title:", j.get("Title"))
                    print("Id:", j.get("Id"))
                    print("PrimaryLocation:", j.get("PrimaryLocation"))
                    print("PostedDate:", j.get("PostedDate"))

def probe_turbohire():
    print("\n=== PROBING TURBOHIRE (Flipkart) ===")
    # Step 1: get auth token
    r_tok = client.get(
        "https://api.turbohire.co/api/token/noauth",
        headers={"Origin": "https://flipkart.turbohire.co", "Referer": "https://flipkart.turbohire.co/"}
    )
    print("TurboHire token status:", r_tok.status_code)
    tok_data = r_tok.json()
    token = tok_data.get("token") or tok_data.get("data")
    print("Token obtained:", bool(token))

    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "https://flipkart.turbohire.co",
        "Referer": "https://flipkart.turbohire.co/",
        "Content-Type": "application/json",
    }
    url = "https://api.turbohire.co/api/careerpagev2/filteredjobs?orgId=4d757ba0-3d57-448a-b82c-238ed87ac90f&pageType=public"
    r = client.post(url, headers=headers, json={"searchKeywords": "", "locations": [], "functions": [], "experience": [], "pageNumber": 1, "pageSize": 10})
    print("TurboHire jobs status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        print("TurboHire response keys:", list(data.keys()) if isinstance(data, dict) else type(data))
        res_data = data.get("data", {})
        if isinstance(res_data, dict):
            print("Data keys:", list(res_data.keys()))
            print("Total jobs count:", res_data.get("totalJobsCount") or res_data.get("totalCount"))
            jobs = res_data.get("jobs", [])
            print("Jobs returned:", len(jobs))
            if jobs:
                j = jobs[0]
                print("Sample keys:", list(j.keys()))
                print("JobTitle:", j.get("jobTitle"))
                print("JobCode / Id:", j.get("jobCode"), j.get("jobId"))
                print("Location:", j.get("location"))
                print("CreatedOn:", j.get("createdOn"))

if __name__ == "__main__":
    probe_amazon()
    probe_infosys()
    probe_successfactors_rss()
    probe_oracle_cloud_hcm()
    probe_turbohire()
