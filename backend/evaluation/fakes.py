"""Fake provider, fake tools, fake memory — the doubles that let the evaluation
harness run the real `fleet.py` / `orchestrator.py` graphs with no network, no API
keys, and no Postgres.

Design: every LLM call in the real agent goes through exactly one of two provider
methods — `complete()` (one-shot, used by Planner/Analyst/Strategist/replan-check/
conflict-resolution) or `start()` (a tool-using conversation, used by Researchers and
the single-loop orchestrator). Each system prompt in `agent/fleet.py` and
`agent/orchestrator.py` has a distinctive phrase identifying which role is calling, so
`FakeProvider` routes each call to that role's scripted response on the `Case` being
run, rather than needing a mock per call site.
"""

import re
import uuid
from unittest.mock import patch

from agent.providers.base import Conversation, LLMProvider, ToolCall, ToolResult, Turn

from .datasets import ALL_TOOL_NAMES, Case

_ROLE_MARKERS = [
    ("conflict", "VERIFIER's conflict-resolution step"),
    ("replan", "mid-investigation self-check"),
    ("planner", "PLANNER of a competitive-intelligence agent fleet"),
    ("analyst", "ANALYST of a competitive-intelligence fleet"),
    ("strategist", "STRATEGIST of a competitive-intelligence fleet"),
]

_RESEARCHER_MARKER = "RESEARCH agent in a competitive-intelligence fleet"
_SINGLE_MARKER = "autonomous competitive-intelligence agent"

_DEFAULT_ROLE_PAYLOAD = {
    "planner": {"sub_questions": [], "rationale": "no script"},
    "analyst": {"items": [], "coverage_ok": False, "coverage_gaps": ["no script"], "executive_summary": ""},
    "strategist": {"competitors": [], "opportunities": [], "risks": [], "recommended_actions": []},
    "replan": {"new_sub_questions": [], "rationale": "no replan scripted for this case"},
    "conflict": {"resolutions": []},
}


def _hash_embed(text: str, dim: int) -> list[float]:
    """Deterministic bag-of-words embedding — no model call, but real cosine
    similarity driven by actual shared vocabulary between texts, so relevance
    scoring in `scoring.py` behaves meaningfully rather than being a constant."""
    import hashlib
    import math

    vec = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", (text or "").lower()):
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class _FakeResearchConversation:
    """Backs one researcher's `provider.start(RESEARCHER_SYSTEM, ...)` call. Scripted
    as exactly one round: `.send()` returns the lane's tool calls (if any), then
    `.send_tool_results()` returns the lane's final JSON — matching the real
    Researcher's "call tools once, then answer" shape used throughout the dataset."""

    def __init__(self, case: Case):
        self._case = case
        self._lane = None

    async def send(self, message: str) -> Turn:
        match = re.search(r"Sub-question: (.+)", message)
        question = match.group(1).strip() if match else ""
        lane = self._case.lanes_by_question.get(question)
        if lane is None:
            return Turn(
                text='{"items": [], "coverage_gaps": ["no fake data for this sub-question"]}',
                calls=[],
                input_tokens=5,
                output_tokens=5,
            )
        self._lane = lane
        if lane.tool_calls:
            calls = [
                ToolCall(id=f"c{i}", name=tc["name"], args=tc["args"])
                for i, tc in enumerate(lane.tool_calls)
            ]
            return Turn(text=lane.thought, calls=calls, input_tokens=5, output_tokens=5)
        return self._final_turn()

    async def send_tool_results(self, results: list[ToolResult]) -> Turn:
        return self._final_turn()

    def _final_turn(self) -> Turn:
        import json

        lane = self._lane
        payload = {"items": lane.items, "coverage_gaps": lane.coverage_gaps}
        return Turn(text=json.dumps(payload, default=str), calls=[], input_tokens=5, output_tokens=5)


