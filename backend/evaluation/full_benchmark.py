"""python -m evaluation.full_benchmark

Runs one deterministic scenario — a Semantic Scholar outage across two research
lanes of the real `agent.fleet` LangGraph pipeline — end to end, twice:

    BEFORE (fault active, default policy)
        -> observability.trace_analyzer.analyze + observability.root_cause.diagnose
        -> observability.optimizer.propose(top finding).apply()
    AFTER  (same fault, same scenario, diagnosed fix now applied)
        -> observability.comparison.compare(before, after)

Writes `evaluation/results/{benchmark.json,before_after.json,report.md}` and prints
a BEFORE/AFTER table. Every number comes from two real `run_fleet_stream`
executions against a scripted `FakeProvider` (no LLM API calls) with only the two
Semantic Scholar/Crossref leaf HTTP functions in `agent/tools.py` mocked out (see
`fault_injection.py`) — `search_papers()`'s own control flow, including the
circuit-breaker check this benchmark proves out, runs for real. Nothing here is
hardcoded: change the scenario and the printed table changes with it.
"""

import asyncio
import json
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from observability import comparison, policy, root_cause

from .datasets import Case, ResearchLane
from .fakes import (
    FakeProvider,
    _fake_finish_run,
    _fake_get_known_ids,
    _fake_save_items,
    _fake_save_progress,
    _fake_start_run,
)
from .fault_injection import semantic_scholar_timeout


def _db_avoidance_patches() -> list:
    """Same DB-avoidance patches evaluation.fakes.patches_for() applies — reused
    individually here (fresh patch objects each call, run twice per benchmark)
    rather than via patches_for() itself, because that function also replaces
    agent.runtime.TOOL_MAP wholesale with scripted fakes, which would bypass the
    real search_papers()/circuit-breaker code path this benchmark exists to
    exercise. finish_run/save_items live in agent.orchestrator (shared by both
    pipelines via finalize_run) even though this scenario runs agent.fleet."""
    return [
        patch("agent.fleet.get_known_ids", _fake_get_known_ids),
        patch("agent.fleet.start_run", _fake_start_run),
        patch("agent.fleet.save_progress", _fake_save_progress),
        patch("agent.orchestrator.save_items", _fake_save_items),
        patch("agent.orchestrator.finish_run", _fake_finish_run),
    ]


RESULTS_DIR = Path(__file__).resolve().parent / "results"

_Q1 = "What recent research exists on quantum error correction hardware?"
_Q2 = "What recent research exists on fault-tolerant qubit control?"

_CROSSREF_DATA = {
    "quantum error correction hardware": [
        {
            "title": "Scalable Surface-Code Error Correction on Superconducting Qubits",
            "abstract": "",
            "url": "https://doi.org/10.9999/qec.0001",
            "year": 2026,
            "citationCount": 4,
            "externalIds": {"DOI": "10.9999/qec.0001"},
        }
    ],
    "fault tolerant qubit control": [
        {
            "title": "Real-Time Feedback Control for Fault-Tolerant Qubits",
            "abstract": "",
            "url": "https://doi.org/10.9999/qec.0002",
            "year": 2026,
            "citationCount": 2,
            "externalIds": {"DOI": "10.9999/qec.0002"},
        }
    ],
}

CASE = Case(
    id="benchmark-semantic-scholar-outage",
    category="tool_failure",
    goal="find recent hardware progress on quantum error correction",
    context="Evaluating whether our qubit control stack should track surface-code hardware work.",
    planner={
        "sub_questions": [
            {"question": _Q1, "sources": ["papers"], "why": "Grounds the hardware state of the art."},
            {"question": _Q2, "sources": ["papers"], "why": "Grounds control-stack-adjacent research."},
        ],
        "rationale": "Two independent literature lanes, both dependent on the same (faulted) papers source.",
    },
    lanes=[
        ResearchLane(
            question=_Q1,
            tool_calls=[{"name": "search_papers", "args": {"query": "quantum error correction hardware"}}],
            items=[
                {
                    "source": "research",
                    "external_id": "10.9999/qec.0001",
                    "title": "Scalable Surface-Code Error Correction on Superconducting Qubits",
                    "url": "https://doi.org/10.9999/qec.0001",
                    "summary": "Surface-code error correction demonstrated on superconducting hardware.",
                    "date": "2026-01-01",
                    "engagement": 4,
                    "organization": "",
                }
            ],
        ),
        ResearchLane(
            question=_Q2,
            tool_calls=[{"name": "search_papers", "args": {"query": "fault tolerant qubit control"}}],
            items=[
                {
                    "source": "research",
                    "external_id": "10.9999/qec.0002",
                    "title": "Real-Time Feedback Control for Fault-Tolerant Qubits",
                    "url": "https://doi.org/10.9999/qec.0002",
                    "summary": "Real-time feedback control loop for fault-tolerant qubit operation.",
                    "date": "2026-01-01",
                    "engagement": 2,
                    "organization": "",
                }
            ],
        ),
    ],
    analyst={
        "items": [
            {
                "external_id": "10.9999/qec.0001",
                "relevance_reason": "Directly on-topic hardware progress.",
                "organization": "",
                "keep": True,
            },
            {
                "external_id": "10.9999/qec.0002",
                "relevance_reason": "Directly on-topic control-stack progress.",
                "organization": "",
                "keep": True,
            },
        ],
        "coverage_ok": True,
        "coverage_gaps": [],
        "executive_summary": (
            "Both literature lanes returned usable findings via the Crossref fallback "
            "after Semantic Scholar failed."
        ),
    },
)


