import httpx
import asyncio
import json

async def test_patents():
    query = "language model"
    url = "https://api.patentsview.org/patents/query"
    params = {
        "q": json.dumps({"_text_any": {"patent_title": query}}),
        "f": json.dumps(["patent_id", "patent_title", "patent_date", "assignee_organization"])
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.get(url, params=params)
        print("Status:", r.status_code)
        print("Text:", r.text[:500])

asyncio.run(test_patents())
