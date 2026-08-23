"""Tests for backend/evaluation/llm_judge.py and judge_runner.py. Stdlib `unittest`
only (repo convention — no pytest installed). Fully offline — a fake judge provider
stands in for the real LLM call, so this file never needs an API key and never
makes a real request. For a real, billed, end-to-end proof against a live model,
see `backend/judge_smoke_test.py` (a manual probe, same convention as
`backend/test_patents.py` — deliberately outside `tests/` so it is never picked up
by `python -m unittest discover`).

Run: cd backend && python -m unittest tests.test_llm_judge -v
"""

import json
import unittest

from agent.providers.base import Turn
from evaluation.datasets import DATASET
from evaluation.llm_judge import build_prompt, judge, parse_judge_response
from evaluation.judge_runner import _mean, _one_per_category, render


class _FakeJudgeProvider:
    """Minimal LLMProvider stub — only `complete()` is exercised by `judge()`."""

    name = "fake-judge"
    model = "fake-judge-model"

    def __init__(self, response_text: str):
        self._response_text = response_text
        self.last_system = None
        self.last_prompt = None

    def start(self, system, tools=None):
        raise NotImplementedError("judge() never opens a tool-using conversation")

    async def complete(self, system: str, prompt: str) -> Turn:
        self.last_system = system
        self.last_prompt = prompt
        return Turn(text=self._response_text, calls=[], input_tokens=10, output_tokens=10)

    async def embed(self, texts, dim):
        raise NotImplementedError


_GOOD_RESPONSE = json.dumps(
    {
        "accuracy": 0.9,
        "groundedness": 0.85,
        "completeness": 0.7,
        "evidence_quality": 0.8,
        "uncertainty_handling": 1.0,
        "unsupported_claims": 0,
        "overall": 0.85,
        "reason": "Claims trace cleanly to the two kept findings; no unsupported assertions.",
    }
)

_OUT_OF_RANGE_RESPONSE = json.dumps(
    {
        "accuracy": 1.5,
        "groundedness": -0.2,
        "completeness": 0.5,
        "evidence_quality": 0.5,
        "uncertainty_handling": 0.5,
        "unsupported_claims": 2.0,
        "overall": 0.5,
        "reason": "ok",
    }
)

_SAMPLE_FINAL = {
    "items": [
        {
            "title": "Scalable Surface-Code Error Correction on Superconducting Qubits",
            "source": "research",
            "organization": "",
            "summary": "Surface-code error correction demonstrated on superconducting hardware.",
            "relevance_reason": "Directly on-topic hardware progress.",
            "impact_1_10": 7.2,
        }
    ],
    "coverage_gaps": [],
    "executive_summary": "One directly relevant paper found on surface-code error correction hardware.",
    "coverage_ok": True,
}


class TestParseJudgeResponse(unittest.TestCase):
    def test_parses_valid_json(self):
        result = parse_judge_response(_GOOD_RESPONSE)
        self.assertTrue(result.parse_ok)
        self.assertEqual(result.accuracy, 0.9)
        self.assertEqual(result.unsupported_claims, 0)
        self.assertIn("trace cleanly", result.reason)

    def test_clamps_out_of_range_scores(self):
        result = parse_judge_response(_OUT_OF_RANGE_RESPONSE)
        self.assertTrue(result.parse_ok)
        self.assertEqual(result.accuracy, 1.0)  # 1.5 clamped down
        self.assertEqual(result.groundedness, 0.0)  # -0.2 clamped up
        self.assertEqual(result.unsupported_claims, 2)  # float coerced to int

    def test_handles_unparseable_response(self):
        result = parse_judge_response("The answer looks pretty good overall, I'd say.")
        self.assertFalse(result.parse_ok)
        self.assertEqual(result.overall, 0.0)
        self.assertEqual(result.accuracy, 0)

    def test_tolerates_prose_wrapped_json(self):
        wrapped = f"Sure, here's my grading:\n```json\n{_GOOD_RESPONSE}\n```\nHope that helps!"
        result = parse_judge_response(wrapped)
        self.assertTrue(result.parse_ok)
        self.assertEqual(result.accuracy, 0.9)