async def _run(label: str) -> tuple:
    from agent.fleet import run_fleet_stream

    provider = FakeProvider(CASE)
    with ExitStack() as stack:
        for p in [*_db_avoidance_patches(), *semantic_scholar_timeout(_CROSSREF_DATA)]:
            stack.enter_context(p)
        return await comparison.run_labeled(
            label,
            lambda: run_fleet_stream(
                CASE.goal, CASE.context, provider=provider, competitors=[], depth=5, track=CASE.goal
            ),
        )


async def main_async() -> dict:
    policy.reset()
    before_metrics, before_final, before_trace = await _run("before")

    ranked = root_cause.analyze_and_rank(before_trace, before_final)
    diagnosis = root_cause.to_dict(ranked)
    action_applied = False
    if ranked:
        from observability.optimizer import propose

        propose(ranked[0]).apply()
        action_applied = True

    after_metrics, after_final, _after_trace = await _run("after")
    result = comparison.compare(before_metrics, after_metrics)
    result["diagnosis"] = diagnosis
    result["action_applied"] = action_applied
    policy.reset()
    return result


def _render_report(result: dict) -> str:
    b, a, d = result["before"], result["after"], result["deltas"]
    diag = result["diagnosis"]
    lines = [
        "# AgentX observability closed-loop benchmark",
        "",
        f"Scenario: `{CASE.id}` — Semantic Scholar outage across {len(CASE.lanes)} research lane(s).",
        "",
        f"Root cause diagnosed from the BEFORE trace: **{diag['root_cause']}** "
        f"(severity={diag['severity']}, confidence={diag['confidence']})",
        f"Recommended action: **{diag['recommended_action']}** — applied before the AFTER run: {result['action_applied']}",
        "",
        "| Metric | Before | After | Delta |",
        "|---|---:|---:|---:|",
        f"| Tool calls used | {b['tool_calls_used']} | {a['tool_calls_used']} | {d['tool_calls_used']} |",
        f"| Elapsed seconds | {b['elapsed_seconds']} | {a['elapsed_seconds']} | {d['elapsed_seconds']} |",
        f"| Tokens (in+out) | {b['input_tokens'] + b['output_tokens']} | {a['input_tokens'] + a['output_tokens']} | {d['tokens']} |",
        f"| Fallback count | {b['fallback_count']} | {a['fallback_count']} | {d['fallback_count']} |",
        f"| Error count | {b['error_count']} | {a['error_count']} | {d['error_count']} |",
        f"| Items found | {b['items_count']} | {a['items_count']} | unchanged={result['unchanged']['items_count']} |",
        f"| coverage_ok | {b['coverage_ok']} | {a['coverage_ok']} | unchanged={result['unchanged']['coverage_ok']} |",
        "",
        f"Improvement: {result['improvement_pct']['elapsed_seconds']}% lower elapsed time, "
        f"{result['improvement_pct']['tokens']}% fewer tokens.",
    ]
    return "\n".join(lines)


def main() -> int:
    result = asyncio.run(main_async())

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "benchmark.json").write_text(json.dumps(result, indent=2, default=str))
    (RESULTS_DIR / "before_after.json").write_text(
        json.dumps(
            {"before": result["before"], "after": result["after"], "deltas": result["deltas"]},
            indent=2,
            default=str,
        )
    )
    report = _render_report(result)
    (RESULTS_DIR / "report.md").write_text(report)
    print(report)

    ok = (
        result["deltas"]["elapsed_seconds"] >= 0
        and result["unchanged"]["items_count"]
        and result["unchanged"]["coverage_ok"]
    )
    if not ok:
        print("\nFAIL: the optimization changed what was found, or made things worse.", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
