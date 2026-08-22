import type { AgentMode, Cancel, RunHandlers, Step } from "./types";

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

// backend /run emits {step, thought, tools_called: [{name, input}]} per SSE "trace" event
export function normalizeBackendStep(raw: {
  thought?: string;
  tools_called?: { name: string; input: unknown }[];
}): Step {
  return {
    thought: raw.thought,
    calls: (raw.tools_called ?? []).map((c) => ({ tool: c.name, input: c.input })),
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

  es.addEventListener("trace", (e) => {
    try {
      handlers.onStep(normalizeBackendStep(JSON.parse((e as MessageEvent).data)));
    } catch {
      // malformed trace event — skip, stream continues
    }
  });

  es.addEventListener("final", (e) => {
    try {
      const raw = JSON.parse((e as MessageEvent).data);
      handlers.onFinal({ items: raw.items ?? [], coverage_ok: !!raw.coverage_ok });
    } catch {
      handlers.onError("Agent finished but returned an unreadable result.");
    }
    es.close();
    handlers.onDone();
  });

  es.onerror = () => {
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
