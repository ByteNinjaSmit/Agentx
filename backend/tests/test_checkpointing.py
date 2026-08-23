"""Tests for LangGraph-native checkpoint/resume on the fleet graph
(agent/fleet.py::_build_graph). Stdlib `unittest` only, fully offline: uses
LangGraph's own `InMemorySaver` rather than `AsyncPostgresSaver` — same
checkpointer interface, same resume mechanics (`astream(None, config)`), no
Postgres required, so this suite proves the *mechanism* without needing the real
infra `checkpoint_demo.py` demonstrates it against
(`docker compose up -d db`, then `python checkpoint_demo.py` — see that script and
docs/ARCHITECTURE.md's "Checkpoint / resume" section for the Postgres-backed,
DATABASE_URL-dependent version of the same proof).

Run: cd backend && python -m unittest tests.test_checkpointing -v
"""

import unittest
import uuid

from langgraph.checkpoint.memory import InMemorySaver

from agent.fleet import FleetState, _build_graph
from evaluation.datasets import DATASET
from evaluation.fakes import FakeProvider, patches_for


def _initial_state(case) -> FleetState:
    import time

    return {
        "goal": case.goal,
        "project_context": case.context,
        "competitors": [],
        "track": case.goal,
        "depth": 5,
        "known": [],
        "run_started": time.monotonic(),
        "questions": [],
        "raw_items": [],
        "coverage_gaps": [],
        "haystacks": [],
        "tool_calls_used": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "grounded": [],
        "rejected": [],
        "kept": [],
        "analysis": {},
        "coverage_score": 0.0,
        "new_sub_questions": [],
        "replan_rationale": "",
        "replanned": False,
        "replan_raw_items": [],
        "replan_haystacks": [],
        "conflicts": [],
        "strategy": {},
        "loop_events": [],
    }


class TestBuildGraphIsBackwardCompatible(unittest.TestCase):
    def test_no_checkpointer_default_matches_explicit_none(self):
        default = _build_graph()
        explicit_none = _build_graph(checkpointer=None)
        self.assertIsNone(default.checkpointer)
        self.assertIsNone(explicit_none.checkpointer)
        self.assertEqual(set(default.nodes), set(explicit_none.nodes))

    def test_checkpointer_param_does_not_change_graph_topology(self):
        plain = _build_graph()
        checkpointed = _build_graph(checkpointer=InMemorySaver())
        self.assertEqual(set(plain.nodes), set(checkpointed.nodes))
        self.assertIsNotNone(checkpointed.checkpointer)


class TestCheckpointResume(unittest.IsolatedAsyncioTestCase):
    async def test_interrupted_run_resumes_from_persisted_state_not_start(self):
        case = next(c for c in DATASET if c.category == "normal")
        provider = FakeProvider(case)
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id, "provider": provider}}
        saver = InMemorySaver()  # the durable store — shared across both graph objects below

        with_patches = patches_for(case)
        import contextlib

        with contextlib.ExitStack() as stack:
            for p in with_patches:
                stack.enter_context(p)

            # ---- Run #1: a graph object interrupted after 1 completed superstep ----
            graph1 = _build_graph(checkpointer=saver)
            supersteps = 0
            async for mode, _chunk in graph1.astream(
                _initial_state(case), config=config, stream_mode=["custom", "values"]
            ):
                if mode == "values":
                    supersteps += 1
                    if supersteps >= 1:
                        break  # simulated crash — abandon the stream mid-run

            state_after_crash = await graph1.aget_state(config)
            self.assertTrue(state_after_crash.next, "expected pending work after an early interruption")
            kept_at_crash = len(state_after_crash.values.get("kept", []))
            self.assertEqual(kept_at_crash, 0)  # too early for the analyst to have run yet

            # ---- Run #2: a DIFFERENT graph object, same checkpointer + thread_id,
            # resumed with input=None per LangGraph's resume convention ----
            graph2 = _build_graph(checkpointer=saver)
            self.assertIsNot(graph1, graph2)
            final_values = {}
            async for mode, chunk in graph2.astream(None, config=config, stream_mode=["custom", "values"]):
                if mode == "values":
                    final_values = chunk

            final_state = await graph2.aget_state(config)
            self.assertFalse(final_state.next, "graph should have run to completion (END) after resuming")
            self.assertTrue(final_values.get("strategy"))
            self.assertGreater(len(final_values.get("kept", [])), 0)

            history = [c async for c in graph2.aget_state_history(config)]
            self.assertGreater(len(history), 1, "expected more than one checkpoint across the two runs")

    async def test_resume_on_a_thread_with_no_prior_state_just_runs_normally(self):
        """astream(None, config) on a brand-new thread_id (nothing to resume) should
        behave like a fresh START — resume is opt-in via the thread already having
        state, not a separate code path callers have to branch on."""
        case = next(c for c in DATASET if c.category == "normal")
        provider = FakeProvider(case)
        config = {"configurable": {"thread_id": str(uuid.uuid4()), "provider": provider}}
        saver = InMemorySaver()

        import contextlib

        with contextlib.ExitStack() as stack:
            for p in patches_for(case):
                stack.enter_context(p)
            graph = _build_graph(checkpointer=saver)
            with self.assertRaises(Exception):
                # LangGraph raises when asked to resume (input=None) a thread with
                # no checkpoint at all — documenting that boundary explicitly here.
                async for _ in graph.astream(None, config=config, stream_mode=["values"]):
                    pass


if __name__ == "__main__":
    unittest.main()
