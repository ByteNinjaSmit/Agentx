import { API_URL } from "./agent-client";
import type { Answer, Stats } from "./types";

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API_URL}/stats`);
  if (!res.ok) throw new Error(`Statistics unavailable (${res.status})`);
  return res.json();
}

export async function fetchSuggestions(): Promise<string[]> {
  const res = await fetch(`${API_URL}/ask/suggestions`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.questions ?? [];
}

export async function askQuestion(
  question: string,
  options: { runId?: string | null; provider?: string | null; signal?: AbortSignal } = {}
): Promise<Answer> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      run_id: options.runId ?? null,
      provider: options.provider ?? null,
    }),
    signal: options.signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Could not answer that (${res.status}). ${detail.slice(0, 200)}`);
  }
  return res.json();
}
