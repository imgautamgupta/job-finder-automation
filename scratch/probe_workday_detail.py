import sqlite3
import json
import httpx
import asyncio

async def main():
    conn = sqlite3.connect('data/jobs.db')
    conn.row_factory = sqlite3.Row
    rows = conn.cursor().execute(
        "SELECT id, company, title, url, raw_metadata FROM jobs WHERE company IN ('Adobe', 'Intel') LIMIT 5"
    ).fetchall()

    for row in rows:
        print(f"Company: {row['company']}, Title: {row['title']}")
        print(f"URL: {row['url']}")
        meta = json.loads(row['raw_metadata']) if row['raw_metadata'] else {}
        print("Meta keys:", list(meta.keys()))
        ext_path = meta.get('externalPath')
        print(f"externalPath: {ext_path}")

    # Now let's test fetching a detail page from Workday CXS
    # Adobe host: adobe.wd5.myworkdayjobs.com, tenant: adobe, site: external_experienced
    # If externalPath is e.g. /job/Noida/Software-Development-Engineer_R170776
    # In CXS: https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/job/Noida/Software-Development-Engineer_R170776
    # or /job/job-id
    test_url = "https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/job/Noida/Software-Development-Engineer_R170776"
    print("\nProbing CXS detail endpoint:", test_url)
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            resp = await client.get(test_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print("Response keys:", list(data.keys()))
                job_desc = data.get("jobPostingInfo", {}).get("jobDescription", "")
                print(f"jobPostingInfo keys: {list(data.get('jobPostingInfo', {}).keys())}")
                print(f"jobDescription snippet: {repr(job_desc[:200])}")
        except Exception as e:
            print("Error probing:", e)

if __name__ == "__main__":
    asyncio.run(main())
