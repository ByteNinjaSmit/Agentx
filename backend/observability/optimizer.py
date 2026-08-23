"""Turns one `trace_analyzer.Finding` into one `PolicyAction` from a small, fixed
vocabulary. No LLM proposes or writes code here — `propose()` is a plain lookup by
finding category, and `PolicyAction.apply()` only ever flips a field on
`observability.policy.CURRENT` that a real call site already reads.

Only `unreliable_primary_source` maps to an action this codebase actually enforces
today (`agent/tools.py::search_papers`'s circuit breaker) — everything else returns
`no_action` with an honest reason rather than claiming a fix that has no call site
behind it yet. `policy.Policy.suppress_duplicate_tool_calls` and
`.research_max_steps_override` exist as reserved knobs for exactly this reason: the
next categories to wire up, not yet claimed as working."""

from dataclasses import dataclass

from . import policy
from .trace_analyzer import Finding


@dataclass
class PolicyAction:
    action: str
    target: str
    reason: str
    evidence: list[str]
    confidence: float
    expected_impact: dict

    def apply(self) -> None:
        _APPLIERS[self.action](self.target)


def _apply_fallback_after_first_failure(target: str) -> None:
    policy.CURRENT.circuit_open.add(target)


def _apply_no_action(target: str) -> None:
    return None


_APPLIERS = {
    "fallback_after_first_failure": _apply_fallback_after_first_failure,
    "no_action": _apply_no_action,
}


def propose(finding: Finding) -> PolicyAction:
    if finding.category == "unreliable_primary_source" and finding.target:
        return PolicyAction(
            action="fallback_after_first_failure",
            target=finding.target,
            reason=(
                f"{finding.target} failed on its primary source repeatedly this run; "
                "skip straight to the fallback source instead of paying the primary's "
                "latency tax on every subsequent call."
            ),
            evidence=finding.evidence,
            confidence=finding.confidence,
            expected_impact={"latency": "lower", "tool_calls": "unchanged", "errors": "lower"},
        )
    return PolicyAction(
        action="no_action",
        target=finding.target,
        reason=f"No automated fix is wired up for '{finding.category}' yet — flagging for a human.",
        evidence=finding.evidence,
        confidence=finding.confidence,
        expected_impact={},
    )
