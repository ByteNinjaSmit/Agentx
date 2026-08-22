"""The specialist pipeline.

    Planner      decomposes the goal into sub-questions and a source plan
    Researcher   one per sub-question, run in parallel, tools only
    Verifier     deterministic — drops any item not present in a real tool result
    Analyst      scores relevance, normalizes organizations, writes the summary
    Strategist   threat level and recommended action per competitor

The split is not decoration. The Researchers are bad at judging relevance and
good at querying; the Analyst is the reverse and never touches a flaky API; and
the Verifier is deliberately not a model at all, because "did this actually appear
in a tool result" is a question code can answer and a model can only guess at.
"""

import asyncio
import json
import os
import re
import time
from typing import AsyncIterator

from .memory import get_known_ids, save_progress, start_run
from .orchestrator import finalize_run
from .providers import LLMProvider, get_provider
from .runtime import TOOL_SPECS, execute_calls, extract_json
from .scoring import score_items

MAX_SUBQUESTIONS = int(os.environ.get("FLEET_MAX_SUBQUESTIONS", "4"))
RESEARCH_MAX_STEPS = int(os.environ.get("FLEET_RESEARCH_STEPS", "4"))

# Resource budget: the run must be able to explain "I stopped chasing more
# coverage because I was out of budget" rather than either running forever or
# blowing through it silently. Checked only at the one place that can spend a
# meaningful chunk in one go — deciding whether to open a replanning round.
MAX_TOOL_CALLS = int(os.environ.get("FLEET_MAX_TOOL_CALLS", "60"))
TIME_BUDGET_SECONDS = float(os.environ.get("FLEET_TIME_BUDGET_SECONDS", "180"))

# Self-evaluation: below this fraction of sub-questions producing a kept finding,
# the fleet asks the planner whether a follow-up round is worth it. One round max
# per run — bounded so a thin-coverage run can't loop forever chasing 100%.
COVERAGE_THRESHOLD = float(os.environ.get("FLEET_COVERAGE_THRESHOLD", "0.7"))
MAX_REPLAN_QUESTIONS = int(os.environ.get("FLEET_MAX_REPLAN_QUESTIONS", "2"))

# Evidence-conflict detection: same organization, findings from >= 2 distinct
# source types, impact scores at least this far apart on the 0-10 scale.
CONFLICT_SPREAD = float(os.environ.get("FLEET_CONFLICT_SPREAD", "3.5"))

REPLAN_SYSTEM = """You are the PLANNER doing a mid-investigation self-check in a
competitive-intelligence fleet. You already split the goal into sub-questions and
researchers have reported back. Decide whether to open UP TO 2 new, narrowly
targeted sub-questions:

- because a planned sub-question's coverage is thin (few or no kept findings, or a
  reported coverage gap), or
- because a researcher surfaced a genuinely unexpected organization or technology
  that none of the current sub-questions cover and that plausibly matters to the
  project context.

Do not propose a sub-question that duplicates or lightly rephrases an existing one.
Replanning has a real cost in time and tool calls — if coverage already looks
adequate and nothing unexpected turned up, return an empty list rather than
manufacturing busywork.

Output ONLY this JSON object, no prose and no markdown fences:
{"new_sub_questions": [{"question": "...", "sources": ["news", "papers"], "why": "..."}],
 "rationale": "one or two sentences on why you did or didn't add anything"}"""

CONFLICT_SYSTEM = """You are the VERIFIER's conflict-resolution step in a
competitive-intelligence fleet. You are given one or more organizations where
different sources produced meaningfully different signal strength about the same
organization in the same investigation — e.g. strong research/patent activity
against weak or absent news/product coverage, or the reverse.

For each organization, write one sentence on the likely reason for the
disagreement (e.g. "early-stage technical activity not yet reflected in public
news or product coverage" / "media coverage that patent and research activity
doesn't yet support") and a confidence 0-1 in the overall signal once the
conflict is accounted for.

Output ONLY this JSON object, no prose and no markdown fences:
{"resolutions": [{"organization": "...", "note": "...", "confidence": 0.7}]}"""

PLANNER_SYSTEM = """You are the PLANNER of a competitive-intelligence agent fleet.
You do not search. You decide what should be searched.

Split the user's goal into 2-4 sub-questions that a specialist researcher can each
answer independently, with no overlap between them. For each, name the sources
worth querying from: papers, patents, news, social, github, web.

Output ONLY this JSON object, no prose and no markdown fences:
{"sub_questions": [{"question": "...", "sources": ["papers", "news"], "why": "..."}],
 "rationale": "one or two sentences on how you split the work"}

"why" is one short sentence on what a good answer to that sub-question would tell
the user about their competitive position."""

