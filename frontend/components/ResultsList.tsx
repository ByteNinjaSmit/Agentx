"use client";

import { useMemo, useState } from "react";
import type { FinalResult } from "@/lib/types";

// The final JSON isn't schema-validated the way save_item's tool args are — Gemini
// occasionally emits a structured object where a plain string was asked for (e.g.
// a coverage_gaps entry as {reason, source} instead of "source: reason"). Never
// render a raw object as a React child — coerce defensively instead of crashing.
function asText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    if (typeof obj.source === "string" && typeof obj.reason === "string") {
      return `${obj.source}: ${obj.reason}`;
    }
    return JSON.stringify(value);
  }
  return String(value);
}

function impactColor(score: number) {
  if (score >= 8) return "bg-danger/10 text-danger border border-danger/20 shadow-[0_0_10px_rgba(239,68,68,0.1)]";
  if (score >= 5) return "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 shadow-[0_0_10px_rgba(245,158,11,0.1)]";
  return "bg-surface-2 text-foreground/60 border border-border";
}

export default function ResultsList({ final, running }: { final: FinalResult | null; running: boolean }) {
  const [activeSources, setActiveSources] = useState<Set<string> | null>(null);

  const sources = useMemo(() => {
    const set = new Set<string>();
    final?.items.forEach((it) => set.add(it.source));
    return [...set].sort();
  }, [final]);

  const visible = useMemo(() => {
    if (!final) return [];
    const filtered = activeSources
      ? final.items.filter((it) => activeSources.has(it.source))
      : final.items;
    return [...filtered].sort((a, b) => b.impact_1_10 - a.impact_1_10);
  }, [final, activeSources]);

  if (!final || running) return null;

  function toggleSource(source: string) {
    setActiveSources((prev) => {
      const base = prev ?? new Set(sources);
      const next = new Set(base);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  }

  const isActive = (source: string) => !activeSources || activeSources.has(source);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-foreground/50">
          Ranked brief
        </h2>
        <div className="flex items-center gap-2">
        {final.new_items_count != null && (
          <span className="text-[11px] rounded-full px-2.5 py-0.5 font-medium border border-border bg-surface-2 text-foreground/60">
            {final.new_items_count} new
            {final.alerted_count ? ` · ${final.alerted_count} alerted` : ""}
          </span>
        )}
        <span
          className={`text-[11px] rounded-full px-2.5 py-0.5 font-medium border ${
            final.coverage_ok
              ? "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20"
              : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
          }`}
        >
          {final.coverage_ok
            ? (final.coverage_gaps?.length ?? 0) > 0
              ? "coverage ok · gaps noted"
              : "coverage ok"
            : "coverage thin"}
        </span>
        </div>
      </div>

      {final.executive_summary && (
        <div className="rounded-xl border border-accent/25 bg-accent/5 px-4 py-3.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-accent mb-1.5">
            Executive summary
          </p>
          <p className="text-sm text-foreground/80 leading-relaxed">{asText(final.executive_summary)}</p>
        </div>
      )}

      {(final.coverage_gaps?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-700 dark:text-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.05)]">
          <p className="font-semibold mb-1.5 flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-amber-500 animate-pulse" />
            Coverage gaps — flagged honestly, not silently dropped:
          </p>
          <ul className="list-disc list-inside space-y-0.5">
            {final.coverage_gaps!.map((g, i) => (
              <li key={i}>{asText(g)}</li>
            ))}
          </ul>
        </div>
      )}

      {sources.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          {sources.map((s) => (
            <button
              key={s}
              onClick={() => toggleSource(s)}
              className={`text-[11px] rounded-full px-3 py-1 font-medium transition-all duration-300 border ${
                isActive(s)
                  ? "border-accent/30 bg-gradient-to-r from-accent/10 to-accent/5 text-accent shadow-[0_0_10px_var(--accent-soft)]"
                  : "border-border bg-surface-2 text-foreground/40 hover:text-foreground/70"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {final.items.length === 0 && (
        <p className="text-sm text-foreground/40 italic">no new items — already known</p>
      )}
      {final.items.length > 0 && visible.length === 0 && (
        <p className="text-sm text-foreground/40 italic">no items match the selected sources</p>
      )}

      <div className="space-y-2">
        {visible.map((it, i) => (
          <div
            key={i}
            className="animate-fade-in-up surface-card p-5 group"
          >
            <div className="flex justify-between items-start gap-4">
              <a
                href={it.url}
                target="_blank"
                rel="noreferrer"
                className="font-semibold text-sm text-foreground/90 group-hover:text-accent transition-colors decoration-accent/30 hover:underline underline-offset-4"
              >
                {asText(it.title)}
              </a>
              <span
                className={`text-[10px] uppercase font-bold tracking-wider shrink-0 rounded-full px-2.5 py-1 ${impactColor(it.impact_1_10)}`}
              >
                {asText(it.source)} · {it.impact_1_10}/10
              </span>
            </div>
            <div className="flex items-center gap-2 mt-1">
              {it.organization && (
                <span className="text-[10px] font-medium text-foreground/40 shrink-0">
                  {asText(it.organization)} ·
                </span>
              )}
              <p className="text-sm text-foreground/50">{asText(it.relevance_reason)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
