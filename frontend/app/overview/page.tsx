"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, AlertTriangle } from "lucide-react";
import { fetchStats } from "@/lib/insight-client";
import { fetchRuns } from "@/lib/history-client";
import { StatTile } from "@/components/charts/Charts";
import type { RunSummary, Stats } from "@/lib/types";

function timeAgo(iso: string | null) {
  if (!iso) return "unknown time";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function OverviewPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchStats(), fetchRuns(5)])
      .then(([s, r]) => {
        setStats(s);
        setRuns(r);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const evidenceGroundedPct = useMemo(() => {
    if (!stats?.run_economics.length) return null;
    const grounded = stats.run_economics.filter((r) => r.gap_count === 0).length;
    return Math.round((grounded / stats.run_economics.length) * 100);
  }, [stats]);

  const reliabilityPct = useMemo(() => {
    if (!stats || !stats.overview.runs) return null;
    return Math.round(((stats.overview.runs - stats.overview.unfinished) / stats.overview.runs) * 100);
  }, [stats]);

  return (
    <div className="max-w-5xl mx-auto pb-12 animate-slide-up">
      <div className="mb-10">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)] mb-2">
          AgentX · Autonomous intelligence
        </p>
        <h1 className="text-3xl font-semibold text-[var(--foreground)] mb-2">Overview</h1>
        <p className="text-[var(--foreground-secondary)] text-lg max-w-2xl">
          Discover what changed. Understand why it matters. Decide what to do next.
        </p>
        <div className="flex items-center gap-3 mt-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-[var(--foreground)] text-[var(--surface)] font-medium rounded-lg hover:bg-[var(--accent)] transition-colors"
          >
            + New investigation
          </Link>
          <Link
            href="/intelligence"
            className="inline-flex items-center gap-2 px-5 py-2.5 border border-[var(--border)] text-[var(--foreground)] font-medium rounded-lg hover:bg-[var(--surface-2)] transition-colors"
          >
            View intelligence
          </Link>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-[var(--danger)] bg-red-50 rounded-lg px-3 py-2.5 border border-red-200 mb-6">
          {error}
        </p>
      )}
      {!stats && !error && <p className="text-sm text-[var(--foreground-secondary)]">Loading…</p>}

      {stats && (
        <>
          <section className="mb-10">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <StatTile label="New signals" value={stats.overview.new_this_week} detail="last 7 days" />
              <StatTile label="High impact" value={stats.overview.high_impact} detail="impact ≥ 8/10" accent />
              <StatTile
                label="Evidence grounded"
                value={evidenceGroundedPct != null ? `${evidenceGroundedPct}%` : "Not available"}
                detail="runs with no coverage gaps"
              />
              <StatTile
                label="Agent reliability"
                value={reliabilityPct != null ? `${reliabilityPct}%` : "Not available"}
                detail={`${stats.overview.runs} runs total`}
              />
              <StatTile label="Tracked competitors" value={stats.by_competitor.length} />
              <StatTile
                label="Avg impact"
                value={stats.overview.avg_impact != null ? `${stats.overview.avg_impact}/10` : "Not available"}
              />
            </div>
          </section>

          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground-secondary)]">
                Recent intelligence
              </h2>
              <Link href="/activity" className="text-xs font-medium text-[var(--accent)] hover:underline flex items-center gap-1">
                All activity <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {runs && runs.length === 0 && (
              <div className="surface-card p-8 text-center">
                <p className="text-sm text-[var(--foreground-secondary)] mb-3">No investigations yet.</p>
                <Link href="/" className="text-sm font-medium text-[var(--accent)] hover:underline">
                  Start your first intelligence investigation →
                </Link>
              </div>
            )}

            {runs && runs.length > 0 && (
              <div className="space-y-3">
                {runs.map((r) => (
                  <Link
                    key={r.id}
                    href={`/intelligence/${r.id}`}
                    className="surface-card p-4 flex items-start justify-between gap-4 block hover:border-[var(--border-highlight)] transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-[var(--foreground)] truncate">{r.goal}</p>
                      <p className="text-xs text-[var(--foreground-secondary)] mt-1">
                        {r.item_count} finding{r.item_count === 1 ? "" : "s"}
                        {r.new_items_count ? ` · ${r.new_items_count} new` : ""} · {timeAgo(r.finished_at)}
                      </p>
                    </div>
                    <div
                      className={`shrink-0 flex items-center gap-1.5 px-2 py-1 rounded border text-[11px] font-medium ${
                        r.coverage_ok
                          ? "bg-teal-50 text-[var(--accent-secondary)] border-teal-200"
                          : "bg-amber-50 text-[var(--warning)] border-amber-200"
                      }`}
                    >
                      {r.coverage_ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                      {r.coverage_ok ? "Coverage OK" : "Coverage thin"}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
