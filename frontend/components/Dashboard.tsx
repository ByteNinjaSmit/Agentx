"use client";

import { useEffect, useRef, useState } from "react";
import RunForm from "./RunForm";
import TraceLog from "./TraceLog";
import ResultsList from "./ResultsList";
import ThemeToggle from "./ThemeToggle";
import { defaultAgentMode, runAgent } from "@/lib/agent-client";
import type { AgentMode, Cancel, FinalResult, Step } from "@/lib/types";

const MODE_KEY = "agentx-mode";

export default function Dashboard() {
  const [goal, setGoal] = useState(
    "Find new developments relevant to our project in the last week."
  );
  const [context, setContext] = useState("");
  const [mode, setModeState] = useState<AgentMode>(defaultAgentMode);
  const setMode = (m: AgentMode) => {
    setModeState(m);
    localStorage.setItem(MODE_KEY, m);
  };

  // sync from localStorage after mount only — keeps server/client first render
  // identical (avoids hydration mismatch) since defaultAgentMode is env-derived
  useEffect(() => {
    const stored = localStorage.getItem(MODE_KEY);
    if (stored === "backend" || stored === "n8n") setModeState(stored);
  }, []);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [final, setFinal] = useState<FinalResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<Cancel | null>(null);

  function startRun() {
    setSteps([]);
    setFinal(null);
    setError(null);
    setRunning(true);

    cancelRef.current = runAgent(mode, goal, context, {
      onStep: (step) => setSteps((s) => [...s, step]),
      onFinal: (result) => setFinal(result),
      onError: (message) => setError(message),
      onDone: () => setRunning(false),
    });
  }

  function stopRun() {
    cancelRef.current?.();
    cancelRef.current = null;
    setRunning(false);
  }

  return (
    <div className="min-h-dvh flex flex-col">
      <header className="border-b border-border">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold">Competitive Intelligence Agent</h1>
            <p className="text-xs text-foreground/50 mt-0.5">
              Autonomous ReAct agent — plans tool calls, retries on weak coverage, remembers what
              it already found.
            </p>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main className="max-w-5xl mx-auto w-full px-6 py-8 grid gap-8 lg:grid-cols-[minmax(0,20rem)_1fr]">
        <RunForm
          goal={goal}
          setGoal={setGoal}
          context={context}
          setContext={setContext}
          mode={mode}
          setMode={setMode}
          running={running}
          onRun={startRun}
          onStop={stopRun}
        />

        <div className="space-y-8 min-w-0">
          {error && (
            <p role="alert" className="text-sm text-danger rounded-md bg-danger/10 px-3 py-2">
              {error}
            </p>
          )}
          {!error && !running && steps.length === 0 && !final && (
            <p className="text-sm text-foreground/40">
              Set a goal and run the agent to see its reasoning trace and ranked findings here.
            </p>
          )}
          <TraceLog steps={steps} running={running} />
          <ResultsList final={final} running={running} />
        </div>
      </main>
    </div>
  );
}
