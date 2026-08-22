"""Ladder 6 evaluation harness for AgentX.

Runs the real `agent.fleet.run_fleet_stream` / `agent.orchestrator.run_agent_stream`
graphs against scripted (fake) providers and tools instead of live models/APIs/DB, so
the *framework mechanics* — verification, coverage self-eval, replanning, tool
fallback recovery, conflict detection, cite-or-refuse — get checked deterministically
and repeatably, without needing network access, API keys, or a running Postgres.

Entry point: `python -m evaluation.runner` from `backend/`.
"""
