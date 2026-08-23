"""Manual demonstration of LangGraph-native durable checkpointing on the fleet
graph: run partway, interrupt (simulating a crash), reconnect with a fresh
compiled graph object and the same thread_id, and resume from the last completed
superstep instead of restarting from START.

Separate from agent/memory.py's save_progress()/run_log.trace column — that is the
application-level "what has this run found so far" snapshot the SSE UI and
GET /runs/{id} read; this is LangGraph's own graph-execution state (which node ran,
what FleetState looked like after each superstep), keyed by thread_id, owned by
LangGraph's AsyncPostgresSaver in its own tables on the same DATABASE_URL Postgres.

Needs a real, reachable Postgres — start the project's dev one with
`docker compose up -d db` from the repo root (see docker-compose.yml) — since
AsyncPostgresSaver.setup() creates its own checkpoint tables there. Same
manual-probe convention as test_patents.py/judge_smoke_test.py: reads backend/.env
directly, run standalone, not part of any automated test suite.

Run with `python checkpoint_demo.py`.
"""

import asyncio
import os
import sys
import time
import uuid
from contextlib import ExitStack

# psycopg's async mode (AsyncPostgresSaver, used below) cannot run under Windows'
# default ProactorEventLoop — only the Selector one. Standard, documented fix;
# scoped to this standalone script, not the FastAPI app (which doesn't use
# psycopg/checkpointing at all today).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv

load_dotenv()

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agent.fleet import FleetState, _build_graph
from evaluation.datasets import DATASET
from evaluation.fakes import FakeProvider, patches_for


def _initial_state(case) -> FleetState:
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


async def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set (see backend/.env) — nothing to demo against.", file=sys.stderr)
        return 2

    async def _connectivity_check():
        async with AsyncPostgresSaver.from_conn_string(database_url) as saver:
            await saver.setup()

    try:
        # A wrong host/port often hangs on TCP connect rather than refusing
        # outright — fail fast instead of blocking indefinitely.
        await asyncio.wait_for(_connectivity_check(), timeout=8)
    except Exception as exc:
        print(f"Could not reach/prepare Postgres at DATABASE_URL: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Start it with: docker compose up -d db   (from the repo root)", file=sys.stderr)
        return 2

    case = next(c for c in DATASET if c.category == "normal")
    provider = FakeProvider(case)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id, "provider": provider}}
    initial_state = _initial_state(case)

    print(f"Scenario: {case.id!r}  thread_id={thread_id}\n")

    with ExitStack() as stack:
        for p in patches_for(case):
            stack.enter_context(p)

        # ---- Run #1: interrupted after 2 completed supersteps ("crash") ----
        async with AsyncPostgresSaver.from_conn_string(database_url) as saver:
            graph = _build_graph(checkpointer=saver)
            supersteps_seen = 0
            async for mode, chunk in graph.astream(
                initial_state, config=config, stream_mode=["custom", "values"]
            ):
                if mode != "values":
                    continue
                supersteps_seen += 1
                print(f"  superstep {supersteps_seen} completed")
                if supersteps_seen >= 2:
                    print(f"[simulated crash] abandoning the stream after {supersteps_seen} supersteps\n")
                    break

            state_after_crash = await graph.aget_state(config)
            print(f"Checkpointed state after 'crash': next node(s) = {state_after_crash.next}")
            print(f"  kept items so far: {len(state_after_crash.values.get('kept', []))}")
            print(f"  strategy present: {bool(state_after_crash.values.get('strategy'))}\n")

            if not state_after_crash.next:
                print("Graph already completed before the intended interruption point — ", file=sys.stderr)
                print("nothing left to resume. Re-run; this can happen on a very fast scripted case.", file=sys.stderr)
                return 1

        # ---- Run #2: fresh graph object (simulating a process restart), same
        # thread_id, resumes from the last checkpoint instead of START ----
        async with AsyncPostgresSaver.from_conn_string(database_url) as saver:
            graph2 = _build_graph(checkpointer=saver)
            resumed_supersteps = 0
            final_values: dict = {}
            async for mode, chunk in graph2.astream(None, config=config, stream_mode=["custom", "values"]):
                if mode == "values":
                    resumed_supersteps += 1
                    final_values = chunk

            history = [c async for c in graph2.aget_state_history(config)]

            print(f"Resumed with a fresh graph object + same thread_id: {resumed_supersteps} more superstep(s) ran.")
            print(f"Checkpoint history depth for this thread: {len(history)}")
            print(f"Final strategy present: {bool(final_values.get('strategy'))}")
            print(f"Final kept items: {len(final_values.get('kept', []))}")
            print(f"Final coverage_score: {final_values.get('coverage_score')}")

    print("\nRESULT: execution resumed from persisted LangGraph state, not from START.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
