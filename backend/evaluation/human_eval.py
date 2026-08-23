"""Human-evaluation protocol tooling — the third evaluator tier from
docs/ROADMAP.md § 8 (deterministic/code, LLM judge, human), for the one thing
neither of the first two fully substitutes for: whether a strategic recommendation
actually reads as *useful* to a person who would act on it.

This module only ever prepares a rating sheet and scores one that has actually been
filled in — it never fabricates rater scores itself. `python -m evaluation.human_eval
--generate` writes evaluation/results/human_eval_sheet.csv with one row per
(case, pipeline), every scoring column blank, ready for a human rater to open in a
spreadsheet. `python -m evaluation.human_eval --score PATH` reads a filled-in copy
back and computes mean scores and inter-rater agreement — but only once real scores
exist; do not claim human evaluation is "done" from an unscored sheet.

See docs/HUMAN_EVAL_PROTOCOL.md for the rubric and rater instructions.
"""

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

from .datasets import DATASET, Case
from .runner import _run_fleet, _run_single

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_SHEET_PATH = RESULTS_DIR / "human_eval_sheet.csv"

# 1-5 per dimension, per docs/HUMAN_EVAL_PROTOCOL.md's rubric.
SCORE_COLUMNS = (
    "accuracy",
    "groundedness",
    "completeness",
    "evidence_quality",
    "useful_recommendation",
    "uncertainty_handling",
    "overall",
)

FIELDNAMES = (
    "case_id",
    "category",
    "pipeline",
    "task",
    "context",
    "answer",
    "evidence",
    "coverage_ok",
    "coverage_gaps",
    "rater_id",
    *SCORE_COLUMNS,
    "notes",
)


def one_per_category(cases: list[Case] = DATASET) -> list[Case]:
    seen: set[str] = set()
    out = []
    for c in cases:
        if c.category in seen:
            continue
        seen.add(c.category)
        out.append(c)
    return out


def _evidence_summary(final: dict) -> str:
    return json.dumps(
        [
            {
                "title": it.get("title"),
                "source": it.get("source"),
                "organization": it.get("organization"),
                "url": it.get("url"),
            }
            for it in final.get("items", [])
        ],
        default=str,
    )


async def _row_for(case: Case, pipeline: str) -> dict:
    final, _events = await (_run_fleet(case) if pipeline == "fleet" else _run_single(case))
    row = {
        "case_id": case.id,
        "category": case.category,
        "pipeline": pipeline,
        "task": case.goal,
        "context": case.context,
        "answer": final.get("executive_summary", ""),
        "evidence": _evidence_summary(final),
        "coverage_ok": final.get("coverage_ok"),
        "coverage_gaps": " | ".join(final.get("coverage_gaps") or []),
        "rater_id": "",
        "notes": "",
    }
    row.update({field: "" for field in SCORE_COLUMNS})
    return row


async def generate_rows(cases: list[Case], pipelines: tuple[str, ...] = ("fleet", "single")) -> list[dict]:
    rows = []
    for case in cases:
        for pipeline in pipelines:
            if pipeline == "single" and case.single is None:
                continue
            rows.append(await _row_for(case, pipeline))
    return rows


def write_sheet(rows: list[dict], path: Path = DEFAULT_SHEET_PATH) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def read_sheet(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def mean_scores(rows: list[dict]) -> dict:
    out = {}
    for col in SCORE_COLUMNS:
        vals = [v for v in (_to_float(r.get(col)) for r in rows) if v is not None]
        out[col] = round(statistics.mean(vals), 2) if vals else None
    return out


def inter_rater_agreement(rows: list[dict], within: float = 1.0) -> dict:
    """Groups scored rows by (case_id, pipeline); for any group rated by >= 2
    distinct raters, compares every rater pair's "overall" score. Reports mean
    absolute difference (lower = more agreement) and the fraction of pairs within
    `within` points on the 1-5 scale — simple, transparent, no extra dependency
    (no scipy/statsmodels for e.g. Cohen's kappa)."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        rater = (r.get("rater_id") or "").strip()
        overall = _to_float(r.get("overall"))
        if not rater or overall is None:
            continue
        groups.setdefault((r["case_id"], r["pipeline"]), []).append({"rater_id": rater, "overall": overall})

    diffs = []
    for entries in groups.values():
        by_rater = {e["rater_id"]: e["overall"] for e in entries}  # last write wins per rater
        raters = list(by_rater)
        for i in range(len(raters)):
            for j in range(i + 1, len(raters)):
                diffs.append(abs(by_rater[raters[i]] - by_rater[raters[j]]))

    if not diffs:
        return {"pairs_compared": 0, "mean_absolute_difference": None, "agreement_rate": None}
    return {
        "pairs_compared": len(diffs),
        "mean_absolute_difference": round(statistics.mean(diffs), 2),
        "agreement_rate": round(sum(1 for d in diffs if d <= within) / len(diffs), 2),
    }


def score(rows: list[dict]) -> dict:
    scored_rows = [r for r in rows if (r.get("rater_id") or "").strip()]
    return {
        "rows_total": len(rows),
        "rows_scored": len(scored_rows),
        "raters": sorted({r["rater_id"].strip() for r in scored_rows if r.get("rater_id")}),
        "mean_scores": mean_scores(scored_rows),
        "inter_rater_agreement": inter_rater_agreement(scored_rows),
    }


async def _generate(path: Path) -> int:
    cases = one_per_category()
    rows = await generate_rows(cases)
    write_sheet(rows, path)
    print(f"Wrote {len(rows)} row(s) across {len(cases)} case(s)/7 categories to {path}")
    print("All scoring columns are blank — see docs/HUMAN_EVAL_PROTOCOL.md before rating.")
    return 0


def _score(path: Path) -> int:
    if not path.exists():
        print(f"{path} does not exist. Run --generate first, or pass --score to a filled-in copy.", file=sys.stderr)
        return 2
    rows = read_sheet(path)
    result = score(rows)
    print(json.dumps(result, indent=2))
    if result["rows_scored"] == 0:
        print(
            "\nNo scored rows found (every 'rater_id' cell is blank) — this is the "
            "protocol/tooling working, not a completed human evaluation. See "
            "docs/HUMAN_EVAL_PROTOCOL.md.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AgentX human-evaluation sheet generator/scorer")
    parser.add_argument("--generate", action="store_true", help="write a fresh, unscored rating sheet")
    parser.add_argument("--score", metavar="PATH", help="score a filled-in sheet")
    parser.add_argument("--path", default=str(DEFAULT_SHEET_PATH), help="sheet path for --generate")
    args = parser.parse_args(argv)

    if args.score:
        return _score(Path(args.score))
    if args.generate:
        import asyncio

        return asyncio.run(_generate(Path(args.path)))

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
