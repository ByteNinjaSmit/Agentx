"""Turns a completed run's trace + final result into a list of `Finding`s. Every
detector reads fields `agent/fleet.py`/`agent/orchestrator.py` already emit —
`fallback_used`, `latency_ms`, `ok`, `count` on each tool observation;
`resource_usage`, `self_evaluation`, `rejected_count` on the final result — so
nothing had to be added to either pipeline's trace shape to make this possible.

`trace` is the list of `{"type": "trace", "step": ..., "agent": ..., "tools_called":
[...], "observations": [...], ...}` dicts either pipeline produces (with
`observations` re-attached — see `orchestrator.run_agent()` and
`observability/comparison.py::run_labeled` for the two places that do this; the raw
SSE stream keeps trace and observation events separate to save bandwidth). `final`
is the pipeline's `{"type": "final", ...}` event."""

import re
from dataclasses import dataclass, field

SLOW_MS = 1500
DUPLICATE_MIN_COUNT = 2
LOW_YIELD_MIN_COUNT = 2
FALLBACK_RATIO_THRESHOLD = 0.5
BUDGET_RATIO_THRESHOLD = 0.8


@dataclass
class Finding:
    category: str
    severity: str  # low | medium | high | critical
    evidence: list[str]
    confidence: float
    target: str = ""  # tool name the finding is about, when there is one
    metrics: dict = field(default_factory=dict)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _all_observations(trace: list[dict]) -> list[dict]:
    return [obs for entry in trace for obs in (entry.get("observations") or [])]


def detect_unreliable_primary_source(trace: list[dict], final: dict) -> list[Finding]:
    by_tool: dict[str, list[dict]] = {}
    for obs in _all_observations(trace):
        by_tool.setdefault(obs["tool"], []).append(obs)

    findings = []
    for tool, calls in by_tool.items():
        fell_back = [c for c in calls if c.get("fallback_used")]
        if not fell_back or len(fell_back) / len(calls) < FALLBACK_RATIO_THRESHOLD:
            continue
        source = fell_back[0]["fallback_used"]
        findings.append(
            Finding(
                category="unreliable_primary_source",
                severity="high" if len(fell_back) >= 2 else "medium",
                evidence=[
                    f"{len(fell_back)} of {len(calls)} {tool} call(s) this run fell back to {source}",
                    *[
                        f"{tool} call for {c.get('query')!r} took {c.get('latency_ms')}ms before falling back to {c.get('fallback_used')}"
                        for c in fell_back[:3]
                    ],
                ],
                confidence=round(min(0.95, 0.55 + 0.15 * len(fell_back)), 2),
                target=tool,
                metrics={"fallback_count": len(fell_back), "total_calls": len(calls)},
            )
        )
    return findings


def detect_slow_tools(trace: list[dict], final: dict) -> list[Finding]:
    by_tool: dict[str, list[dict]] = {}
    for obs in _all_observations(trace):
        if (obs.get("latency_ms") or 0) >= SLOW_MS:
            by_tool.setdefault(obs["tool"], []).append(obs)

    return [
        Finding(
            category="slow_tool",
            severity="high" if len(calls) >= 2 else "medium",
            evidence=[
                f"{tool} call for {c.get('query')!r} took {c.get('latency_ms')}ms (>= {SLOW_MS}ms)"
                for c in calls[:3]
            ],
            confidence=0.8,
            target=tool,
            metrics={"count": len(calls), "max_latency_ms": max(c["latency_ms"] for c in calls)},
        )
        for tool, calls in by_tool.items()
    ]


def detect_tool_failures(trace: list[dict], final: dict) -> list[Finding]:
    by_tool: dict[str, list[dict]] = {}
    for obs in _all_observations(trace):
        if obs.get("ok") is False:
            by_tool.setdefault(obs["tool"], []).append(obs)

    return [
        Finding(
            category="tool_failure",
            severity="critical" if len(calls) >= 2 else "high",
            evidence=[f"{tool} call for {c.get('query')!r} failed: {c.get('error')}" for c in calls[:3]],
            confidence=0.9,
            target=tool,
            metrics={"count": len(calls)},
        )
        for tool, calls in by_tool.items()
    ]


