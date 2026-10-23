import re
import httpx

r_html = httpx.get("https://ibegin.tcsapps.com/candidate/next/", headers={"User-Agent": "Mozilla/5.0"})
chunks = re.findall(r'(chunk-[a-zA-Z0-9]+\.js)', r_html.text)

for c in chunks:
    r = httpx.get("https://ibegin.tcsapps.com/candidate/next/" + c, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    for m in re.finditer(r'this\.http\.(?:get|post)\(["\'`]([^"\'`]+)["\'`]', r.text):
        print(c, "HTTP call:", m.group(1))
