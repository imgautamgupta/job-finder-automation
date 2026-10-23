import httpx
import re
import json

client = httpx.Client(follow_redirects=True, timeout=12.0, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
r = client.get('https://flipkart.turbohire.co/careerpage/4d757ba0-3d57-448a-b82c-238ed87ac90f')
print("TurboHire page:", r.status_code, "len:", len(r.text))

# Search for jobs in HTML or embedded json
scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
for s in scripts:
    if "job" in s.lower() and len(s) > 100:
        print("Script with job data length:", len(s))
        if "f0fd59cd" in s or "FIPL" in s or "title" in s.lower():
            print("Found job IDs or title in script!")

# Also inspect how the search request payload is formatted:
r_tok = client.get('https://api.turbohire.co/api/token/noauth', headers={'Origin': 'https://flipkart.turbohire.co', 'Referer': 'https://flipkart.turbohire.co/'})
token = r_tok.json().get('access_token')

post_url = 'https://api.turbohire.co/api/careerpagev2/filteredjobs?orgId=4d757ba0-3d57-448a-b82c-238ed87ac90f&pageType=public'
headers = {
    'Authorization': f'Bearer {token}',
    'Origin': 'https://flipkart.turbohire.co',
    'Referer': 'https://flipkart.turbohire.co/',
    'Content-Type': 'application/json'
}

# Try payload variations
for payload in [
    {},
    {"page": 1, "pageSize": 10},
    {"filters": {}, "page": 1, "pageSize": 10},
    {"filters": [], "page": 1, "pageSize": 10},
    {"filters": {"search": ""}, "page": 1, "pageSize": 10}
]:
    res = client.post(post_url, headers=headers, json=payload)
    print(f"Payload {payload} -> status: {res.status_code}, response: {res.text[:150]}")
