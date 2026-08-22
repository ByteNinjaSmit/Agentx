"use client";

import { useEffect, useRef } from "react";
import type { Observation, RunStatus, Step } from "@/lib/types";

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

function isErrorObservation(value: unknown) {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? "");
  return /^HTTP \d{3}\b/.test(text) || /there was an error/i.test(text);
}

// A step has failed if the n8n-style opaque observation looks like an error, or if
// any of the backend's structured observations came back not-ok.
function stepFailed(step: Step) {
  if (step.observations?.length) return step.observations.some((o) => !o.ok);
  return isErrorObservation(step.observation);
}

function prettyJson(text?: string) {
  if (!text) return "";
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text; // preview is truncated mid-JSON, so this is the normal case
  }
}

const AGENT_LABEL: Record<string, string> = {
  planner: "Planner — splitting the goal into independent lines of enquiry",
  researcher: "Researchers — gathering in parallel, one lane per sub-question",
  research: "Research Agent — gathering findings",
  verifier: "Verifier — checking every finding against real tool output",
  analyst: "Analyst — judging relevance, normalizing organizations, summarizing",
  strategist: "Strategist — threat levels and recommended actions",
};

const LANE_COLORS = [
  "border-sky-500/60",
  "border-purple-500/60",
  "border-teal-500/60",
  "border-amber-500/60",
];