def detect_duplicate_tool_calls(trace: list[dict], final: dict) -> list[Finding]:
    seen: dict[tuple[str, str], list[dict]] = {}
    for obs in _all_observations(trace):
        key = (obs["tool"], _norm(str(obs.get("query") or "")))
        seen.setdefault(key, []).append(obs)

    findings = []
    for (tool, query), calls in seen.items():
        if len(calls) < DUPLICATE_MIN_COUNT:
            continue
        findings.append(
            Finding(
                category="duplicate_tool_call",
                severity="medium",
                evidence=[f"{tool} was called with the same query {query!r} {len(calls)} times this run"],
                confidence=0.85,
                target=tool,
                metrics={"count": len(calls)},
            )
        )
    return findings


def detect_low_yield_tools(trace: list[dict], final: dict) -> list[Finding]:
    by_tool: dict[str, list[dict]] = {}
    for obs in _all_observations(trace):
        if obs.get("ok") and obs.get("count") == 0:
            by_tool.setdefault(obs["tool"], []).append(obs)

    return [
        Finding(
            category="low_yield_tool",
            severity="low",
            evidence=[f"{tool} returned 0 results for {c.get('query')!r}" for c in calls[:3]],
            confidence=0.7,
            target=tool,
            metrics={"count": len(calls)},
        )
        for tool, calls in by_tool.items()
        if len(calls) >= LOW_YIELD_MIN_COUNT
    ]


def detect_replanning_overhead(trace: list[dict], final: dict) -> list[Finding]:
    self_eval = final.get("self_evaluation") or {}
    if not self_eval.get("replanned"):
        return []
    rationale = self_eval.get("replan_rationale") or "coverage was below threshold"
    return [
        Finding(
            category="replanning_overhead",
            severity="low",
            evidence=[f"a replanning round was opened: {rationale}"],
            confidence=0.6,
            metrics={"coverage_score": self_eval.get("coverage_score")},
        )
    ]


def detect_ungrounded_findings_rejected(trace: list[dict], final: dict) -> list[Finding]:
    rejected_count = final.get("rejected_count", 0)
    if not rejected_count:
        return []
    reasons = []
    for entry in trace:
        if entry.get("agent") == "verifier":
            reasons.extend(r.get("reason", "") for r in (entry.get("rejected") or []))
    return [
        Finding(
            category="ungrounded_findings_rejected",
            severity="medium" if rejected_count >= 2 else "low",
            evidence=[f"the verifier discarded {rejected_count} ungrounded finding(s)", *reasons[:3]],
            confidence=0.9,
            metrics={"rejected_count": rejected_count},
        )
    ]


def detect_budget_pressure(trace: list[dict], final: dict) -> list[Finding]:
    usage = final.get("resource_usage") or {}
    calls_used, calls_budget = usage.get("tool_calls_used", 0), usage.get("tool_call_budget", 0)
    elapsed, time_budget = usage.get("elapsed_seconds", 0), usage.get("time_budget_seconds", 0)
    call_ratio = calls_used / calls_budget if calls_budget else 0
    time_ratio = elapsed / time_budget if time_budget else 0
    ratio = max(call_ratio, time_ratio)
    if ratio < BUDGET_RATIO_THRESHOLD:
        return []
    return [
        Finding(
            category="budget_pressure",
            severity="high" if ratio >= 0.95 else "medium",
            evidence=[
                f"tool calls used {calls_used}/{calls_budget}, elapsed {elapsed}/{time_budget}s "
                f"({ratio:.0%} of the tighter budget)"
            ],
            confidence=0.85,
            metrics={"ratio": round(ratio, 2)},
        )
    ]


DETECTORS = [
    detect_unreliable_primary_source,
    detect_slow_tools,
    detect_tool_failures,
    detect_duplicate_tool_calls,
    detect_low_yield_tools,
    detect_replanning_overhead,
    detect_ungrounded_findings_rejected,
    detect_budget_pressure,
]


def analyze(trace: list[dict], final: dict) -> list[Finding]:
    findings = []
    for detector in DETECTORS:
        findings.extend(detector(trace, final))
    return findings
