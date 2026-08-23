"""Runs a scripted scenario, collects the real metrics one execution actually
produced, and diffs two such runs (BEFORE a diagnosed fix is applied, AFTER). No
number here is synthesized — `run_labeled` drains a real `run_fleet_stream`/
`run_agent_stream` async generator to completion and reads its own reported
`resource_usage`/token counts/observations, the same way
`agent/orchestrator.py::run_agent()`'s non-streaming wrapper reattaches
observations onto trace steps."""

import time
from dataclasses import asdict, dataclass
from typing import Awaitable, Callable


@dataclass
class RunMetrics:
    label: str
    tool_calls_used: int
    elapsed_seconds: float
    input_tokens: int
    output_tokens: int
    fallback_count: int
    error_count: int
    items_count: int
    coverage_ok: bool


def _metrics_from(label: str, final: dict, observations: list[dict], wall_seconds: float) -> RunMetrics:
    usage = final.get("resource_usage") or {}
    return RunMetrics(
        label=label,
        tool_calls_used=usage.get("tool_calls_used", len(observations)),
        elapsed_seconds=round(wall_seconds, 3),
        input_tokens=final.get("input_tokens", 0),
        output_tokens=final.get("output_tokens", 0),
        fallback_count=sum(1 for o in observations if o.get("fallback_used")),
        error_count=sum(1 for o in observations if o.get("ok") is False),
        items_count=len(final.get("items", [])),
        coverage_ok=bool(final.get("coverage_ok")),
    )


async def run_labeled(
    label: str, make_stream: Callable[[], Awaitable]
) -> tuple[RunMetrics, dict, list[dict]]:
    """`make_stream` is a zero-arg callable returning the async generator from
    `run_fleet_stream`/`run_agent_stream` (already bound to goal/context/provider).
    Returns (metrics, final_event, trace_with_observations_reattached)."""
    events: list[dict] = []
    started = time.monotonic()
    async for event in make_stream():
        events.append(event)
    wall = time.monotonic() - started

    final = next(e for e in reversed(events) if e["type"] == "final")
    trace = [dict(e) for e in events if e["type"] == "trace"]
    observations: list[dict] = []
    for e in events:
        if e["type"] != "observation":
            continue
        observations.extend(e["results"])
        for step in trace:
            if step.get("step") == e.get("step"):
                step["observations"] = e["results"]

    metrics = _metrics_from(label, final, observations, wall)
    return metrics, final, trace


def _pct_improvement(before: float, after: float) -> float:
    if not before:
        return 0.0
    return round((before - after) / before * 100, 1)


def compare(before: RunMetrics, after: RunMetrics) -> dict:
    before_tokens = before.input_tokens + before.output_tokens
    after_tokens = after.input_tokens + after.output_tokens
    return {
        "before": asdict(before),
        "after": asdict(after),
        "deltas": {
            "tool_calls_used": before.tool_calls_used - after.tool_calls_used,
            "elapsed_seconds": round(before.elapsed_seconds - after.elapsed_seconds, 3),
            "tokens": before_tokens - after_tokens,
            "fallback_count": before.fallback_count - after.fallback_count,
            "error_count": before.error_count - after.error_count,
        },
        "improvement_pct": {
            "elapsed_seconds": _pct_improvement(before.elapsed_seconds, after.elapsed_seconds),
            "tool_calls_used": _pct_improvement(before.tool_calls_used, after.tool_calls_used),
            "tokens": _pct_improvement(before_tokens, after_tokens),
        },
        "unchanged": {
            "items_count": before.items_count == after.items_count,
            "coverage_ok": before.coverage_ok == after.coverage_ok,
        },
    }