function Dots({ className = "bg-slate-500" }: { className?: string }) {
  return (
    <div className="flex gap-1.5">
      {[0, 150, 300].map((delay) => (
        <div
          key={delay}
          className={`size-1.5 rounded-full animate-bounce ${className}`}
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}

function ObservationRow({ obs }: { obs: Observation }) {
  return (
    <details className="mt-1.5 group/obs">
      <summary
        className={`flex items-center gap-2 text-xs cursor-pointer list-none marker:hidden select-none ${
          obs.ok ? "text-slate-500 hover:text-slate-300" : "text-red-400"
        }`}
      >
        <span className="shrink-0 transition-transform group-open/obs:rotate-90">▸</span>
        <span className="shrink-0">{obs.ok ? "↳" : "✕"}</span>
        <span className="truncate">
          {obs.tool}
          {obs.query ? ` "${obs.query}"` : ""}
        </span>
        <span className="ml-auto shrink-0 flex items-center gap-2 tabular-nums text-[11px] text-slate-500">
          {obs.ok && obs.count != null && <span>{obs.count} result{obs.count === 1 ? "" : "s"}</span>}
          {obs.latency_ms != null && <span>{obs.latency_ms}ms</span>}
        </span>
      </summary>
      {obs.error ? (
        <p className="mt-1 ml-6 text-xs text-red-400 break-words">{obs.error}</p>
      ) : (
        <pre className="mt-1 ml-6 max-h-56 overflow-auto rounded-md bg-black/40 p-3 text-[11px] leading-relaxed text-slate-400 whitespace-pre-wrap break-words">
          {prettyJson(obs.preview)}
        </pre>
      )}
    </details>
  );
}

export default function TraceLog({
  steps,
  running,
  status,
}: {
  steps: Step[];
  running: boolean;
  status?: RunStatus | null;
}) {
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
      <div className="rounded-xl border border-border bg-[#0f172a] dark:bg-black/40 backdrop-blur-xl shadow-lg overflow-hidden flex flex-col">
        {/* Terminal Header */}
        <div className="bg-[#1e293b]/50 dark:bg-white/5 border-b border-white/10 px-4 py-2.5 flex items-center relative">
          <div className="flex gap-1.5 z-10">
            <div className="size-3 rounded-full bg-red-500/80 border border-red-500/50" />
            <div className="size-3 rounded-full bg-yellow-500/80 border border-yellow-500/50" />
            <div className="size-3 rounded-full bg-green-500/80 border border-green-500/50" />
          </div>
          <span className="text-[11px] font-mono text-slate-400 absolute inset-x-0 text-center pointer-events-none">agent-trace ~ zsh</span>
        </div>

        <div
          role="log"
          aria-live="polite"
          aria-relevant="additions"
          className="font-mono text-[13px] max-h-96 overflow-y-auto p-5 space-y-4 text-slate-300"
        >
        {steps.length === 0 && !running && <p className="text-slate-500">ready.</p>}
        {steps.length === 0 && running && (
          <div className="flex items-center gap-3 text-slate-400 animate-fade-in-up">
            <Dots className="bg-sky-500" />
            <span className="text-xs">waiting for first thought...</span>
          </div>
        )}
        {steps.map((s, i) => {
          const failed = stepFailed(s);
          const showAgentHeader = s.agent && s.agent !== steps[i - 1]?.agent;
          const showLane =
            s.lane_label && (s.lane !== steps[i - 1]?.lane || s.agent !== steps[i - 1]?.agent);
          const laneBorder =
            s.lane != null ? LANE_COLORS[s.lane % LANE_COLORS.length] : "border-sky-500/50";
          const tokens = (s.input_tokens ?? 0) + (s.output_tokens ?? 0);
          const awaitingObservation =
            running && s.calls.length > 0 && !s.observations && s.observation == null;
          return (
            <div key={i}>
              {showAgentHeader && (
                <p className="text-[11px] uppercase tracking-wider text-slate-500 mt-3 mb-1.5 first:mt-0">
                  {AGENT_LABEL[s.agent!] ?? s.agent}
                </p>
              )}
              {showLane && (
                <p className="mb-1 pl-4 text-[11px] text-slate-400">
                  <span className="text-slate-600">lane {(s.lane ?? 0) + 1}</span> {s.lane_label}
                </p>
              )}
              <div
                className={`animate-fade-in-up border-l-2 pl-4 py-0.5 transition-colors ${
                  failed
                    ? "border-red-500/50 shadow-[-2px_0_8px_rgba(239,68,68,0.2)]"
                    : `${laneBorder} shadow-[-2px_0_8px_rgba(14,165,233,0.2)]`
                }`}
              >
              {s.thought && <p className="text-slate-200 whitespace-pre-wrap leading-relaxed">{s.thought}</p>}
              {s.calls.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {s.calls.map((c, j) => (
                    <span
                      key={j}
                      className={`rounded-md px-2 py-0.5 text-[11px] font-medium tracking-wide ${toolColor(c.tool)} bg-opacity-20 border border-current/20`}
                      title={JSON.stringify(c.input)}
                    >
                      {c.tool}({preview(c.input, 60)})
                    </span>
                  ))}
                </div>
              )}

              {/* the planner's split, shown as the lanes it is about to fan out to */}
              {s.plan?.length ? (
                <ol className="mt-1.5 space-y-0.5 text-xs text-slate-400">
                  {s.plan.map((q, j) => (
                    <li key={j}>
                      <span className="text-slate-600">{j + 1}.</span> {q.question}
                      {q.sources?.length ? (
                        <span className="text-slate-600"> — {q.sources.join(", ")}</span>
                      ) : null}
                    </li>
                  ))}
                </ol>
              ) : null}

              {/* what the verifier threw away, named rather than silently dropped */}
              {s.rejected?.length ? (
                <ul className="mt-1.5 space-y-0.5 text-xs text-red-400/80">
                  {s.rejected.map((r, j) => (
                    <li key={j} className="truncate" title={r.title ?? ""}>
                      ✕ {r.title} <span className="text-slate-600">— {r.reason}</span>
                    </li>
                  ))}
                </ul>
              ) : null}

              {/* backend: one collapsible grounded observation per tool call */}
              {s.observations?.map((obs, j) => <ObservationRow key={j} obs={obs} />)}

              {tokens > 0 && (
                <p className="mt-1.5 text-[10px] tabular-nums text-slate-600">
                  {s.input_tokens ?? 0} in · {s.output_tokens ?? 0} out
                </p>
              )}

              {awaitingObservation && (
                <p className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                  <Dots />
                  <span>calling {s.calls.map((c) => c.tool).join(", ")}…</span>
                </p>
              )}

              {/* n8n: a single opaque observation string for the whole step */}
              {!s.observations && preview(s.observation) && (
                <p
                  className={`mt-2 flex items-start gap-2 text-xs ${
                    failed ? "text-red-400" : "text-slate-500"
                  }`}
                >
                  <span className="shrink-0">{failed ? "✕" : "↳"}</span>
                  <span className="break-words">{preview(s.observation)}</span>
                </p>
              )}
              </div>
            </div>
          );
        })}
        {running && steps.length > 0 && (
          <div className="flex items-center gap-3 text-slate-500 animate-fade-in-up pt-2">
            <Dots />
            <span className="text-xs">{status?.message ?? "working"}...</span>
          </div>
        )}
        <div ref={endRef} />
        </div>
      </div>
    </div>
  );
}
