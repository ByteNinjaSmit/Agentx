import { API_URL, normalizeBackendStep } from "./agent-client";
import type { RunDetail, RunSummary } from "./types";

export async function fetchRuns(limit = 30): Promise<RunSummary[]> {
  const res = await fetch(`${API_URL}/runs?limit=${limit}`);
  if (!res.ok) throw new Error(`History unavailable (${res.status})`);
  return res.json();
}

export async function fetchRun(id: string): Promise<RunDetail> {
  const res = await fetch(`${API_URL}/runs/${id}`);
  if (!res.ok) throw new Error(`Run not found (${res.status})`);
  const raw = await res.json();
  return {
    ...raw,
    trace: (raw.trace ?? []).map(normalizeBackendStep),
  };
}
