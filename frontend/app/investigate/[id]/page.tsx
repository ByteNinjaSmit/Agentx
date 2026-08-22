"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import RunForm from "@/components/RunForm";
import TraceLog from "@/components/TraceLog";
import AgentGraph from "@/components/AgentGraph";
import Legend from "@/components/Legend";
import { runAgent } from "@/lib/agent-client";
import { useRunSettings } from "@/lib/run-settings";
import type { Cancel, FinalResult, RunStatus, Step } from "@/lib/types";

/** Past a run's final event lives here, keyed by its id, so the intelligence
 *  page can render it instantly without a round trip — and so a finished n8n
 *  run (which has no backend-assigned id) has somewhere to live at all. */
export function stashResult(id: string, payload: { final: FinalResult; trace: Step[] }) {
  try {
    sessionStorage.setItem(`agentx-result-${id}`, JSON.stringify(payload));
  } catch {
    // sessionStorage unavailable (private mode) — the intelligence page falls
    // back to fetching the run from the backend when it has a real run_id
  }
}

function NewInvestigation() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const settings = useRunSettings();

  const [goal, setGoal] = useState(searchParams.get("goal") ?? "");
  const [context, setContext] = useState(searchParams.get("context") ?? "");
  const competitors = (searchParams.get("competitors") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const track = searchParams.get("track") ?? "";
  const depthParam = Number(searchParams.get("depth"));
  const depth = Number.isFinite(depthParam) && depthParam > 0 ? depthParam : undefined;

  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<Cancel | null>(null);
  const startedAt = useRef<number | null>(null);
  // onFinal fires from a closure created when the run started, so `steps` state
  // there would be stale — mirror every update into a ref it can read live.
  const stepsRef = useRef<Step[]>([]);

  useEffect(() => () => cancelRef.current?.(), []);

  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => {
      setElapsed(startedAt.current ? Math.floor((Date.now() - startedAt.current) / 1000) : 0);
    }, 1000);
    return () => clearInterval(timer);
  }, [running]);

  function startRun() {
    if (!goal.trim() || running) return;
    setSteps([]);
    stepsRef.current = [];
    setStatus(null);
    setError(null);
    setRunning(true);
    setElapsed(0);
    startedAt.current = Date.now();

    cancelRef.current = runAgent(
      settings.mode,
      goal,
      context,
      {
        onStep: (step) =>
          setSteps((s) => {
            const next = [...s, step];
            stepsRef.current = next;
            return next;
          }),
        onObservation: (stepIndex, results) =>
          setSteps((s) => {
            const next = s.map((step, i) => (i === stepIndex ? { ...step, observations: results } : step));
            stepsRef.current = next;
            return next;
          }),
        onStatus: (s) => setStatus(s),
        onFinal: (result) => {
          setStatus(null);
          const resultId = result.run_id ?? crypto.randomUUID();
          stashResult(resultId, { final: result, trace: stepsRef.current });
          router.replace(`/intelligence/${resultId}`);
        },
        onError: (message) => setError(message),
        onDone: () => {
          setStatus(null);
          setRunning(false);
        },
      },
      { pipeline: settings.pipeline, provider: settings.provider, competitors, depth, track }
    );
  }

  function stopRun() {
    cancelRef.current?.();
    cancelRef.current = null;
    setStatus(null);
    setRunning(false);
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-8">
        <Link
          href="/"
          className="inline-flex items-center text-sm font-medium text-[var(--foreground-secondary)] hover:text-[var(--foreground)] mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4 mr-1" />
          Investigate
        </Link>
        <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-2">
          {running ? goal || "Investigation" : "New investigation"}
        </h1>
        {running && (
          <p className="text-sm text-[var(--foreground-secondary)]">
            Running on the {settings.mode === "backend" ? "local backend" : "n8n webhook"} ·{" "}
            {elapsed}s elapsed
          </p>
        )}
      </div>

      {!running && steps.length === 0 && (
        <div className="surface-card p-6 space-y-5">
          <RunForm
            goal={goal}
            setGoal={setGoal}
            context={context}
            setContext={setContext}
            mode={settings.mode}
            setMode={settings.setMode}
            pipeline={settings.pipeline}
            setPipeline={settings.setPipeline}
            provider={settings.provider}
            setProvider={settings.setProvider}
            providers={settings.providers}
            running={running}
            onRun={startRun}
            onStop={stopRun}
          />
        </div>
      )}

      {(running || steps.length > 0) && (
        <div className="space-y-6">
          {error && (
            <p role="alert" className="text-sm text-[var(--danger)] bg-red-50 rounded-lg px-3 py-2.5 border border-red-200">
              {error}
            </p>
          )}
          {settings.pipeline === "fleet" && <AgentGraph steps={steps} status={status} running={running} />}
          <Legend />
          <TraceLog steps={steps} running={running} status={status} />
          {!running && error && (
            <button
              onClick={() => {
                setSteps([]);
                setError(null);
              }}
              className="text-sm font-medium text-[var(--accent)] hover:underline"
            >
              Try again
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** A real (backend-assigned) run id opened directly — jump straight to its
 *  report rather than duplicating the fetch/render logic here. */
function ExistingRun() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  useEffect(() => {
    router.replace(`/intelligence/${params.id}`);
  }, [params.id, router]);
  return <p className="text-sm text-[var(--foreground-secondary)]">Opening report…</p>;
}

export default function InvestigatePage() {
  const params = useParams<{ id: string }>();
  const isNew = params.id === "new";
  return (
    <Suspense fallback={<p className="text-sm text-[var(--foreground-secondary)]">Loading…</p>}>
      {isNew ? <NewInvestigation /> : <ExistingRun />}
    </Suspense>
  );
}
