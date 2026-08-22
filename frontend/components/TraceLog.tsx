"use client";

import { useEffect, useRef } from "react";
import type { Step } from "@/lib/types";

const TOOL_COLORS = [
  "bg-teal-500/10 text-teal-600 dark:text-teal-400",
  "bg-purple-500/10 text-purple-600 dark:text-purple-400",
  "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  "bg-sky-500/10 text-sky-600 dark:text-sky-400",
];

function toolColor(tool: string) {
  let hash = 0;
  for (let i = 0; i < tool.length; i++) hash = (hash * 31 + tool.charCodeAt(i)) | 0;
  return TOOL_COLORS[Math.abs(hash) % TOOL_COLORS.length];
}

function preview(value: unknown, max = 280) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (!text) return null;
  return text.length > max ? text.slice(0, max) + "…" : text;
}

export default function TraceLog({ steps, running }: { steps: Step[]; running: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [steps.length]);

  if (steps.length === 0 && !running) return null;

  return (
    <div className="space-y-2">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-foreground/50">
        Reasoning trace
      </h2>
      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        className="rounded-md border border-border bg-surface font-mono text-[13px] max-h-80 overflow-y-auto p-3 space-y-3"
      >
        {steps.length === 0 && (
          <p className="text-foreground/40">
            waiting for first thought<span className="animate-blink">_</span>
          </p>
        )}
        {steps.map((s, i) => (
          <div key={i} className="animate-fade-in-up border-l-2 border-accent/50 pl-3">
            {s.thought && <p className="text-foreground/80 whitespace-pre-wrap">{s.thought}</p>}
            {s.calls.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {s.calls.map((c, j) => (
                  <span
                    key={j}
                    className={`rounded px-1.5 py-0.5 text-[11px] ${toolColor(c.tool)}`}
                    title={JSON.stringify(c.input)}
                  >
                    {c.tool}({preview(c.input, 60)})
                  </span>
                ))}
              </div>
            )}
            {preview(s.observation) && (
              <p className="text-foreground/40 mt-1">→ {preview(s.observation)}</p>
            )}
          </div>
        ))}
        {running && steps.length > 0 && (
          <p className="text-foreground/30">
            <span className="animate-blink">_</span>
          </p>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
