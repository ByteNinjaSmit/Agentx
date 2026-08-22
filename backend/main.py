import json

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from agent.orchestrator import run_agent

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
    async def gen():
        final, trace = await run_agent(goal, context)
        for step in trace:
            yield {"event": "trace", "data": json.dumps(step, default=str)}
        yield {"event": "final", "data": json.dumps(final, default=str)}

    return EventSourceResponse(gen())
