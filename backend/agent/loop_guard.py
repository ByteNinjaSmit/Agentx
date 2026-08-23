"""Explicit loop/no-progress detection for the ReAct research loop.

`RESEARCH_MAX_STEPS` in `fleet.py` already stops a researcher from running forever
— but says nothing about a researcher spinning on the identical query without
new evidence *within* that bound. This makes that specific pattern detectable and
interruptible in-run, not just eventually capped: same tool + same normalized
query + no new evidence, repeated, gets blocked before the redundant call is
issued, and the researcher is told so in its next tool result so it can try
something else. `observability/trace_analyzer.py::detect_duplicate_tool_calls`
covers the same failure mode post-hoc, after a run finishes; this is the live,
in-run counterpart that prevents the waste in the first place — the two are
complementary, not redundant (a duplicate this guard prevented never becomes
`fallback_used`/latency evidence for the post-hoc detector to find)."""

import json
import re
from dataclasses import dataclass, field


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def call_signature(tool: str, args: dict) -> str:
    return f"{tool}:{_norm(str(args.get('query', '')))}"


@dataclass
class LoopGuard:
    """One instance scopes one bounded tool-using loop (one fleet research lane,
    or the whole single-agent run). `should_block()` before executing a tool call,
    `record()` after (with the tool's raw result) so the next `should_block()` call
    knows whether the last attempt actually produced anything new.

    `max_no_progress_repeats`: how many times the identical (tool, query) signature
    may be called and come back with the identical raw result before the next
    identical attempt is blocked. Default 1 — the system prompts already ask the
    model never to repeat an identical query; this is the code-level backstop for
    when it does anyway."""

    max_no_progress_repeats: int = 1
    _seen: dict[str, int] = field(default_factory=dict)
    _no_progress_streak: dict[str, int] = field(default_factory=dict)
    _last_result_hash: dict[str, int] = field(default_factory=dict)
    loop_events: list[dict] = field(default_factory=list)

    def should_block(self, tool: str, args: dict) -> str | None:
        """Returns a human-readable reason if this call is a detected loop and
        should be blocked, else None. Call BEFORE executing the tool."""
        sig = call_signature(tool, args)
        if self._no_progress_streak.get(sig, 0) >= self.max_no_progress_repeats:
            reason = (
                f"{tool} already called with this exact query {self._seen.get(sig, 0)} time(s), "
                "yielding no new evidence each time — blocking the repeat."
            )
            self.loop_events.append(
                {
                    "tool": tool,
                    "query": args.get("query"),
                    "repeat_count": self._seen.get(sig, 0),
                    "reason": reason,
                }
            )
            return reason
        return None

    def record(self, tool: str, args: dict, raw_result) -> None:
        """Call AFTER a real tool execution (never for a blocked call — its outcome
        is already known: identical to last time)."""
        sig = call_signature(tool, args)
        result_hash = hash(json.dumps(raw_result, default=str, sort_keys=True))
        made_progress = self._seen.get(sig, 0) == 0 or self._last_result_hash.get(sig) != result_hash
        self._seen[sig] = self._seen.get(sig, 0) + 1
        self._no_progress_streak[sig] = 0 if made_progress else self._no_progress_streak.get(sig, 0) + 1
        self._last_result_hash[sig] = result_hash
