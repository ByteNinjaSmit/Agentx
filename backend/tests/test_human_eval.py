"""Tests for backend/evaluation/human_eval.py. Stdlib `unittest` only. Fully
offline — `generate_rows` reuses the same FakeProvider-scripted `_run_fleet`/
`_run_single` the deterministic harness uses. Every rater score used here is
synthetic test fixture data, constructed only to check the aggregation math — never
to be mistaken for a real collected human rating (see
docs/HUMAN_EVAL_PROTOCOL.md and evaluation/results/human_eval_sheet.csv, which is
real and currently unscored).

Run: cd backend && python -m unittest tests.test_human_eval -v
"""

import csv
import io
import unittest

from evaluation.datasets import DATASET
from evaluation.human_eval import (
    FIELDNAMES,
    SCORE_COLUMNS,
    generate_rows,
    inter_rater_agreement,
    mean_scores,
    one_per_category,
    score,
)


class TestOnePerCategory(unittest.TestCase):
    def test_covers_every_category_exactly_once(self):
        sampled = one_per_category()
        categories = [c.category for c in sampled]
        self.assertEqual(len(categories), len(set(categories)))
        self.assertEqual(set(categories), {c.category for c in DATASET})


class TestGenerateRows(unittest.IsolatedAsyncioTestCase):
    async def test_rows_have_blank_score_columns_and_real_content(self):
        cases = one_per_category()
        rows = await generate_rows(cases)

        self.assertGreaterEqual(len(rows), len(cases))  # at least one row per case
        self.assertLessEqual(len(rows), len(cases) * 2)  # at most fleet+single per case

        for row in rows:
            self.assertEqual(set(row), set(FIELDNAMES))
            for col in SCORE_COLUMNS:
                self.assertEqual(row[col], "")
            self.assertEqual(row["rater_id"], "")
            self.assertTrue(row["task"])  # real goal text, not blank
            self.assertIn(row["pipeline"], ("fleet", "single"))

    async def test_single_pipeline_skipped_when_case_has_no_script(self):
        # every DATASET case is scripted for both pipelines today (ROADMAP.md § 8),
        # so this documents the fallback behavior via a synthetic case rather than
        # asserting on live dataset content that could change.
        from evaluation.datasets import Case

        no_single = Case(
            id="synthetic-no-single",
            category="normal",
            goal="g",
            context="c",
            planner={"sub_questions": [], "rationale": ""},
            lanes=[],
            analyst={"items": [], "coverage_ok": True, "coverage_gaps": [], "executive_summary": "s"},
            single=None,
        )
        rows = await generate_rows([no_single])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pipeline"], "fleet")


class TestScoring(unittest.TestCase):
    def _synthetic_rows(self) -> list[dict]:
        """Fabricated purely to exercise the aggregation math offline — not real
        human ratings. rater_a and rater_b score the same case+pipeline."""
        base = {col: "" for col in SCORE_COLUMNS}
        return [
            {"case_id": "normal-001", "pipeline": "fleet", "rater_id": "rater_a",
             **{**base, "accuracy": "5", "groundedness": "4", "overall": "4"}},
            {"case_id": "normal-001", "pipeline": "fleet", "rater_id": "rater_b",
             **{**base, "accuracy": "4", "groundedness": "4", "overall": "3"}},
            {"case_id": "tool_failure-001", "pipeline": "fleet", "rater_id": "rater_a",
             **{**base, "accuracy": "3", "groundedness": "3", "overall": "3"}},
            {"case_id": "blank-row", "pipeline": "fleet", "rater_id": "",
             **base},  # unscored — must be excluded entirely
        ]

    def test_mean_scores_ignores_blank_cells(self):
        rows = self._synthetic_rows()
        means = mean_scores(rows)
        self.assertAlmostEqual(means["accuracy"], (5 + 4 + 3) / 3)
        self.assertIsNone(means["completeness"])  # never filled in by any row

    def test_inter_rater_agreement_computes_pairwise_diff(self):
        rows = self._synthetic_rows()
        agreement = inter_rater_agreement(rows)
        # only normal-001/fleet has 2 raters -> exactly 1 pair; overall diff = |4-3| = 1
        self.assertEqual(agreement["pairs_compared"], 1)
        self.assertEqual(agreement["mean_absolute_difference"], 1.0)
        self.assertEqual(agreement["agreement_rate"], 1.0)  # within default threshold of 1.0

    def test_inter_rater_agreement_empty_when_no_shared_cases(self):
        rows = [
            {"case_id": "a", "pipeline": "fleet", "rater_id": "r1", "overall": "5"},
            {"case_id": "b", "pipeline": "fleet", "rater_id": "r2", "overall": "1"},
        ]
        agreement = inter_rater_agreement(rows)
        self.assertEqual(agreement["pairs_compared"], 0)
        self.assertIsNone(agreement["mean_absolute_difference"])

    def test_score_excludes_unrated_rows_from_rows_scored(self):
        rows = self._synthetic_rows()
        result = score(rows)
        self.assertEqual(result["rows_total"], 4)
        self.assertEqual(result["rows_scored"], 3)
        self.assertEqual(result["raters"], ["rater_a", "rater_b"])

    def test_csv_round_trip_via_dictwriter_reader(self):
        rows = self._synthetic_rows()
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        buf.seek(0)
        read_back = list(csv.DictReader(buf))
        self.assertEqual(len(read_back), len(rows))
        self.assertEqual(read_back[0]["rater_id"], "rater_a")


if __name__ == "__main__":
    unittest.main()
