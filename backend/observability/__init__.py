"""The observability closed loop: trace diagnosis -> controlled failure ->
optimization -> before/after.

Every signal `trace_analyzer` reads is a field `agent/fleet.py` and
`agent/orchestrator.py` already emit into their trace/final shape — nothing new was
added to the pipelines to make diagnosis possible. Root-cause selection
(`root_cause.py`) and the optimizer's fix vocabulary (`optimizer.py`) are both
deterministic/rule-based, not LLM calls, for the same reason the fleet's Verifier is
code and not a model: a diagnosis has to be reproducible for a before/after
benchmark to mean anything. `policy.py` is the one piece of mutable runtime state —
a small, explicit set of tunable knobs that production code (currently
`agent/tools.py::search_papers`) reads at call time, only ever changed by an
`optimizer.PolicyAction.apply()` call, never automatically.

See docs/ARCHITECTURE.md ("Observability closed loop") and
`backend/evaluation/full_benchmark.py` for the end-to-end demonstration.
"""
