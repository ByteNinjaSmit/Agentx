export type Item = {
  source: string;
  title: string;
  url: string;
  summary: string;
  relevance_reason: string;
  impact_1_10: number;
  organization?: string;
  /** Which watched competitor this finding is evidence about — "" when it belongs
   *  to the wider market lane rather than to anyone on the watchlist. */
  competitor?: string;
  date?: string | null;
  engagement?: number | null;
  /** Fleet only: the text from a real tool result that this finding was matched against. */
  grounded_on?: string;
  /** Fleet only: which sub-questions surfaced it. More than one is a stronger signal. */
  found_by?: string[];
  /** Set when this item's organization had conflicting signal strength across
   *  sources and the verifier ran a resolution pass over it. */
  conflict_note?: string;
  /** 0-1 confidence from conflict resolution, when it ran for this item's organization. */
  confidence?: number;
};

/** The fleet's coverage self-check after the analyst step: did enough
 *  sub-questions actually produce a kept finding, and if not, did the planner
 *  open a bounded follow-up round to close the gap. */
export type SelfEvaluation = {
  coverage_score: number;
  threshold: number;
  replanned: boolean;
  replan_rationale?: string | null;
};

/** One organization where sources disagreed on signal strength strongly enough
 *  to trigger a resolution pass, and what the resolver concluded. */
export type Conflict = {
  organization: string;
  note: string;
  confidence?: number | null;
  items: string[];
};

/** What the run actually spent against its tool-call and wall-clock budget —
 *  the concrete number behind "skipped the replan because the budget was tight". */
export type ResourceUsage = {
  tool_calls_used: number;
  tool_call_budget: number;
  elapsed_seconds: number;
  time_budget_seconds: number;
};

export type Competitor = {
  organization: string;
  threat_level: "high" | "medium" | "low" | string;
  evidence?: string[];
  assessment?: string;
};

export type RecommendedAction = {
  action: string;
  rationale?: string;
  horizon?: "now" | "quarter" | "year" | string;
};

export type Strategy = {
  competitors?: Competitor[];
  opportunities?: string[];
  risks?: string[];
  recommended_actions?: RecommendedAction[];
};

export type SubQuestion = {
  question: string;
  sources?: string[];
  why?: string;
  /** Set when the lane was created for one named competitor rather than by the planner. */
  competitor?: string | null;
};

/** What the operator dials in before a scan: the market, who is being watched,
 *  and how deep to go per source. */
export type MarketParams = {
  track: string;
  competitors: string[];
  depth: number;
  context: string;
};

export type FinalResult = {
  items: Item[];
  coverage_ok: boolean;
  coverage_gaps?: string[];
  executive_summary?: string;
  run_id?: string;
  new_items_count?: number;
  alerted_count?: number;
  strategy?: Strategy;
  plan?: SubQuestion[];
  rejected_count?: number;
  provider?: string;
  model?: string;
  pipeline?: Pipeline;
  input_tokens?: number;
  output_tokens?: number;
  /** Echo of the market parameters the run was launched with. */
  competitors_watched?: string[];
  track?: string;
  depth?: number;
  /** Fleet only: coverage self-check and whether it triggered a replan. */
  self_evaluation?: SelfEvaluation;
  /** Fleet only: organizations where sources disagreed and were reconciled. */
  conflicts?: Conflict[];
  /** Fleet only: tool-call/time budget spent, and the limits it ran against. */
  resource_usage?: ResourceUsage;
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
  /** Name of the secondary source this call recovered on, when the primary
   *  one failed — null when the primary source answered normally. */
  fallback_used?: string | null;
};

// Which specialist produced a step. "research"/"analyst" are the n8n workflow's
// two agents; the rest are the Python fleet's.
export type AgentTag =
  | "planner"
  | "researcher"
  | "verifier"
  | "analyst"
  | "strategist"
  | "research"
  /** Fleet only: a tool recovered on a fallback source mid-run. */
  | "runtime";

export type Pipeline = "fleet" | "single";