RESEARCHER_SYSTEM = """You are a RESEARCH agent in a competitive-intelligence fleet.
Your job is ONLY to gather raw findings for the one sub-question you were given.
A separate ANALYST scores relevance and writes the summary — do not do their job,
do not rank, do not editorialize.

State a one-sentence Thought before each tool call: what gap remains and why this
query. Then call tools. When you have enough, stop calling tools and output ONLY a
JSON object, no prose and no markdown fences:

{"items": [{"source": "research|patent|news|social|reddit|github|web", "external_id": "...",
"title": "...", "url": "...", "summary": "...", "date": "YYYY-MM-DD or null",
"engagement": 42, "organization": "..."}], "coverage_gaps": []}

COVERAGE RULES:
- A tool call that errors (rate limit / 429, timeout, non-2xx) means that source is
  NOT covered. Retry that category ONCE with a rephrased or narrower query, never the
  identical query twice.
- If it still fails, record it in "coverage_gaps" as a single STRING such as
  "news: rate-limited after retry". Never silently drop a failed source.

Only report items you actually saw in a tool result. Copy "external_id", "url" and
"engagement" from the tool output verbatim — a downstream verifier checks every item
against the raw results and discards anything it cannot find. Inventing a plausible
URL will get the item deleted, not accepted.

Use "" for a string you genuinely don't have, and null for an unavailable date or
engagement count. Never null on a string field."""

ANALYST_SYSTEM = """You are the ANALYST of a competitive-intelligence fleet.
Researchers gathered the findings below; a verifier already discarded anything not
grounded in a real tool result. You never call tools.

For each item, judge relevance to THIS project — not generic importance — and
normalize the organization name (e.g. "Meta Platforms, Inc.", "facebook" and "Meta AI"
are all "Meta"; use "" when no organization is identifiable).

Output ONLY this JSON object, no prose and no markdown fences:
{"items": [{"external_id": "...", "relevance_reason": "...", "organization": "...",
"keep": true}], "coverage_ok": true, "coverage_gaps": [],
"executive_summary": "..."}

- "external_id" must match an id from the input exactly — it is how your judgement is
  joined back onto the item.
- "keep": false for an item that is genuinely off-topic for this project. Be strict;
  a thin brief of real signals beats a padded one.
- "relevance_reason" is one sentence on why it matters to this specific project.
- "coverage_ok" is true only when every relevant source either returned results or is
  named in "coverage_gaps". Each gap is a single STRING, never an object.
- "executive_summary" is 2-4 plain sentences for someone who will read nothing else.
  Write one even when there are no items, explaining why nothing new turned up."""

STRATEGIST_SYSTEM = """You are the STRATEGIST of a competitive-intelligence fleet.
You see the analyst's kept findings and the user's project context. You never call
tools and you never invent facts — every claim must trace to a finding you were given.

Output ONLY this JSON object, no prose and no markdown fences:
{"competitors": [{"organization": "...", "threat_level": "high|medium|low",
"evidence": ["exact title of a finding", "..."], "assessment": "..."}],
"opportunities": ["..."], "risks": ["..."],
"recommended_actions": [{"action": "...", "rationale": "...", "horizon": "now|quarter|year"}]}

- Only list an organization that actually appears in the findings. If none do, return
  an empty "competitors" array rather than naming a company you assume is in the space.
- "evidence" entries must be titles copied from the findings.
- 2-5 recommended actions, each concrete enough to assign to someone."""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _grounding_haystack(raw_results: list) -> str:
    """Everything the tools actually returned for one researcher, flattened to a
    single lowercase string. The verifier asks whether an item's id, url or title
    appears anywhere in it."""
    return json.dumps(raw_results, default=str).lower()


def verify_items(items: list[dict], haystack: str) -> tuple[list[dict], list[dict]]:
    """Splits items into (grounded, rejected). An item is grounded when its
    external_id, its url, or its title appears in the raw tool output the researcher
    saw. This is the cheapest honest defence against a fabricated finding, and unlike
    an LLM check it cannot itself hallucinate."""
    grounded, rejected = [], []
    for item in items:
        candidates = [
            str(item.get("external_id") or ""),
            str(item.get("url") or ""),
            str(item.get("title") or ""),
        ]
        evidence = next(
            (c for c in candidates if len(_norm(c)) >= 8 and _norm(c) in haystack), None
        )
        if evidence:
            item["grounded_on"] = evidence[:200]
            grounded.append(item)
        else:
            rejected.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "source": item.get("source"),
                    "reason": "not found in any tool result for this sub-question",
                }
            )
    return grounded, rejected


