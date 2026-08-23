"""Deterministic controlled-failure scenarios for the observability closed loop and
its tests. Same idea as `fakes.py`'s `patches_for` — a list of `unittest.mock.patch`
context managers the caller enters via `contextlib.ExitStack` — but these patch only
the two leaf HTTP functions in `agent/tools.py` (`_search_papers_semantic_scholar`,
`_search_papers_crossref`), not `agent.runtime.TOOL_MAP` wholesale. That matters: the
Ladder 6 harness's fakes replace tools entirely so no real code in `tools.py` runs at
all, which is right for grading framework mechanics but wrong here — the whole point
of this scenario is to exercise `search_papers()`'s real control flow, including the
circuit-breaker check `observability/optimizer.py` can open, with no network."""

import asyncio

from unittest.mock import patch

import agent.tools as tools

# Long enough to be a clearly non-noise, real latency tax in a before/after
# comparison; short enough that a full test run stays well under a second.
SEMANTIC_SCHOLAR_FAIL_DELAY_SECONDS = 0.3


async def _failing_semantic_scholar(query: str, limit: int):
    await asyncio.sleep(SEMANTIC_SCHOLAR_FAIL_DELAY_SECONDS)
    raise TimeoutError("semantic scholar: simulated outage (fault_injection)")


def _make_crossref_stub(query_to_result: dict[str, list]):
    async def _crossref(query: str, limit: int):
        return query_to_result.get(query, [])[:limit]

    return _crossref


def semantic_scholar_timeout(query_to_result: dict[str, list]) -> list:
    """Primary source (Semantic Scholar) always times out after a short, deterministic
    delay; the fallback (Crossref) always succeeds instantly with `query_to_result`.

    Clears `agent.tools._cache` first — a warm cache from an earlier call with the
    same (query, limit) would let a run skip both mocked functions entirely and
    silently invalidate a before/after comparison."""
    tools._cache.clear()
    return [
        patch("agent.tools._search_papers_semantic_scholar", _failing_semantic_scholar),
        patch("agent.tools._search_papers_crossref", _make_crossref_stub(query_to_result)),
    ]
