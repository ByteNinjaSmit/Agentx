"use client";

import { useMemo } from "react";
import { BarList, ChartFrame, EmptyChart, StackedShareBar, StatTile } from "./charts/Charts";
import { signalShare } from "@/lib/brief";
import type { FinalResult, Step } from "@/lib/types";

/** Headline numbers and the two shape-of-the-run charts, rendered from the run's
 *  own final payload — no extra fetch, so what is counted here is exactly what is
 *  listed below it. */
export default function SignalSummary({
  final,
  steps,
}: {
  final: FinalResult | null;
  steps: Step[];
}) {
  const items = final?.items ?? [];
  const watched = final?.competitors_watched ?? [];

  // Colour follows the entity: a competitor keeps its hue whether or not the
  // filter below is hiding the others.
  const share = useMemo(
    () =>
      signalShare(items, watched).map((row, i) => ({
        label: row.name,
        value: row.items,
        colorIndex: row.name === "wider market" ? 5 : i,
      })),
    [items, watched]
  );

  const bySource = useMemo(() => {
    const counts = new Map<string, number>();
    for (const it of items) counts.set(it.source, (counts.get(it.source) ?? 0) + 1);
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([label, value], i) => ({ label, value, colorIndex: i }));
  }, [items]);

  if (!final) return null;

  const highImpact = items.filter((it) => it.impact_1_10 >= 8).length;
  const covered = watched.filter((name) => items.some((it) => it.competitor === name)).length;
  const grounded = items.filter((it) => it.grounded_on).length;

  return (
    <section className="space-y-4">
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Signals"
          value={items.length}
          detail={
            final.new_items_count != null
              ? `${final.new_items_count} new since last scan`
              : undefined
          }
          accent
        />
        <StatTile
          label="Competitors covered"
          value={watched.length ? `${covered}/${watched.length}` : "—"}
          detail={
            watched.length
              ? covered === watched.length
                ? "every watched name produced signal"
                : `${watched.length - covered} produced nothing this scan`
              : "no watchlist set"
          }
        />
        <StatTile
          label="Sources"
          value={bySource.length}
          detail={bySource.map((s) => s.label).join(", ") || undefined}
        />
        <StatTile
          label="High impact"
          value={highImpact}
          detail={`${grounded}/${items.length} traced to raw tool output`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame
          title="Competitor signal share"
          hint="Who the scan actually found something on. A watched name at zero is a finding too."
        >
          {share.length ? (
            <BarList data={share} valueLabel={(v) => `${v}`} />
          ) : (
            <EmptyChart message="no competitors named — run a scan with a watchlist" />
          )}
        </ChartFrame>

        <ChartFrame
          title="Source breakdown"
          hint="Where the evidence came from, as a share of this scan."
        >
          <StackedShareBar data={bySource} totalLabel="signals" />
        </ChartFrame>
      </div>

      {steps.length > 0 && (
        <p className="text-[11px] text-foreground/35">
          {steps.length} reasoning step{steps.length === 1 ? "" : "s"}
          {final.model ? ` · ${final.model}` : ""}
          {final.pipeline ? ` · ${final.pipeline} pipeline` : ""}
          {final.input_tokens != null
            ? ` · ${(final.input_tokens + (final.output_tokens ?? 0)).toLocaleString()} tokens`
            : ""}
          {final.depth ? ` · depth ${final.depth}/source` : ""}
        </p>
      )}
    </section>
  );
}
