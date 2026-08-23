"""Aggregates raw per-run `EvalResult`s into category/pipeline summaries."""

from dataclasses import dataclass, field

from .evaluators import EvalResult


@dataclass
class CaseRunOutcome:
    case_id: str
    category: str
    pipeline: str
    repeat_index: int
    results: list[EvalResult]
    error: str | None = None

    @property
    def passed_all(self) -> bool:
        return self.error is None and all(r.passed for r in self.results)


@dataclass
class Summary:
    total_runs: int = 0
    total_checks: int = 0
    passed_checks: int = 0
    runs_with_error: int = 0
    by_category: dict = field(default_factory=dict)  # category -> {"runs": n, "checks": n, "passed": n}
    by_check: dict = field(default_factory=dict)  # check name -> {"runs": n, "passed": n}
    by_pipeline: dict = field(default_factory=dict)  # pipeline -> {"runs": n, "checks": n, "passed": n}
    consistency: dict = field(default_factory=dict)  # (case_id, pipeline) -> pass-rate across repeats


def summarize(outcomes: list[CaseRunOutcome]) -> Summary:
    s = Summary()
    per_case: dict[tuple, list[bool]] = {}

    for o in outcomes:
        s.total_runs += 1
        if o.error:
            s.runs_with_error += 1
        cat = s.by_category.setdefault(o.category, {"runs": 0, "checks": 0, "passed": 0})
        cat["runs"] += 1
        pipe = s.by_pipeline.setdefault(o.pipeline, {"runs": 0, "checks": 0, "passed": 0})
        pipe["runs"] += 1
        for r in o.results:
            s.total_checks += 1
            cat["checks"] += 1
            pipe["checks"] += 1
            chk = s.by_check.setdefault(r.name, {"runs": 0, "passed": 0})
            chk["runs"] += 1
            if r.passed:
                s.passed_checks += 1
                cat["passed"] += 1
                pipe["passed"] += 1
                chk["passed"] += 1
        per_case.setdefault((o.case_id, o.pipeline), []).append(o.passed_all)

    for key, outcomes_bool in per_case.items():
        s.consistency[key] = sum(outcomes_bool) / len(outcomes_bool)

    return s
