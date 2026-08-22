import json
import logging

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent import qa, stats
from agent.fleet import run_fleet_stream
from agent.memory import get_run, list_runs
from agent.orchestrator import run_agent_stream
from agent.providers import DEFAULT_PROVIDER, available_providers, get_provider

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


@app.get("/providers")
async def providers():
    """What this deployment can actually run, so the UI never offers a provider
    whose key is missing."""
    found = available_providers()
    return {
        "providers": found,
        "default": DEFAULT_PROVIDER if DEFAULT_PROVIDER in found else (found[0] if found else None),
        "pipelines": ["fleet", "single"],
    }


@app.get("/run")
async def run(
    goal: str,
    context: str,
    pipeline: str = Query("fleet", pattern="^(fleet|single)$"),
    provider: str | None = None,
):
    """Streams the agent's events as they happen. `pipeline=fleet` runs the
    specialist agents (planner, parallel researchers, verifier, analyst,
    strategist); `pipeline=single` runs the original one-agent ReAct loop."""

    async def gen():
        try:
            llm = get_provider(provider)
            stream = (
                run_fleet_stream(goal, context, llm)
                if pipeline == "fleet"
                else run_agent_stream(goal, context, provider=llm)
            )
            async for event in stream:
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


@app.get("/stats")
async def all_stats():
    return await stats.all_stats()


_STAT_SECTIONS = {
    "overview": stats.overview,
    "by_source": stats.by_source,
    "by_organization": stats.by_organization,
    "momentum": stats.momentum,
    "impact_distribution": stats.impact_distribution,
    "source_reliability": stats.source_reliability,
    "run_economics": stats.run_economics,
    "novelty": stats.novelty,
}


@app.get("/stats/{section}")
async def stat_section(section: str):
    fn = _STAT_SECTIONS.get(section)
    if fn is None:
        raise HTTPException(
            status_code=404, detail=f"unknown section; try one of {sorted(_STAT_SECTIONS)}"
        )
    return await fn()


class AskRequest(BaseModel):
    question: str
    run_id: str | None = None
    provider: str | None = None
    limit: int = 8


@app.post("/ask")
async def ask(request: AskRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    return await qa.ask(
        request.question,
        limit=max(1, min(request.limit, 20)),
        run_id=request.run_id,
        provider=get_provider(request.provider),
    )


@app.get("/ask/suggestions")
async def ask_suggestions():
    return {"questions": await qa.suggested_questions()}