def _competitor_plan(competitors: list[str], track: str) -> list[dict]:
    """One research lane per named competitor, plus one lane for the rest of the
    market. Deliberately not an LLM decision: when the user has already named who
    they are watching, asking a model to re-split the work only introduces a way to
    drop one of them, and a competitor silently missing from a competitive brief is
    the single worst failure this product has."""
    lanes = [
        {
            "question": f"What has {name} shipped, announced, published or patented in {track}?",
            "sources": ["news", "papers", "github", "reddit", "social"],
            "why": f"Direct read on {name}'s current position and pace in {track}.",
            "competitor": name,
        }
        for name in competitors
    ]
    others = ", ".join(competitors)
    lanes.append(
        {
            "question": f"Who else besides {others} is moving in {track}, and what are they shipping?",
            "sources": ["news", "papers", "github"],
            "why": "Catches the entrant that is not yet on the watchlist.",
            "competitor": None,
        }
    )
    return lanes


def attribute_competitor(item: dict, competitors: list[str]) -> str:
    """Which watched competitor a finding belongs to. Text match first — an article
    naming Sarvam belongs to Sarvam even when a researcher watching Google surfaced
    it — then the lane that found it, then unattributed. Deterministic for the same
    reason the verifier is: this drives the per-competitor counts on screen, and a
    model guessing at attribution would quietly skew them."""
    haystack = _norm(
        " ".join(
            str(item.get(field) or "")
            for field in ("title", "summary", "organization", "url", "relevance_reason")
        )
    )
    scored = [(haystack.count(_norm(name)), name) for name in competitors if _norm(name)]
    best = max(scored, default=(0, ""), key=lambda pair: pair[0])
    if best[0] > 0:
        return best[1]
    return item.get("_lane_competitor") or ""


async def _plan(provider: LLMProvider, goal: str, context: str) -> dict:
    turn = await provider.complete(
        PLANNER_SYSTEM,
        f"Goal: {goal}\n\nProject context:\n{context}",
    )
    parsed = extract_json(turn.text) or {}
    questions = [
        q
        for q in parsed.get("sub_questions", [])
        if isinstance(q, dict) and q.get("question")
    ][:MAX_SUBQUESTIONS]
    if not questions:
        # A planner that returns nothing usable must not take the run down with it.
        questions = [{"question": goal, "sources": [], "why": "planner returned no usable split"}]
        parsed.setdefault("rationale", "planner output unusable — researching the goal as given")
    return {
        "sub_questions": questions,
        "rationale": parsed.get("rationale", ""),
        "thinking": turn.thinking or turn.text,
        "tokens": (turn.input_tokens, turn.output_tokens),
    }


async def _research(
    provider: LLMProvider,
    index: int,
    sub_question: dict,
    context: str,
    known: list[str],
    depth: int = 5,
) -> dict:
    """One researcher's whole ReAct loop. Runs to completion and returns its steps
    rather than yielding, so several can run concurrently; the caller interleaves
    the collected steps into the trace."""
    conversation = provider.start(RESEARCHER_SYSTEM, TOOL_SPECS)
    sources = ", ".join(sub_question.get("sources") or []) or "any relevant source"
    turn = await conversation.send(
        f"Sub-question: {sub_question['question']}\n"
        f"Suggested sources: {sources}\n\n"
        f"Project context:\n{context}\n\n"
        f"Already-known item IDs (skip these, they are not new signals): {known}"
    )

    steps: list[dict] = []
    raw_results: list = []
    payload: dict = {"items": [], "coverage_gaps": []}
    tokens = [0, 0]

    for step in range(RESEARCH_MAX_STEPS):
        tokens[0] += turn.input_tokens
        tokens[1] += turn.output_tokens
        record = {
            "agent": "researcher",
            "lane": index,
            "lane_label": sub_question["question"],
            "thought": turn.thinking or turn.text,
            "tools_called": [{"name": c.name, "input": c.args} for c in turn.calls],
            "observations": [],
            "input_tokens": turn.input_tokens,
            "output_tokens": turn.output_tokens,
        }
        steps.append(record)

        if not turn.calls:
            parsed = extract_json(turn.text)
            if parsed is None:
                payload = {
                    "items": [],
                    "coverage_gaps": [f"researcher {index}: no parseable JSON returned"],
                }
            else:
                payload = parsed
            break

        observations, tool_results, raw = await execute_calls(turn.calls, depth)
        record["observations"] = observations
        # Surfaced as its own trace line, not just a field on the observation —
        # a tool recovering on a fallback source is a runtime decision worth
        # seeing live, not something to bury in a collapsed detail row.
        for obs in observations:
            if obs.get("fallback_used"):
                steps.append(
                    {
                        "agent": "runtime",
                        "lane": index,
                        "lane_label": sub_question["question"],
                        "thought": (
                            f"{obs['tool']} failed on its primary source for "
                            f'"{obs.get("query") or sub_question["question"]}" — '
                            f"recovered on {obs['fallback_used']}."
                        ),
                        "tools_called": [],
                        "observations": [],
                    }
                )
        raw_results.extend(raw)
        turn = await conversation.send_tool_results(tool_results)
    else:
        payload.setdefault("coverage_gaps", []).append(
            f"researcher {index}: stopped after {RESEARCH_MAX_STEPS} steps without a final answer"
        )

    items = [it for it in payload.get("items", []) if isinstance(it, dict)]
    for item in items:
        item.setdefault("external_id", item.get("url") or item.get("title") or "")
        item["sub_question"] = sub_question["question"]
        # remembered so attribution can fall back to the lane when the item's own
        # text never names anyone; stripped again once attribution has run
        item["_lane_competitor"] = sub_question.get("competitor") or ""



    return {
        "steps": steps,
        "items": items,
        "coverage_gaps": [g for g in payload.get("coverage_gaps", []) if g],
        "haystack": _grounding_haystack(raw_results),
        "tokens": tuple(tokens),
    }


