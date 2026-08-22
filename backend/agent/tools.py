import contextvars
import os
import json
import time
from pathlib import Path
import httpx

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# Set by a tool when its primary source failed and it recovered on a secondary
# one, read back by runtime.timed_call right after the await returns. A
# ContextVar rather than a return value so the tool functions keep returning
# plain result lists/dicts — no shape change for every call site that already
# expects that. asyncio.gather wraps each coroutine in its own Task, and each
# Task gets its own copy of the context, so concurrent tool calls never bleed
# their fallback flag into each other.
fallback_used: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "fallback_used", default=None
)

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


async def _search_papers_crossref(query: str, limit: int):
    """Fallback source for search_papers. Crossref needs no API key and has no
    per-key rate limit, so it stays up when Semantic Scholar is 429'd or down —
    real live literature data, not a synthetic stand-in. Reshaped to look like
    a Semantic Scholar hit so the researcher's parsing prompt needs no branch."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.crossref.org/works",
            params={
                "query": query,
                "rows": limit,
                "select": "title,DOI,URL,published-print,published-online,is-referenced-by-count",
            },
        )
        r.raise_for_status()
        works = r.json().get("message", {}).get("items", [])

    result = []
    for w in works:
        date_parts = (
            (w.get("published-print") or w.get("published-online") or {}).get("date-parts", [[None]])
        )
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        titles = w.get("title") or []
        result.append(
            {
                "title": titles[0] if titles else "",
                "abstract": "",
                "url": w.get("URL", ""),
                "year": year,
                "citationCount": w.get("is-referenced-by-count", 0),
                "externalIds": {"DOI": w.get("DOI", "")},
            }
        )
    return result


async def search_papers(query: str, limit: int = 5):
    key = f"papers:{query.strip().lower()}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    fallback_used.set(None)
    headers = {}
    s2_api_key = os.environ.get("S2_API_KEY")
    if s2_api_key:
        headers["x-api-key"] = s2_api_key

    try:
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
    except Exception:
        # Primary source down or rate-limited — recover on Crossref rather than
        # surfacing a hard failure. Only a genuine failure from BOTH sources
        # propagates up to timed_call as a coverage gap.
        result = await _search_papers_crossref(query, limit)
        fallback_used.set("crossref")

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


async def search_reddit(query: str, limit: int = 5):
    """Reddit's public search JSON. Practitioner sentiment lives here in a way it
    doesn't on Hacker News — a competitor's launch thread on r/LocalLLaMA says more
    about adoption than its press release does."""
    key = f"reddit:{query.strip().lower()}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # Reddit hard-blocks the default httpx UA. A descriptive one is what their API
    # terms ask for, and it is the difference between results and a 429.
    headers = {"User-Agent": "compintel-agent/1.0 (competitive intelligence research)"}
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
        r = await c.get(
            "https://www.reddit.com/search.json",
            params={"q": query, "sort": "relevance", "t": "year", "limit": limit},
            headers=headers,
        )
        r.raise_for_status()
        children = r.json().get("data", {}).get("children", [])

    result = [
        {
            "id": d.get("id"),
            "title": d.get("title"),
            "url": f"https://www.reddit.com{d.get('permalink', '')}",
            "subreddit": d.get("subreddit_name_prefixed"),
            "score": d.get("score"),
            "num_comments": d.get("num_comments"),
            "created_utc": d.get("created_utc"),
            "selftext": (d.get("selftext") or "")[:500],
        }
        for d in (child.get("data", {}) for child in children)
        if d.get("title")
    ]
    _cache_set(key, result)
    return result


async def search_github(query: str, limit: int = 5):
    key = f"github:{query.strip().lower()}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
            headers=headers,
        )
        r.raise_for_status()
        result = r.json().get("items", [])

    _cache_set(key, result)
    return result


async def search_google(query: str, limit: int = 5):
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
    cx = os.environ.get("GOOGLE_SEARCH_CX")
    if not api_key or not cx:
        return {"error": "Google search not configured (missing GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_CX)"}

    key = f"google:{query.strip().lower()}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": api_key, "cx": cx, "q": query, "num": limit},
        )
        r.raise_for_status()
        result = r.json().get("items", [])

    _cache_set(key, result)
    return result


TOOL_MAP = {
    "search_papers": search_papers,
    "search_patents": search_patents,
    "search_news": search_news,
    "search_social": search_social,
    "search_reddit": search_reddit,
    "search_github": search_github,
    "search_google": search_google,
}