class TestBuildPrompt(unittest.TestCase):
    def test_separates_goal_evidence_and_candidate_answer(self):
        prompt = build_prompt("find quantum error correction progress", "context here", _SAMPLE_FINAL)
        self.assertIn("USER GOAL:\nfind quantum error correction progress", prompt)
        self.assertIn("Scalable Surface-Code Error Correction", prompt)
        self.assertIn("CANDIDATE ANSWER (executive summary — grade this):", prompt)
        candidate_section = prompt.split("CANDIDATE ANSWER (executive summary — grade this):\n")[1]
        self.assertIn(_SAMPLE_FINAL["executive_summary"], candidate_section)

    def test_includes_reference_only_when_given(self):
        without_ref = build_prompt("g", "c", _SAMPLE_FINAL)
        self.assertNotIn("REFERENCE ANSWER", without_ref)
        with_ref = build_prompt("g", "c", _SAMPLE_FINAL, reference="a strong answer covers X and Y")
        self.assertIn("REFERENCE ANSWER", with_ref)
        self.assertIn("a strong answer covers X and Y", with_ref)

    def test_includes_strategy_when_present(self):
        final = {**_SAMPLE_FINAL, "strategy": {"competitors": [{"organization": "Acme"}]}}
        prompt = build_prompt("g", "c", final)
        self.assertIn("CANDIDATE STRATEGY", prompt)
        self.assertIn("Acme", prompt)


class TestJudgeAsync(unittest.IsolatedAsyncioTestCase):
    async def test_judge_calls_provider_and_returns_parsed_result(self):
        provider = _FakeJudgeProvider(_GOOD_RESPONSE)
        result = await judge("goal", "context", _SAMPLE_FINAL, provider)
        self.assertTrue(result.parse_ok)
        self.assertEqual(result.overall, 0.85)
        self.assertIn("goal", provider.last_prompt.lower())
        self.assertIn("CANDIDATE ANSWER", provider.last_prompt)
        self.assertIn("evaluator", provider.last_system.lower())

    async def test_judge_survives_a_bad_response(self):
        provider = _FakeJudgeProvider("not json at all")
        result = await judge("goal", "context", _SAMPLE_FINAL, provider)
        self.assertFalse(result.parse_ok)


class TestJudgeRunnerHelpers(unittest.TestCase):
    def test_one_per_category_covers_every_category_exactly_once(self):
        sampled = _one_per_category(DATASET)
        categories = [c.category for c in sampled]
        self.assertEqual(len(categories), len(set(categories)))
        self.assertEqual(set(categories), {c.category for c in DATASET})

    def test_mean_ignores_missing_and_non_numeric_fields(self):
        rows = [{"overall": 0.8}, {"overall": 0.6}, {"other": 1}]
        self.assertAlmostEqual(_mean(rows, "overall"), 0.7)

    def test_mean_returns_none_when_no_values(self):
        self.assertIsNone(_mean([], "overall"))

    def test_mean_excludes_bool_typed_fields(self):
        rows = [{"parse_ok": True}, {"parse_ok": False}]
        self.assertIsNone(_mean(rows, "parse_ok"))

    def test_render_handles_mixed_ok_and_error_rows(self):
        rows = [
            {
                "case_id": "normal-001",
                "pipeline": "fleet",
                "category": "normal",
                "accuracy": 0.9,
                "groundedness": 0.9,
                "completeness": 0.8,
                "evidence_quality": 0.8,
                "uncertainty_handling": 1.0,
                "unsupported_claims": 0,
                "overall": 0.88,
                "parse_ok": True,
                "reason": "fine",
            },
            {"case_id": "broken-001", "pipeline": "fleet", "category": "normal", "error": "TimeoutError: boom"},
        ]
        text = render(rows)
        self.assertIn("normal-001", text)
        self.assertIn("FAIL broken-001", text)
        self.assertIn("Graded: 1", text)
        self.assertIn("Errors: 1", text)


if __name__ == "__main__":
    unittest.main()