def _dedupe(items: list[dict]) -> list[dict]:
    """Two researchers looking at neighbouring sub-questions will surface the same
    paper. Keep the first, remember which sub-questions found it — an item found by
    more than one line of enquiry is a stronger signal, not a duplicate to hide."""
    by_key: dict[tuple, dict] = {}
    for item in items:
        key = (item.get("source"), _norm(str(item.get("external_id") or item.get("url") or "")))
        existing = by_key.get(key)
        if existing:
            found_by = existing.setdefault("found_by", [existing.get("sub_question")])
            if item.get("sub_question") not in found_by:
                found_by.append(item.get("sub_question"))
        else:
            by_key[key] = item
    return list(by_key.values())


def _apply_analysis(items: list[dict], analysis: dict) -> list[dict]:
    """Joins the analyst's per-item judgement back onto the items by external_id."""
    verdicts = {
        _norm(str(v.get("external_id", ""))): v
        for v in analysis.get("items", [])
        if isinstance(v, dict)
    }
    kept = []
    for item in items:
        verdict = verdicts.get(_norm(str(item.get("external_id", ""))))
        if verdict is None:
            # No verdict is not a rejection — the analyst may simply have omitted it.
            # Keep it and say so, rather than silently dropping a grounded finding.
            item.setdefault("relevance_reason", "not individually assessed by the analyst")
            kept.append(item)
            continue
        if verdict.get("keep") is False:
            continue
        item["relevance_reason"] = verdict.get("relevance_reason") or item.get(
            "relevance_reason", ""
        )
        if verdict.get("organization"):
            item["organization"] = verdict["organization"]
        kept.append(item)
    return kept


async def _analyze_and_score(
    provider: LLMProvider,
    goal: str,
    project_context: str,
    grounded: list[dict],
    coverage_gaps: list[str],
    competitors: list[str],
) -> dict:
    """Analyst judgement + scoring + competitor attribution over an already-
    verified item set. Shared by the initial research round and any replanning
    round so the two can't drift apart on how a finding gets kept."""
    if not grounded:
        return {"kept": [], "analysis": {}, "tokens": (0, 0)}

    analyst_input = json.dumps(
        [
            {
                "external_id": it.get("external_id"),
                "source": it.get("source"),
                "title": it.get("title"),
                "summary": it.get("summary"),
                "organization": it.get("organization"),
                "date": it.get("date"),
                "found_by": it.get("found_by") or [it.get("sub_question")],
            }
            for it in grounded
        ],
        default=str,
    )[:120000]
    analyst_turn = await provider.complete(
        ANALYST_SYSTEM,
        f"Project context:\n{project_context}\n\nGoal: {goal}\n\n"
        f"Coverage gaps reported by the researchers: {coverage_gaps}\n\n"
        f"Findings:\n{analyst_input}",
    )
    analysis = extract_json(analyst_turn.text) or {}
    kept = _apply_analysis(grounded, analysis)
    for item in kept:
        item["competitor"] = attribute_competitor(item, competitors)
    kept = await score_items(kept, project_context, provider)
    return {
        "kept": kept,
        "analysis": analysis,
        "tokens": (analyst_turn.input_tokens, analyst_turn.output_tokens),
    }


