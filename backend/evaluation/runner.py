"""CLI entry point for the Ladder 6 evaluation harness.

    cd backend
    python -m evaluation.runner                       # all cases, pipeline=fleet, 1 rep
    python -m evaluation.runner --pipeline both        # also runs pipeline=single where scripted
    python -m evaluation.runner --repeat 3             # repeat each case 3x, report consistency
    python -m evaluation.runner --category tool_failure
    python -m evaluation.runner --case normal-001
    python -m evaluation.runner --pipeline both --repeat 2 --save   # also writes results/summary.json

No network access, no API keys, and no Postgres are used or required — see
`evaluation/fakes.py` for what is faked and why.
"""

import argparse
import asyncio
import contextlib
import datetime
import json
import sys
from pathlib import Path

from .datasets import BY_CATEGORY, DATASET, Case
from .evaluators import evaluate
from .fakes import FakeProvider, patches_for
from .metrics import CaseRunOutcome, Summary, summarize
from .report import render

RESULTS_DIR = Path(__file__).resolve().parent / "results"


async def _run_fleet(case: Case) -> tuple[dict, list[dict]]:
    from agent.fleet import run_fleet_stream

    provider = FakeProvider(case)
    events: list[dict] = []
    with contextlib.ExitStack() as stack:
        for p in patches_for(case):
            stack.enter_context(p)
        async for event in run_fleet_stream(case.goal, case.context, provider=provider, competitors=[], depth=5, track=case.goal):
            events.append(event)
    final = next(e for e in reversed(events) if e["type"] == "final")
    return final, events


async def _run_single(case: Case) -> tuple[dict, list[dict]]:
    from agent.orchestrator import run_agent_stream

    provider = FakeProvider(case)
    events: list[dict] = []
    with contextlib.ExitStack() as stack:
        for p in patches_for(case):
            stack.enter_context(p)
        async for event in run_agent_stream(case.goal, case.context, provider=provider, competitors=[], depth=5, track=case.goal):
            events.append(event)
    final = next(e for e in reversed(events) if e["type"] == "final")
    return final, events


async def run_all(cases: list[Case], pipelines: list[str], repeat: int) -> list[CaseRunOutcome]:
    outcomes: list[CaseRunOutcome] = []
    for case in cases:
        for pipeline in pipelines:
            if pipeline == "single" and case.single is None:
                continue  # not every case has a baseline script (see docs/ROADMAP.md § 8)
            for rep in range(repeat):
                try:
                    final, events = await (_run_fleet(case) if pipeline == "fleet" else _run_single(case))
                    results = evaluate(case, final, events, pipeline)
                    outcomes.append(CaseRunOutcome(case.id, case.category, pipeline, rep, results))
                except Exception as exc:  # a harness bug must not stop the rest of the suite
                    outcomes.append(CaseRunOutcome(case.id, case.category, pipeline, rep, [], error=f"{type(exc).__name__}: {exc}"))
    return outcomes


def _to_summary_json(
    outcomes: list[CaseRunOutcome], summary: Summary, pipelines: list[str], repeat: int
) -> dict:
    """The subset of a run worth persisting for the Evaluation dashboard — real
    numbers only, nothing the frontend has to invent."""
    failures = []
    for o in outcomes:
        if o.error:
            failures.append(
                {"case_id": o.case_id, "category": o.category, "pipeline": o.pipeline,
                 "repeat_index": o.repeat_index, "check": "run_error", "detail": o.error}
            )
            continue
        for r in o.results:
            if not r.passed:
                failures.append(
                    {"case_id": o.case_id, "category": o.category, "pipeline": o.pipeline,
                     "repeat_index": o.repeat_index, "check": r.name, "detail": r.detail}
                )

    consistency = [
        {"case_id": case_id, "pipeline": pipeline, "rate": rate}
        for (case_id, pipeline), rate in sorted(summary.consistency.items())
    ]

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "pipelines": pipelines,
        "repeat": repeat,
        "cases_total": len(DATASET),
        "categories_total": len(BY_CATEGORY),
        "runs": {"total": summary.total_runs, "with_error": summary.runs_with_error},
        "checks": {"total": summary.total_checks, "passed": summary.passed_checks},
        "overall_pct": round(summary.passed_checks / summary.total_checks * 100, 1)
        if summary.total_checks
        else None,
        "by_category": summary.by_category,
        "by_check": summary.by_check,
        "by_pipeline": summary.by_pipeline,
        "consistency": consistency,
        "failures": failures,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="AgentX Ladder 6 evaluation harness")
    parser.add_argument("--pipeline", choices=["fleet", "single", "both"], default="fleet")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--category", default=None)
    parser.add_argument("--case", default=None, help="run only this case id")
    parser.add_argument(
        "--save", action="store_true", help="also write results/summary.json for the Evaluation dashboard"
    )
    args = parser.parse_args(argv)

    cases = DATASET
    if args.category:
        cases = [c for c in cases if c.category == args.category]
    if args.case:
        cases = [c for c in cases if c.id == args.case]
    if not cases:
        print("No cases matched the given filters.", file=sys.stderr)
        return 2

    pipelines = ["fleet", "single"] if args.pipeline == "both" else [args.pipeline]

    outcomes = asyncio.run(run_all(cases, pipelines, args.repeat))
    summary = summarize(outcomes)
    print(render(outcomes, summary))

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        payload = _to_summary_json(outcomes, summary, pipelines, args.repeat)
        (RESULTS_DIR / "summary.json").write_text(json.dumps(payload, indent=2))
        print(f"\nWrote {RESULTS_DIR / 'summary.json'}")

    return 0 if summary.passed_checks == summary.total_checks and summary.runs_with_error == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
