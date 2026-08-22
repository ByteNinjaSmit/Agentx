import type { AgentMode, Cancel, Observation, RunHandlers, Step } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WEBHOOK_URL =
  process.env.NEXT_PUBLIC_N8N_WEBHOOK_URL || "http://localhost:5678/webhook/compintel-run";

export const defaultAgentMode: AgentMode = process.env.NEXT_PUBLIC_API_URL ? "backend" : "n8n";

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

const SESSION_KEY = "agentx-session-id";

// Persistent per-browser session id — lets the n8n Agent's Postgres Chat Memory
// recall context across separate runs (e.g. "what did I just ask about?").
// Purely additive: omitting session_id just falls back to a shared "default" key.
export function getSessionId(): string {
  if (typeof window === "undefined") return "default";
  try {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    return "default";
  }
}

// backend /run emits {step, thought, tools_called: [{name, input}]} per SSE "trace"
// event; stored rows in run_log additionally carry the "observations" that arrived
// afterwards on the live stream, so replayed history shows the same detail.
export function normalizeBackendStep(raw: {
  thought?: string;
  tools_called?: { name: string; input: unknown }[];
  observations?: Observation[];
}): Step {
  return {
    thought: raw.thought,
    calls: (raw.tools_called ?? []).map((c) => ({ tool: c.name, input: c.input })),
    observations: raw.observations?.length ? raw.observations : undefined,
  };
}

// n8n AI Agent node emits intermediateSteps as {action: {tool, toolInput, log}, observation}
export function normalizeN8nStep(raw: {
  action?: { tool?: string; toolInput?: unknown; log?: string };
  observation?: unknown;
  agent?: "research" | "analyst";
}): Step {
  return {
    thought: raw.action?.log,
    calls: raw.action?.tool ? [{ tool: raw.action.tool, input: raw.action.toolInput }] : [],
    observation: raw.observation,
    agent: raw.agent,
  };
}

function runBackend(goal: string, context: string, handlers: RunHandlers): Cancel {
  const url = `${API_URL}/run?goal=${encodeURIComponent(goal)}&context=${encodeURIComponent(context)}`;
  const es = new EventSource(url);
  let finished = false;

  function parse<T>(e: Event): T | null {
    try {
      return JSON.parse((e as MessageEvent).data) as T;
    } catch {
      return null; // malformed event — skip it, the stream continues
    }
  }

  es.addEventListener("trace", (e) => {
    const raw = parse<Parameters<typeof normalizeBackendStep>[0]>(e);
    if (raw) handlers.onStep(normalizeBackendStep(raw));
  });

  // observations arrive after their thought, once the tools have actually returned
  es.addEventListener("observation", (e) => {
    const raw = parse<{ step: number; results: Observation[] }>(e);
    if (raw && typeof raw.step === "number") {
      handlers.onObservation(raw.step, raw.results ?? []);
    }
  });

  es.addEventListener("status", (e) => {
    const raw = parse<{ phase: string; message: string }>(e);
    if (raw) handlers.onStatus({ phase: raw.phase, message: raw.message });
  });

  es.addEventListener("error", (e) => {
    // a named "error" event is the backend reporting a failed run, distinct from
    // EventSource's own transport-level onerror below
    const raw = parse<{ message?: string }>(e);
    if (raw?.message) {
      finished = true;
      handlers.onError(raw.message);
      es.close();
      handlers.onDone();
    }
  });

  es.addEventListener("final", (e) => {
    finished = true;
    const raw = parse<Record<string, unknown>>(e);
    if (raw) {
      handlers.onFinal({
        items: (raw.items as never) ?? [],
        coverage_ok: !!raw.coverage_ok,
        coverage_gaps: (raw.coverage_gaps as string[]) ?? [],
        executive_summary: raw.executive_summary as string | undefined,
        run_id: raw.run_id as string | undefined,
        new_items_count: raw.new_items_count as number | undefined,
        alerted_count: raw.alerted_count as number | undefined,
      });
    } else {
      handlers.onError("Agent finished but returned an unreadable result.");
    }
    es.close();
    handlers.onDone();
  });

  es.onerror = () => {
    // EventSource also fires onerror on a normal server-side stream close, so only
    // report a connection problem if the run never produced its final event
    if (finished) return;
    handlers.onError(`Could not reach agent backend at ${API_URL}. Is it running?`);
    es.close();
    handlers.onDone();
  };

  return () => es.close();
}

function runWebhook(goal: string, context: string, handlers: RunHandlers): Cancel {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal, context, session_id: getSessionId() }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`Webhook returned ${res.status}`);
      const data = await res.json();
      const steps = (data.trace ?? []) as Parameters<typeof normalizeN8nStep>[0][];

      // n8n returns the whole run at once — reveal steps with a delay to keep the live feel
      for (const raw of steps) {
        if (controller.signal.aborted) return;
        await sleep(350);
        handlers.onStep(normalizeN8nStep(raw));
      }
      if (controller.signal.aborted) return;
      handlers.onFinal({
        items: data.final?.items ?? [],
        coverage_ok: !!data.final?.coverage_ok,
        coverage_gaps: data.final?.coverage_gaps ?? [],
        executive_summary: data.final?.executive_summary,
      });
    } catch (e) {
      if (controller.signal.aborted) return;
      handlers.onError(
        `Could not reach n8n webhook at ${WEBHOOK_URL}. Is the workflow active? (${(e as Error).message})`
      );
    } finally {
      if (!controller.signal.aborted) handlers.onDone();
    }
  })();

  return () => controller.abort();
}

export function runAgent(
  mode: AgentMode,
  goal: string,
  context: string,
  handlers: RunHandlers
): Cancel {
  return mode === "backend" ? runBackend(goal, context, handlers) : runWebhook(goal, context, handlers);
}
