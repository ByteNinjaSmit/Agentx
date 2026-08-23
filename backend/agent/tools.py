import contextvars
import os
import json
import re
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


async def _search_papers_semantic_scholar(query: str, limit: int):
    """Primary source for search_papers, split out from search_papers() itself so
    it (and the Crossref fallback below) can each be patched independently — by the
    observability closed loop's controlled-failure scenarios and by its own
    circuit-breaker check — without disturbing search_papers()'s own control flow."""
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
        return r.json().get("data", [])


async def search_papers(query: str, limit: int = 5):
    key = f"papers:{query.strip().lower()}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    fallback_used.set(None)
    # A per-run circuit breaker: opened only by an explicit optimization action
    # (see observability/optimizer.py), never automatically, so a demoted source is
    # always the result of a diagnosed decision, not silent self-healing.
    from observability.policy import CURRENT as _policy

    if "search_papers" in _policy.circuit_open:
        result = await _search_papers_crossref(query, limit)
        fallback_used.set("crossref")
    else:
        try:
            result = await _search_papers_semantic_scholar(query, limit)
        except Exception:
            # Primary source down or rate-limited — recover on Crossref rather than
            # surfacing a hard failure. Only a genuine failure from BOTH sources
            # propagates up to timed_call as a coverage gap.
            result = await _search_papers_crossref(query, limit)
            fallback_used.set("crossref")

    _cache_set(key, result)
    return result


async def _search_patents_uspto_odp(query: str, limit: int):
    """Live primary source for search_patents: the USPTO Open Data Portal's patent
    application search. Endpoint (`GET /api/v1/patent/applications/search`) and auth
    header (`X-Api-Key`) were confirmed empirically against api.uspto.gov's API
    Gateway — a request with no key returns 401 Unauthorized, a wrong header name
    also returns 401 (proving it isn't checked), and `X-Api-Key` with a bad value
    returns 403 Forbidden (proving that header is the one being read) — rather than
    assumed from documentation, since USPTO's own reference docs require a
    signed-in USPTO.gov account to view a live sample payload and this project has
    no such account to test one against. Field extraction below reads several
    plausible paths defensively (`applicationMetaData.*` nesting per USPTO's own
    Python/Go client docs, with top-level fallbacks) so a wrong guess yields a
    blank field rather than a crash.

    ODP data starts at applications filed 2001-01-01 onward and is keyed by
    application, not just granted patent — a pending application has no
    patentNumber/grantDate yet, which is why both are optional below."""
    api_key = os.environ["USPTO_ODP_API_KEY"]
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.uspto.gov/api/v1/patent/applications/search",
            params={"q": f"inventionTitle:({query})", "limit": limit},
            headers={"X-Api-Key": api_key},
        )
        r.raise_for_status()
        body = r.json()
        rows = body.get("patentFileWrapperDataBag") or body.get("results") or []

    result = []
    for row in rows[:limit]:
        meta = row.get("applicationMetaData") or {}
        title = meta.get("inventionTitle") or row.get("inventionTitle") or ""
        patent_number = meta.get("patentNumber") or row.get("patentNumber") or ""
        app_number = row.get("applicationNumberText") or meta.get("applicationNumberText") or ""
        assignees = meta.get("assigneeBag") or row.get("assigneeBag") or []
        assignee = (assignees[0].get("assigneeNameText") if assignees else "") or ""
        date = meta.get("grantDate") or meta.get("filingDate") or ""
        result.append(
            {
                "title": title,
                "url": (
                    f"https://patentcenter.uspto.gov/applications/{app_number}"
                    if app_number
                    else ""
                ),
                "publication_number": patent_number or app_number,
                "assignee": assignee,
                "date": date or None,
            }
        )
    return result


_PATENT_NUMBER_RE = re.compile(r"/patent/([A-Za-z]{2}\d+[A-Za-z0-9]*)/")


