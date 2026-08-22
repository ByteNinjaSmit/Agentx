"use client";

import type { Conflict, SelfEvaluation } from "@/lib/types";

/** The fleet's own account of whether it trusted its result enough to stop —
 *  coverage against the plan, whether that triggered a replan, and any
 *  cross-source disagreements it had to reconcile. Only present on fleet runs;
 *  the single ReAct loop has no self-check step to report. */
export default function SelfEvalPanel({
  selfEvaluation,
  conflicts,
}: {
  selfEvaluation?: SelfEvaluation;
  conflicts?: Conflict[];
}) {
  if (!selfEvaluation && !conflicts?.length) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {selfEvaluation && (
        <div className="surface-card p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--foreground-secondary)] mb-2">
            Self-evaluation
          </p>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-semibold tabular-nums">
              {Math.round(selfEvaluation.coverage_score * 100)}%
            </span>
            <span className="text-xs text-[var(--foreground-secondary)]">
              coverage · threshold {Math.round(selfEvaluation.threshold * 100)}%
            </span>
          </div>
          <p className="mt-2 text-xs text-[var(--foreground-secondary)]">
            {selfEvaluation.replanned
              ? `Below threshold — the planner opened a follow-up round. ${selfEvaluation.replan_rationale ?? ""}`
              : selfEvaluation.replan_rationale ?? "Coverage was sufficient; no follow-up round was needed."}
          </p>
        </div>
      )}

      {conflicts && conflicts.length > 0 && (
        <div className="surface-card p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--foreground-secondary)] mb-2">
            Evidence conflicts resolved
          </p>
          <ul className="space-y-2">
            {conflicts.map((c) => (
              <li key={c.organization} className="text-xs">
                <span className="font-medium text-[var(--foreground)]">{c.organization}</span>
                {c.confidence != null && (
                  <span className="text-[var(--foreground-secondary)]"> · {Math.round(c.confidence * 100)}% confidence</span>
                )}
                <p className="text-[var(--foreground-secondary)] mt-0.5">{c.note}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
