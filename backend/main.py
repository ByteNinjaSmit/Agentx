import json
import logging

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from fastapi import HTTPException

from agent.orchestrator import run_agent_stream
from agent.memory import list_runs, get_run

log = logging.getLogger("compintel")

app = FastAPI(title="CompIntel Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/run")
async def run(goal: str, context: str):
    """Streams the agent's events as they happen. This used to await the whole run
    and only then replay the finished trace into the stream, which made the live
    trace view a re-enactment rather than a live feed."""

    async def gen():
        try:
            async for event in run_agent_stream(goal, context):
                yield {"event": event["type"], "data": json.dumps(event, default=str)}
        except Exception as exc:
            log.exception("run failed")
            yield {
                "event": "error",
                "data": json.dumps({"message": f"{type(exc).__name__}: {exc}"}),
            }

    return EventSourceResponse(gen())


@app.get("/runs")
async def runs(limit: int = 30):
    return await list_runs(limit)


@app.get("/runs/{run_id}")
async def run_detail(run_id: str):
    run = await get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run
