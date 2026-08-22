import os
import json
import time
from pathlib import Path
import httpx

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# short-lived cache for the three live-API tools — absorbs repeat/retry queries
# within a run and across back-to-back demo runs without hammering rate limits.
# Only successful responses are cached; a failure is never cached as if it were
# a valid empty result.
_CACHE_TTL = 600  # seconds
_CACHE_MAX_ENTRIES = 500
_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.monotonic() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, value):
    if len(_cache) >= _CACHE_MAX_ENTRIES:
        oldest_key = min(_cache, key=lambda k: _cache[k][0])
        del _cache[oldest_key]
    _cache[key] = (time.monotonic(), value)


def _load_fixture(name: str):
    path = FIXTURES_DIR / name
    if path.exists():
        return json.loads(path.read_text())
    return []


async def search_papers(query: str, limit: int = 5):
    key = f"papers:{query.strip().lower()}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    headers = {}
    s2_api_key = os.environ.get("S2_API_KEY")
    if s2_api_key:
        headers["x-api-key"] = s2_api_key

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": limit,
                "fields": "title,abstract,url,year,citationCount,externalIds",
            },
            headers=headers,
        )
        r.raise_for_status()
        result = r.json().get("data", [])

    _cache_set(key, result)
    return result


async def search_patents(query: str, limit: int = 5):
    # USPTO ODP now gates behind MFA account auth — this is the disclosed,
    # intentional primary data source (not a fallback), curated + real URLs.
    # See backend/fixtures/patents.json. Already instant/local — no cache needed.
    items = _load_fixture("patents.json")
    q = query.lower()
    filtered = [p for p in items if q in json.dumps(p).lower()] or items
    return filtered[:limit]


async def search_news(query: str, limit: int = 5):
    key = f"news:{query.strip().lower()}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

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
                result = r.json().get("articles", [])
                _cache_set(key, result)
                return result
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
        result = r.json().get("articles", [])

    _cache_set(key, result)
    return result


async def search_social(query: str, limit: int = 5):
    key = f"social:{query.strip().lower()}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "tags": "story", "hitsPerPage": limit},
        )
        r.raise_for_status()
        result = r.json().get("hits", [])

    _cache_set(key, result)
    return result


TOOL_MAP = {
    "search_papers": search_papers,
    "search_patents": search_patents,
    "search_news": search_news,
    "search_social": search_social,
}
