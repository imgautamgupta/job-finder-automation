import httpx
import json

client = httpx.Client(
    follow_redirects=True, 
    timeout=12.0, 
    headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8',
    }
)

targets = [
    ('SAP Feed', 'https://jobs.sap.com/search/feed/?q=India'),
    ('SAP CSB API', 'https://jobs.sap.com/services/jobs/search?q=India'),
    ('Capgemini Jobs API', 'https://www.capgemini.com/wp-json/capgemini/v1/jobs?country=in'),
    ('Capgemini Phenom Widget', 'https://careers.capgemini.com/global/en/search-results'),
    ('TCS iBegin', 'https://ibegin.tcs.com/iBegin/jobs/search'),
    ('TCS Career portal', 'https://www.tcs.com/careers/india'),
    ('Wipro Feed', 'https://careers.wipro.com/search/feed/?q=India'),
    ('Wipro CSB API', 'https://careers.wipro.com/services/jobs/search?q=India'),
    ('HCLTech Feed', 'https://careers.hcltech.com/search/feed/?q=India'),
    ('HCLTech CSB API', 'https://careers.hcltech.com/services/jobs/search?q=India'),
    ('Tech Mahindra', 'https://careers.techmahindra.com/JobSearch.aspx')
]

for name, url in targets:
    try:
        r = client.get(url)
        print(f"[{name}] URL: {url} -> Status: {r.status_code}, Length: {len(r.text)}, Content-Type: {r.headers.get('content-type', '')[:40]}")
        # check preview
        if r.status_code == 200:
            preview = r.text[:200].replace('\n', ' ')
            print(f"   Preview: {preview}")
    except Exception as e:
        print(f"[{name}] URL: {url} -> Exception: {e}")
