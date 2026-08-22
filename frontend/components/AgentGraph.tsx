"use client";

import { useMemo } from "react";
import type { RunStatus, Step } from "@/lib/types";

// Mirrors the "type": "status" phase names backend/agent/fleet.py actually
// yields, in the order it yields them — this is not a guess, it is read
// straight off the SSE stream the run already sends.
const PHASE_ORDER = [
  "planning",
  "researching",
  "verifying",
  "analyzing",
  "self_eval",
  "replanning",
  "strategy",
  "saving",
  "alerting",
] as const;

type NodeState = "pending" | "active" | "done";

const STATE_STYLE: Record<NodeState, { border: string; dot: string; pulse: boolean }> = {
  pending: { border: "border-[var(--border)] opacity-60", dot: "bg-[var(--border-highlight)]", pulse: false },
  active: { border: "border-[var(--accent)] shadow-[0_0_0_3px_var(--accent-soft,rgba(49,85,212,0.12))]", dot: "bg-[var(--accent)]", pulse: true },
  done: { border: "border-[var(--border)]", dot: "bg-[var(--accent-secondary)]", pulse: false },
};

function Node({ label, sub, state }: { label: string; sub: string; state: NodeState }) {
  const style = STATE_STYLE[state];
  return (
    <div className={`surface-card border ${style.border} px-4 py-3 text-center transition-all duration-300`}>
      <div className="flex items-center justify-center gap-2">
        <span className={`inline-block w-[7px] h-[7px] rounded-full ${style.dot} ${style.pulse ? "animate-pulse" : ""}`} />
        <span className="text-[13px] font-semibold text-[var(--foreground)]">{label}</span>
      </div>
      <div className="mt-0.5 text-[11px] text-[var(--foreground-secondary)] truncate" title={sub}>
        {sub}
      </div>
    </div>
  );
}

/** Visual summary of the fleet's Planner → parallel Researchers → Verifier →
 *  Analyst → Strategist run, driven entirely by the real SSE `status` phase
 *  events and the real trace steps — no simulated timing, no fixed lane
 *  names. Fleet-pipeline only; the single ReAct loop has none of these
 *  distinct agents to show. */
