import asyncio
import json
import os
import time
from typing import AsyncIterator

from google import genai
from google.genai import types

from .tools import TOOL_MAP
from .memory import get_known_ids, save_items, start_run, finish_run
from .scoring import score_items
from alerts.slack import ALERT_THRESHOLD, send_alert

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_STRING_PARAM = {"type": "OBJECT", "properties": {"query": {"type": "STRING"}}, "required": ["query"]}

TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="search_papers",
        description="Search academic research papers via Semantic Scholar.",
        parameters=_STRING_PARAM,
    ),
    types.FunctionDeclaration(
        name="search_patents",
        description="Search granted US patents relevant to a query.",
        parameters=_STRING_PARAM,
    ),
    types.FunctionDeclaration(
        name="search_news",
        description="Search recent news and competitor announcements.",
        parameters=_STRING_PARAM,
    ),
    types.FunctionDeclaration(
        name="search_social",
        description="Search Hacker News discussion/sentiment for a topic.",
        parameters=_STRING_PARAM,
    ),
    types.FunctionDeclaration(
        name="search_github",
        description="Search GitHub repositories relevant to a query — finds competing open-source projects and new tools.",
        parameters=_STRING_PARAM,
    ),
    types.FunctionDeclaration(
        name="search_google",
        description="General web search (Google) for anything not well covered by the other sources.",
        parameters=_STRING_PARAM,
    ),
]
TOOLS = [types.Tool(function_declarations=TOOL_DECLARATIONS)]

SYSTEM = """You are an autonomous competitive-intelligence agent.
Ground every finding against the user's project context — explain WHY it matters to
this specific project, not generic relevance.

On each turn: state a short Thought (one or two sentences: what you know so far, what
gap remains, why you're calling the tool you're about to call). Then either call tools,
or — once you've decided you have enough evidence — stop calling tools and output ONLY
a final JSON object (no prose around it, no markdown fences).

COVERAGE RULES — read carefully, this is the most important part of your job:
- A tool call that returns an error (rate limit / 429, timeout, non-2xx status, or an
  observation containing "error") means that source is NOT covered. A failed call is
  not the same as a checked source.
- If a source fails, retry that category ONCE with a different tool or a narrower/
  rephrased query before giving up on it. Don't repeat an identical query twice.
- If a source still fails after one retry, do NOT silently move on. Record it explicitly
  in the final JSON's "coverage_gaps" array, e.g. "news: rate-limited after retry".
- Only set "coverage_ok": true when every relevant category either returned usable
  results or has an explicit, honest entry in "coverage_gaps". Never claim full
  coverage while a real gap exists unflagged — that defeats the point of this step.

Final JSON shape:
{"items": [{"source": "research|patent|news|social|github|web", "external_id": "...",
"title": "...", "url": "...", "summary": "...", "relevance_reason": "...",
"date": "YYYY-MM-DD or null", "engagement": 42, "organization": "..."}],
"coverage_ok": true, "coverage_gaps": [], "executive_summary": "..."}

"engagement" is a raw traction number pulled from the tool result you already saw for
that item — citationCount for papers, points for Hacker News posts,
stargazers_count for GitHub repos. If the source type has no such number (patents,
news, web), use null. Never estimate or invent a number — only report one you
actually saw in the tool's output.

"organization" is the company/entity behind the item if one is identifiable (patent
assignee, news article's subject company, GitHub repo owner org) — empty string "" if
none. Used to compare which competitors keep showing up.

"executive_summary" is 2-4 plain-language sentences: what was found overall, why it
matters, and any major gap — written for someone who will only read this, not the
full list. Always include it, even when items is empty (explain why nothing new
turned up).

STRICT TYPING — every field except "date" and "engagement" must be a non-null
string. Use "" for a genuinely unavailable value — never null, never omit the key.
Passing null on a string field is a hard validation error.

"coverage_gaps" must be present and be an empty array when nothing failed. Each
entry must be a single STRING like "news: rate-limited after retry" — never an
object like {"source": "news", "reason": "..."}."""

# How much of a tool result the UI shows inline. The model still sees MODEL_RESULT_CHARS.
PREVIEW_CHARS = 600
MODEL_RESULT_CHARS = 8000


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {"items": [], "coverage_ok": False, "coverage_gaps": ["agent produced no parseable output"]}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {"items": [], "coverage_ok": False, "coverage_gaps": ["agent output was not valid JSON"]}


def _preview(result) -> str:
    text = json.dumps(result, default=str)
    return text[:PREVIEW_CHARS] + "…" if len(text) > PREVIEW_CHARS else text


def _is_error(result) -> bool:
    return isinstance(result, dict) and "error" in result


def _result_count(result) -> int | None:
    return len(result) if isinstance(result, list) else None


