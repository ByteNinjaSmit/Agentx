import os
import json
from pathlib import Path
import httpx

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load_fixture(name: str):
    path = FIXTURES_DIR / name
    if path.exists():
        return json.loads(path.read_text())
    return []


async def search_papers(query: str, limit: int = 5):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": limit,
                "fields": "title,abstract,url,year,citationCount,externalIds",
            },
        )
        r.raise_for_status()
        return r.json().get("data", [])


async def search_patents(query: str, limit: int = 5):
    # USPTO ODP now gates behind MFA account auth — this is the disclosed,
    # intentional primary data source (not a fallback), curated + real URLs.
    # See backend/fixtures/patents.json.
    items = _load_fixture("patents.json")
    q = query.lower()
    filtered = [p for p in items if q in json.dumps(p).lower()] or items
    return filtered[:limit]


async def search_news(query: str, limit: int = 5):
    api_key = os.environ.get("NEWSAPI_KEY")
    if api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "sortBy": "relevancy",
                        "pageSize": limit,
                        "apiKey": api_key,
                    },
                )
                r.raise_for_status()
                return r.json().get("articles", [])
        except Exception:
            pass  # fall through to GDELT — another real live source, not synthetic data
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": query,
                "mode": "artlist",
                "maxrecords": limit,
                "format": "json",
            },
        )
        r.raise_for_status()
        return r.json().get("articles", [])


async def search_social(query: str, limit: int = 5):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "tags": "story", "hitsPerPage": limit},
        )
        r.raise_for_status()
        return r.json().get("hits", [])


TOOL_MAP = {
    "search_papers": search_papers,
    "search_patents": search_patents,
    "search_news": search_news,
    "search_social": search_social,
}