def _coverage_score(questions: list[dict], kept: list[dict]) -> float:
    """Fraction of planned sub-questions that produced at least one kept finding.
    Deterministic, not model-judged, for the same reason the Verifier isn't: "did
    this sub-question get an answer" is a question code can answer honestly."""
    if not questions:
        return 1.0
    covered = {it.get("sub_question") for it in kept if it.get("sub_question")}
    hit = sum(1 for q in questions if q["question"] in covered)
    return hit / len(questions)


def _detect_conflicts(kept: list[dict]) -> list[dict]:
    """Same organization, findings from >= 2 distinct source types, impact scores
    far enough apart to be a real disagreement rather than scoring noise. The
    concrete, checkable shape of "the sources disagree" — a resolver call
    explains it, this function just decides when one is warranted."""
    groups: dict[str, list[dict]] = {}
    for it in kept:
        org = _norm(it.get("organization") or "")
        if org:
            groups.setdefault(org, []).append(it)
    conflicts = []
    for its in groups.values():
        sources = {it.get("source") for it in its}
        impacts = [it.get("impact_1_10", 0) for it in its]
        if len(sources) >= 2 and impacts and (max(impacts) - min(impacts)) >= CONFLICT_SPREAD:
            conflicts.append({"organization": its[0].get("organization"), "items": its})
    return conflicts


async def _resolve_conflicts(
    provider: LLMProvider, conflicts: list[dict], project_context: str
) -> tuple[dict[str, dict], tuple[int, int]]:
    payload = [
        {
            "organization": c["organization"],
            "signals": [
                {
                    "source": it.get("source"),
                    "title": it.get("title"),
                    "impact_1_10": it.get("impact_1_10"),
                }
                for it in c["items"]
            ],
        }
        for c in conflicts
    ]
    turn = await provider.complete(
        CONFLICT_SYSTEM,
        f"Project context:\n{project_context}\n\n"
        f"Conflicting signals:\n{json.dumps(payload, default=str)[:40000]}",
    )
    parsed = extract_json(turn.text) or {}
    resolutions = {
        _norm(str(r.get("organization", ""))): r
        for r in parsed.get("resolutions", [])
        if isinstance(r, dict)
    }
    return resolutions, (turn.input_tokens, turn.output_tokens)


async def _replan_check(
    provider: LLMProvider,
    goal: str,
    project_context: str,
    questions: list[dict],
    kept: list[dict],
    coverage_gaps: list[str],
    coverage_score: float,
) -> tuple[list[dict], str, tuple[int, int]]:
    digest = [
        {
            "question": q["question"],
            "kept_findings": [
                {
                    "title": it.get("title"),
                    "organization": it.get("organization"),
                    "source": it.get("source"),
                }
                for it in kept
                if it.get("sub_question") == q["question"]
            ][:5],
        }
        for q in questions
    ]
    turn = await provider.complete(
        REPLAN_SYSTEM,
        f"Goal: {goal}\nProject context:\n{project_context}\n\n"
        f"Coverage score: {coverage_score:.0%}\nCoverage gaps reported: {coverage_gaps}\n\n"
        f"Per-question results:\n{json.dumps(digest, default=str)[:20000]}",
    )
    parsed = extract_json(turn.text) or {}
    new_qs = [
        q for q in parsed.get("new_sub_questions", []) if isinstance(q, dict) and q.get("question")
    ][:MAX_REPLAN_QUESTIONS]
    return new_qs, parsed.get("rationale", ""), (turn.input_tokens, turn.output_tokens)


