"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Activity, Plus, TrendingUp } from "lucide-react";
import { fetchStats } from "@/lib/insight-client";
import { ChartFrame, EmptyChart, LineChart, type LineSeries } from "@/components/charts/Charts";
import type { Stats } from "@/lib/types";

function timeAgo(iso: string | null) {
  if (!iso) return "never scanned";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function MonitorPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchStats()
      .then(setStats)
      .catch((e) => setError((e as Error).message));
  }, []);

  const momentum = useMemo<LineSeries[]>(() => {
    if (!stats) return [];
    const bySource = new Map<string, { x: string; y: number }[]>();
    for (const row of stats.momentum) {
      const points = bySource.get(row.source) ?? [];
      points.push({ x: row.week, y: row.items });
      bySource.set(row.source, points);
    }
    return [...bySource.entries()]
      .sort((a, b) => b[1].reduce((s, p) => s + p.y, 0) - a[1].reduce((s, p) => s + p.y, 0))
      .slice(0, 6)
      .map(([name, points]) => ({ name, points }));
  }, [stats]);

  const watchlist = useMemo(() => {
    if (!stats) return [];
    return [...stats.by_competitor].sort(
      (a, b) => b.new_this_week - a.new_this_week || b.items - a.items
    );
  }, [stats]);

  return (
    <div className="max-w-5xl mx-auto pb-12 animate-slide-up">
      <div className="mb-10">
        <h1 className="text-3xl font-semibold text-[var(--foreground)] mb-2 uppercase tracking-wide">
          Monitoring
        </h1>
        <p className="text-[var(--foreground-secondary)]">
          Every competitor named across past runs, tracked automatically from what the agent
          actually found.
        </p>
      </div>

      {error && (
        <p role="alert" className="text-sm text-[var(--danger)] bg-red-50 rounded-lg px-3 py-2.5 border border-red-200 mb-6">
          {error}
        </p>
      )}
      {!stats && !error && <p className="text-sm text-[var(--foreground-secondary)]">Loading…</p>}

      {stats && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
          {/* Left Column: Watchlist */}
          <div className="lg:col-span-1">
            <h2 className="text-sm font-semibold text-[var(--foreground)] mb-4">Tracked competitors</h2>

            {watchlist.length === 0 ? (
              <div className="surface-card p-4 mb-4 text-sm text-[var(--foreground-secondary)]">
                No competitor has been named in a run yet.
              </div>
            ) : (
              <div className="space-y-3 mb-4">
                {watchlist.map((c) => (
                  <div key={c.competitor} className="surface-card p-4 relative overflow-hidden">
                    {c.new_this_week > 0 && (
                      <div className="absolute top-0 left-0 w-1 h-full bg-[var(--accent)]" />
                    )}
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="font-semibold text-[var(--foreground)]">{c.competitor}</h3>
                      {c.new_this_week > 0 && (
                        <span className="flex items-center gap-1.5 text-xs font-medium text-[var(--accent)]">
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--accent)] opacity-75" />
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--accent)]" />
                          </span>
                          {c.new_this_week} new
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[var(--foreground-secondary)] mb-3">
                      {c.sources.join(" · ") || "no source breakdown yet"}
                    </p>
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-[var(--border-highlight)]">
                        {timeAgo(c.last_seen)} · {c.items} signal{c.items === 1 ? "" : "s"}
                      </span>
                      <Link
                        href={`/investigate/new?goal=${encodeURIComponent(
                          `Find new developments and competitor activity for ${c.competitor}`
                        )}&competitors=${encodeURIComponent(c.competitor)}`}
                        className="font-medium text-[var(--accent)] hover:underline"
                      >
                        Scan now →
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <Link
              href="/"
              className="w-full py-3 border border-dashed border-[var(--border-highlight)] rounded-xl text-sm font-medium text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:border-[var(--border)] hover:bg-[var(--surface)] transition-all flex items-center justify-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Name a new competitor in an investigation
            </Link>
          </div>

          {/* Right Column: What Changed */}
          <div className="lg:col-span-2 space-y-6">
            <h2 className="text-2xl font-semibold text-[var(--foreground)]">What Changed?</h2>

            <ChartFrame
              title="Signal momentum"
              hint="Findings per week by source, across every run stored so far."
            >
              {momentum.length ? <LineChart series={momentum} yLabel="items per week" /> : <EmptyChart message="Not enough history yet." />}
            </ChartFrame>

            <div>
              <h3 className="text-sm font-semibold text-[var(--foreground)] mb-3 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-[var(--accent)]" />
                Most novel recent signals
              </h3>
              {stats.novelty.length === 0 ? (
                <div className="surface-card p-6 text-center text-sm text-[var(--foreground-secondary)]">
                  No scored findings yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {stats.novelty.slice(0, 6).map((n) => (
                    <div key={n.id} className="surface-card p-4 flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <p className="font-medium text-sm text-[var(--foreground)] truncate">{n.title}</p>
                        <p className="text-xs text-[var(--foreground-secondary)] mt-0.5">
                          {n.source}
                          {n.organization ? ` · ${n.organization}` : ""}
                          {n.first_seen_at ? ` · first seen ${timeAgo(n.first_seen_at)}` : ""}
                        </p>
                      </div>
                      <div className="flex items-center gap-3 shrink-0 text-xs">
                        {n.impact_score != null && (
                          <span className="font-mono px-2 py-0.5 bg-[var(--surface-2)] rounded border border-[var(--border)]">
                            {n.impact_score}/10
                          </span>
                        )}
                        {n.novelty != null && (
                          <span className="flex items-center gap-1 text-[var(--accent-secondary)]">
                            <Activity className="w-3 h-3" />
                            {n.novelty.toFixed(2)} novelty
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
