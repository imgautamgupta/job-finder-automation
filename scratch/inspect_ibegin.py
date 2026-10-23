import httpx
import re

client = httpx.Client(follow_redirects=True, timeout=12.0)
r = client.get('https://ibegin.tcsapps.com/candidate/next/main-2WFMRSVT.js')

print("main.js contains 'fetch':", "fetch(" in r.text)
print("main.js contains 'post':", "post(" in r.text)
print("main.js contains 'get':", "get(" in r.text)
print("Occurrences of 'job':", len(re.findall(r'job', r.text, re.I)))

matches = set(re.findall(r'[a-zA-Z0-9_\-\./]{5,50}/[a-zA-Z0-9_\-\./]{3,50}', r.text))
print("Slash paths sample:", [m for m in matches if 'api' in m or 'job' in m][:10])