async def _timed_call(name: str, args: dict):
    """Runs one tool call and reports how long it took and whether it worked — the
    raw material for the grounded-observation line in the UI and, later, for the
    per-source reliability statistics."""
    started = time.monotonic()
    try:
        result = await TOOL_MAP[name](**args)
    except Exception as exc:  # a failed source must stay visible, never be swallowed
        result = {"error": f"{type(exc).__name__}: {exc}"}
    return result, round((time.monotonic() - started) * 1000)


def _strip_private(final: dict) -> dict:
    """Item embeddings are 768 floats each — useful in Postgres, ruinous in an SSE
    payload and in the run_log JSON. Drop them once they've been persisted."""
    for item in final.get("items", []):
        item.pop("_embedding", None)
    return final


async def run_agent_stream(
    goal: str, project_context: str, max_steps: int = 10
) -> AsyncIterator[dict]:
    """Yields the run as it happens: one event per thought, per batch of tool
    observations, and one final event. Callers that only want the end result can use
    run_agent() below."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    known = await get_known_ids()
    run_id = await start_run(goal, project_context)

    yield {
        "type": "run_started",
        "run_id": run_id,
        "goal": goal,
        "context": project_context,
        "known_count": len(known),
        "model": MODEL,
    }

    chat = client.aio.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(system_instruction=SYSTEM, tools=TOOLS),
    )

    message = (
        f"Goal: {goal}\n"
        f"Project context:\n{project_context}\n\n"
        f"Already-known item IDs (do not repeat these in your final list, "
        f"only report new signals): {known}"
    )

    trace: list[dict] = []
    final = {"items": [], "coverage_ok": False, "coverage_gaps": ["max steps reached before final answer"]}

    for step in range(max_steps):
        resp = await chat.send_message(message)
        parts = resp.candidates[0].content.parts or []

        text = "".join(p.text for p in parts if getattr(p, "text", None))
        calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        step_record = {
            "step": step,
            "thought": text.strip(),
            "tools_called": [{"name": c.name, "input": dict(c.args or {})} for c in calls],
            "observations": [],
        }
        trace.append(step_record)

        # emitted before the tools run, so the UI shows the intent while it waits
        yield {"type": "trace", **{k: v for k, v in step_record.items() if k != "observations"}}

        if not calls:
            final = _extract_json(text)
            yield {"type": "status", "phase": "scoring", "message": "Scoring findings"}
            final["items"] = await score_items(final.get("items", []), project_context)
            break

        call_args = [dict(c.args or {}) for c in calls]
        outcomes = await asyncio.gather(
            *[_timed_call(c.name, a) for c, a in zip(calls, call_args)]
        )

        observations = [
            {
                "tool": c.name,
                "query": a.get("query"),
                "ok": not _is_error(result),
                "count": _result_count(result),
                "latency_ms": latency,
                "preview": _preview(result),
                "error": result.get("error") if _is_error(result) else None,
            }
            for c, a, (result, latency) in zip(calls, call_args, outcomes)
        ]
        step_record["observations"] = observations
        yield {"type": "observation", "step": step, "results": observations}

        message = [
            types.Part.from_function_response(
                name=c.name,
                response={"result": json.dumps(result, default=str)[:MODEL_RESULT_CHARS]},
            )
            for c, (result, _) in zip(calls, outcomes)
        ]

    yield {"type": "status", "phase": "saving", "message": "Saving new items"}
    new_count = await save_items(final.get("items", []), run_id)

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    alerted = [it for it in final.get("items", []) if it.get("impact_1_10", 0) >= ALERT_THRESHOLD]
    if webhook and alerted:
        yield {
            "type": "status",
            "phase": "alerting",
            "message": f"Alerting Slack on {len(alerted)} high-impact finding(s)",
        }
        # one bad webhook post must not lose the run's results
        await asyncio.gather(
            *[send_alert(it, webhook) for it in alerted], return_exceptions=True
        )

    final = _strip_private(final)
    await finish_run(run_id, trace, final, new_count)

    yield {
        "type": "final",
        "run_id": run_id,
        "new_items_count": new_count,
        "alerted_count": len(alerted) if webhook else 0,
        **final,
    }


async def run_agent(goal: str, project_context: str, max_steps: int = 10):
    """Non-streaming convenience wrapper — drains the stream and returns the same
    (final, trace) pair the pre-streaming version returned."""
    final: dict = {}
    trace: list[dict] = []
    async for event in run_agent_stream(goal, project_context, max_steps):
        if event["type"] == "trace":
            trace.append({k: v for k, v in event.items() if k != "type"})
        elif event["type"] == "observation":
            for record in trace:
                if record.get("step") == event["step"]:
                    record["observations"] = event["results"]
        elif event["type"] == "final":
            final = {k: v for k, v in event.items() if k != "type"}
    return final, trace
