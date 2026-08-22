import asyncio
import json
import os

from google import genai
from google.genai import types

from .tools import TOOL_MAP
from .memory import get_known_ids, save_items, log_run
from .scoring import score_item

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
{"items": [{"source": "research|patent|news|social", "external_id": "...", "title": "...",
"url": "...", "summary": "...", "relevance_reason": "...", "date": "YYYY-MM-DD or null"}],
"coverage_ok": true, "coverage_gaps": []}

"coverage_gaps" must be present and be an empty array when nothing failed."""


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {"items": [], "coverage_ok": False, "coverage_gaps": ["agent produced no parseable output"]}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {"items": [], "coverage_ok": False, "coverage_gaps": ["agent output was not valid JSON"]}


async def run_agent(goal: str, project_context: str, max_steps: int = 10):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    known = await get_known_ids()

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

    trace = []
    final = {"items": [], "coverage_ok": False, "coverage_gaps": ["max steps reached before final answer"]}

    for step in range(max_steps):
        resp = await chat.send_message(message)
        parts = resp.candidates[0].content.parts or []

        text = "".join(p.text for p in parts if getattr(p, "text", None))
        calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        trace.append(
            {
                "step": step,
                "thought": text.strip(),
                "tools_called": [{"name": c.name, "input": dict(c.args or {})} for c in calls],
            }
        )

        if not calls:
            final = _extract_json(text)
            for item in final.get("items", []):
                item["impact_1_10"] = score_item(item, project_context)
            break

        results = await asyncio.gather(
            *[TOOL_MAP[c.name](**dict(c.args or {})) for c in calls], return_exceptions=True
        )
        results = [
            {"error": str(r)} if isinstance(r, Exception) else r for r in results
        ]

        message = [
            types.Part.from_function_response(
                name=c.name, response={"result": json.dumps(r, default=str)[:8000]}
            )
            for c, r in zip(calls, results)
        ]

    new_count = await save_items(final.get("items", []))
    await log_run(goal, trace, new_count)
    return final, trace
