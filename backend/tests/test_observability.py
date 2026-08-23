"""Tests for backend/observability/ — the trace-diagnosis -> controlled-failure ->
optimization -> before/after closed loop. Stdlib `unittest` only, matching the
zero-extra-dependency evaluation harness (`evaluation/runner.py`) already in this
repo — no pytest is installed.

Run: cd backend && python -m unittest tests.test_observability -v
"""

import time
import unittest
from contextlib import ExitStack

import agent.tools as tools
from evaluation import fault_injection
from observability import optimizer, policy, root_cause
from observability.trace_analyzer import (
    Finding,
    analyze,
    detect_budget_pressure,
    detect_duplicate_tool_calls,
    detect_low_yield_tools,
    detect_replanning_overhead,
    detect_slow_tools,
    detect_tool_failures,
    detect_ungrounded_findings_rejected,
    detect_unreliable_primary_source,
)


def _obs(**kwargs) -> dict:
    base = {"tool": "search_papers", "query": "q", "ok": True, "count": 1, "latency_ms": 50, "fallback_used": None}
    base.update(kwargs)
    return base


def _trace(*observations: dict) -> list[dict]:
    return [{"step": 0, "agent": "researcher", "tools_called": [], "observations": list(observations)}]


class TestTraceAnalyzerDetectors(unittest.TestCase):
    def test_unreliable_primary_source_needs_majority_fallback(self):
        trace = _trace(
            _obs(fallback_used="crossref", latency_ms=2000),
            _obs(fallback_used="crossref", latency_ms=1800),
        )
        findings = detect_unreliable_primary_source(trace, {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "unreliable_primary_source")
        self.assertEqual(findings[0].target, "search_papers")
        self.assertEqual(findings[0].severity, "high")

    def test_unreliable_primary_source_absent_when_reliable(self):
        trace = _trace(_obs(fallback_used=None), _obs(fallback_used=None))
        self.assertEqual(detect_unreliable_primary_source(trace, {}), [])

    def test_slow_tool(self):
        trace = _trace(_obs(latency_ms=3000))
        findings = detect_slow_tools(trace, {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "slow_tool")

    def test_tool_failure(self):
        trace = _trace(_obs(ok=False, error="RateLimited: 429"))
        findings = detect_tool_failures(trace, {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "high")

    def test_duplicate_tool_call(self):
        trace = _trace(_obs(query="same"), _obs(query="same"))
        findings = detect_duplicate_tool_calls(trace, {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].metrics["count"], 2)

    def test_duplicate_tool_call_absent_for_distinct_queries(self):
        trace = _trace(_obs(query="a"), _obs(query="b"))
        self.assertEqual(detect_duplicate_tool_calls(trace, {}), [])

    def test_low_yield_tool(self):
        trace = _trace(_obs(count=0), _obs(count=0))
        findings = detect_low_yield_tools(trace, {})
        self.assertEqual(len(findings), 1)

    def test_replanning_overhead(self):
        final = {"self_evaluation": {"replanned": True, "replan_rationale": "thin coverage", "coverage_score": 0.6}}
        findings = detect_replanning_overhead([], final)
        self.assertEqual(len(findings), 1)
        self.assertIn("thin coverage", findings[0].evidence[0])

    def test_replanning_overhead_absent_when_not_replanned(self):
        self.assertEqual(detect_replanning_overhead([], {"self_evaluation": {"replanned": False}}), [])

    def test_ungrounded_findings_rejected(self):
        trace = [{"agent": "verifier", "rejected": [{"reason": "not found in any tool result"}]}]
        final = {"rejected_count": 1}
        findings = detect_ungrounded_findings_rejected(trace, final)
        self.assertEqual(len(findings), 1)
        self.assertIn("not found in any tool result", findings[0].evidence)

    def test_budget_pressure(self):
        final = {"resource_usage": {"tool_calls_used": 55, "tool_call_budget": 60, "elapsed_seconds": 10, "time_budget_seconds": 180}}
        findings = detect_budget_pressure([], final)
        self.assertEqual(len(findings), 1)

    def test_budget_pressure_absent_under_threshold(self):
        final = {"resource_usage": {"tool_calls_used": 5, "tool_call_budget": 60, "elapsed_seconds": 10, "time_budget_seconds": 180}}
        self.assertEqual(detect_budget_pressure([], final), [])

    def test_analyze_runs_every_detector(self):
        trace = _trace(_obs(fallback_used="crossref", latency_ms=2000), _obs(fallback_used="crossref", latency_ms=1900))
        findings = analyze(trace, {})
        categories = {f.category for f in findings}
        self.assertIn("unreliable_primary_source", categories)
        self.assertIn("slow_tool", categories)


class TestRootCause(unittest.TestCase):
    def test_ranks_by_severity_then_confidence(self):
        low = Finding(category="low_yield_tool", severity="low", evidence=["e"], confidence=0.9)
        high = Finding(category="unreliable_primary_source", severity="high", evidence=["e"], confidence=0.7, target="search_papers")
        ranked = root_cause.rank([low, high])
        self.assertEqual(ranked[0], high)

    def test_to_dict_shape_matches_no_findings(self):
        d = root_cause.to_dict([])
        self.assertEqual(d["root_cause"], "none")
        self.assertEqual(d["recommended_action"], "no_action")

    def test_to_dict_includes_optimizer_action(self):
        top = Finding(category="unreliable_primary_source", severity="high", evidence=["e"], confidence=0.9, target="search_papers")
        d = root_cause.to_dict([top])
        self.assertEqual(d["root_cause"], "unreliable_primary_source:search_papers")
        self.assertEqual(d["recommended_action"], "fallback_after_first_failure")
        self.assertEqual(d["action_detail"]["target"], "search_papers")


class TestOptimizer(unittest.TestCase):
    def test_unreliable_primary_source_maps_to_fallback_action(self):
        finding = Finding(category="unreliable_primary_source", severity="high", evidence=[], confidence=0.9, target="search_papers")
        action = optimizer.propose(finding)
        self.assertEqual(action.action, "fallback_after_first_failure")
        self.assertEqual(action.target, "search_papers")

    def test_unknown_category_maps_to_no_action(self):
        finding = Finding(category="tool_failure", severity="high", evidence=[], confidence=0.9, target="search_news")
        action = optimizer.propose(finding)
        self.assertEqual(action.action, "no_action")


class TestPolicy(unittest.TestCase):
    def tearDown(self):
        policy.reset()

    def test_apply_and_reset_roundtrip(self):
        finding = Finding(category="unreliable_primary_source", severity="high", evidence=[], confidence=0.9, target="search_papers")
        optimizer.propose(finding).apply()
        self.assertIn("search_papers", policy.CURRENT.circuit_open)
        policy.reset()
        self.assertEqual(policy.CURRENT.circuit_open, set())


class TestCircuitBreakerMechanism(unittest.IsolatedAsyncioTestCase):
    """The one production code hook (agent/tools.py::search_papers) actually
    behaves differently once the optimizer's action is applied — the core claim of
    the closed loop, proven directly against the real function rather than a
    synthetic trace."""

    async def asyncTearDown(self):
        policy.reset()

    async def test_open_circuit_skips_primary_and_its_latency_tax(self):
        policy.reset()
        fixture = {
            "alpha": [{"title": "A", "url": "https://x/a", "year": 2026, "citationCount": 1, "externalIds": {"DOI": "a"}}],
            "beta": [{"title": "B", "url": "https://x/b", "year": 2026, "citationCount": 1, "externalIds": {"DOI": "b"}}],
        }
        with ExitStack() as stack:
            for p in fault_injection.semantic_scholar_timeout(fixture):
                stack.enter_context(p)

            started = time.monotonic()
            result_before = await tools.search_papers("alpha", limit=3)
            elapsed_before = time.monotonic() - started
            self.assertGreaterEqual(elapsed_before, fault_injection.SEMANTIC_SCHOLAR_FAIL_DELAY_SECONDS)
            self.assertEqual(result_before[0]["title"], "A")

            finding = Finding(
                category="unreliable_primary_source", severity="high", evidence=["synthetic"], confidence=0.9, target="search_papers"
            )
            optimizer.propose(finding).apply()
            self.assertIn("search_papers", policy.CURRENT.circuit_open)

            started = time.monotonic()
            result_after = await tools.search_papers("beta", limit=3)
            elapsed_after = time.monotonic() - started
            self.assertLess(elapsed_after, fault_injection.SEMANTIC_SCHOLAR_FAIL_DELAY_SECONDS / 2)
            self.assertEqual(result_after[0]["title"], "B")


class TestFullBenchmarkEndToEnd(unittest.IsolatedAsyncioTestCase):
    """Runs the actual `python -m evaluation.full_benchmark` scenario against the
    real `agent.fleet` LangGraph pipeline (FakeProvider, no network/DB) and checks
    the before/after proof it produces holds: strictly cheaper, same findings."""

    async def asyncTearDown(self):
        policy.reset()

    async def test_before_after_shows_real_improvement_with_unchanged_findings(self):
        from evaluation.full_benchmark import main_async

        result = await main_async()

        self.assertTrue(result["action_applied"])
        self.assertEqual(result["diagnosis"]["category"], "unreliable_primary_source")
        self.assertGreater(result["deltas"]["elapsed_seconds"], 0)
        self.assertTrue(result["unchanged"]["items_count"])
        self.assertTrue(result["unchanged"]["coverage_ok"])
        self.assertEqual(result["before"]["items_count"], 2)


if __name__ == "__main__":
    unittest.main()