export default function AgentGraph({
  steps,
  status,
  running,
}: {
  steps: Step[];
  status: RunStatus | null;
  running: boolean;
}) {
  const phase = status?.phase ?? null;
  const idx = phase ? PHASE_ORDER.indexOf(phase as (typeof PHASE_ORDER)[number]) : -1;

  const lanes = useMemo(() => {
    const byLane = new Map<number, string>();
    for (const s of steps) {
      if (s.agent === "researcher" && s.lane != null) {
        byLane.set(s.lane, s.lane_label ?? byLane.get(s.lane) ?? `Lane ${s.lane + 1}`);
      }
    }
    return [...byLane.entries()].sort((a, b) => a[0] - b[0]);
  }, [steps]);

  const researchersActive = phase === "researching" || phase === "replanning";
  const researchersDone = idx > PHASE_ORDER.indexOf("researching") && phase !== "replanning";
  const researchersState: NodeState = researchersActive ? "active" : researchersDone ? "done" : "pending";

  const plannerState: NodeState = idx >= 1 ? "done" : running ? "active" : "pending";
  const verifierState: NodeState = idx === 2 ? "active" : idx > 2 ? "done" : "pending";
  const analystState: NodeState =
    idx === 3 || idx === 4 ? "active" : idx > 4 ? "done" : "pending";
  const strategistState: NodeState = idx === 6 ? "active" : idx > 6 ? "done" : "pending";

  const fallbackEvents = steps.filter((s) => s.agent === "runtime");
  const replanStep = steps.find((s) => s.agent === "planner" && s.thought?.includes("Replanning"));
  const conflictStep = [...steps]
    .reverse()
    .find((s) => s.agent === "verifier" && s.thought?.toLowerCase().includes("conflict"));

  return (
    <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr] items-start">
      {/* ---- graph ---- */}
      <div className="surface-card p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground-secondary)] mb-5">
          Agent graph
        </h2>
        <div className="flex flex-col items-center gap-0">
          <div className="w-56">
            <Node
              label="Planner"
              sub={plannerState === "pending" ? "queued" : plannerState === "active" ? "planning…" : `${lanes.length || "—"} sub-questions`}
              state={plannerState}
            />
          </div>
          <div className="w-px h-6 bg-[var(--border-highlight)]" />

          <div className="w-full grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.max(lanes.length, 1)}, minmax(0, 1fr))` }}>
            {lanes.length === 0 ? (
              <Node label="Researchers" sub={plannerState === "done" ? "starting…" : "waiting"} state={plannerState === "done" ? "active" : "pending"} />
            ) : (
              lanes.map(([lane, label]) => (
                <Node key={lane} label={label} sub={researchersState === "active" ? "researching…" : researchersState === "done" ? "complete" : "waiting"} state={researchersState} />
              ))
            )}
          </div>
          <div className="w-px h-6 bg-[var(--border-highlight)]" />

          <div className="w-56">
            <Node label="Verifier" sub={verifierState === "active" ? "checking…" : verifierState === "done" ? "grounded findings kept" : "waiting"} state={verifierState} />
          </div>
          <div className="w-px h-5 bg-[var(--border)]" />
          <div className="w-56">
            <Node label="Analyst" sub={analystState === "active" ? "judging…" : analystState === "done" ? "relevance judged" : "waiting"} state={analystState} />
          </div>
          <div className="w-px h-5 bg-[var(--border)]" />
          <div className="w-56">
            <Node label="Strategist" sub={strategistState === "active" ? "assessing…" : strategistState === "done" ? "threats assessed" : "waiting"} state={strategistState} />
          </div>
        </div>
      </div>

      {/* ---- real-time event cards ---- */}
      <div className="space-y-4">
        {replanStep && (
          <div className="surface-card p-4 border-[var(--accent)]" style={{ borderWidth: 1.5 }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-5 h-5 rounded-md bg-[var(--accent-soft,rgba(49,85,212,0.1))] text-[var(--accent)] flex items-center justify-center text-[10px] font-bold">↝</span>
              <span className="text-[11px] font-bold uppercase tracking-wide text-[var(--accent)]">Plan updated</span>
            </div>
            <p className="text-[13px] leading-relaxed text-[var(--foreground)]">{replanStep.thought}</p>
          </div>
        )}

        {fallbackEvents.length > 0 && (
          <div className="surface-card p-4 border-[var(--warning)]" style={{ borderWidth: 1.5 }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-5 h-5 rounded-md bg-amber-50 text-[var(--warning)] flex items-center justify-center text-[10px] font-bold">↺</span>
              <span className="text-[11px] font-bold uppercase tracking-wide text-[var(--warning)]">Runtime recovery</span>
            </div>
            <p className="text-[13px] leading-relaxed text-[var(--foreground)]">
              {fallbackEvents[fallbackEvents.length - 1].thought}
            </p>
            {fallbackEvents.length > 1 && (
              <p className="mt-1 text-[11px] text-[var(--foreground-secondary)]">
                +{fallbackEvents.length - 1} more recovery{fallbackEvents.length - 1 === 1 ? "" : "ies"} this run
              </p>
            )}
          </div>
        )}

        {conflictStep && (
          <div className="surface-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-5 h-5 rounded-md bg-teal-50 text-[var(--accent-secondary)] flex items-center justify-center text-[10px] font-bold">✓</span>
              <span className="text-[11px] font-bold uppercase tracking-wide text-[var(--accent-secondary)]">Verifier</span>
            </div>
            <p className="text-[13px] leading-relaxed text-[var(--foreground)]">{conflictStep.thought}</p>
          </div>
        )}

        {!replanStep && !conflictStep && fallbackEvents.length === 0 && (
          <div className="surface-card p-4 text-[13px] text-[var(--foreground-secondary)]">
            No replanning, recovery or conflict events yet — the full reasoning trace is below.
          </div>
        )}
      </div>
    </div>
  );
}