class _FakeSingleConversation:
    """Backs the single-loop orchestrator's one `provider.start(SYSTEM, ...)` call."""

    def __init__(self, case: Case):
        self._case = case
        self._sent_calls = False

    async def send(self, message: str) -> Turn:
        spec = self._case.single
        if spec is None:
            return Turn(text='{"items": [], "coverage_gaps": ["no single-pipeline script for this case"], "coverage_ok": false, "executive_summary": ""}', calls=[])
        if spec.get("tool_calls"):
            self._sent_calls = True
            calls = [
                ToolCall(id=f"c{i}", name=tc["name"], args=tc["args"])
                for i, tc in enumerate(spec["tool_calls"])
            ]
            return Turn(text=spec.get("thought", "Researching."), calls=calls, input_tokens=5, output_tokens=5)
        return self._final_turn()

    async def send_tool_results(self, results: list[ToolResult]) -> Turn:
        return self._final_turn()

    def _final_turn(self) -> Turn:
        import json

        spec = self._case.single
        payload = {
            "items": spec["items"],
            "coverage_ok": spec.get("coverage_ok", True),
            "coverage_gaps": spec.get("coverage_gaps", []),
            "executive_summary": spec.get("executive_summary", ""),
        }
        return Turn(text=json.dumps(payload, default=str), calls=[], input_tokens=5, output_tokens=5)


class FakeProvider(LLMProvider):
    """One `FakeProvider` per case run. Routes `complete()` by system-prompt role and
    `start()` by whether the caller is a Researcher or the single-loop orchestrator."""

    name = "fake"
    model = "fake-eval-model"

    def __init__(self, case: Case):
        self.case = case

    def start(self, system: str, tools=None) -> Conversation:
        if _RESEARCHER_MARKER in system:
            return _FakeResearchConversation(self.case)
        if _SINGLE_MARKER in system:
            return _FakeSingleConversation(self.case)
        raise ValueError(f"FakeProvider.start(): unrecognized system prompt: {system[:80]!r}")

    async def complete(self, system: str, prompt: str) -> Turn:
        import json

        role = next((r for r, marker in _ROLE_MARKERS if marker in system), None)
        if role is None:
            raise ValueError(f"FakeProvider.complete(): unrecognized system prompt: {system[:80]!r}")
        payload = getattr(self.case, role, None) or _DEFAULT_ROLE_PAYLOAD[role]
        return Turn(text=json.dumps(payload, default=str), calls=[], input_tokens=8, output_tokens=8, thinking=f"[fake {role}]")

    async def embed(self, texts: list[str], dim: int) -> list[list[float]]:
        return [_hash_embed(t, dim) for t in texts]


def _build_fake_tool_map(case: Case) -> dict:
    """One fake tool function per known tool name, sharing a single (tool_name,
    query)-keyed lookup built from every lane's `tool_calls`/`tool_results`. A
    lookup miss returns an empty list — a tool call the case didn't script behaves
    like a source with nothing relevant, not a network error."""
    lookup: dict[tuple[str, str], object] = {}
    all_lanes = list(case.lanes)
    if case.single and case.single.get("tool_calls"):
        # the single-pipeline script reuses the same lookup table
        class _StubLane:
            pass

        stub = _StubLane()
        stub.tool_calls = case.single["tool_calls"]
        stub.tool_results = case.single.get("tool_results", {})
        all_lanes.append(stub)

    for lane in all_lanes:
        for tc in lane.tool_calls:
            name, query = tc["name"], tc["args"]["query"]
            lookup[(name, query)] = lane.tool_results.get(name, [])

    def _make(tool_name: str):
        async def _fake(query: str = "", **kwargs):
            payload = lookup.get((tool_name, query), [])
            if isinstance(payload, Exception):
                raise payload
            return payload

        return _fake

    return {name: _make(name) for name in ALL_TOOL_NAMES}


async def _fake_get_known_ids():
    return []


async def _fake_start_run(goal: str, context: str) -> str:
    return f"eval-{uuid.uuid4()}"


async def _fake_save_progress(run_id: str, trace: list) -> None:
    return None


async def _fake_save_items(items: list[dict], run_id: str | None = None) -> int:
    return 0


async def _fake_finish_run(run_id: str, trace: list, final: dict, new_items_count: int):
    return None


def patches_for(case: Case) -> list:
    """The full set of `unittest.mock.patch` context managers needed to run either
    pipeline against `case` with zero network/DB access. Caller enters them all
    (e.g. via `contextlib.ExitStack`)."""
    return [
        patch("agent.fleet.get_known_ids", _fake_get_known_ids),
        patch("agent.fleet.start_run", _fake_start_run),
        patch("agent.fleet.save_progress", _fake_save_progress),
        patch("agent.orchestrator.get_known_ids", _fake_get_known_ids),
        patch("agent.orchestrator.start_run", _fake_start_run),
        patch("agent.orchestrator.save_items", _fake_save_items),
        patch("agent.orchestrator.finish_run", _fake_finish_run),
        patch.dict("agent.runtime.TOOL_MAP", _build_fake_tool_map(case), clear=True),
    ]
