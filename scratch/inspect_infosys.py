import re
import httpx

r = httpx.get("https://career.infosys.com/main.js", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
matches = set(re.findall(r'this\.http\.post\([^,]+', r.text))
job_posts = [m for m in matches if 'job' in m.lower() or 'search' in m.lower()]
print("POST calls with job/search:", job_posts)

matches_get = set(re.findall(r'this\.http\.get\([^,\)]+', r.text))
job_gets = [m for m in matches_get if 'job' in m.lower() or 'search' in m.lower()]
print("GET calls with job/search:", job_gets)
