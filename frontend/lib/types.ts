export type Item = {
  source: string;
  title: string;
  url: string;
  summary: string;
  relevance_reason: string;
  impact_1_10: number;
  organization?: string;
};

export type FinalResult = {
  items: Item[];
  coverage_ok: boolean;
  coverage_gaps?: string[];
  executive_summary?: string;
};

export type ToolCall = {
  tool: string;
  input: unknown;
};

// n8n's pipeline is two agents (Research -> Analyst) — steps carry which one
// produced them so the trace can show the handoff, not just a flat list
export type AgentTag = "research" | "analyst";

export type Step = {
  thought?: string;
  calls: ToolCall[];
  observation?: unknown;
  agent?: AgentTag;
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
  onFinal: (final: FinalResult) => void;
  onError: (message: string) => void;
  onDone: () => void;
};

export type Cancel = () => void;
