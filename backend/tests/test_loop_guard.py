"""Tests for backend/agent/loop_guard.py and its wiring into fleet.py/
orchestrator.py. Stdlib `unittest` only (repo convention).

Run: cd backend && python -m unittest tests.test_loop_guard -v
"""

import unittest

from agent.loop_guard import LoopGuard, call_signature
from evaluation.datasets import Case, ResearchLane
from evaluation.runner import _run_fleet, _run_single


class TestLoopGuardMechanics(unittest.TestCase):
    def test_first_call_never_blocked(self):
        guard = LoopGuard()
        self.assertIsNone(guard.should_block("search_papers", {"query": "q"}))

    def test_repeat_with_identical_result_is_blocked(self):
        guard = LoopGuard()
        guard.record("search_papers", {"query": "q"}, [{"title": "same"}])
        self.assertIsNone(guard.should_block("search_papers", {"query": "q"}))  # 1st repeat still allowed
        guard.record("search_papers", {"query": "q"}, [{"title": "same"}])  # identical result again
        reason = guard.should_block("search_papers", {"query": "q"})
        self.assertIsNotNone(reason)
        self.assertIn("search_papers", reason)

    def test_repeat_with_new_evidence_is_not_blocked(self):
        guard = LoopGuard()
        guard.record("search_papers", {"query": "q"}, [{"title": "first"}])
        guard.record("search_papers", {"query": "q"}, [{"title": "second, genuinely new"}])
        self.assertIsNone(guard.should_block("search_papers", {"query": "q"}))

    def test_different_query_is_never_conflated(self):
        guard = LoopGuard()
        guard.record("search_papers", {"query": "a"}, [{"title": "x"}])
        guard.record("search_papers", {"query": "a"}, [{"title": "x"}])
        self.assertIsNone(guard.should_block("search_papers", {"query": "b"}))

    def test_normalizes_whitespace_and_case_in_query(self):
        self.assertEqual(
            call_signature("search_papers", {"query": "  Quantum   Error  "}),
            call_signature("search_papers", {"query": "quantum error"}),
        )

    def test_loop_events_recorded_on_block(self):
        guard = LoopGuard()
        guard.record("search_papers", {"query": "q"}, [])
        guard.record("search_papers", {"query": "q"}, [])
        guard.should_block("search_papers", {"query": "q"})
        self.assertEqual(len(guard.loop_events), 1)
        self.assertEqual(guard.loop_events[0]["tool"], "search_papers")


_DUP_QUESTION = "What has org X published?"

_DUP_LANE = ResearchLane(
    question=_DUP_QUESTION,
    tool_calls=[
        {"name": "search_papers", "args": {"query": "duplicate query"}},
        {"name": "search_papers", "args": {"query": "duplicate query"}},
    ],
    tool_results={
        "search_papers": [
            {
                "title": "One Real Paper",
                "url": "https://example.org/paper",
                "year": 2026,
                "citationCount": 3,
                "externalIds": {"DOI": "10.1/one"},
            }
        ]
    },
    items=[
        {
            "source": "research",
            "external_id": "https://example.org/paper",
            "title": "One Real Paper",
            "url": "https://example.org/paper",
            "summary": "A real paper.",
            "date": "2026-01-01",
            "engagement": 3,
            "organization": "",
        }
    ],
)

DUP_CASE = Case(
    id="loop-guard-dup-001",
    category="normal",
    goal="find publications from org X",
    context="test context",
    planner={
        "sub_questions": [{"question": _DUP_QUESTION, "sources": ["papers"], "why": "test"}],
        "rationale": "single lane",
    },
    lanes=[_DUP_LANE],
    analyst={
        "items": [
            {
                "external_id": "https://example.org/paper",
                "relevance_reason": "on-topic",
                "organization": "",
                "keep": True,
            }
        ],
        "coverage_ok": True,
        "coverage_gaps": [],
        "executive_summary": "Found one real paper.",
    },
    single={
        "tool_calls": _DUP_LANE.tool_calls,
        "tool_results": _DUP_LANE.tool_results,
        "items": _DUP_LANE.items,
        "coverage_ok": True,
        "coverage_gaps": [],
        "executive_summary": "Found one real paper.",
    },
)


class TestLoopGuardIntegration(unittest.IsolatedAsyncioTestCase):
    """A lane/single-loop script that issues the identical (tool, query) call
    twice in the same turn — the fake tool map necessarily returns the identical
    payload both times, so this always trips the intra-batch dedup path (the
    cheapest, always-safe case: two identical calls in one response can never be
    useful, the second is decided before either executes)."""

    async def test_fleet_blocks_duplicate_call_in_same_turn(self):
        final, events = await _run_fleet(DUP_CASE)

        self.assertEqual(len(final.get("items", [])), 1)
        loop_events = final.get("loop_events", [])
        self.assertEqual(len(loop_events), 1)
        self.assertEqual(loop_events[0]["tool"], "search_papers")

        runtime_thoughts = [
            e.get("thought", "")
            for e in events
            if e.get("type") == "trace" and e.get("agent") == "runtime"
        ]
        self.assertTrue(any("Loop guard" in t for t in runtime_thoughts))

    async def test_single_pipeline_blocks_duplicate_call_in_same_turn(self):
        final, events = await _run_single(DUP_CASE)

        self.assertEqual(len(final.get("items", [])), 1)
        loop_events = final.get("loop_events", [])
        self.assertEqual(len(loop_events), 1)

        observation_events = [e for e in events if e.get("type") == "observation"]
        blocked = [
            obs
            for e in observation_events
            for obs in e.get("results", [])
            if obs.get("loop_blocked")
        ]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["tool"], "search_papers")


if __name__ == "__main__":
    unittest.main()