export type Step = {
  step?: number;
  thought?: string;
  calls: ToolCall[];
  observation?: unknown; // n8n: a single opaque observation string per step
  observations?: Observation[]; // backend: one structured record per tool call
  agent?: AgentTag;
  /** Which parallel researcher produced this step, and the sub-question it owns. */
  lane?: number;
  lane_label?: string;
  plan?: SubQuestion[];
  rejected?: { title?: string; url?: string; source?: string; reason?: string }[];
  input_tokens?: number;
  output_tokens?: number;
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

export type ProviderInfo = {
  providers: string[];
  default: string | null;
  pipelines: Pipeline[];
};

/* ---------------------------------------------------------------- statistics */

export type Stats = {
  overview: {
    items: number;
    sources: number;
    organizations: number;
    avg_impact: number | null;
    high_impact: number;
    new_this_week: number;
    runs: number;
    unfinished: number;
    avg_seconds: number | null;
    input_tokens: number;
    output_tokens: number;
  };
  by_source: {
    source: string;
    items: number;
    avg_impact: number | null;
    max_impact: number | null;
    avg_engagement: number | null;
  }[];
  by_competitor: {
    competitor: string;
    items: number;
    avg_impact: number | null;
    max_impact: number | null;
    last_seen: string | null;
    new_this_week: number;
    sources: string[];
  }[];
  by_organization: {
    organization: string;
    items: number;
    avg_impact: number | null;
    max_impact: number | null;
    last_seen: string | null;
    sources: string[];
  }[];
  momentum: { week: string; source: string; items: number; avg_impact: number | null }[];
  impact_distribution: { from: number; to: number; items: number }[];
  source_reliability: {
    tool: string;
    calls: number;
    ok_calls: number;
    success_rate: number | null;
    p50_ms: number | null;
    p95_ms: number | null;
  }[];
  run_economics: {
    id: string;
    goal: string;
    started_at: string | null;
    pipeline: string | null;
    provider: string | null;
    model: string | null;
    input_tokens: number | null;
    output_tokens: number | null;
    item_count: number;
    gap_count: number;
    new_items_count: number;
    seconds: number | null;
  }[];
  novelty: {
    id: string;
    title: string;
    source: string;
    organization: string | null;
    impact_score: number | null;
    first_seen_at: string | null;
    novelty: number | null;
  }[];
};

/* ------------------------------------------------------------------- Q&A */

export type Citation = {
  id: string;
  source: string;
  title: string;
  url: string;
  summary: string;
  relevance_reason: string | null;
  organization: string | null;
  impact_1_10: number | null;
  date: string | null;
  matched_by: "both" | "semantic" | "keyword";
};

export type Answer = {
  question: string;
  answer: string;
  citations: Citation[];
  cited: number[];
  provider: string;
  model: string;
};

/* ------------------------------------------------------------ evaluation */

export type CategoryTally = { runs: number; checks: number; passed: number };
export type CheckTally = { runs: number; passed: number };
export type PipelineTally = { runs: number; checks: number; passed: number };

export type BenchmarkSummary = {
  generated_at: string;
  pipelines: string[];
  repeat: number;
  cases_total: number;
  categories_total: number;
  runs: { total: number; with_error: number };
  checks: { total: number; passed: number };
  overall_pct: number | null;
  by_category: Record<string, CategoryTally>;
  by_check: Record<string, CheckTally>;
  by_pipeline: Record<string, PipelineTally>;
  consistency: { case_id: string; pipeline: string; rate: number }[];
  failures: { case_id: string; category: string; pipeline: string; repeat_index: number; check: string; detail: string }[];
};

export type FaultInjectionRun = {
  label: string;
  tool_calls_used: number;
  elapsed_seconds: number;
  input_tokens: number;
  output_tokens: number;
  fallback_count: number;
  error_count: number;
  items_count: number;
  coverage_ok: boolean;
};

export type FaultInjection = {
  before_after: { before: FaultInjectionRun; after: FaultInjectionRun; deltas: Record<string, number> } | null;
  diagnosis: Record<string, unknown> | null;
  action_applied: boolean | null;
  improvement_pct: Record<string, number> | null;
};

export type JudgeSample = {
  case_id: string;
  category: string;
  pipeline: string;
  accuracy: number;
  groundedness: number;
  completeness: number;
  evidence_quality: number;
  uncertainty_handling: number;
  unsupported_claims: number;
  overall: number;
  parse_ok: boolean;
  reason: string;
};

export type LlmJudgeSummary = {
  cases_judged: number;
  averages: Record<string, number | null>;
  samples: JudgeSample[];
};

export type HumanEvalProgress = { total_rows: number; scored_rows: number };

export type EvaluationDashboard = {
  benchmark: BenchmarkSummary | null;
  fault_injection: FaultInjection | null;
  llm_judge: LlmJudgeSummary | null;
  human_eval: HumanEvalProgress | null;
};
