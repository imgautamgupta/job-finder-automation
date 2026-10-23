"""Detailed endpoint testing for Task 10:
1. Amazon jobs pagination & query parameters
2. Infosys IntapGateway query & parameters
3. SuccessFactors RSS pagination parameters
4. Oracle Cloud HCM pagination parameters
5. Flipkart TurboHire pagination & payload
"""
import httpx
import json
import xml.etree.ElementTree as ET

client = httpx.Client(timeout=15.0, follow_redirects=True, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
})

def test_amazon():
    print("=== TESTING AMAZON ===")
    # Test base query + pagination
    # Let's try base_query=python and offset/result_limit
    url = "https://www.amazon.jobs/en/search.json?country=IND&facets[]=normalized_country_code%3A%3AIND&offset=0&result_limit=10&sort=recent"
    r = client.get(url)
    print("Amazon offset=0 status:", r.status_code)
    data = r.json()
    total_hits = data.get("hits")
    jobs_p1 = data.get("jobs", [])
    print(f"Total hits: {total_hits}, page 1 jobs: {len(jobs_p1)}")
    if jobs_p1:
        print("Page 1 first job ID:", jobs_p1[0].get("id_icims"), jobs_p1[0].get("title"))

    # Test page 2 (offset=10)
    url2 = "https://www.amazon.jobs/en/search.json?country=IND&facets[]=normalized_country_code%3A%3AIND&offset=10&result_limit=10&sort=recent"
    r2 = client.get(url2)
    jobs_p2 = r2.json().get("jobs", [])
    print(f"Page 2 jobs: {len(jobs_p2)}")
    if jobs_p2:
        print("Page 2 first job ID:", jobs_p2[0].get("id_icims"), jobs_p2[0].get("title"))

    # Test targeted role query: base_query=software engineer
    url_role = "https://www.amazon.jobs/en/search.json?country=IND&facets[]=normalized_country_code%3A%3AIND&base_query=software+engineer&offset=0&result_limit=10"
    r_role = client.get(url_role)
    data_role = r_role.json()
    print("Amazon 'software engineer' hits:", data_role.get("hits"), "returned:", len(data_role.get("jobs", [])))

def test_infosys():
    print("\n=== TESTING INFOSYS ===")
    # Test searchText parameter
    url = "https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/getCareerSearchJobs?sourceId=1&searchText=India"
    r = client.get(url)
    jobs = r.json()
    print("Infosys searchText=India returned:", len(jobs))
    if jobs:
        j = jobs[0]
        print("Sample Infosys job:", {
            "title": j.get("postingTitle"),
            "ref": j.get("referenceCode"),
            "reqId": j.get("requisitionId"),
            "location": j.get("location"),
            "createdOn": j.get("createdOn"),
            "minExp": j.get("minExperienceLevel"),
            "maxExp": j.get("maxExperienceLevel"),
            "skills": j.get("skills"),
            "desc": (j.get("postingDescription") or "")[:100]
        })
    # Test targeted query: searchText=python
    url_py = "https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/getCareerSearchJobs?sourceId=1&searchText=python"
    r_py = client.get(url_py)
    jobs_py = r_py.json() if r_py.status_code == 200 else []
    print("Infosys searchText=python returned:", len(jobs_py))

def test_successfactors():
    print("\n=== TESTING SUCCESSFACTORS RSS (Capgemini, Wipro, HCLTech) ===")
    # Test pagination parameters on RSS: startrow, page, offset, count
    base_url = "https://careers.capgemini.com/services/rss/job/?locale=en_US&keywords=(India)"
    r1 = client.get(base_url)
    root1 = ET.fromstring(r1.content)
    items1 = root1.find("channel").findall("item")
    first_title_p1 = items1[0].findtext("title") if items1 else None
    print(f"Capgemini page 1 item count: {len(items1)}, first: {first_title_p1}")

    # Try startrow=20 or startrow=21 or page=2
    for param in ["startrow=20", "startrow=21", "page=2", "offset=20", "count=50", "start=20"]:
        test_url = f"{base_url}&{param}"
        r_test = client.get(test_url)
        try:
            root_test = ET.fromstring(r_test.content)
            items_test = root_test.find("channel").findall("item")
            first_title_test = items_test[0].findtext("title") if items_test else None
            same = (first_title_test == first_title_p1)
            print(f"Capgemini with {param} -> items: {len(items_test)}, first: '{first_title_test}', same as p1: {same}")
        except Exception as e:
            print(f"Capgemini with {param} failed: {e}")

    # Check total jobs or total available in RSS channel tags
    for tag in ["total", "totalResults", "itemsPerPage", "description"]:
        print(f"Channel {tag}:", root1.find("channel").findtext(tag))

