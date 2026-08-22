"use client";

import { useState } from "react";

type AgentStep = {
  action?: { tool?: string; toolInput?: unknown; log?: string };
  observation?: unknown;
};
type Item = {
  source: string;
  title: string;
  url: string;
  summary: string;
  relevance_reason: string;
  impact_1_10: number;
};
type FinalResult = { items: Item[]; coverage_ok: boolean };

const WEBHOOK_URL =
  process.env.NEXT_PUBLIC_N8N_WEBHOOK_URL || "http://localhost:5678/webhook/compintel-run";

function stepLabel(step: AgentStep, i: number) {
  const tool = step.action?.tool;
  if (!tool) return `Step ${i}: finalizing`;
  const input = JSON.stringify(step.action?.toolInput ?? {});
  return `Step ${i}: called ${tool} with ${input}`;
}

function observationPreview(step: AgentStep) {
  if (step.observation === undefined) return null;
  const text =
    typeof step.observation === "string" ? step.observation : JSON.stringify(step.observation);
  return text.length > 240 ? text.slice(0, 240) + "…" : text;
}

export default function TraceView() {
  const [goal, setGoal] = useState(
    "Find new developments relevant to our project in the last week."
  );
  const [context, setContext] = useState("");
  const [running, setRunning] = useState(false);
  const [trace, setTrace] = useState<AgentStep[]>([]);
  const [final, setFinal] = useState<FinalResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function startRun() {
    setTrace([]);
    setFinal(null);
    setError(null);
    setRunning(true);

    try {
      const res = await fetch(WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal, context }),
      });
      if (!res.ok) throw new Error(`Webhook returned ${res.status}`);
      const data = await res.json();
      const steps: AgentStep[] = data.trace || [];

      // reveal steps one at a time — n8n returns the whole run at once,
      // this fakes the live feel of the original SSE stream
      for (let i = 0; i < steps.length; i++) {
        await new Promise((r) => setTimeout(r, 400));
        setTrace((t) => [...t, steps[i]]);
      }
      setFinal(data.final || { items: [], coverage_ok: false });
    } catch (e) {
      setError(
        `Could not reach agent at ${WEBHOOK_URL}. Is the n8n workflow active? (${(e as Error).message})`
      );
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto py-12 px-6 space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Competitive Intelligence Agent</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Autonomous ReAct agent — plans tool calls, retries on weak coverage, remembers what it already found.
        </p>
      </div>

      <div className="space-y-3">
        <div>
          <label className="text-sm font-medium block mb-1">Goal</label>
          <input
            className="w-full border rounded px-3 py-2 text-sm dark:bg-zinc-900"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
        </div>
        <div>
          <label className="text-sm font-medium block mb-1">Project context</label>
          <textarea
            className="w-full border rounded px-3 py-2 text-sm h-24 dark:bg-zinc-900"
            placeholder="Paste your project synopsis/README so findings are grounded against it..."
            value={context}
            onChange={(e) => setContext(e.target.value)}
          />
        </div>
        <button
          onClick={startRun}
          disabled={running}
          className="rounded bg-black text-white dark:bg-white dark:text-black px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          {running ? "Running..." : "Run agent"}
        </button>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {trace.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Reasoning trace
          </h2>
          {trace.map((s, i) => (
            <div key={i} className="border-l-2 border-purple-400 pl-3 text-sm">
              <p className="text-teal-600">{stepLabel(s, i)}</p>
              {observationPreview(s) && (
                <p className="text-zinc-500 mt-1">→ {observationPreview(s)}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {final && !running && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Ranked brief {final.items.length === 0 && "(no new items — already known)"}
          </h2>
          {[...final.items]
            .sort((a, b) => b.impact_1_10 - a.impact_1_10)
            .map((it, i) => (
              <div key={i} className="border rounded p-3">
                <div className="flex justify-between items-start gap-2">
                  <a href={it.url} target="_blank" className="font-medium hover:underline">
                    {it.title}
                  </a>
                  <span className="text-xs shrink-0 rounded bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5">
                    {it.source} · {it.impact_1_10}/10
                  </span>
                </div>
                <p className="text-sm text-zinc-500 mt-1">{it.relevance_reason}</p>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
