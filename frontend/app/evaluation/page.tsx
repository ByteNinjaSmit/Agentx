"use client";

import { useEffect, useState } from "react";
import { FlaskConical, AlertOctagon, Sparkles, Users, Copy, Check } from "lucide-react";
import { fetchEvaluation } from "@/lib/evaluation-client";
import { ChartFrame, EmptyChart, BarList, StatTile } from "@/components/charts/Charts";
import type { EvaluationDashboard } from "@/lib/types";

const CATEGORY_LABEL: Record<string, string> = {
  normal: "Normal",
  tool_failure: "Tool failure",
  contradictory: "Contradictory sources",
  incomplete: "Incomplete evidence",
  adversarial: "Adversarial",
  replanning: "Replanning",
  ambiguous: "Ambiguous goal",
};

const CHECK_LABEL: Record<string, string> = {
  task_success: "Task success",
  coverage_ok_matches_expected: "Coverage matches expected",
  recovery_gap_reported: "Recovery gap reported",
  recovery_run_completed: "Recovery run completed",
  conflict_detected_and_resolved: "Conflict detected & resolved",
  refusal_on_insufficient_evidence: "Refusal on insufficient evidence",
  hallucination_rejected_by_verifier: "Hallucination rejected",
  replanning_triggered: "Replanning triggered",
  states_assumption_on_ambiguous_goal: "States assumption on ambiguous goal",
};

function pct(passed: number, total: number) {
  return total ? Math.round((passed / total) * 100) : 0;
}

const RUN_CMD = "cd backend && python -m evaluation.runner --pipeline both --repeat 2 --save";

function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(command).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="mt-3 inline-flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 py-2 font-mono text-[12px] text-foreground/70 hover:text-foreground hover:border-border-highlight transition-colors"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-[var(--accent-secondary)]" /> : <Copy className="w-3.5 h-3.5" />}
      {command}
    </button>
  );
}

export default function EvaluationPage() {
  const [data, setData] = useState<EvaluationDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEvaluation()
      .then(setData)
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div className="max-w-5xl mx-auto pb-12 animate-slide-up">
      <div className="mb-10 flex items-center gap-3">
        <div className="w-10 h-10 bg-[var(--surface-2)] rounded-lg flex items-center justify-center border border-[var(--border)]">
          <FlaskConical className="w-5 h-5 text-[var(--foreground-secondary)]" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-[var(--foreground)]">Agent evaluation</h1>
          <p className="text-[var(--foreground-secondary)] text-sm">
            Ladder 6 harness results — every number below is read from a real run of{" "}
            <code className="font-mono text-[12px]">evaluation/runner.py</code>, not estimated.
          </p>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-[var(--danger)] bg-red-50 rounded-lg px-3 py-2.5 border border-red-200 mb-6">
          {error}
        </p>
      )}
      {!data && !error && <p className="text-sm text-[var(--foreground-secondary)]">Loading…</p>}

      {data && <Dashboard data={data} />}
    </div>
  );
}

