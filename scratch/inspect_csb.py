import httpx
import re

client = httpx.Client(follow_redirects=True, timeout=12.0, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

for name, url in [
    ('Wipro', 'https://careers.wipro.com/search/?q=India'),
    ('HCLTech', 'https://careers.hcltech.com/search/?q=India'),
    ('Capgemini', 'https://careers.capgemini.com/search/?q=India'),
    ('Tech Mahindra', 'https://careers.techmahindra.com/JobSearch.aspx')
]:
    try:
        r = client.get(url)
        print(f"=== {name} ({r.status_code}) ===")
        title = re.search(r'<title>(.*?)</title>', r.text, re.IGNORECASE)
        print(f"Title: {title.group(1).strip() if title else 'None'}")
        
        # Look for job links
        job_links = set(re.findall(r'href=[\'"]([^\'"]*(?:/job/|jobdetails|JobDescription)[^\'"]*)[\'"]', r.text, re.I))
        print(f"Job links found ({len(job_links)}): {list(job_links)[:3]}")
        
        # Look for total jobs indicator
        totals = re.findall(r'(\d+[\d,]*)\s*(?:jobs|results|openings|positions)', r.text, re.I)
        print(f"Total indicators: {totals[:3]}")

        # Check for table rows or json data
        if "searchResults" in r.text or "jobRecords" in r.text or "totalFound" in r.text:
            print("Found structured search state!")
    except Exception as e:
        print(f"Error {name}: {e}")
