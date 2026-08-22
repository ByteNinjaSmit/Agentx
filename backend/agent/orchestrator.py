import asyncio
import json
import os

import anthropic

from .tools import TOOL_MAP
from .memory import get_known_ids, save_items, log_run
from .scoring import score_item

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

TOOLS = [
    {
        "name": "search_papers",
        "description": "Search academic research papers via Semantic Scholar.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "search_patents",
        "description": "Search granted US patents relevant to a query.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "search_news",
        "description": "Search recent news and competitor announcements.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "search_social",
        "description": "Search Hacker News discussion/sentiment for a topic.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]

SYSTEM = """You are an autonomous competitive-intelligence agent.
Ground every finding against the user's project context — explain WHY it matters to
this specific project, not generic relevance.

On each turn: state a short Thought (one or two sentences: what you know so far, what
gap remains, why you're calling the tool you're about to call). Then either call tools,
or — once coverage across research/patents/news/social is sufficient for the goal —
stop calling tools and instead output ONLY a final JSON object (no prose around it):

{"items": [{"source": "research|patent|news|social", "external_id": "...", "title": "...",
"url": "...", "summary": "...", "relevance_reason": "...", "date": "YYYY-MM-DD or null"}],
"coverage_ok": true}

If coverage is thin in some category, say so in your Thought and call more/different
tools with a refined query (narrower terms, synonyms, or a different angle) instead of
settling for a weak result. Do not repeat an identical query you've already tried."""


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {"items": [], "coverage_ok": False}
    return json.loads(text[start : end + 1])


async def run_agent(goal: str, project_context: str, max_steps: int = 6):
    client = anthropic.Anthropic()
    known = await get_known_ids()
    messages = [
        {
            "role": "user",
            "content": (
                f"Goal: {goal}\n"
                f"Project context:\n{project_context}\n\n"
                f"Already-known item IDs (do not repeat these in your final list, "
                f"only report new signals): {known}"
            ),
        }
    ]
    trace = []
    final = {"items": [], "coverage_ok": False}

    for step in range(max_steps):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        thought = "".join(b.text for b in resp.content if b.type == "text")
        calls = [b for b in resp.content if b.type == "tool_use"]
        trace.append(
            {
                "step": step,
                "thought": thought.strip(),
                "tools_called": [{"name": c.name, "input": c.input} for c in calls],
            }
        )

        if not calls:
            final = _extract_json(thought)
            for item in final.get("items", []):
                item["impact_1_10"] = score_item(item, project_context)
            break

        results = await asyncio.gather(
            *[TOOL_MAP[c.name](**c.input) for c in calls], return_exceptions=True
        )
        results = [r if not isinstance(r, Exception) else {"error": str(r)} for r in results]

        messages.append({"role": "assistant", "content": resp.content})
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": c.id,
                        "content": json.dumps(r, default=str)[:8000],
                    }
                    for c, r in zip(calls, results)
                ],
            }
        )

    new_count = await save_items(final.get("items", []))
    await log_run(goal, trace, new_count)
    return final, trace
