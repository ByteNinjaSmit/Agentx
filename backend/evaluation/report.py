"""Renders a `Summary` (and the raw per-run outcomes) as a plain-text console
report. No dependency beyond the stdlib — this is meant to run in CI as easily as
on a laptop."""

from .metrics import CaseRunOutcome, Summary


def render(outcomes: list[CaseRunOutcome], summary: Summary) -> str:
    lines = []
    lines.append("=" * 78)
    lines.append("AgentX Ladder 6 evaluation report")
    lines.append("=" * 78)
    lines.append(
        f"Runs: {summary.total_runs}  |  Checks: {summary.passed_checks}/{summary.total_checks} passed "
        f"({_pct(summary.passed_checks, summary.total_checks)})  |  Errored runs: {summary.runs_with_error}"
    )
    lines.append("")

    lines.append("By category:")
    for cat, stats in sorted(summary.by_category.items()):
        lines.append(
            f"  {cat:<14} runs={stats['runs']:<3} checks={stats['passed']}/{stats['checks']} "
            f"({_pct(stats['passed'], stats['checks'])})"
        )
    lines.append("")

    lines.append("By check:")
    for name, stats in sorted(summary.by_check.items()):
        lines.append(f"  {name:<38} {stats['passed']}/{stats['runs']} ({_pct(stats['passed'], stats['runs'])})")
    lines.append("")

    if any(v < 1.0 for v in summary.consistency.values()):
        lines.append("Consistency (pass rate across repeats, only cases run more than once):")
        for (case_id, pipeline), rate in sorted(summary.consistency.items()):
            lines.append(f"  {case_id} [{pipeline}]  {rate:.0%}")
        lines.append("")

    lines.append("Failures:")
    any_failure = False
    for o in outcomes:
        if o.error:
            any_failure = True
            lines.append(f"  FAIL {o.case_id} [{o.pipeline}] rep{o.repeat_index}: RUN ERROR - {o.error}")
            continue
        for r in o.results:
            if not r.passed:
                any_failure = True
                lines.append(f"  FAIL {o.case_id} [{o.pipeline}] rep{o.repeat_index}: {r.name} - {r.detail}")
    if not any_failure:
        lines.append("  (none)")

    lines.append("=" * 78)
    return "\n".join(lines)


def _pct(n: int, d: int) -> str:
    return f"{(n / d * 100):.0f}%" if d else "n/a"
