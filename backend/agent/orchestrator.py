"""The single-agent ReAct pipeline: one model plans, calls tools, and writes the
final JSON. `fleet.py` holds the multi-agent alternative; both stream the same
event shapes, so the frontend does not need to know which ran."""

import asyncio
import os
from typing import AsyncIterator

from .memory import finish_run, get_known_ids, save_items, start_run
from .providers import LLMProvider, get_provider
from .runtime import TOOL_SPECS, execute_calls, extract_json, strip_private
from .scoring import score_items
from alerts.slack import ALERT_THRESHOLD, send_alert

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
{"items": [{"source": "research|patent|news|social|reddit|github|web", "external_id": "...",
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


async def run_agent_stream(
    goal: str,
    project_context: str,
    max_steps: int = 10,
    provider: LLMProvider | None = None,
    competitors: list[str] | None = None,
    depth: int = 5,
    track: str = "",
) -> AsyncIterator[dict]:
    """Yields the run as it happens: one event per thought, per batch of tool
    observations, and one final event. Callers that only want the end result can use
    run_agent() below."""
    provider = provider or get_provider()
    competitors = [c for c in (competitors or []) if c.strip()]
    track = track.strip() or goal
    known = await get_known_ids()
    run_id = await start_run(goal, project_context)

    yield {
        "type": "run_started",
        "run_id": run_id,
        "goal": goal,
        "context": project_context,
        "known_count": len(known),
        "provider": provider.name,
        "model": provider.model,
        "pipeline": "single",
        "competitors": competitors,
        "track": track,
        "depth": depth,
    }

    watchlist = (
        f"Watched competitors — cover EVERY one of them with at least one query: "
        f"{', '.join(competitors)}\n"
        if competitors
        else ""
    )
    conversation = provider.start(SYSTEM, TOOL_SPECS)
    turn = await conversation.send(
        f"Goal: {goal}\n"
        f"Domain / track: {track}\n"
        f"{watchlist}"
        f"Each source returns up to {depth} items per query.\n"
        f"Project context:\n{project_context}\n\n"
        f"Already-known item IDs (do not repeat these in your final list, "
        f"only report new signals): {known}"
    )

    trace: list[dict] = []
    tokens = {"input": 0, "output": 0}
    final = {
        "items": [],
        "coverage_ok": False,
        "coverage_gaps": ["max steps reached before final answer"],
    }

    for step in range(max_steps):
        tokens["input"] += turn.input_tokens
        tokens["output"] += turn.output_tokens

        step_record = {
            "step": step,
            "agent": "researcher",
            "thought": turn.thinking or turn.text,
            "tools_called": [{"name": c.name, "input": c.args} for c in turn.calls],
            "observations": [],
            "input_tokens": turn.input_tokens,
            "output_tokens": turn.output_tokens,
        }
        trace.append(step_record)

        # emitted before the tools run, so the UI shows the intent while it waits
        yield {"type": "trace", **{k: v for k, v in step_record.items() if k != "observations"}}

        if not turn.calls:
            parsed = extract_json(turn.text)
            if parsed is None:
                final = {
                    "items": [],
                    "coverage_ok": False,
                    "coverage_gaps": ["agent produced no parseable final JSON"],
                    "executive_summary": turn.text[:2000],
                }
            else:
                final = parsed
            yield {"type": "status", "phase": "scoring", "message": "Scoring findings"}
            final["items"] = await score_items(
                final.get("items", []), project_context, provider
            )
            if competitors:
                from .fleet import attribute_competitor

                for item in final["items"]:
                    item["competitor"] = attribute_competitor(item, competitors)
            final["competitors_watched"] = competitors
            final["track"] = track
            final["depth"] = depth
            break

        observations, tool_results, _raw = await execute_calls(turn.calls, depth)
        step_record["observations"] = observations
        yield {"type": "observation", "step": step, "results": observations}

        turn = await conversation.send_tool_results(tool_results)

    async for event in finalize_run(run_id, trace, final, tokens, provider, "single"):
        yield event


async def finalize_run(
    run_id: str,
    trace: list[dict],
    final: dict,
    tokens: dict,
    provider: LLMProvider,
    pipeline: str,
) -> AsyncIterator[dict]:
    """Save, alert, log and emit the final event. Shared by both pipelines so they
    cannot drift apart on the parts the frontend and the database depend on."""
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
        await asyncio.gather(*[send_alert(it, webhook) for it in alerted], return_exceptions=True)

    final = strip_private(final)
    final.setdefault("coverage_gaps", [])
    final["provider"] = provider.name
    final["model"] = provider.model
    final["pipeline"] = pipeline
    final["input_tokens"] = tokens["input"]
    final["output_tokens"] = tokens["output"]

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
