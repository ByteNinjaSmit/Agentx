"use client";

import type { KeyboardEvent } from "react";
import type { AgentMode } from "@/lib/types";

type Props = {
  goal: string;
  setGoal: (v: string) => void;
  context: string;
  setContext: (v: string) => void;
  mode: AgentMode;
  setMode: (m: AgentMode) => void;
  running: boolean;
  onRun: () => void;
  onStop: () => void;
};

const EXAMPLES = [
  {
    label: "Edge AI cameras",
    goal: "Find new developments and competitor activity",
    context:
      "edge AI face recognition and embedding models for public safety cameras, TFLite model optimization for mobile hardware.",
  },
  {
    label: "Dev agent tools",
    goal: "Find new developments and competitor activity",
    context: "AI coding assistants and autonomous developer agent tools.",
  },
];

export default function RunForm({
  goal,
  setGoal,
  context,
  setContext,
  mode,
  setMode,
  running,
  onRun,
  onStop,
}: Props) {
  function handleKeyDown(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !running && goal.trim()) {
      onRun();
    }
  }

  function applyExample(ex: (typeof EXAMPLES)[number]) {
    setGoal(ex.goal);
    setContext(ex.context);
  }

  return (
    <div className="space-y-5">
      <fieldset className="space-y-1">
        <legend className="text-xs font-medium uppercase tracking-wide text-foreground/50 mb-1">
          Agent source
        </legend>
        <div className="inline-flex rounded-lg border border-border p-0.5 bg-surface-2">
          {(["backend", "n8n"] as const).map((m) => (
            <button
              key={m}
              type="button"
              disabled={running}
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                mode === m
                  ? "bg-accent text-white shadow-sm"
                  : "text-foreground/60 hover:text-foreground"
              }`}
            >
              {m === "backend" ? "Local backend (SSE)" : "n8n webhook"}
            </button>
          ))}
        </div>
      </fieldset>

      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-foreground/50 mb-1.5">
          Try an example
        </p>
        <div className="flex flex-wrap gap-1.5">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              type="button"
              disabled={running}
              onClick={() => applyExample(ex)}
              className="text-[11px] rounded-full px-2.5 py-1 border border-border text-foreground/60 hover:border-accent/50 hover:text-accent transition-colors disabled:opacity-50"
            >
              {ex.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label htmlFor="goal" className="text-xs font-medium uppercase tracking-wide text-foreground/50 block mb-1.5">
          Goal
        </label>
        <input
          id="goal"
          className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent focus:bg-background transition-colors"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Find new developments relevant to our project in the last week."
          disabled={running}
        />
      </div>

      <div>
        <label htmlFor="context" className="text-xs font-medium uppercase tracking-wide text-foreground/50 block mb-1.5">
          Project context
        </label>
        <textarea
          id="context"
          className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm h-64 resize-y focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent focus:bg-background transition-colors"
          placeholder="Paste your project synopsis/README so findings are grounded against it..."
          value={context}
          onChange={(e) => setContext(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={running}
        />
      </div>

      <div className="flex items-center gap-3">
        {running ? (
          <button
            onClick={onStop}
            className="rounded-lg bg-danger text-white px-4 py-2 text-sm font-medium shadow-sm hover:opacity-90 hover:shadow transition-all"
          >
            Stop
          </button>
        ) : (
          <button
            onClick={onRun}
            disabled={!goal.trim()}
            className="rounded-lg bg-accent text-white px-4 py-2 text-sm font-medium shadow-sm hover:opacity-90 hover:shadow transition-all disabled:opacity-40 disabled:shadow-none disabled:cursor-not-allowed"
          >
            Run agent
          </button>
        )}
        <span className="text-xs text-foreground/40">⌘/Ctrl + Enter</span>
        {running && (
          <span className="flex items-center gap-1.5 text-xs text-foreground/50 ml-auto">
            <span className="size-1.5 rounded-full bg-accent animate-pulse" />
            running
          </span>
        )}
      </div>
    </div>
  );
}
