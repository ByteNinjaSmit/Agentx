"""LLM-as-judge: the second of the three evaluator trust tiers documented in
docs/ROADMAP.md § 8 (deterministic/code, LLM judge, human) — for grading what a
regex can't: whether an answer reads as accurate, evidence-grounded, complete, and
honest about its own uncertainty, not just structurally correct.

Never runs the agent itself — grades whatever `final` result the caller already
has. In `judge_runner.py` that `final` still comes from evaluation.fakes' scripted,
deterministic pipeline run (same FakeProvider as evaluation.runner.py), so the
agent's own output stays fixed and reproducible; the judge call is the only live
model call, which is this tier's own inherent property (a judge is stochastic by
nature) rather than a harness bug. Reuses `agent.providers.LLMProvider` and
`agent.runtime.extract_json` — no new provider abstraction, no new JSON parser.
"""

import json
from dataclasses import dataclass

from agent.providers import LLMProvider
from agent.runtime import extract_json

JUDGE_SYSTEM = """You are an impartial evaluator grading one competitive-intelligence
agent's output. You did not produce this output and have no stake in it reading well.

Grade ONLY against the EVIDENCE provided below — never reward a claim because you
happen to know it's true from your own training, and never penalize a claim the
evidence supports even if it conflicts with what you'd otherwise expect. This
project's "cite or refuse" contract means every claim in the answer should trace to
something in the evidence; your job is to check whether it actually does, not to
fact-check the world.

Score each 0.0-1.0:
- "accuracy": do the claims in the candidate answer follow from the evidence,
  without overstating, misreading, or reversing what a finding actually says?
- "groundedness": is every substantive claim traceable to a specific evidence item,
  rather than asserted on the answer's own authority?
- "completeness": given the evidence available, does the answer surface the
  findings that actually matter, rather than a partial or padded subset of them?
- "evidence_quality": is the evidence itself high-signal (real, specific, on-topic
  findings) rather than sparse, generic, or off-topic?
- "uncertainty_handling": where the evidence is incomplete, absent, or conflicting,
  does the answer say so honestly, rather than asserting confidence it hasn't earned?

Also report:
- "unsupported_claims": an integer count of specific claims in the candidate answer
  you could not trace to any evidence item.
- "overall": 0.0-1.0, your holistic judgement — not required to be an average of
  the scores above.
- "reason": two or three sentences explaining the scores, citing what evidence (or
  its absence) drove them.

Output ONLY this JSON object, no prose and no markdown fences:
{"accuracy": 0.0, "groundedness": 0.0, "completeness": 0.0, "evidence_quality": 0.0,
"uncertainty_handling": 0.0, "unsupported_claims": 0, "overall": 0.0, "reason": "..."}"""

_SCORE_FIELDS = (
    "accuracy",
    "groundedness",
    "completeness",
    "evidence_quality",
    "uncertainty_handling",
    "overall",
)


@dataclass
class JudgeResult:
    accuracy: float
    groundedness: float
    completeness: float
    evidence_quality: float
    uncertainty_handling: float
    unsupported_claims: int
    overall: float
    reason: str
    raw_text: str
    parse_ok: bool


def _clamp01(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _as_int(value) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def build_prompt(goal: str, project_context: str, final: dict, reference: str | None = None) -> str:
    """Goal, evidence, and candidate answer as clearly separated fields — the
    candidate output never gets to phrase its own grading criteria; the judge only
    ever sees it labeled "CANDIDATE ANSWER"."""
    evidence = [
        {
            "title": it.get("title"),
            "source": it.get("source"),
            "organization": it.get("organization"),
            "summary": it.get("summary"),
            "relevance_reason": it.get("relevance_reason"),
            "impact_1_10": it.get("impact_1_10"),
        }
        for it in final.get("items", [])
    ]
    parts = [
        f"USER GOAL:\n{goal}",
        f"PROJECT CONTEXT:\n{project_context}",
        f"EVIDENCE (what the agent actually retrieved and kept — {len(evidence)} item(s)):\n"
        f"{json.dumps(evidence, default=str)[:40000]}",
        f"COVERAGE GAPS THE AGENT REPORTED:\n{final.get('coverage_gaps') or []}",
        f"CANDIDATE ANSWER (executive summary — grade this):\n{final.get('executive_summary', '')}",
    ]
    if final.get("strategy"):
        parts.append(f"CANDIDATE STRATEGY (grade this too, if present):\n{json.dumps(final['strategy'], default=str)[:8000]}")
    if reference:
        parts.append(
            "REFERENCE ANSWER (what a strong answer would cover, for comparison only "
            f"— the candidate need not match it verbatim):\n{reference}"
        )
    return "\n\n".join(parts)


def parse_judge_response(text: str) -> JudgeResult:
    parsed = extract_json(text)
    if parsed is None:
        return JudgeResult(0, 0, 0, 0, 0, 0, 0.0, "judge returned no parseable JSON", text, False)
    return JudgeResult(
        accuracy=_clamp01(parsed.get("accuracy")),
        groundedness=_clamp01(parsed.get("groundedness")),
        completeness=_clamp01(parsed.get("completeness")),
        evidence_quality=_clamp01(parsed.get("evidence_quality")),
        uncertainty_handling=_clamp01(parsed.get("uncertainty_handling")),
        unsupported_claims=_as_int(parsed.get("unsupported_claims")),
        overall=_clamp01(parsed.get("overall")),
        reason=str(parsed.get("reason") or ""),
        raw_text=text,
        parse_ok=True,
    )


async def judge(
    goal: str,
    project_context: str,
    final: dict,
    provider: LLMProvider,
    reference: str | None = None,
) -> JudgeResult:
    prompt = build_prompt(goal, project_context, final, reference)
    turn = await provider.complete(JUDGE_SYSTEM, prompt)
    return parse_judge_response(turn.text)
