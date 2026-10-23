import asyncio
import httpx

async def test_salesforce_pagination():
    host = "salesforce.wd12.myworkdayjobs.com"
    tenant = "salesforce"
    site = "External_Career_Site"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": f"https://{host}",
        "Referer": f"https://{host}/en-US/{site}/jobs",
    }
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        await client.get(f"https://{host}/en-US/{site}/jobs", headers={"User-Agent": headers["User-Agent"]})
        
        offset = 0
        limit = 20
        total_available = 0
        collected = []
        
        while True:
            payload = {
                "appliedFacets": {
                    "CF_-_REC_-_LRV_-_Job_Posting_Anchor_-_Country_from_Job_Posting_Location_Extended": ["c4f78be1a8f14da0ab49ce1162348a5e"]
                },
                "limit": limit,
                "offset": offset,
                "searchText": "",
            }
            
            # Retry loop for 429
            max_retries = 3
            resp = None
            for attempt in range(max_retries + 1):
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 429:
                        wait_sec = 2.0 * (2 ** attempt)
                        print(f"  HTTP 429 at offset {offset}. Backoff {wait_sec}s (attempt {attempt+1}/{max_retries})...")
                        await asyncio.sleep(wait_sec)
                        continue
                    break
                except Exception as e:
                    print(f"  Request exception: {e}")
                    await asyncio.sleep(1.0)
            
            if not resp or resp.status_code != 200:
                print(f"Failed at offset {offset}: status={resp.status_code if resp else 'None'}")
                break
                
            data = resp.json()
            if offset == 0 or total_available == 0:
                page_total = data.get("total", 0)
                if page_total > 0:
                    total_available = page_total
                    
            postings = data.get("jobPostings", [])
            if not postings:
                print(f"No more postings at offset {offset}.")
                break
                
            collected.extend(postings)
            print(f"Fetched page at offset {offset}: got {len(postings)} (running total: {len(collected)} / {total_available})")
            
            offset += len(postings)
            if total_available > 0 and offset >= total_available:
                print(f"Reached total available ({total_available}). Done.")
                break
                
            await asyncio.sleep(1.0)  # Polite delay
            
        print(f"Finished Salesforce pagination: collected {len(collected)} of {total_available} jobs.")

if __name__ == "__main__":
    asyncio.run(test_salesforce_pagination())
