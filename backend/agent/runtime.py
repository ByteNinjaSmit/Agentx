"""Pieces shared by the single-loop orchestrator and the specialist fleet:
the tool catalogue, timed tool execution, and the grounded-observation record
that both pipelines stream to the UI.
"""

import asyncio
import json
import time

from .providers import ToolCall, ToolResult, ToolSpec
from .tools import TOOL_MAP

# How much of a tool result the UI shows inline. The model still sees MODEL_RESULT_CHARS.
PREVIEW_CHARS = 600
MODEL_RESULT_CHARS = 8000

TOOL_SPECS = [
    ToolSpec("search_papers", "Search academic research papers via Semantic Scholar."),
    ToolSpec("search_patents", "Search granted US patents relevant to a query."),
    ToolSpec("search_news", "Search recent news and competitor announcements."),
    ToolSpec("search_social", "Search Hacker News discussion/sentiment for a topic."),
    ToolSpec(
        "search_github",
        "Search GitHub repositories relevant to a query — finds competing "
        "open-source projects and new tools.",
    ),
    ToolSpec(
        "search_google",
        "General web search (Google) for anything not well covered by the other sources.",
    ),
]


def extract_json(text: str) -> dict | None:
    """Models are asked for a bare JSON object; they sometimes wrap it in prose or
    fences anyway. Returns None when nothing parseable is present so the caller can
    decide what a missing answer means."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def preview(result) -> str:
    text = json.dumps(result, default=str)
    return text[:PREVIEW_CHARS] + "…" if len(text) > PREVIEW_CHARS else text


def is_error(result) -> bool:
    return isinstance(result, dict) and "error" in result


def result_count(result) -> int | None:
    return len(result) if isinstance(result, list) else None


async def timed_call(name: str, args: dict):
    """Runs one tool call and reports how long it took and whether it worked — the
    raw material for the grounded-observation line in the UI and for the per-source
    reliability statistics."""
    started = time.monotonic()
    try:
        if name not in TOOL_MAP:
            raise KeyError(f"no such tool: {name}")
        result = await TOOL_MAP[name](**args)
    except Exception as exc:  # a failed source must stay visible, never be swallowed
        result = {"error": f"{type(exc).__name__}: {exc}"}
    return result, round((time.monotonic() - started) * 1000)


async def execute_calls(calls: list[ToolCall]) -> tuple[list[dict], list[ToolResult], list]:
    """Runs a turn's tool calls in parallel. Returns the observation records for the
    UI, the results to hand back to the model, and the raw payloads — the raw ones
    are what the Verifier checks item claims against."""
    outcomes = await asyncio.gather(*[timed_call(c.name, c.args) for c in calls])

    observations, tool_results, raw = [], [], []
    for call, (result, latency) in zip(calls, outcomes):
        failed = is_error(result)
        observations.append(
            {
                "tool": call.name,
                "query": call.args.get("query"),
                "ok": not failed,
                "count": result_count(result),
                "latency_ms": latency,
                "preview": preview(result),
                "error": result.get("error") if failed else None,
            }
        )
        tool_results.append(
            ToolResult(
                call=call,
                content=json.dumps(result, default=str)[:MODEL_RESULT_CHARS],
                is_error=failed,
            )
        )
        raw.append(result)
    return observations, tool_results, raw


def strip_private(final: dict) -> dict:
    """Item embeddings are 768 floats each — useful in Postgres, ruinous in an SSE
    payload and in the run_log JSON. Drop them once they've been persisted."""
    for item in final.get("items", []):
        item.pop("_embedding", None)
    return final
