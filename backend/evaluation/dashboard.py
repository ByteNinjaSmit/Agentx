"""Read-only aggregation of whatever real evaluation artifacts exist on disk into
the shape the frontend Evaluation page renders. Every field is either a real
number read from a results/*.json|csv file this session (or a previous
`python -m evaluation.runner --save` / `python -m evaluation.full_benchmark`
/ `python -m evaluation.judge_runner`) produced, or `None` — nothing here is
computed to look complete. `evaluation/results/` is gitignored, so a fresh
checkout legitimately has none of these until the harness is run."""

import csv
import json
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _read_json(name: str):
    path = RESULTS_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _human_eval_progress():
    path = RESULTS_DIR / "human_eval_sheet.csv"
    if not path.exists():
        return None
    try:
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return None
    if not rows:
        return None
    scored = [r for r in rows if (r.get("overall") or "").strip()]
    return {"total_rows": len(rows), "scored_rows": len(scored)}


def _judge_summary(rows: list | None):
    """`llm_judge.json` is a list of per-case judge scores — average the
    dimensions that are present rather than assuming a fixed sample size, since
    a smoke test and a full judged run share the same file shape."""
    if not rows:
        return None
    dims = ["accuracy", "groundedness", "completeness", "evidence_quality", "uncertainty_handling", "overall"]
    n = len(rows)
    avgs = {}
    for d in dims:
        vals = [r[d] for r in rows if isinstance(r.get(d), (int, float))]
        avgs[d] = round(sum(vals) / len(vals), 3) if vals else None
    return {"cases_judged": n, "averages": avgs, "samples": rows[:20]}


def get_dashboard() -> dict:
    summary = _read_json("summary.json")
    benchmark = _read_json("benchmark.json")  # fault-injection before/after + diagnosis
    before_after = _read_json("before_after.json") or (
        {k: benchmark[k] for k in ("before", "after", "deltas") if k in benchmark} if benchmark else None
    )
    judge = _judge_summary(_read_json("llm_judge.json"))
    human_eval = _human_eval_progress()

    return {
        "benchmark": summary,
        "fault_injection": {
            "before_after": before_after,
            "diagnosis": benchmark.get("diagnosis") if benchmark else None,
            "action_applied": benchmark.get("action_applied") if benchmark else None,
            "improvement_pct": benchmark.get("improvement_pct") if benchmark else None,
        }
        if (before_after or benchmark)
        else None,
        "llm_judge": judge,
        "human_eval": human_eval,
    }
