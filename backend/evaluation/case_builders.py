"""Factory functions for `Case` objects, one per evaluation category. Each function
captures the *shape* a category needs (a happy path, a forced tool failure, a
same-org cross-source disagreement, ...) so `datasets.py` can supply just the
domain-specific content (goal, context, orgs, titles, urls) for many cases without
re-deriving the planner/analyst/verifier script wiring every time.

Every builder produces the same kind of `Case` the hand-written ones in the original
6-case dataset did — these are not a simplified variant, just a non-repetitive way to
author more of them.
"""

from .datasets import Case, ResearchLane

TOOL_FOR_SOURCE = {
    "research": "search_papers",
    "patent": "search_patents",
    "news": "search_news",
    "social": "search_social",
    "reddit": "search_reddit",
    "github": "search_github",
    "web": "search_google",
}


def _lane(question: str, source: str, query: str, raw: dict, item: dict, coverage_gaps=None) -> ResearchLane:
    tool = TOOL_FOR_SOURCE[source]
    return ResearchLane(
        question=question,
        tool_calls=[{"name": tool, "args": {"query": query}}],
        tool_results={tool: [raw]},
        items=[item],
        coverage_gaps=coverage_gaps or [],
    )


def _empty_lane(question: str, source: str, query: str, gap: str) -> ResearchLane:
    tool = TOOL_FOR_SOURCE[source]
    return ResearchLane(
        question=question,
        tool_calls=[{"name": tool, "args": {"query": query}}],
        tool_results={tool: []},
        items=[],
        coverage_gaps=[gap],
    )


def _failing_lane(question: str, source: str, query: str, error: Exception, gap: str) -> ResearchLane:
    tool = TOOL_FOR_SOURCE[source]
    return ResearchLane(
        question=question,
        tool_calls=[{"name": tool, "args": {"query": query}}],
        tool_results={tool: error},
        items=[],
        coverage_gaps=[gap],
    )


def _combine_for_single(lanes: list[ResearchLane]) -> dict:
    """Flattens several fleet lanes into one `pipeline=single` script: the
    single-loop orchestrator has one conversation, not one per sub-question, so its
    baseline script issues every real lane's tool call(s) in one turn and reports
    the union of their items. Safe as long as no two combined lanes call the same
    tool name (true across this dataset — every case pairs distinct sources)."""
    tool_calls: list[dict] = []
    tool_results: dict = {}
    items: list[dict] = []
    for lane in lanes:
        tool_calls.extend(lane.tool_calls)
        tool_results.update(lane.tool_results)
        items.extend(lane.items)
    return {"tool_calls": tool_calls, "tool_results": tool_results, "items": items}


def normal_case(id: str, goal: str, context: str, findings: list[dict]) -> Case:
    """`findings`: [{question, source, query, raw, item, why}, ...] — every lane
    succeeds and every item is kept. `item["external_id"]` must match a value that
    actually appears in `raw` (title/url/external_id) so the verifier grounds it."""
    lanes = [_lane(f["question"], f["source"], f["query"], f["raw"], f["item"]) for f in findings]
    planner_qs = [
        {"question": f["question"], "sources": [f["source"]], "why": f.get("plan_why", f["why"])}
        for f in findings
    ]
    analyst_items = [
        {
            "external_id": f["item"]["external_id"],
            "relevance_reason": f["why"],
            "organization": f["item"].get("organization", ""),
            "keep": True,
        }
        for f in findings
    ]
    summary = f"Found {len(findings)} relevant signal(s) across {len({f['source'] for f in findings})} source(s); no coverage gaps."
    return Case(
        id=id,
        category="normal",
        goal=goal,
        context=context,
        planner={"sub_questions": planner_qs, "rationale": "Split by source and sub-topic."},
        lanes=lanes,
        analyst={"items": analyst_items, "coverage_ok": True, "coverage_gaps": [], "executive_summary": summary},
        single={**_combine_for_single(lanes), "coverage_ok": True, "coverage_gaps": [], "executive_summary": summary},
        expect={"expected_kept_ids": {f["item"]["external_id"] for f in findings}, "coverage_ok": True},
    )


