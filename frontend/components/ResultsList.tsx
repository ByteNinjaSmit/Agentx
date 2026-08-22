"use client";

import { useMemo, useState } from "react";
import type { FinalResult } from "@/lib/types";

function impactColor(score: number) {
  if (score >= 8) return "bg-danger/10 text-danger";
  if (score >= 5) return "bg-amber-500/10 text-amber-600 dark:text-amber-400";
  return "bg-surface-2 text-foreground/50";
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
        <span
          className={`text-[11px] rounded px-1.5 py-0.5 ${
            final.coverage_ok
              ? "bg-teal-500/10 text-teal-600 dark:text-teal-400"
              : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
          }`}
        >
          {final.coverage_ok
            ? (final.coverage_gaps?.length ?? 0) > 0
              ? "coverage ok · gaps noted"
              : "coverage ok"
            : "coverage thin"}
        </span>
      </div>

      {(final.coverage_gaps?.length ?? 0) > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <p className="font-medium mb-1">Coverage gaps — flagged honestly, not silently dropped:</p>
          <ul className="list-disc list-inside space-y-0.5">
            {final.coverage_gaps!.map((g, i) => (
              <li key={i}>{g}</li>
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
              className={`text-[11px] rounded-full px-2 py-0.5 border transition-colors ${
                isActive(s)
                  ? "border-accent/50 bg-accent/10 text-accent"
                  : "border-border text-foreground/40"
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
            className="animate-fade-in-up surface-card p-4"
          >
            <div className="flex justify-between items-start gap-2">
              <a
                href={it.url}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-sm hover:underline"
              >
                {it.title}
              </a>
              <span
                className={`text-[11px] shrink-0 rounded px-1.5 py-0.5 ${impactColor(it.impact_1_10)}`}
              >
                {it.source} · {it.impact_1_10}/10
              </span>
            </div>
            <p className="text-sm text-foreground/50 mt-1">{it.relevance_reason}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