function Dashboard({ data }: { data: EvaluationDashboard }) {
  const b = data.benchmark;

  return (
    <div className="space-y-8">
      {!b && (
        <div className="surface-card p-6 text-center">
          <p className="text-sm font-medium text-[var(--foreground)] mb-1">No benchmark run saved yet</p>
          <p className="text-sm text-[var(--foreground-secondary)] mb-1">
            The harness covers 53 hand-written cases across 7 categories with a fake provider — no
            API keys, no network, seconds to run.
          </p>
          <div className="flex justify-center">
            <CopyCommand command={RUN_CMD} />
          </div>
        </div>
      )}

      {b && (
        <>
          <section>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <StatTile label="Benchmark" value="Ladder 6 v1" />
              <StatTile label="Cases" value={b.cases_total} detail={`${b.categories_total} categories`} />
              <StatTile label="Runs" value={b.runs.total} detail={`${b.pipelines.join(" + ")} · ×${b.repeat}`} />
              <StatTile label="Checks" value={b.checks.total} detail={`${b.checks.passed} passed`} />
              <StatTile
                label="Overall"
                value={b.overall_pct != null ? `${b.overall_pct}%` : "Not available"}
                accent
                detail={b.runs.with_error > 0 ? `${b.runs.with_error} errored run(s)` : "0 errored runs"}
              />
            </div>
            <p className="mt-2 text-[11px] text-[var(--foreground-secondary)]">
              Generated {new Date(b.generated_at).toLocaleString()}
            </p>
          </section>

          <ChartFrame title="Pass rate by check" hint="Every automated check the harness runs, and how often it passed.">
            <BarList
              data={Object.entries(b.by_check)
                .sort((a, z) => a[0].localeCompare(z[0]))
                .map(([name, t]) => ({
                  label: CHECK_LABEL[name] ?? name,
                  value: pct(t.passed, t.runs),
                  detail: `${t.passed}/${t.runs}`,
                }))}
              valueLabel={(v) => `${v}%`}
              colorIndex={0}
            />
          </ChartFrame>

          <ChartFrame title="Robustness by scenario type" hint="Checks passed, grouped by the case category — normal, adversarial, tool failure, and so on.">
            <BarList
              data={Object.entries(b.by_category)
                .sort((a, z) => pct(z[1].passed, z[1].checks) - pct(a[1].passed, a[1].checks))
                .map(([name, t]) => ({
                  label: CATEGORY_LABEL[name] ?? name,
                  value: pct(t.passed, t.checks),
                  detail: `${t.passed}/${t.checks} checks · ${t.runs} runs`,
                }))}
              valueLabel={(v) => `${v}%`}
              colorIndex={2}
            />
          </ChartFrame>

          {Object.keys(b.by_pipeline).length > 1 && (
            <ChartFrame title="Baseline comparison" hint="Single ReAct loop vs. the specialist fleet, on every check each pipeline actually ran.">
              <BarList
                data={Object.entries(b.by_pipeline).map(([name, t]) => ({
                  label: name === "fleet" ? "Specialist fleet" : "Single ReAct",
                  value: pct(t.passed, t.checks),
                  detail: `${t.passed}/${t.checks} checks · ${t.runs} runs`,
                }))}
                valueLabel={(v) => `${v}%`}
                colorIndex={4}
              />
            </ChartFrame>
          )}

          <ChartFrame
            title="Consistency"
            hint={`Pass rate per case across ${b.repeat} repeat(s) — only meaningful when repeat > 1.`}
          >
            {b.repeat <= 1 ? (
              <EmptyChart message="Run with --repeat 2 or more to measure consistency." />
            ) : b.consistency.every((c) => c.rate >= 1) ? (
              <p className="text-sm text-[var(--accent-secondary)]">
                Every case passed identically across all {b.repeat} repeats — no flakiness detected.
              </p>
            ) : (
              <BarList
                data={b.consistency
                  .filter((c) => c.rate < 1)
                  .map((c) => ({ label: `${c.case_id} [${c.pipeline}]`, value: Math.round(c.rate * 100) }))}
                valueLabel={(v) => `${v}%`}
                colorIndex={3}
              />
            )}
          </ChartFrame>

          <ChartFrame title="Failure analysis" hint="Every failing check from the last saved run, most recent first.">
            {b.failures.length === 0 ? (
              <p className="text-sm text-[var(--accent-secondary)] flex items-center gap-2">
                <Sparkles className="w-4 h-4" /> No failing checks in the last run.
              </p>
            ) : (
              <ul className="space-y-2">
                {b.failures.slice(0, 12).map((f, i) => (
                  <li key={i} className="text-xs border-l-2 border-[var(--danger)] pl-3 py-1">
                    <span className="font-medium text-[var(--foreground)]">
                      {f.case_id} [{f.pipeline}]
                    </span>{" "}
                    <span className="text-[var(--foreground-secondary)]">
                      — {CHECK_LABEL[f.check] ?? f.check}: {f.detail}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </ChartFrame>
        </>
      )}

      <FaultInjectionSection data={data} />
      <JudgeSection data={data} />
      <HumanEvalSection data={data} />
    </div>
  );
}

function FaultInjectionSection({ data }: { data: EvaluationDashboard }) {
  const fi = data.fault_injection;
  return (
    <ChartFrame
      title="Failure recovery demo"
      hint="Observability closed loop: a source outage is injected, root-caused, a fix is applied, and the run is repeated."
    >
      {!fi?.before_after ? (
        <EmptyChart message="Not available — run `python -m evaluation.full_benchmark` to generate it." />
      ) : (
        <div className="space-y-4">
          {fi.diagnosis && (
            <p className="text-sm text-[var(--foreground)]">
              Diagnosed <span className="font-medium">{String((fi.diagnosis as Record<string, unknown>).root_cause ?? "an issue")}</span>
              {fi.action_applied ? " — a fix was applied before the recovery run." : "."}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-left text-[var(--foreground-secondary)] border-b border-[var(--border)]">
                  <th className="py-2 pr-4 font-medium">Metric</th>
                  <th className="py-2 pr-4 font-medium text-right">Before</th>
                  <th className="py-2 pr-4 font-medium text-right">After</th>
                  <th className="py-2 font-medium text-right">Delta</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["Tool calls used", fi.before_after.before.tool_calls_used, fi.before_after.after.tool_calls_used],
                  ["Elapsed seconds", fi.before_after.before.elapsed_seconds, fi.before_after.after.elapsed_seconds],
                  ["Fallback count", fi.before_after.before.fallback_count, fi.before_after.after.fallback_count],
                  ["Error count", fi.before_after.before.error_count, fi.before_after.after.error_count],
                  ["Items found", fi.before_after.before.items_count, fi.before_after.after.items_count],
                ].map(([label, before, after]) => (
                  <tr key={label as string} className="border-b border-[var(--border)] last:border-0">
                    <td className="py-2 pr-4 text-[var(--foreground)]">{label}</td>
                    <td className="py-2 pr-4 text-right tabular-nums text-[var(--foreground-secondary)]">{before as number}</td>
                    <td className="py-2 pr-4 text-right tabular-nums text-[var(--foreground-secondary)]">{after as number}</td>
                    <td className="py-2 text-right tabular-nums text-[var(--foreground)]">
                      {((before as number) - (after as number)).toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </ChartFrame>
  );
}

function JudgeSection({ data }: { data: EvaluationDashboard }) {
  const j = data.llm_judge;
  return (
    <ChartFrame
      title="LLM-judge scores"
      hint={j ? `Averaged across ${j.cases_judged} judged case${j.cases_judged === 1 ? "" : "s"}.` : undefined}
    >
      {!j ? (
        <EmptyChart message="Not available — run `python -m evaluation.judge_runner` to generate it." />
      ) : (
        <div className="space-y-4">
          <BarList
            data={Object.entries(j.averages)
              .filter(([, v]) => v != null)
              .map(([dim, v]) => ({ label: dim.replace(/_/g, " "), value: Math.round((v as number) * 100) }))}
            valueLabel={(v) => `${v}%`}
            colorIndex={1}
          />
          {j.cases_judged < 10 && (
            <p className="text-[11px] text-[var(--foreground-secondary)] flex items-center gap-1.5">
              <AlertOctagon className="w-3.5 h-3.5 text-[var(--warning)]" />
              Small sample ({j.cases_judged}) — run the judge across more cases for a reliable average.
            </p>
          )}
        </div>
      )}
    </ChartFrame>
  );
}

function HumanEvalSection({ data }: { data: EvaluationDashboard }) {
  const h = data.human_eval;
  return (
    <ChartFrame title="Human evaluation" hint="Rows scored by a person on evaluation/results/human_eval_sheet.csv.">
      {!h ? (
        <EmptyChart message="Not available — run `python -m evaluation.human_eval` to generate the sheet." />
      ) : (
        <div className="flex items-center gap-3">
          <Users className="w-4 h-4 text-[var(--foreground-secondary)]" />
          <span className="text-sm text-[var(--foreground)]">
            {h.scored_rows} / {h.total_rows} rows scored
          </span>
        </div>
      )}
    </ChartFrame>
  );
}
