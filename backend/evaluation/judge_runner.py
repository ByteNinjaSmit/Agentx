"""python -m evaluation.judge_runner

Second evaluator tier from docs/ROADMAP.md § 8: grades what the deterministic
evaluators.py checks can't (answer quality, groundedness, whether an `ambiguous`
case's stated assumption is actually *reasonable*) using a real LLM as judge.

The AGENT run stays exactly as deterministic as evaluation.runner's — same
FakeProvider-scripted cases (`_run_fleet`/`_run_single`, reused from `runner.py`),
no network, no live model. Only the JUDGE call is live, so this needs a real
provider/API key (`GET /providers` in main.py lists what's configured; pass
--provider to pick one explicitly).

Default sample is one case per category (cheap, still exercises every category);
--case/--category/--all widen it.
"""

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

from agent.providers import available_providers, get_provider

from .datasets import DATASET, Case
from .llm_judge import JudgeResult, judge
from .runner import _run_fleet, _run_single

RESULTS_DIR = Path(__file__).resolve().parent / "results"

_REPORT_FIELDS = (
    "accuracy",
    "groundedness",
    "completeness",
    "evidence_quality",
    "uncertainty_handling",
    "unsupported_claims",
    "overall",
    "parse_ok",
)


def _one_per_category(cases: list[Case]) -> list[Case]:
    seen: set[str] = set()
    out = []
    for c in cases:
        if c.category in seen:
            continue
        seen.add(c.category)
        out.append(c)
    return out


async def _judge_one(case: Case, pipeline: str, provider) -> dict:
    final, _events = await (_run_fleet(case) if pipeline == "fleet" else _run_single(case))
    result: JudgeResult = await judge(case.goal, case.context, final, provider)
    return {
        "case_id": case.id,
        "category": case.category,
        "pipeline": pipeline,
        **{field: getattr(result, field) for field in _REPORT_FIELDS},
        "reason": result.reason,
    }


async def run_all(cases: list[Case], pipelines: list[str], provider) -> list[dict]:
    rows = []
    for case in cases:
        for pipeline in pipelines:
            if pipeline == "single" and case.single is None:
                continue  # not every case has a baseline script — same rule as runner.py
            try:
                rows.append(await _judge_one(case, pipeline, provider))
            except Exception as exc:  # a judge-call failure must not stop the rest of the sample
                rows.append(
                    {"case_id": case.id, "category": case.category, "pipeline": pipeline, "error": f"{type(exc).__name__}: {exc}"}
                )
    return rows


def _mean(rows: list[dict], field: str) -> float | None:
    vals = [r[field] for r in rows if isinstance(r.get(field), (int, float)) and not isinstance(r.get(field), bool)]
    return round(statistics.mean(vals), 3) if vals else None


def render(rows: list[dict]) -> str:
    ok_rows = [r for r in rows if "error" not in r]
    err_rows = [r for r in rows if "error" in r]

    lines = ["=" * 78, "AgentX LLM-judge report", "=" * 78]
    lines.append(f"Graded: {len(ok_rows)}  |  Errors: {len(err_rows)}")
    lines.append("")
    lines.append("Mean scores:")
    for field in ("accuracy", "groundedness", "completeness", "evidence_quality", "uncertainty_handling", "overall"):
        lines.append(f"  {field:<20} {_mean(ok_rows, field)}")
    lines.append(f"  {'unsupported_claims':<20} {_mean(ok_rows, 'unsupported_claims')} (mean count, lower is better)")
    lines.append("")

    lines.append("Per case:")
    for r in ok_rows:
        flag = "" if r["parse_ok"] else "  [UNPARSEABLE JUDGE RESPONSE — scored 0]"
        lines.append(
            f"  {r['case_id']:<28} [{r['pipeline']:<6}] overall={r['overall']:<5} "
            f"unsupported_claims={r['unsupported_claims']}{flag}"
        )
        lines.append(f"      {r['reason'][:140]}")

    if err_rows:
        lines.append("")
        lines.append("Errors:")
        for r in err_rows:
            lines.append(f"  FAIL {r['case_id']} [{r['pipeline']}]: {r['error']}")

    lines.append("=" * 78)
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AgentX LLM-as-judge evaluation")
    parser.add_argument("--pipeline", choices=["fleet", "single", "both"], default="fleet")
    parser.add_argument("--provider", default=None, help="anthropic|gemini; default is this deployment's configured default")
    parser.add_argument("--category", default=None)
    parser.add_argument("--case", default=None, help="run only this case id")
    parser.add_argument("--all", action="store_true", help="grade every matching case, not just one per category")
    args = parser.parse_args(argv)

    # Loaded here, not at module import time: this module is also imported for its
    # helpers by tests/test_llm_judge.py, and loading .env as an import side effect
    # would make an "offline" test run silently start making real, billed judge
    # calls on any machine that happens to have backend/.env configured. Run
    # standalone (`python -m evaluation.judge_runner`), not imported by main.py, so
    # — unlike runner.py, which needs no API key at all — this has to load it itself
    # to pick up GEMINI_API_KEY/ANTHROPIC_API_KEY, same as test_patents.py does.
    from dotenv import load_dotenv

    load_dotenv()

    if not available_providers():
        print(
            "No LLM provider configured (need GEMINI_API_KEY or ANTHROPIC_API_KEY) — "
            "the judge call itself needs a real model. See .env.example.",
            file=sys.stderr,
        )
        return 2
    try:
        provider = get_provider(args.provider)
    except Exception as exc:
        print(f"Could not construct provider {args.provider!r}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    cases = DATASET
    if args.category:
        cases = [c for c in cases if c.category == args.category]
    if args.case:
        cases = [c for c in cases if c.id == args.case]
    if not args.case and not args.all:
        cases = _one_per_category(cases)
    if not cases:
        print("No cases matched the given filters.", file=sys.stderr)
        return 2

    pipelines = ["fleet", "single"] if args.pipeline == "both" else [args.pipeline]

    rows = asyncio.run(run_all(cases, pipelines, provider))
    print(render(rows))

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "llm_judge.json").write_text(json.dumps(rows, indent=2, default=str))

    return 0 if not any("error" in r for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
