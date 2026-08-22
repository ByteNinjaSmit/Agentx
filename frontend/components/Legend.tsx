"use client";

import { useState } from "react";

export default function Legend() {
  const [open, setOpen] = useState(false);

  return (
    <div className="surface-card overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-sm font-medium flex items-center gap-2">
          <span className="text-accent">?</span> How to read this
        </span>
        <span className={`text-foreground/40 transition-transform ${open ? "rotate-90" : ""}`}>
          ›
        </span>
      </button>

      {open && (
        <div className="border-t border-border px-4 py-4 space-y-4 text-xs text-foreground/60 bg-surface-2/30">
          <div>
            <p className="font-medium text-foreground/80 mb-1">Two agent sources</p>
            <p>
              <span className="text-accent font-medium">Local backend (SSE)</span> and{" "}
              <span className="text-accent font-medium">n8n webhook</span> are two independent
              implementations of the same agent (Python/FastAPI vs. a visual n8n workflow), both
              powered by Gemini. Same behavior, different plumbing — useful for comparing
              approaches.
            </p>
          </div>

          <div>
            <p className="font-medium text-foreground/80 mb-1">Reasoning trace</p>
            <ul className="space-y-1">
              <li>
                <span className="text-foreground/40">→</span> a tool call that returned usable
                results
              </li>
              <li>
                <span className="text-danger">✕</span> a tool call that failed (rate limit,
                timeout, error) — the agent is expected to retry or flag it, not silently ignore it
              </li>
              <li>
                colored pills like{" "}
                <span className="rounded px-1 py-0.5 bg-teal-500/10 text-teal-600 dark:text-teal-400">
                  search_papers(…)
                </span>{" "}
                show which tool was called and with what input
              </li>
            </ul>
          </div>

          <div>
            <p className="font-medium text-foreground/80 mb-1">Ranked brief</p>
            <ul className="space-y-1">
              <li>
                <span className="rounded px-1.5 py-0.5 bg-teal-500/10 text-teal-600 dark:text-teal-400">
                  coverage ok
                </span>{" "}
                — every source the agent tried came back with usable results
              </li>
              <li>
                <span className="rounded px-1.5 py-0.5 bg-amber-500/10 text-amber-600 dark:text-amber-400">
                  coverage ok · gaps noted
                </span>{" "}
                — got enough to answer, but honestly logged a source that failed after retrying
                (see the amber gaps box)
              </li>
              <li>
                <span className="rounded px-1.5 py-0.5 bg-danger/10 text-danger">
                  coverage thin
                </span>{" "}
                — not enough usable results to be confident; treat findings as partial
              </li>
              <li>
                <span className="text-foreground/50">source · N/10</span> — impact score:
                weighted from source authority (patent/paper &gt; news &gt; forum post), recency,
                and relevance to your project context
              </li>
              <li>
                <span className="italic">&quot;no new items — already known&quot;</span> means the
                agent checked its memory and everything it found this run was already saved from a
                previous run — that&apos;s the delta-tracking working correctly, not a bug
              </li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
