"use client";

import type { Strategy } from "@/lib/types";

const THREAT_STYLE: Record<string, string> = {
  high: "bg-danger/10 text-danger border-danger/20",
  medium: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  low: "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20",
};

const HORIZON_LABEL: Record<string, string> = {
  now: "now",
  quarter: "this quarter",
  year: "this year",
};

function List({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground/40">{title}</p>
      <ul className="mt-1.5 space-y-1 text-sm text-foreground/75">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-foreground/25">—</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The Strategist's output. Only rendered when the fleet pipeline ran — the single
 *  ReAct loop produces findings and a summary, but no competitive assessment. */
export default function StrategyPanel({ strategy }: { strategy?: Strategy }) {
  const competitors = strategy?.competitors ?? [];
  const actions = strategy?.recommended_actions ?? [];
  const hasContent =
    competitors.length ||
    actions.length ||
    strategy?.opportunities?.length ||
    strategy?.risks?.length;
  if (!hasContent) return null;

  return (
    <div className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-foreground/50">
        Strategist assessment
      </h2>

      {competitors.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {competitors.map((c) => (
            <div key={c.organization} className="surface-card p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="font-semibold text-sm">{c.organization}</p>
                <span
                  className={`shrink-0 rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                    THREAT_STYLE[c.threat_level] ?? "border-border bg-surface-2 text-foreground/60"
                  }`}
                >
                  {c.threat_level} threat
                </span>
              </div>
              {c.assessment && (
                <p className="mt-1.5 text-sm text-foreground/60">{c.assessment}</p>
              )}
              {c.evidence?.length ? (
                <ul className="mt-2 space-y-0.5">
                  {c.evidence.map((e, i) => (
                    <li key={i} className="truncate text-[11px] text-foreground/35" title={e}>
                      ↳ {e}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
      )}

      {actions.length > 0 && (
        <div className="surface-card p-4 space-y-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground/40">
            Recommended actions
          </p>
          {actions.map((a, i) => (
            <div key={i} className="flex items-start gap-3">
              <span className="mt-0.5 shrink-0 rounded-full border border-border bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-foreground/50">
                {HORIZON_LABEL[a.horizon ?? ""] ?? a.horizon ?? "—"}
              </span>
              <div>
                <p className="text-sm text-foreground/85">{a.action}</p>
                {a.rationale && <p className="text-xs text-foreground/45">{a.rationale}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <List title="Opportunities" items={strategy?.opportunities} />
        <List title="Risks" items={strategy?.risks} />
      </div>
    </div>
  );
}
