"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, AlertTriangle } from "lucide-react";
import ResultsList from "@/components/ResultsList";
import StrategyPanel from "@/components/StrategyPanel";
import SignalSummary from "@/components/SignalSummary";
import SelfEvalPanel from "@/components/SelfEvalPanel";
import AskPanel from "@/components/AskPanel";
import { fetchRun } from "@/lib/history-client";
import type { FinalResult, RunSummary, Step } from "@/lib/types";

type Loaded = {
  final: FinalResult;
  trace: Step[];
  summary?: Pick<RunSummary, "goal" | "context" | "started_at" | "finished_at">;
};

function impactTier(score: number) {
  if (score >= 8) return { label: "HIGH IMPACT", bg: "bg-[#FEF2F2]", fg: "text-[var(--danger)]", border: "border-[#FECACA]" };
  if (score >= 5) return { label: "MEDIUM IMPACT", bg: "bg-amber-50", fg: "text-[var(--warning)]", border: "border-amber-200" };
  return { label: "LOW IMPACT", bg: "bg-[var(--surface-2)]", fg: "text-[var(--foreground-secondary)]", border: "border-[var(--border)]" };
}

export default function IntelligencePage() {
  const params = useParams<{ id: string }>();
  // Keying by id remounts Report on navigation between two reports, so its
  // state starts fresh instead of needing a synchronous reset inside an effect.
  return <Report key={params.id} id={params.id} />;
}

function Report({ id }: { id: string }) {
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // A just-finished run is stashed client-side before the redirect here —
    // read that first so the report renders instantly with zero network
    // round trips, and so an n8n-sourced run (no backend run_id, nothing to
    // fetch) still has somewhere to come from.
    let cached: string | null = null;
    try {
      cached = sessionStorage.getItem(`agentx-result-${id}`);
    } catch {
      // fall through to fetching
    }
    if (cached) {
      const parsed = JSON.parse(cached) as { final: FinalResult; trace: Step[] };
      // deferred to a microtask so this still counts as a callback rather
      // than a synchronous setState in the effect body
      Promise.resolve().then(() => setData({ final: parsed.final, trace: parsed.trace ?? [] }));
      return;
    }

    fetchRun(id)
      .then((run) =>
        setData({
          final: run.final,
          trace: run.trace,
          summary: { goal: run.goal, context: run.context, started_at: run.started_at, finished_at: run.finished_at },
        })
      )
      .catch((e) => setError((e as Error).message));
  }, [id]);

  return (
    <div className="max-w-5xl mx-auto pb-12 animate-slide-up">
      <div className="mb-8">
        <Link
          href="/activity"
          className="inline-flex items-center text-sm font-medium text-[var(--foreground-secondary)] hover:text-[var(--foreground)] mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4 mr-1" />
          All investigations
        </Link>

        {data?.summary?.goal && (
          <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-2">{data.summary.goal}</h1>
        )}
        {!data?.summary && <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-2">Intelligence report</h1>}

        {data && (
          <div className="flex items-center gap-3 flex-wrap">
            <div
              className={`flex items-center gap-2 px-3 py-1 rounded border font-medium text-sm tracking-wide ${
                data.final.coverage_ok
                  ? "bg-teal-50 text-[var(--accent-secondary)] border-teal-200"
                  : "bg-[#FEF2F2] text-[var(--danger)] border-[#FECACA]"
              }`}
            >
              {data.final.coverage_ok ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
              {data.final.coverage_ok ? "Coverage OK" : "Coverage thin"}
            </div>
            {data.final.pipeline && (
              <span className="font-mono text-sm text-[var(--foreground)] bg-[var(--surface-2)] px-2 py-1 rounded border border-[var(--border)]">
                {data.final.pipeline} pipeline{data.final.model ? ` · ${data.final.model}` : ""}
              </span>
            )}
          </div>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-[var(--danger)] bg-red-50 rounded-lg px-3 py-2.5 border border-red-200">
          {error}
        </p>
      )}
      {!data && !error && <p className="text-sm text-[var(--foreground-secondary)]">Loading report…</p>}

      {data && (
        <div className="space-y-8">
          {(() => {
            const top = [...data.final.items].sort((a, b) => b.impact_1_10 - a.impact_1_10)[0];
            if (!top) return null;
            const tier = impactTier(top.impact_1_10);
            const coverage = data.final.self_evaluation?.coverage_score;
            return (
              <div className="grid gap-6 lg:grid-cols-[1fr_auto] items-start">
                <div>
                  <div className={`inline-flex items-center gap-2 px-3 py-1 rounded border font-medium text-sm tracking-wide mb-4 ${tier.bg} ${tier.fg} ${tier.border}`}>
                    <AlertTriangle className="w-4 h-4" />
                    {tier.label}
                  </div>
                  <h2 className="text-2xl font-semibold text-[var(--foreground)] leading-snug mb-2">{top.title}</h2>
                  <p className="text-sm text-[var(--foreground-secondary)]">
                    {top.organization || top.competitor ? `${top.competitor || top.organization} · ` : ""}
                    {top.source}
                    {top.relevance_reason ? ` — ${top.relevance_reason}` : ""}
                  </p>
                </div>
                <div className="surface-card px-6 py-4 text-center shrink-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--foreground-secondary)] mb-1">
                    Impact score
                  </p>
                  <p className="text-4xl font-bold text-[var(--foreground)] tabular-nums leading-none">
                    {top.impact_1_10}
                    <span className="text-base text-[var(--foreground-secondary)] font-medium">/10</span>
                  </p>
                  {coverage != null && (
                    <p className="text-[11px] text-[var(--foreground-secondary)] mt-2">
                      {Math.round(coverage * 100)}% evidence coverage
                    </p>
                  )}
                </div>
              </div>
            );
          })()}

          {data.final.executive_summary && (
            <div className="text-xl text-[var(--foreground)] leading-relaxed">{data.final.executive_summary}</div>
          )}

          <SignalSummary final={data.final} steps={data.trace} />
          <SelfEvalPanel
            selfEvaluation={data.final.self_evaluation}
            conflicts={data.final.conflicts}
            resourceUsage={data.final.resource_usage}
          />
          <StrategyPanel strategy={data.final.strategy} />
          <ResultsList final={data.final} running={false} />

          <div className="surface-card p-6">
            <AskPanel runId={data.final.run_id ?? (id !== "new" ? id : null)} />
          </div>
        </div>
      )}
    </div>
  );
}
