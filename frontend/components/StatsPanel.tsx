"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchStats } from "@/lib/insight-client";
import type { Stats } from "@/lib/types";
import {
  BarList,
  ChartFrame,
  EmptyChart,
  Histogram,
  LineChart,
  Scatter,
  type LineSeries,
} from "./charts/Charts";

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="surface-card p-4">
      <p className="text-[11px] font-medium uppercase tracking-wide text-foreground/40">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-foreground/40">{hint}</p>}
    </div>
  );
}

function compact(n: number | null | undefined) {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export default function StatsPanel() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showMomentumTable, setShowMomentumTable] = useState(false);

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
    // fixed slot order, never cycled: the six busiest sources keep their hue and a
    // seventh would fold into "Other" rather than inventing one
    return [...bySource.entries()]
      .sort((a, b) => b[1].reduce((s, p) => s + p.y, 0) - a[1].reduce((s, p) => s + p.y, 0))
      .slice(0, 6)
      .map(([name, points]) => ({ name, points }));
  }, [stats]);

  if (error) {
    return (
      <p role="alert" className="rounded-lg border border-danger/20 bg-danger/10 px-3 py-2.5 text-sm text-danger">
        {error}
      </p>
    );
  }
  if (!stats) return <p className="text-sm text-foreground/40">Loading statistics…</p>;

  const o = stats.overview;

  return (
    <div className="space-y-6">
      <p className="text-xs text-foreground/40">
        Every number here is computed in SQL over what the agent actually stored. Market
        size and revenue are not derivable from these sources, so they are absent rather
        than estimated.
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Findings" value={compact(o.items)} hint={`${o.new_this_week} new this week`} />
        <Tile
          label="High impact"
          value={compact(o.high_impact)}
          hint={`avg impact ${o.avg_impact ?? "—"}/10`}
        />
        <Tile
          label="Organizations"
          value={compact(o.organizations)}
          hint={`${o.sources} source types`}
        />
        <Tile
          label="Runs"
          value={compact(o.runs)}
          hint={`${compact(o.input_tokens + o.output_tokens)} tokens · ${o.avg_seconds ?? "—"}s avg`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame
          title="Who keeps showing up"
          hint="Findings per organization. Two spellings of one company still count separately — entity resolution is not implemented yet."
        >
          {stats.by_organization.length === 0 ? (
            <EmptyChart message="No organizations identified yet." />
          ) : (
            <BarList
              data={stats.by_organization.slice(0, 8).map((r) => ({
                label: r.organization,
                value: r.items,
                detail: `avg ${r.avg_impact ?? "—"}`,
              }))}
              valueLabel={(v) => `${v} item${v === 1 ? "" : "s"}`}
            />
          )}
        </ChartFrame>

        <ChartFrame title="Where findings come from" hint="Count and average impact per source.">
          {stats.by_source.length === 0 ? (
            <EmptyChart message="No findings stored yet." />
          ) : (
            <BarList
              colorIndex={2}
              data={stats.by_source.map((r) => ({
                label: r.source,
                value: r.items,
                detail: `avg ${r.avg_impact ?? "—"}`,
              }))}
            />
          )}
        </ChartFrame>
      </div>

      <ChartFrame
        title="Momentum"
        hint="Findings per week by source. The slope is the trend — nothing here asserts a direction the data doesn't show."
        action={
          <button
            onClick={() => setShowMomentumTable((v) => !v)}
            className="rounded-md border border-border px-2 py-1 text-[11px] text-foreground/60 transition-colors hover:text-foreground"
          >
            {showMomentumTable ? "Chart" : "Table"}
          </button>
        }
      >
        {showMomentumTable ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-foreground/40">
                <tr>
                  <th className="py-1 pr-4 font-medium">Week</th>
                  <th className="py-1 pr-4 font-medium">Source</th>
                  <th className="py-1 pr-4 font-medium">Items</th>
                  <th className="py-1 font-medium">Avg impact</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {stats.momentum.map((r) => (
                  <tr key={`${r.week}-${r.source}`} className="border-t border-border/50">
                    <td className="py-1 pr-4">{r.week}</td>
                    <td className="py-1 pr-4">{r.source}</td>
                    <td className="py-1 pr-4">{r.items}</td>
                    <td className="py-1">{r.avg_impact ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <LineChart series={momentum} yLabel="items per week" />
        )}
      </ChartFrame>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame title="Impact distribution" hint="How the 0–10 scores are spread.">
          <Histogram bins={stats.impact_distribution} />
        </ChartFrame>

        <ChartFrame
          title="Source reliability"
          hint="Read back out of stored traces — this is what separates a one-off coverage gap from a source that is always down."
        >
          {stats.source_reliability.length === 0 ? (
            <EmptyChart message="No tool calls recorded yet." />
          ) : (
            <BarList
              colorIndex={3}
              data={stats.source_reliability.map((r) => ({
                label: r.tool,
                value: r.success_rate ?? 0,
                detail: `${r.calls} calls · p95 ${r.p95_ms ?? "—"}ms`,
              }))}
              valueLabel={(v) => `${v}%`}
            />
          )}
        </ChartFrame>
      </div>

      <ChartFrame
        title="Novelty against impact"
        hint="Distance from the nearest thing already seen (x) against the impact score (y). Top-right is a genuinely new signal that also matters."
      >
        <Scatter
          xLabel="novelty"
          yLabel="impact"
          points={stats.novelty
            .filter((n) => n.novelty != null && n.impact_score != null)
            .map((n) => ({
              label: n.title,
              x: n.novelty!,
              y: n.impact_score!,
              detail: `${n.source}${n.organization ? ` · ${n.organization}` : ""}`,
            }))}
        />
      </ChartFrame>

      <ChartFrame title="Run economics" hint="Cost and yield of the last runs.">
        {stats.run_economics.length === 0 ? (
          <EmptyChart message="No completed runs yet." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-foreground/40">
                <tr>
                  <th className="py-1 pr-4 font-medium">Goal</th>
                  <th className="py-1 pr-4 font-medium">Pipeline</th>
                  <th className="py-1 pr-4 font-medium">Model</th>
                  <th className="py-1 pr-4 font-medium">Items</th>
                  <th className="py-1 pr-4 font-medium">New</th>
                  <th className="py-1 pr-4 font-medium">Gaps</th>
                  <th className="py-1 pr-4 font-medium">Tokens</th>
                  <th className="py-1 font-medium">Seconds</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {stats.run_economics.map((r) => (
                  <tr key={r.id} className="border-t border-border/50">
                    <td className="max-w-56 truncate py-1 pr-4" title={r.goal}>
                      {r.goal}
                    </td>
                    <td className="py-1 pr-4">{r.pipeline ?? "—"}</td>
                    <td className="py-1 pr-4">{r.model ?? "—"}</td>
                    <td className="py-1 pr-4">{r.item_count}</td>
                    <td className="py-1 pr-4">{r.new_items_count ?? "—"}</td>
                    <td className="py-1 pr-4">{r.gap_count}</td>
                    <td className="py-1 pr-4">
                      {compact((r.input_tokens ?? 0) + (r.output_tokens ?? 0))}
                    </td>
                    <td className="py-1">{r.seconds ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ChartFrame>
    </div>
  );
}
