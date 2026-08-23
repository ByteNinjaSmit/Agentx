"""The one piece of mutable runtime state in the observability closed loop: a small,
explicit set of tunable knobs that production code reads at call time. Every field
here starts at the value that reproduces today's hardcoded behaviour exactly —
nothing changes for a run that never gets diagnosed and optimized.

Changed only two ways: `optimizer.PolicyAction.apply()` (an explicit, diagnosed
decision) or `reset()` (restores defaults — used between a benchmark's BEFORE and
AFTER runs so they start from the same clean state)."""

from dataclasses import dataclass, field


@dataclass
class Policy:
    # Tool names for which the primary source is skipped in favour of its fallback
    # every call, for the rest of the process — set by the "fallback_after_first_
    # failure" action. Read by agent/tools.py::search_papers.
    circuit_open: set[str] = field(default_factory=set)

    # When true, a tool call whose (tool, normalized query) was already issued this
    # run is served from the existing result rather than re-issued. Not yet wired
    # into a call site — reserved for the "suppress_duplicate_queries" action.
    suppress_duplicate_tool_calls: bool = False

    # Overrides agent/fleet.py's RESEARCH_MAX_STEPS when set — reserved for the
    # "reduce_research_steps" action.
    research_max_steps_override: int | None = None


CURRENT = Policy()


def reset() -> None:
    CURRENT.circuit_open.clear()
    CURRENT.suppress_duplicate_tool_calls = False
    CURRENT.research_max_steps_override = None
