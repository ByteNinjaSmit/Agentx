import { API_URL, normalizeBackendStep, normalizeN8nStep } from "./agent-client";
import type { RunDetail, RunSummary, Step } from "./types";

export async function fetchRuns(limit = 30): Promise<RunSummary[]> {
  const res = await fetch(`${API_URL}/runs?limit=${limit}`);
  if (!res.ok) throw new Error(`History unavailable (${res.status})`);
  return res.json();
}

// Python backend rows store {thought, tools_called: [...]}; n8n-sourced rows
// (written by the workflow's own Log Run node) store {action: {...}, observation}.
// Same run_log table, two shapes — detect per-row instead of assuming one.
function normalizeStoredStep(raw: unknown): Step {
  if (raw && typeof raw === "object" && "action" in raw) {
    return normalizeN8nStep(raw as Parameters<typeof normalizeN8nStep>[0]);
  }
  return normalizeBackendStep(raw as Parameters<typeof normalizeBackendStep>[0]);
}

export async function fetchRun(id: string): Promise<RunDetail> {
  const res = await fetch(`${API_URL}/runs/${id}`);
  if (!res.ok) throw new Error(`Run not found (${res.status})`);
  const raw = await res.json();
  return {
    ...raw,
    trace: (raw.trace ?? []).map(normalizeStoredStep),
  };
}
