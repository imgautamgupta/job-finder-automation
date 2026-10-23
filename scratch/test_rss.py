import httpx
import xml.etree.ElementTree as ET

client = httpx.Client(follow_redirects=True, timeout=12.0, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

for name, url in [
    ('Capgemini RSS', 'https://careers.capgemini.com/services/rss/job/?locale=en_US&keywords=(India)'),
    ('Wipro RSS', 'https://careers.wipro.com/services/rss/job/?locale=en_US&keywords=(India)'),
    ('HCLTech RSS', 'https://careers.hcltech.com/services/rss/job/?locale=en_US&keywords=(India)'),
    ('SAP RSS', 'https://jobs.sap.com/services/rss/job/?locale=en_US&keywords=(India)'),
]:
    try:
        r = client.get(url)
        print(f"=== {name} ===")
        print(f"Status: {r.status_code}, Length: {len(r.text)}, Content-Type: {r.headers.get('content-type')}")
        if r.status_code == 200 and 'xml' in r.headers.get('content-type', ''):
            root = ET.fromstring(r.content)
            items = root.findall('.//item')
            print(f"Total items in RSS: {len(items)}")
            if items:
                first = items[0]
                title = first.findtext('title')
                link = first.findtext('link')
                guid = first.findtext('guid')
                print(f"Sample Job -> Title: {title}, Link: {link}, GUID: {guid}")
        else:
            print("Preview:", r.text[:150])
    except Exception as e:
        print(f"Error: {e}")
