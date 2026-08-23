"""Ranks `trace_analyzer.Finding`s and turns the dominant one into the diagnosis
shape the closed loop reports and benchmarks: root cause, severity, evidence,
confidence, and the optimizer's recommended action. Ranking is a fixed severity
order broken by confidence — deterministic, so the same trace always yields the
same diagnosis."""

from . import optimizer
from .trace_analyzer import Finding, analyze

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def rank(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (_SEVERITY_RANK.get(f.severity, 0), f.confidence), reverse=True)


def analyze_and_rank(trace: list[dict], final: dict) -> list[Finding]:
    return rank(analyze(trace, final))


def to_dict(ranked: list[Finding]) -> dict:
    if not ranked:
        return {
            "root_cause": "none",
            "category": "none",
            "severity": "low",
            "evidence": [],
            "confidence": 1.0,
            "recommended_action": "no_action",
            "action_detail": {
                "target": "",
                "reason": "no issues detected in this trace",
                "confidence": 1.0,
            },
            "expected_impact": {},
        }
    top = ranked[0]
    action = optimizer.propose(top)
    label = f"{top.category}:{top.target}" if top.target else top.category
    return {
        "root_cause": label,
        "category": top.category,
        "severity": top.severity,
        "evidence": top.evidence,
        "confidence": round(top.confidence, 2),
        "recommended_action": action.action,
        "action_detail": {
            "target": action.target,
            "reason": action.reason,
            "confidence": round(action.confidence, 2),
        },
        "expected_impact": action.expected_impact,
        "other_findings": [
            {"category": f.category, "severity": f.severity, "target": f.target}
            for f in ranked[1:]
        ],
    }


def diagnose(trace: list[dict], final: dict) -> dict:
    return to_dict(analyze_and_rank(trace, final))
