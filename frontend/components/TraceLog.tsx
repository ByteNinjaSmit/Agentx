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

function isErrorObservation(value: unknown) {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? "");
  return /^HTTP \d{3}\b/.test(text) || /there was an error/i.test(text);
}

const AGENT_LABEL: Record<string, string> = {
  research: "Research Agent — gathering findings",
  analyst: "Analyst Agent — reviewing, scoring, synthesizing",
};

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
        {steps.length === 0 && !running && (
          <p className="text-slate-500">
            ready.
          </p>
        )}
        {steps.length === 0 && running && (
          <div className="flex items-center gap-3 text-slate-400 animate-fade-in-up">
            <div className="flex gap-1.5">
              <div className="size-1.5 rounded-full bg-sky-500 animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="size-1.5 rounded-full bg-sky-500 animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="size-1.5 rounded-full bg-sky-500 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="text-xs">waiting for first thought...</span>
          </div>
        )}
        {steps.map((s, i) => {
          const failed = isErrorObservation(s.observation);
          const showAgentHeader = s.agent && s.agent !== steps[i - 1]?.agent;
          return (
            <div key={i}>
              {showAgentHeader && (
                <p className="text-[11px] uppercase tracking-wider text-slate-500 mt-3 mb-1.5 first:mt-0">
                  {AGENT_LABEL[s.agent!] ?? s.agent}
                </p>
              )}
              <div
                className={`animate-fade-in-up border-l-2 pl-4 py-0.5 transition-colors ${
                  failed
                    ? "border-red-500/50 shadow-[-2px_0_8px_rgba(239,68,68,0.2)]"
                    : "border-sky-500/50 shadow-[-2px_0_8px_rgba(14,165,233,0.2)]"
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
              {preview(s.observation) && (
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
            <div className="flex gap-1.5">
              <div className="size-1.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="size-1.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="size-1.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="text-xs">working...</span>
          </div>
        )}
        <div ref={endRef} />
        </div>
      </div>
    </div>
  );
}