def tool_failure_case(id: str, goal: str, context: str, failing: dict, working: dict) -> Case:
    """`failing`: {question, source, query, error, gap} — the lane whose tool raises.
    `working`: a single finding dict (see `normal_case`) that must still succeed."""
    fail_lane = _failing_lane(failing["question"], failing["source"], failing["query"], failing["error"], failing["gap"])
    work_lane = _lane(working["question"], working["source"], working["query"], working["raw"], working["item"])
    summary = f"{failing['source'].title()} source failed after retry; {working['source']} coverage still produced a usable finding."
    return Case(
        id=id,
        category="tool_failure",
        goal=goal,
        context=context,
        planner={
            "sub_questions": [
                {"question": failing["question"], "sources": [failing["source"]], "why": failing.get("plan_why", "")},
                {"question": working["question"], "sources": [working["source"]], "why": working.get("plan_why", working["why"])},
            ],
            "rationale": "Split by source.",
        },
        lanes=[fail_lane, work_lane],
        analyst={
            "items": [
                {
                    "external_id": working["item"]["external_id"],
                    "relevance_reason": working["why"],
                    "organization": working["item"].get("organization", ""),
                    "keep": True,
                }
            ],
            "coverage_ok": True,
            "coverage_gaps": [failing["gap"]],
            "executive_summary": summary,
        },
        single={**_combine_for_single([fail_lane, work_lane]), "coverage_ok": True, "coverage_gaps": [failing["gap"]], "executive_summary": summary},
        expect={
            "expected_kept_ids": {working["item"]["external_id"]},
            "expect_gap_containing": failing.get("gap_needle", failing["source"]),
            "coverage_ok": True,
        },
    )


def contradictory_case(id: str, goal: str, context: str, org: str, hot: dict, cold: dict, note: str) -> Case:
    """`hot`: high-authority, fresh, on-topic finding for `org` (source should be
    "research" or "patent", `item["date"]` should be `None` for a fresh-recency
    boost). `cold`: low-authority, stale, tangential finding for the same `org`
    (source "social" or "web", `item["date"]` should be an old date, low engagement).
    This combination is what reliably clears `FLEET_CONFLICT_SPREAD` (3.5)."""
    hot_lane = _lane(hot["question"], hot["source"], hot["query"], hot["raw"], hot["item"])
    cold_lane = _lane(cold["question"], cold["source"], cold["query"], cold["raw"], cold["item"])
    return Case(
        id=id,
        category="contradictory",
        goal=goal,
        context=context,
        planner={
            "sub_questions": [
                {"question": hot["question"], "sources": [hot["source"]], "why": hot.get("plan_why", "")},
                {"question": cold["question"], "sources": [cold["source"]], "why": cold.get("plan_why", "")},
            ],
            "rationale": f"Compare technical/IP signal against public signal for {org}.",
        },
        lanes=[hot_lane, cold_lane],
        analyst={
            "items": [
                {"external_id": hot["item"]["external_id"], "relevance_reason": hot["why"], "organization": org, "keep": True},
                {"external_id": cold["item"]["external_id"], "relevance_reason": cold["why"], "organization": org, "keep": True},
            ],
            "coverage_ok": True,
            "coverage_gaps": [],
            "executive_summary": f"{org} shows strong {hot['source']} activity but weak matching public visibility.",
        },
        conflict={"resolutions": [{"organization": org, "note": note, "confidence": 0.65}]},
        single={
            **_combine_for_single([hot_lane, cold_lane]),
            "coverage_ok": True,
            "coverage_gaps": [],
            # single-loop has no conflict-resolution step, so its summary can't flag the
            # disagreement the way the fleet's does — that gap is itself part of the comparison.
            "executive_summary": f"Found signals for {org} across {hot['source']} and {cold['source']} sources.",
        },
        expect={
            "expected_kept_ids": {hot["item"]["external_id"], cold["item"]["external_id"]},
            "expect_conflict_org": org,
        },
    )


def incomplete_case(id: str, goal: str, context: str, probes: list[dict]) -> Case:
    """`probes`: [{question, source, query, gap}, ...] — every lane comes back
    empty; the run must refuse rather than fabricate a conclusion."""
    lanes = [_empty_lane(p["question"], p["source"], p["query"], p["gap"]) for p in probes]
    planner_qs = [{"question": p["question"], "sources": [p["source"]], "why": p.get("plan_why", "")} for p in probes]
    gaps = [p["gap"] for p in probes]
    summary = "No verifiable evidence was found in any searched source; nothing to report."
    return Case(
        id=id,
        category="incomplete",
        goal=goal,
        context=context,
        planner={"sub_questions": planner_qs, "rationale": "Check every plausible source for any trace of this."},
        lanes=lanes,
        analyst={"items": [], "coverage_ok": False, "coverage_gaps": gaps, "executive_summary": summary},
        single={**_combine_for_single(lanes), "coverage_ok": False, "coverage_gaps": gaps, "executive_summary": summary},
        expect={"expected_kept_ids": set(), "coverage_ok": False, "expect_no_fabricated_conclusion": True},
    )


