"""Manual probe for evaluation/llm_judge.py + judge_runner.py against a real,
configured LLM provider — same convention as test_patents.py: reads backend/.env
directly (this script is run standalone, not through main.py's load_dotenv()), and
deliberately lives outside backend/tests/ so it is never picked up by
`python -m unittest discover` — the automated suite (tests/test_llm_judge.py) stays
fully offline, this script is the one place that spends real API budget.

Run with `python judge_smoke_test.py` (or `python judge_smoke_test.py --case
tool_failure-001 --pipeline both`). The AGENT run stays scripted/deterministic
(FakeProvider, no network) — only the judge call itself hits a real model.
"""

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from agent.providers import available_providers, get_provider

from evaluation.datasets import DATASET
from evaluation.judge_runner import _judge_one, render


async def main():
    if not available_providers():
        print("No GEMINI_API_KEY or ANTHROPIC_API_KEY configured in backend/.env — nothing to probe.")
        return 1

    case_id = None
    pipeline = "fleet"
    args = sys.argv[1:]
    if "--case" in args:
        case_id = args[args.index("--case") + 1]
    if "--pipeline" in args:
        pipeline = args[args.index("--pipeline") + 1]

    case = next((c for c in DATASET if c.id == case_id), DATASET[0]) if case_id else next(
        c for c in DATASET if c.category == "normal"
    )
    provider = get_provider()
    print(f"Judging {case.id!r} [{pipeline}] with provider={provider.name} model={provider.model}\n")

    pipelines = ["fleet", "single"] if pipeline == "both" else [pipeline]
    rows = []
    for p in pipelines:
        if p == "single" and case.single is None:
            print(f"({case.id} has no pipeline=single script — skipping)")
            continue
        rows.append(await _judge_one(case, p, provider))

    print(render(rows))
    return 0 if not any("error" in r for r in rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