def test_oracle_hcm():
    print("\n=== TESTING ORACLE CLOUD HCM (Oracle, Dell) ===")
    # Oracle endpoint with finder: findReqs
    # Test pagination parameters: limit, offset
    for comp, base_url, site in [
        ("Oracle", "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions", "CX_45001"),
        ("Dell", "https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions", "CX_1"),
    ]:
        url = f"{base_url}?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber={site},keyword=India&limit=25&offset=0"
        r = client.get(url)
        print(f"{comp} limit=25 offset=0 status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if items:
                reqs = items[0].get("requisitionList", [])
                total_jobs = items[0].get("TotalJobs")
                has_more = data.get("hasMore")
                print(f"{comp}: returned {len(reqs)} reqs, TotalJobs: {total_jobs}, hasMore: {has_more}")
                if reqs:
                    req0 = reqs[0]
                    req_id = req0.get("Id")
                    title = req0.get("Title")
                    loc = req0.get("PrimaryLocation")
                    posted = req0.get("PostedDate")
                    # Construct direct apply URL
                    if comp == "Oracle":
                        apply_url = f"https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/{site}/job/{req_id}"
                    else:
                        apply_url = f"https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/{site}/job/{req_id}"
                    print(f"Sample req: Id={req_id}, Title='{title}', Location='{loc}', Posted='{posted}'")
                    print(f"Apply URL: {apply_url}")

def test_flipkart_turbohire():
    print("\n=== TESTING FLIPKART TURBOHIRE ===")
    r_tok = client.get(
        "https://api.turbohire.co/api/token/noauth",
        headers={"Origin": "https://flipkart.turbohire.co", "Referer": "https://flipkart.turbohire.co/"}
    )
    print("TurboHire token response status:", r_tok.status_code, "body:", r_tok.text[:100])
    token_json = r_tok.json()
    token = token_json.get("access_token") or token_json.get("token") or token_json.get("data")
    print("Token:", token[:30] + "..." if token else "None")

    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "https://flipkart.turbohire.co",
        "Referer": "https://flipkart.turbohire.co/",
        "Content-Type": "application/json",
    }
    url = "https://api.turbohire.co/api/careerpagev2/filteredjobs?orgId=4d757ba0-3d57-448a-b82c-238ed87ac90f&pageType=public"
    payload = {
        "searchKeywords": "",
        "locations": [],
        "functions": [],
        "experience": [],
        "pageNumber": 1,
        "pageSize": 20
    }
    r = client.post(url, headers=headers, json=payload)
    print("TurboHire status:", r.status_code, "body:", r.text[:200])
    if r.status_code == 200:
        data = r.json()
        res_data = data.get("data", {})
        total_count = res_data.get("totalJobsCount") or res_data.get("totalCount") or data.get("total")
        jobs = res_data.get("jobs", [])
        print(f"Flipkart total jobs: {total_count}, returned: {len(jobs)}")
        if jobs:
            j = jobs[0]
            print("Job keys:", list(j.keys()))
            print(f"Job: Title='{j.get('jobTitle')}', Code='{j.get('jobCode')}', Id='{j.get('jobId')}', Loc='{j.get('location')}', Created='{j.get('createdOn')}'")
            print(f"Apply URL: https://flipkart.turbohire.co/job/{j.get('jobCode') or j.get('jobId')}")

if __name__ == "__main__":
    test_amazon()
    test_infosys()
    test_successfactors()
    test_oracle_hcm()
    test_flipkart_turbohire()
