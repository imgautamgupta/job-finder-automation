import httpx
import re

client = httpx.Client(follow_redirects=True, timeout=12.0, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

r1 = client.get('https://ibegin.tcsapps.com/iBegin/')
print("iBegin text preview:", r1.text[:500])

r2 = client.get('https://careers.techmahindra.com/JobSearch.aspx')
print("Tech Mahindra length:", len(r2.text))
inputs = re.findall(r'<input[^>]+name=[\'"]([^\'"]+)[\'"]', r2.text)
print("Tech Mahindra input names:", inputs[:10])
# check if there are job links or a table
job_links = re.findall(r'href=[\'"]([^\'"]*(?:Job|job|Position)[^\'"]*)[\'"]', r2.text)
print("Tech Mahindra job links:", job_links[:5])

# Also check if TCS has any public jobs search API
r3 = client.get('https://ibegin.tcsapps.com/iBegin/jobs/search')
print("iBegin /jobs/search status:", r3.status_code, "length:", len(r3.text))