async def run_fleet_stream(
    goal: str,
    project_context: str,
    provider: LLMProvider | None = None,
    competitors: list[str] | None = None,
    depth: int = 5,
    track: str = "",
) -> AsyncIterator[dict]:
    provider = provider or get_provider()
    competitors = [c for c in (competitors or []) if c.strip()]
    track = track.strip() or goal
    known = await get_known_ids()
    run_id = await start_run(goal, project_context)
    tokens = {"input": 0, "output": 0}
    trace: list[dict] = []
    step_no = 0
    tool_calls_used = 0
    run_started = time.monotonic()

    def record(entry: dict) -> dict:
        nonlocal step_no, tool_calls_used
        entry["step"] = step_no
        step_no += 1
        tool_calls_used += len(entry.get("tools_called") or [])
        trace.append(entry)
        return {"type": "trace", **{k: v for k, v in entry.items() if k != "observations"}}

    async def checkpoint():
        # Best-effort — a checkpoint write failing must never take the run down
        # with it; the worst case is just a less up-to-date crash-recovery state.
        try:
            await save_progress(run_id, trace)
        except Exception:
            pass

    def resource_usage() -> dict:
        return {
            "tool_calls_used": tool_calls_used,
            "tool_call_budget": MAX_TOOL_CALLS,
            "elapsed_seconds": round(time.monotonic() - run_started, 1),
            "time_budget_seconds": TIME_BUDGET_SECONDS,
        }

    def budget_exhausted() -> bool:
        return (
            tool_calls_used >= MAX_TOOL_CALLS
            or (time.monotonic() - run_started) >= TIME_BUDGET_SECONDS
        )

    yield {
        "type": "run_started",
        "run_id": run_id,
        "goal": goal,
        "context": project_context,
        "known_count": len(known),
        "provider": provider.name,
        "model": provider.model,
        "pipeline": "fleet",
        "competitors": competitors,
        "track": track,
        "depth": depth,
    }

    # ---- Planner -----------------------------------------------------------
    yield {"type": "status", "phase": "planning", "message": "Planner is splitting the goal"}
    if competitors:
        # Named watchlist: the split is fixed, so no model call and no lost competitor.
        plan = {
            "sub_questions": _competitor_plan(competitors, track),
            "rationale": (
                f"{len(competitors)} named competitor(s) — one dedicated research lane each, "
                f"plus one lane for unwatched entrants in {track}. "
                f"Scan depth {depth} items per source per query."
            ),
            "thinking": (
                f"The watchlist is explicit, so the split is too: a lane per competitor "
                f"({', '.join(competitors)}) and one for the rest of the market. "
                f"No competitor can be dropped by a planning model that never runs."
            ),
            "tokens": (0, 0),
        }
    else:
        plan = await _plan(provider, goal, project_context)
    tokens["input"] += plan["tokens"][0]
    tokens["output"] += plan["tokens"][1]
    yield record(
        {
            "agent": "planner",
            "thought": plan["thinking"],
            "tools_called": [],
            "observations": [],
            "plan": plan["sub_questions"],
            "rationale": plan["rationale"],
        }
    )

    # ---- Researchers, in parallel ------------------------------------------
    questions = plan["sub_questions"]
    yield {
        "type": "status",
        "phase": "researching",
        "message": f"{len(questions)} researchers working in parallel",
    }
    results = await asyncio.gather(
        *[
            _research(provider, i, q, project_context, known, depth)
            for i, q in enumerate(questions)
        ],
        return_exceptions=True,
    )

    raw_items: list[dict] = []
    coverage_gaps: list[str] = []
    haystacks: list[str] = []
    for index, result in enumerate(results):
        if isinstance(result, Exception):
            # A researcher that dies is a coverage gap, not a run failure.
            coverage_gaps.append(
                f"researcher {index} ({questions[index]['question'][:60]}): "
                f"{type(result).__name__}: {result}"
            )
            yield record(
                {
                    "agent": "researcher",
                    "lane": index,
                    "lane_label": questions[index]["question"],
                    "thought": f"This line of enquiry failed: {type(result).__name__}: {result}",
                    "tools_called": [],
                    "observations": [],
                }
            )
            continue
        for step in result["steps"]:
            event = record(step)
            yield event
            if step["observations"]:
                yield {"type": "observation", "step": step["step"], "results": step["observations"]}
        raw_items.extend(result["items"])
        coverage_gaps.extend(result["coverage_gaps"])
        haystacks.append(result["haystack"])
        tokens["input"] += result["tokens"][0]
        tokens["output"] += result["tokens"][1]

    await checkpoint()

    # ---- Verifier ----------------------------------------------------------
    yield {"type": "status", "phase": "verifying", "message": "Verifying findings against tool output"}
    deduped = _dedupe(raw_items)
    grounded, rejected = verify_items(deduped, "\n".join(haystacks))
    yield record(
        {
            "agent": "verifier",
            "thought": (
                f"{len(grounded)} of {len(deduped)} findings are traceable to a real tool result"
                + (f"; discarded {len(rejected)} that were not." if rejected else ".")
            ),
            "tools_called": [],
            "observations": [],
            "rejected": rejected,
        }
    )

    # ---- Analyst -----------------------------------------------------------
    yield {"type": "status", "phase": "analyzing", "message": "Analyst is judging relevance"}
    result = await _analyze_and_score(provider, goal, project_context, grounded, coverage_gaps, competitors)
    tokens["input"] += result["tokens"][0]
    tokens["output"] += result["tokens"][1]
    analysis = result["analysis"]
    kept = result["kept"]
    yield record(
        {
            "agent": "analyst",
            "thought": f"Kept {len(kept)} of {len(grounded)} findings as relevant to this project.",
            "tools_called": [],
            "observations": [],
            "input_tokens": result["tokens"][0],
            "output_tokens": result["tokens"][1],
        }
    )

    # ---- Self-evaluation -----------------------------------------------------
    # Coverage is computed in code, not asked of a model — the fraction of
    # planned sub-questions that actually produced a kept finding. Below the
    # threshold, ask the planner whether one bounded follow-up round is
    # warranted; above it, say so and move on. Either way this is visible in
    # the trace, not a silent internal check.
    yield {"type": "status", "phase": "self_eval", "message": "Self-evaluating coverage"}
    coverage_score = _coverage_score(questions, kept)
    replanned = False
    replan_rationale = ""

    if (coverage_score < COVERAGE_THRESHOLD or coverage_gaps) and budget_exhausted():
        usage = resource_usage()
        yield record(
            {
                "agent": "planner",
                "thought": (
                    f"Self-evaluation: coverage {coverage_score:.0%} "
                    f"(threshold {COVERAGE_THRESHOLD:.0%}) — thin, but the run is out of budget "
                    f"({usage['tool_calls_used']}/{usage['tool_call_budget']} tool calls, "
                    f"{usage['elapsed_seconds']:.0f}/{usage['time_budget_seconds']:.0f}s). "
                    "Skipping the replan check and proceeding with what was found."
                ),
                "tools_called": [],
                "observations": [],
            }
        )
    elif coverage_score < COVERAGE_THRESHOLD or coverage_gaps:
        new_qs, replan_rationale, replan_tokens = await _replan_check(
            provider, goal, project_context, questions, kept, coverage_gaps, coverage_score
        )
        tokens["input"] += replan_tokens[0]
        tokens["output"] += replan_tokens[1]

        if new_qs:
            replanned = True
            yield record(
                {
                    "agent": "planner",
                    "thought": (
                        f"Self-evaluation: coverage {coverage_score:.0%} "
                        f"(threshold {COVERAGE_THRESHOLD:.0%}). Replanning — {replan_rationale}"
                    ),
                    "tools_called": [],
                    "observations": [],
                    "plan": new_qs,
                }
            )
            yield {
                "type": "status",
                "phase": "replanning",
                "message": f"{len(new_qs)} follow-up researcher(s) working",
            }
            replan_results = await asyncio.gather(
                *[
                    _research(provider, len(questions) + i, q, project_context, known, depth)
                    for i, q in enumerate(new_qs)
                ],
                return_exceptions=True,
            )
            replan_raw: list[dict] = []
            replan_haystacks: list[str] = []
            for i, r in enumerate(replan_results):
                if isinstance(r, Exception):
                    coverage_gaps.append(f"replan lane {i} ({new_qs[i]['question'][:60]}): {type(r).__name__}: {r}")
                    continue
                for step in r["steps"]:
                    event = record(step)
                    yield event
                    if step["observations"]:
                        yield {"type": "observation", "step": step["step"], "results": step["observations"]}
                replan_raw.extend(r["items"])
                coverage_gaps.extend(r["coverage_gaps"])
                replan_haystacks.append(r["haystack"])
                tokens["input"] += r["tokens"][0]
                tokens["output"] += r["tokens"][1]

            if replan_raw:
                replan_deduped = _dedupe(replan_raw)
                replan_grounded, replan_rejected = verify_items(replan_deduped, "\n".join(replan_haystacks))
                rejected.extend(replan_rejected)
                replan_result = await _analyze_and_score(
                    provider, goal, project_context, replan_grounded, coverage_gaps, competitors
                )
                tokens["input"] += replan_result["tokens"][0]
                tokens["output"] += replan_result["tokens"][1]
                kept.extend(replan_result["kept"])
                questions = questions + new_qs  # credited toward coverage from here on

            coverage_score = _coverage_score(questions, kept)
            yield record(
                {
                    "agent": "analyst",
                    "thought": f"Self-evaluation after replanning: coverage now {coverage_score:.0%}.",
                    "tools_called": [],
                    "observations": [],
                }
            )
        else:
            yield record(
                {
                    "agent": "planner",
                    "thought": (
                        f"Self-evaluation: coverage {coverage_score:.0%} "
                        f"(threshold {COVERAGE_THRESHOLD:.0%}). "
                        f"{replan_rationale or 'No replan warranted.'}"
                    ),
                    "tools_called": [],
                    "observations": [],
                }
            )
    else:
        yield record(
            {
                "agent": "analyst",
                "thought": f"Self-evaluation: coverage {coverage_score:.0%} — sufficient, proceeding.",
                "tools_called": [],
                "observations": [],
            }
        )

    # ---- Evidence conflict resolution -----------------------------------------
    conflicts = _detect_conflicts(kept)
    conflict_summaries: list[dict] = []
    if conflicts:
        yield record(
            {
                "agent": "verifier",
                "thought": (
                    f"Conflicting evidence detected for {len(conflicts)} organization(s) — "
                    f"signal strength disagrees by >= {CONFLICT_SPREAD} across sources. "
                    "Requesting additional verification."
                ),
                "tools_called": [],
                "observations": [],
            }
        )
        resolutions, resolve_tokens = await _resolve_conflicts(provider, conflicts, project_context)
        tokens["input"] += resolve_tokens[0]
        tokens["output"] += resolve_tokens[1]
        for c in conflicts:
            res = resolutions.get(_norm(str(c["organization"])), {})
            note = res.get("note", "sources disagree; no automated resolution returned")
            confidence = res.get("confidence")
            for it in c["items"]:
                it["conflict_note"] = note
                if confidence is not None:
                    it["confidence"] = confidence
            conflict_summaries.append(
                {
                    "organization": c["organization"],
                    "note": note,
                    "confidence": confidence,
                    "items": [it.get("title") for it in c["items"]],
                }
            )
        yield record(
            {
                "agent": "verifier",
                "thought": "Conflict resolution: "
                + " ".join(f"{c['organization']} — {c['note']}" for c in conflict_summaries),
                "tools_called": [],
                "observations": [],
            }
        )
    else:
        yield record(
            {
                "agent": "verifier",
                "thought": "No conflicting evidence detected across kept findings.",
                "tools_called": [],
                "observations": [],
            }
        )

    await checkpoint()

    # ---- Strategist --------------------------------------------------------
    yield {"type": "status", "phase": "strategy", "message": "Strategist is assessing competitors"}
    strategy_input = json.dumps(
        [
            {
                "title": it.get("title"),
                "organization": it.get("organization"),
                "competitor": it.get("competitor"),
                "source": it.get("source"),
                "impact_1_10": it.get("impact_1_10"),
                "relevance_reason": it.get("relevance_reason"),
            }
            for it in kept
        ],
        default=str,
    )[:60000]
    strategy_turn = await provider.complete(
        STRATEGIST_SYSTEM,
        f"Project context:\n{project_context}\n\nGoal: {goal}\n\nFindings:\n{strategy_input}",
    )
    tokens["input"] += strategy_turn.input_tokens
    tokens["output"] += strategy_turn.output_tokens
    strategy = extract_json(strategy_turn.text) or {}
    yield record(
        {
            "agent": "strategist",
            "thought": strategy_turn.thinking
            or f"Assessed {len(strategy.get('competitors', []))} competitor(s) against this project.",
            "tools_called": [],
            "observations": [],
            "input_tokens": strategy_turn.input_tokens,
            "output_tokens": strategy_turn.output_tokens,
        }
    )

    gaps = list(dict.fromkeys([*coverage_gaps, *[g for g in analysis.get("coverage_gaps", []) if g]]))
    if rejected:
        gaps.append(f"verifier: discarded {len(rejected)} ungrounded finding(s)")

    executive_summary = analysis.get("executive_summary", "")
    if replanned:
        executive_summary = (
            f"{executive_summary} The planner opened a follow-up research round after "
            f"self-evaluation ({replan_rationale or 'coverage was below threshold'}), "
            f"raising evidence coverage to {coverage_score:.0%}."
        ).strip()
    if conflict_summaries:
        orgs = ", ".join(c["organization"] for c in conflict_summaries)
        executive_summary = (
            f"{executive_summary} Conflicting evidence was found and resolved for: {orgs}."
        ).strip()

    final = {
        "items": kept,
        "coverage_ok": bool(analysis.get("coverage_ok", not gaps)),
        "coverage_gaps": gaps,
        "executive_summary": executive_summary,
        "strategy": strategy,
        "plan": questions,
        "rejected_count": len(rejected),
        "competitors_watched": competitors,
        "track": track,
        "depth": depth,
        "self_evaluation": {
            "coverage_score": round(coverage_score, 2),
            "threshold": COVERAGE_THRESHOLD,
            "replanned": replanned,
            "replan_rationale": replan_rationale or None,
        },
        "conflicts": conflict_summaries,
        "resource_usage": resource_usage(),
    }

    async for event in finalize_run(run_id, trace, final, tokens, provider, "fleet"):
        yield event
