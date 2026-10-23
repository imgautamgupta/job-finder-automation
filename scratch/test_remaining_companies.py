"""Detailed diagnostic probe for HCLTech, Wipro, Infosys, TCS, Tech Mahindra, IBM, Capgemini, and Flipkart."""

import json
import re
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
}


def test_hcltech_and_wipro():
    print("=== HCLTech & Wipro (SAP SuccessFactors CSB) ===")
    for name, base, domain in [
        ("HCLTech", "https://careers.hcltech.com/search/?q=&locationsearch=India", "https://careers.hcltech.com"),
        ("Wipro", "https://careers.wipro.com/search/?q=&locationsearch=India", "https://careers.wipro.com"),
    ]:
        r = httpx.get(base, headers=HEADERS, follow_redirects=True, timeout=15)
        job_links = set(re.findall(r'href=["\'](/job/[^"\']+)["\']', r.text))
        print(f"{name}: HTTP {r.status_code} | Total job links on page 1: {len(job_links)}")
        for link in list(job_links)[:2]:
            job_id_match = re.search(r'/(\d+)/?$', link)
            job_id = job_id_match.group(1) if job_id_match else "N/A"
            print(f"  Sample: ID={job_id} URL={domain}{link}")


def test_tcs():
    print("\n=== TCS ===")
    # TCS has iBegin (https://ibegin.tcs.com/iBegin/jobs/search) and TCS Careers (https://www.tcs.com/careers)
    urls = [
        "https://www.tcs.com/careers/india",
        "https://ibegin.tcs.com/iBegin/jobs/search",
        "https://ibegin.tcs.com/iBegin/",
    ]
    for u in urls:
        try:
            r = httpx.get(u, headers=HEADERS, follow_redirects=True, timeout=10)
            print(f"TCS {u}: HTTP {r.status_code} | final={r.url}")
        except Exception as e:
            print(f"TCS {u}: ERROR {e}")


def test_infosys():
    print("\n=== Infosys ===")
    urls = [
        "https://career.infosys.com/",
        "https://career.infosys.com/joblist",
        "https://career.infosys.com/rest/jobs/search",
    ]
    for u in urls:
        try:
            r = httpx.get(u, headers=HEADERS, follow_redirects=True, timeout=10)
            print(f"Infosys {u}: HTTP {r.status_code} | len={len(r.text)}")
        except Exception as e:
            print(f"Infosys {u}: ERROR {e}")


def test_tech_mahindra():
    print("\n=== Tech Mahindra ===")
    urls = [
        "https://careers.techmahindra.com/",
        "https://careers.techmahindra.com/JobSearch.aspx",
    ]
    for u in urls:
        try:
            r = httpx.get(u, headers=HEADERS, follow_redirects=True, timeout=10)
            print(f"Tech Mahindra {u}: HTTP {r.status_code} | len={len(r.text)}")
        except Exception as e:
            print(f"Tech Mahindra {u}: ERROR {e}")


def test_ibm_careers():
    print("\n=== IBM Careers ===")
    # IBM careers search uses a specific API on ibm.com/careers
    urls = [
        "https://www.ibm.com/careers/search?q=India",
        "https://www.ibm.com/api/v1/careers/search?q=India",
        "https://api.ibm.com/careers/v1/jobs?q=India",
        "https://ibm.eightfold.ai/api/apply/v2/jobs?domain=ibm.com",
    ]
    for u in urls:
        try:
            r = httpx.get(u, headers=HEADERS, follow_redirects=True, timeout=10)
            print(f"IBM {u}: HTTP {r.status_code}")
            if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                print("  JSON keys:", list(r.json().keys())[:5])
        except Exception as e:
            print(f"IBM {u}: ERROR {e}")


def test_flipkart_api():
    print("\n=== Flipkart Careers ===")
    urls = [
        "https://www.flipkartcareers.com/api/jobs",
        "https://www.flipkartcareers.com/#!/joblist",
    ]
    for u in urls:
        try:
            r = httpx.get(u, headers=HEADERS, follow_redirects=True, timeout=10)
            print(f"Flipkart {u}: HTTP {r.status_code} | final={r.url}")
        except Exception as e:
            print(f"Flipkart {u}: ERROR {e}")


if __name__ == "__main__":
    test_hcltech_and_wipro()
    test_tcs()
    test_infosys()
    test_tech_mahindra()
    test_ibm_careers()
    test_flipkart_api()
