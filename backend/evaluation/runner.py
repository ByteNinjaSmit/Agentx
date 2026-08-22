"""CLI entry point for the Ladder 6 evaluation harness.

    cd backend
    python -m evaluation.runner                       # all cases, pipeline=fleet, 1 rep
    python -m evaluation.runner --pipeline both        # also runs pipeline=single where scripted
    python -m evaluation.runner --repeat 3             # repeat each case 3x, report consistency
    python -m evaluation.runner --category tool_failure
    python -m evaluation.runner --case normal-001

No network access, no API keys, and no Postgres are used or required — see
`evaluation/fakes.py` for what is faked and why.
"""

import argparse
import asyncio
import contextlib
import sys

from .datasets import DATASET, Case
from .evaluators import evaluate
from .fakes import FakeProvider, patches_for
from .metrics import CaseRunOutcome, summarize
from .report import render


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
                    results = evaluate(case, final, events)
                    outcomes.append(CaseRunOutcome(case.id, case.category, pipeline, rep, results))
                except Exception as exc:  # a harness bug must not stop the rest of the suite
                    outcomes.append(CaseRunOutcome(case.id, case.category, pipeline, rep, [], error=f"{type(exc).__name__}: {exc}"))
    return outcomes


def main(argv=None):
    parser = argparse.ArgumentParser(description="AgentX Ladder 6 evaluation harness")
    parser.add_argument("--pipeline", choices=["fleet", "single", "both"], default="fleet")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--category", default=None)
    parser.add_argument("--case", default=None, help="run only this case id")
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
    return 0 if summary.passed_checks == summary.total_checks and summary.runs_with_error == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
