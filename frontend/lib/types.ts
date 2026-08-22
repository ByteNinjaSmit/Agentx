export type Item = {
  source: string;
  title: string;
  url: string;
  summary: string;
  relevance_reason: string;
  impact_1_10: number;
  organization?: string;
  date?: string | null;
  engagement?: number | null;
};

export type FinalResult = {
  items: Item[];
  coverage_ok: boolean;
  coverage_gaps?: string[];
  executive_summary?: string;
  run_id?: string;
  new_items_count?: number;
  alerted_count?: number;
};

export type ToolCall = {
  tool: string;
  input: unknown;
};

// One grounded observation: what the tool actually returned, whether it worked,
// and how long it took. The backend emits these in a separate SSE event after the
// thought, so the terminal can show Thought -> Action -> Observation as it happens.
export type Observation = {
  tool: string;
  query?: string | null;
  ok: boolean;
  count?: number | null;
  latency_ms?: number;
  preview?: string;
  error?: string | null;
};

// n8n's pipeline is two agents (Research -> Analyst) — steps carry which one
// produced them so the trace can show the handoff, not just a flat list
export type AgentTag = "research" | "analyst";

export type Step = {
  thought?: string;
  calls: ToolCall[];
  observation?: unknown; // n8n: a single opaque observation string per step
  observations?: Observation[]; // backend: one structured record per tool call
  agent?: AgentTag;
};

export type RunStatus = {
  phase: string;
  message: string;
};

export type AgentMode = "backend" | "n8n";

export type RunSummary = {
  id: string;
  goal: string;
  context: string | null;
  coverage_ok: boolean;
  coverage_gaps: string[];
  item_count: number;
  new_items_count: number;
  started_at: string | null;
  finished_at: string | null;
};

export type RunDetail = RunSummary & {
  trace: Step[];
  final: FinalResult;
};

export type RunHandlers = {
  onStep: (step: Step) => void;
  /** Backend only: attaches observations to an already-emitted step by index. */
  onObservation: (stepIndex: number, results: Observation[]) => void;
  onStatus: (status: RunStatus) => void;
  onFinal: (final: FinalResult) => void;
  onError: (message: string) => void;
  onDone: () => void;
};

export type Cancel = () => void;
