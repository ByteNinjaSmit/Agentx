export type Item = {
  source: string;
  title: string;
  url: string;
  summary: string;
  relevance_reason: string;
  impact_1_10: number;
};

export type FinalResult = {
  items: Item[];
  coverage_ok: boolean;
};

export type ToolCall = {
  tool: string;
  input: unknown;
};

export type Step = {
  thought?: string;
  calls: ToolCall[];
  observation?: unknown;
};

export type AgentMode = "backend" | "n8n";

export type RunHandlers = {
  onStep: (step: Step) => void;
  onFinal: (final: FinalResult) => void;
  onError: (message: string) => void;
  onDone: () => void;
};

export type Cancel = () => void;
