import urllib.request
import json

def check_board(name):
    req = urllib.request.Request(f'https://boards-api.greenhouse.io/v1/boards/{name}/jobs?content=true', headers={'User-Agent': 'JobFinder'})
    data = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))['jobs']
    print(f'=== {name}: Total jobs {len(data)} ===')
    for i, j in enumerate(data):
        t = j['title'].lower()
        loc = (j.get('location') or {}).get('name') or ''
        if 'intern' in t or 'software engineer' in t or 'backend' in t or 'python' in t:
            if 'bangalore' in loc.lower() or 'india' in loc.lower() or 'remote' in loc.lower():
                print(f'  Index {i:3d}: {j["title"]} [{loc}]')

check_board('rubrik')
check_board('hackerrank')
check_board('mongodb')
check_board('stripe')
