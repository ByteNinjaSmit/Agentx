"use client";

import { useEffect, useRef, useState } from "react";
import RunForm from "./RunForm";
import TraceLog from "./TraceLog";
import ResultsList from "./ResultsList";
import ThemeToggle from "./ThemeToggle";
import Legend from "./Legend";
import HistoryPanel from "./HistoryPanel";
import { defaultAgentMode, runAgent } from "@/lib/agent-client";
import type { AgentMode, Cancel, FinalResult, Step } from "@/lib/types";

const MODE_KEY = "agentx-mode";
const TAB_KEY = "agentx-tab";
type Tab = "run" | "history";

export default function Dashboard() {
  const [goal, setGoal] = useState(
    "Find new developments relevant to our project in the last week."
  );
  const [context, setContext] = useState("");
  const [mode, setModeState] = useState<AgentMode>(defaultAgentMode);
  const [tab, setTabState] = useState<Tab>("run");
  const setMode = (m: AgentMode) => {
    setModeState(m);
    localStorage.setItem(MODE_KEY, m);
  };
  const setTab = (t: Tab) => {
    setTabState(t);
    localStorage.setItem(TAB_KEY, t);
  };

  // sync from localStorage after mount only — keeps server/client first render
  // identical (avoids hydration mismatch) since defaultAgentMode is env-derived
  useEffect(() => {
    const storedMode = localStorage.getItem(MODE_KEY);
    if (storedMode === "backend" || storedMode === "n8n") setModeState(storedMode);
    const storedTab = localStorage.getItem(TAB_KEY);
    if (storedTab === "run" || storedTab === "history") setTabState(storedTab);
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
    <div className="min-h-dvh flex flex-col relative z-0">
      <div className="bg-blob blob-1" />
      <div className="bg-blob blob-2" />
      
      <header className="sticky top-4 z-20 mx-auto w-full max-w-6xl px-4 lg:px-6 mb-6">
        <div className="glass-panel rounded-2xl px-6 py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="size-10 rounded-xl bg-gradient-to-br from-accent/20 to-accent-soft border border-accent/20 text-accent grid place-items-center font-mono text-base font-bold shadow-[0_0_15px_rgba(2,132,199,0.2)]">
              X
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-foreground to-foreground/70">
                Competitive Intelligence Agent
              </h1>
              <p className="text-xs font-medium text-foreground/50 mt-0.5 max-w-sm sm:max-w-none">
                Autonomous ReAct agent — plans tool calls, retries on weak coverage, remembers
                what it already found.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 self-end sm:self-auto">
            <ThemeToggle />
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 flex gap-2 -mb-px relative z-10">
          {([
            ["run", "New run"],
            ["history", "History"],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === key
                  ? "border-accent text-foreground"
                  : "border-transparent text-foreground/40 hover:text-foreground/70"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

      <main className="max-w-6xl mx-auto w-full px-6 py-6 relative z-10 flex-1">
        {tab === "run" ? (
          <div className="grid gap-8 lg:grid-cols-[minmax(0,32rem)_1fr]">
            <div className="surface-card p-5 h-fit lg:sticky lg:top-32">
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
            </div>

            <div className="space-y-6 min-w-0">
              <Legend />

              {error && (
                <p role="alert" className="text-sm text-danger bg-danger/10 rounded-lg px-3 py-2.5 border border-danger/20">
                  {error}
                </p>
              )}
              {!error && !running && steps.length === 0 && !final && (
                <div className="surface-card p-8 text-center">
                  <p className="text-sm text-foreground/50">
                    Set a goal and run the agent to see its reasoning trace and ranked findings here.
                  </p>
                </div>
              )}
              <TraceLog steps={steps} running={running} />
              <ResultsList final={final} running={running} />
            </div>
          </div>
        ) : (
          <div className="max-w-3xl space-y-6">
            <Legend />
            <HistoryPanel />
          </div>
        )}
      </main>
    </div>
  );
}