def adversarial_case(id: str, goal: str, context: str, question: str, source: str, query: str, raw: dict, real_item: dict, fake_item: dict, why: str) -> Case:
    """One lane returns one grounded item (`real_item`, present in `raw`) and one
    fabricated item (`fake_item`, never present in `raw`) — the verifier must keep
    the first and reject the second."""
    lane = ResearchLane(
        question=question,
        tool_calls=[{"name": TOOL_FOR_SOURCE[source], "args": {"query": query}}],
        tool_results={TOOL_FOR_SOURCE[source]: [raw]},
        items=[real_item, fake_item],
    )
    summary = "Found one directly relevant, grounded finding."
    return Case(
        id=id,
        category="adversarial",
        goal=goal,
        context=context,
        planner={"sub_questions": [{"question": question, "sources": [source], "why": why}], "rationale": "Single-lane search."},
        lanes=[lane],
        analyst={
            "items": [{"external_id": real_item["external_id"], "relevance_reason": why, "organization": real_item.get("organization", ""), "keep": True}],
            "coverage_ok": True,
            "coverage_gaps": [],
            "executive_summary": summary,
        },
        # single-loop baseline: no independent verifier exists to catch a fabricated
        # item, so its script represents the honest best case (only the real item) —
        # it is not exercised against the hallucination attempt the fleet lane is.
        single={
            "tool_calls": [{"name": TOOL_FOR_SOURCE[source], "args": {"query": query}}],
            "tool_results": {TOOL_FOR_SOURCE[source]: [raw]},
            "items": [real_item],
            "coverage_ok": True,
            "coverage_gaps": [],
            "executive_summary": summary,
        },
        expect={
            "expected_kept_ids": {real_item["external_id"]},
            "expected_rejected_titles": {fake_item["title"]},
        },
    )


def replanning_case(id: str, goal: str, context: str, strong: dict, thin: dict, new: dict) -> Case:
    """`strong`: a finding dict that succeeds initially. `thin`: {question, source,
    query, gap} — a lane that comes back empty, pulling coverage below threshold.
    `new`: a finding dict for the replanned follow-up lane (its `question` is what
    the scripted replan response proposes)."""
    strong_lane = _lane(strong["question"], strong["source"], strong["query"], strong["raw"], strong["item"])
    thin_lane = _empty_lane(thin["question"], thin["source"], thin["query"], thin["gap"])
    new_lane = _lane(new["question"], new["source"], new["query"], new["raw"], new["item"])
    return Case(
        id=id,
        category="replanning",
        goal=goal,
        context=context,
        planner={
            "sub_questions": [
                {"question": strong["question"], "sources": [strong["source"]], "why": strong.get("plan_why", "")},
                {"question": thin["question"], "sources": [thin["source"]], "why": thin.get("plan_why", "")},
            ],
            "rationale": "Split into research and secondary literature.",
        },
        lanes=[strong_lane, thin_lane, new_lane],
        analyst={
            "items": [{"external_id": strong["item"]["external_id"], "relevance_reason": strong["why"], "organization": strong["item"].get("organization", ""), "keep": True}],
            "coverage_ok": False,
            "coverage_gaps": [thin["gap"]],
            "executive_summary": "Found relevant primary-source coverage but a secondary lane came back empty; coverage is thin.",
        },
        replan={
            "new_sub_questions": [{"question": new["question"], "sources": [new["source"]], "why": new.get("plan_why", "recovering coverage after an empty lane")}],
            "rationale": f"{thin['source'].title()} lane was empty; opening a {new['source']} lane instead.",
        },
        # single-loop baseline: no replanning mechanism exists, so it never opens the
        # follow-up lane that recovers coverage — its script is deliberately built from
        # strong+thin only. That gap (fleet recovers, single stays thin) IS the comparison.
        single={
            **_combine_for_single([strong_lane, thin_lane]),
            "coverage_ok": False,
            "coverage_gaps": [thin["gap"]],
            "executive_summary": "Found relevant primary-source coverage but a secondary lane came back empty; coverage stayed thin (the single-agent loop has no replanning mechanism to recover it).",
        },
        expect={
            "expect_replanned": True,
            "expected_kept_ids": {strong["item"]["external_id"], new["item"]["external_id"]},
            "expected_kept_ids_single": {strong["item"]["external_id"]},
        },
    )


def ambiguous_case(id: str, goal: str, context: str, finding: dict, assumption: str) -> Case:
    """`finding`: a single finding dict. `assumption` is the sentence the analyst's
    executive summary must state explaining how it interpreted the vague goal."""
    lane = _lane(finding["question"], finding["source"], finding["query"], finding["raw"], finding["item"])
    summary = f"{assumption} Found one relevant signal under that interpretation."
    return Case(
        id=id,
        category="ambiguous",
        goal=goal,
        context=context,
        planner={"sub_questions": [{"question": finding["question"], "sources": [finding["source"]], "why": finding.get("plan_why", "")}], "rationale": "Interpreting the underspecified goal into one concrete sub-question."},
        lanes=[lane],
        analyst={
            "items": [{"external_id": finding["item"]["external_id"], "relevance_reason": finding["why"], "organization": finding["item"].get("organization", ""), "keep": True}],
            "coverage_ok": True,
            "coverage_gaps": [],
            "executive_summary": summary,
        },
        single={**_combine_for_single([lane]), "coverage_ok": True, "coverage_gaps": [], "executive_summary": summary},
        expect={"expected_kept_ids": {finding["item"]["external_id"]}, "expect_states_assumption": True},
    )
