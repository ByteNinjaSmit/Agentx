"""Deterministic, code-only evaluators — no LLM judge. Each takes a case, the
pipeline's final result, the full stream of events from that run, and which
pipeline ("fleet" or "single") produced it, and returns an `EvalResult` or `None`
if the check does not apply.

Kept deliberately code-only per docs/ROADMAP.md § 8's trust ordering: these are the
checks that can be graded with certainty, so they run before reaching for anything
softer (an LLM judge, a human). Every check here is something the fleet already
claims to do (verify grounding, self-evaluate coverage, replan, detect conflicts,
recover from a failed tool, refuse on insufficient evidence) — this module is what
turns those claims into a pass/fail on a fixed, repeatable case.

Three checks (conflict detection, replanning, verifier-side hallucination rejection)
only make sense for `pipeline=fleet` — `orchestrator.py`'s single loop has no
verifier, no conflict-resolution step, and no replanning mechanism, so its output
shape has no `conflicts`/`self_evaluation` key and its trace has no `verifier`
step. Those evaluators return `None` (not a failure) for `pipeline=single`; that
absence of a defense is itself the point of the fleet-vs-single comparison, not a
harness bug."""

from dataclasses import dataclass

from .datasets import Case


@dataclass
class EvalResult:
    name: str
    passed: bool
    detail: str


def _kept_ids(final: dict) -> set:
    return {str(it.get("external_id")) for it in final.get("items", [])}


def eval_task_success(case: Case, final: dict, events: list[dict], pipeline: str) -> EvalResult | None:
    # a pipeline-specific override (e.g. "expected_kept_ids_single") wins when
    # present — used where the honest single-loop outcome genuinely differs from
    # the fleet's (replanning recovers coverage the single loop structurally can't).
    expected = case.expect.get(f"expected_kept_ids_{pipeline}", case.expect.get("expected_kept_ids"))
    if expected is None:
        return None
    kept = _kept_ids(final)
    missing = expected - kept
    passed = not missing
    detail = f"expected kept={sorted(expected)}, actual kept={sorted(kept)}"
    if missing:
        detail += f"; MISSING={sorted(missing)}"
    return EvalResult("task_success", passed, detail)


def eval_coverage_ok_matches(case: Case, final: dict, events: list[dict], pipeline: str) -> EvalResult | None:
    if "coverage_ok" not in case.expect:
        return None
    expected = bool(case.expect["coverage_ok"])
    actual = bool(final.get("coverage_ok"))
    return EvalResult(
        "coverage_ok_matches_expected", actual == expected,
        f"expected coverage_ok={expected}, got {actual}",
    )


def eval_gap_reported(case: Case, final: dict, events: list[dict], pipeline: str) -> EvalResult | None:
    needle = case.expect.get("expect_gap_containing")
    if not needle:
        return None
    gaps = " | ".join(final.get("coverage_gaps") or [])
    passed = needle in gaps
    return EvalResult("recovery_gap_reported", passed, f"needle={needle!r}, gaps={final.get('coverage_gaps')}")


def eval_recovery_run_completed(case: Case, final: dict, events: list[dict], pipeline: str) -> EvalResult | None:
    if case.category != "tool_failure":
        return None
    passed = bool(final) and isinstance(final.get("items"), list)
    return EvalResult(
        "recovery_run_completed", passed,
        "final result produced despite a forced tool failure" if passed else "no usable final result",
    )


def eval_refusal_on_insufficient_evidence(case: Case, final: dict, events: list[dict], pipeline: str) -> EvalResult | None:
    if not case.expect.get("expect_no_fabricated_conclusion"):
        return None
    passed = len(final.get("items", [])) == 0 and not final.get("coverage_ok", True)
    return EvalResult(
        "refusal_on_insufficient_evidence", passed,
        f"items={len(final.get('items', []))}, coverage_ok={final.get('coverage_ok')}",
    )


def eval_conflict_detected(case: Case, final: dict, events: list[dict], pipeline: str) -> EvalResult | None:
    org = case.expect.get("expect_conflict_org")
    if not org or pipeline != "fleet":
        return None
    conflicts = final.get("conflicts") or []
    passed = any(c.get("organization") == org for c in conflicts)
    return EvalResult("conflict_detected_and_resolved", passed, f"conflicts={conflicts}")


def eval_replanning_triggered(case: Case, final: dict, events: list[dict], pipeline: str) -> EvalResult | None:
    if "expect_replanned" not in case.expect or pipeline != "fleet":
        return None
    se = final.get("self_evaluation") or {}
    expected = bool(case.expect["expect_replanned"])
    actual = bool(se.get("replanned"))
    return EvalResult("replanning_triggered", actual == expected, f"expected replanned={expected}, self_evaluation={se}")


def eval_hallucination_rejected(case: Case, final: dict, events: list[dict], pipeline: str) -> EvalResult | None:
    titles = case.expect.get("expected_rejected_titles")
    if not titles or pipeline != "fleet":
        return None
    kept_titles = {it.get("title") for it in final.get("items", [])}
    leaked = titles & kept_titles
    rejected_titles = set()
    for e in events:
        if e.get("type") == "trace" and e.get("agent") == "verifier":
            for r in e.get("rejected") or []:
                if r.get("title"):
                    rejected_titles.add(r["title"])
    caught = titles <= rejected_titles
    passed = caught and not leaked
    detail = f"expected_rejected={titles}, verifier_rejected={rejected_titles}, leaked_into_final={leaked}"
    return EvalResult("hallucination_rejected_by_verifier", passed, detail)


def eval_states_assumption(case: Case, final: dict, events: list[dict], pipeline: str) -> EvalResult | None:
    if not case.expect.get("expect_states_assumption"):
        return None
    summary = (final.get("executive_summary") or "").lower()
    passed = "assum" in summary or "interpret" in summary
    return EvalResult("states_assumption_on_ambiguous_goal", passed, f"executive_summary={final.get('executive_summary')!r}")


ALL_EVALUATORS = [
    eval_task_success,
    eval_coverage_ok_matches,
    eval_gap_reported,
    eval_recovery_run_completed,
    eval_refusal_on_insufficient_evidence,
    eval_conflict_detected,
    eval_replanning_triggered,
    eval_hallucination_rejected,
    eval_states_assumption,
]


def evaluate(case: Case, final: dict, events: list[dict], pipeline: str) -> list[EvalResult]:
    results = []
    for fn in ALL_EVALUATORS:
        result = fn(case, final, events, pipeline)
        if result is not None:
            results.append(result)
    return results