async def _search_patents_google_cse(query: str, limit: int):
    """Live tertiary source for search_patents: Google Programmable Search
    restricted to patents.google.com. Reuses the exact GOOGLE_SEARCH_API_KEY/
    GOOGLE_SEARCH_CX pair search_google already reads, so a deployment that
    already has one working (from before this project needed it, or an older
    Google Cloud project predating the change below) gets live patent data for
    free, no extra signup. NOT reliably obtainable for a *new* setup, though: as
    of when this was written, Google's Custom Search JSON API (the underlying
    service — `customsearch.googleapis.com`) has stopped granting access to new
    Cloud projects, returning `403 "This project does not have the access to
    Custom Search JSON API"` even with the API enabled, billing linked, and the
    key correctly scoped — confirmed by reproducing exactly that against a fresh
    project. Kept as a fallback tier for whoever already has access, not
    recommended as the thing to newly set up — see _search_patents_serpapi
    below for the easy new-signup path instead. Less structured than either:
    a search snippet doesn't reliably carry an assignee or a filing/grant date, so
    those come back blank rather than guessed — only title, url and the
    publication number (parsed straight from the patents.google.com URL) are
    populated."""
    api_key = os.environ["GOOGLE_SEARCH_API_KEY"]
    cx = os.environ["GOOGLE_SEARCH_CX"]
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": api_key, "cx": cx, "q": f"{query} site:patents.google.com", "num": limit},
        )
        r.raise_for_status()
        rows = r.json().get("items", [])

    result = []
    for row in rows[:limit]:
        url = row.get("link", "")
        match = _PATENT_NUMBER_RE.search(url)
        title = re.sub(r"\s*-\s*Google Patents\s*$", "", row.get("title", "") or "")
        result.append(
            {
                "title": title,
                "url": url,
                "publication_number": match.group(1) if match else "",
                "assignee": "",
                "date": None,
            }
        )
    return result


async def _search_patents_serpapi(query: str, limit: int):
    """Live tier for search_patents via SerpAPI's Google Patents engine
    (https://serpapi.com/google-patents-api) — publicly documented with a full
    field list and no account needed to view it, unlike USPTO ODP's docs. Signup
    is email-only (250 free searches/month) — no MFA-gated identity verification
    like USPTO ODP, and unlike Google's own Custom Search JSON API (see
    _search_patents_google_cse below), which stopped granting access to new
    Cloud projects — this still does, as of when this was written."""
    api_key = os.environ["SERPAPI_API_KEY"]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            "https://serpapi.com/search",
            params={"engine": "google_patents", "q": query, "api_key": api_key},
        )
        r.raise_for_status()
        rows = r.json().get("organic_results", [])

    result = []
    for row in rows[:limit]:
        result.append(
            {
                "title": row.get("title", ""),
                "url": row.get("patent_link", ""),
                "publication_number": row.get("publication_number") or row.get("patent_id", ""),
                "assignee": row.get("assignee", ""),
                "date": row.get("publication_date") or row.get("filing_date") or row.get("priority_date"),
            }
        )
    return result


# Tried in this order; each entry is (fallback label, "is configured" check, live
# call). The first configured source that succeeds wins; fallback_used is set to
# whichever label actually served the result, but only when an earlier source in
# the chain was attempted and failed — so a demoted source is always visible in
# the trace, exactly like search_papers' Crossref fallback, and the common case
# (only one source configured, or none) never claims a fallback that never fired.
_PATENT_LIVE_SOURCES = [
    ("uspto_odp", lambda: bool(os.environ.get("USPTO_ODP_API_KEY")), _search_patents_uspto_odp),
    ("serpapi_google_patents", lambda: bool(os.environ.get("SERPAPI_API_KEY")), _search_patents_serpapi),
    (
        "google_patents_cse",
        lambda: bool(os.environ.get("GOOGLE_SEARCH_API_KEY") and os.environ.get("GOOGLE_SEARCH_CX")),
        _search_patents_google_cse,
    ),
]


async def search_patents(query: str, limit: int = 5):
    """Tries each configured live source in `_PATENT_LIVE_SOURCES` order, then
    falls back to `backend/fixtures/patents.json` — curated, disclosed, not a
    silent stand-in — if none are configured or all fail. With nothing configured
    (the default), behavior is unchanged from before any live source was wired up."""
    fallback_used.set(None)
    demoted = False
    for label, configured, live_fn in _PATENT_LIVE_SOURCES:
        if not configured():
            continue
        try:
            result = await live_fn(query, limit)
            if demoted:
                fallback_used.set(label)
            return result
        except Exception:
            demoted = True

    if demoted:
        fallback_used.set("fixture")
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
