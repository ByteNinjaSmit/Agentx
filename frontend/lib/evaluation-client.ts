import { API_URL } from "./agent-client";
import type { EvaluationDashboard } from "./types";

export async function fetchEvaluation(): Promise<EvaluationDashboard> {
  const res = await fetch(`${API_URL}/evaluation`);
  if (!res.ok) throw new Error(`Evaluation data unavailable (${res.status})`);
  return res.json();
}
