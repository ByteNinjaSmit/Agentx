"use client";

import { useEffect, useRef, useState } from "react";
import RunForm from "./RunForm";
import TraceLog from "./TraceLog";
import ResultsList from "./ResultsList";
import ThemeToggle from "./ThemeToggle";
import Legend from "./Legend";
import HistoryPanel from "./HistoryPanel";
import StatsPanel from "./StatsPanel";
import AskPanel from "./AskPanel";
import StrategyPanel from "./StrategyPanel";
import { defaultAgentMode, fetchProviders, runAgent } from "@/lib/agent-client";
import { usePersistedValue } from "@/lib/client-state";
import type {
  AgentMode,
  Cancel,
  FinalResult,
  Pipeline,
  ProviderInfo,
  RunStatus,
  Step,
} from "@/lib/types";

const MODE_KEY = "agentx-mode";
const TAB_KEY = "agentx-tab";
const PIPELINE_KEY = "agentx-pipeline";
type Tab = "run" | "history" | "stats" | "ask";

const TABS: [Tab, string][] = [
  ["run", "New run"],
  ["history", "History"],
  ["stats", "Statistics"],
  ["ask", "Ask"],
];

export default function Dashboard() {
  const [goal, setGoal] = useState(
    "Find new developments relevant to our project in the last week."
  );
  const [context, setContext] = useState("");
  // Persisted preferences read through useSyncExternalStore: the server snapshot
  // is the env-derived default, so the first paint matches and the stored value
  // takes over on hydration without a second render pass.
  const [mode, setMode] = usePersistedValue<AgentMode>(
    MODE_KEY,
    defaultAgentMode,
    (v) => v === "backend" || v === "n8n"
  );
  const [tab, setTab] = usePersistedValue<Tab>(TAB_KEY, "run", (v) =>
    TABS.some(([key]) => key === v)
  );
  const [pipeline, setPipeline] = usePersistedValue<Pipeline>(
    PIPELINE_KEY,
    "fleet",
    (v) => v === "fleet" || v === "single"
  );
  const [provider, setProvider] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderInfo | null>(null);

  // Which providers this deployment actually has keys for — asking beats guessing,
  // and it keeps the UI from offering a provider whose first call would 401.
  useEffect(() => {
    fetchProviders()
      .then((info) => {
        setProviders(info);
        setProvider((current) => current ?? info.default);
      })
      .catch(() => setProviders(null));
  }, []);

  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [final, setFinal] = useState<FinalResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<Cancel | null>(null);

  function startRun() {
    setSteps([]);
    setStatus(null);
    setFinal(null);
    setError(null);
    setRunning(true);

    cancelRef.current = runAgent(mode, goal, context, {
      onStep: (step) => setSteps((s) => [...s, step]),
      // the thought for a step streams out before its tools have returned, so the
      // observations arrive separately and patch the step already on screen
      onObservation: (stepIndex, results) =>
        setSteps((s) =>
          s.map((step, i) => (i === stepIndex ? { ...step, observations: results } : step))
        ),
      onStatus: (s) => setStatus(s),
      onFinal: (result) => {
        setStatus(null);
        setFinal(result);
      },
      onError: (message) => setError(message),
      onDone: () => {
        setStatus(null);
        setRunning(false);
      },
    }, { pipeline, provider });
  }

  function stopRun() {
    cancelRef.current?.();
    cancelRef.current = null;
    setStatus(null);
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
          {TABS.map(([key, label]) => (
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
                pipeline={pipeline}
                setPipeline={setPipeline}
                provider={provider}
                setProvider={setProvider}
                providers={providers}
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
              <TraceLog steps={steps} running={running} status={status} />
              <ResultsList final={final} running={running} />
              {!running && <StrategyPanel strategy={final?.strategy} />}
            </div>
          </div>
        ) : tab === "history" ? (
          <div className="max-w-3xl space-y-6">
            <Legend />
            <HistoryPanel />
          </div>
        ) : tab === "stats" ? (
          <StatsPanel />
        ) : (
          <div className="max-w-3xl">
            <AskPanel runId={final?.run_id} />
          </div>
        )}
      </main>
    </div>
  );
}
