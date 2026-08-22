"use client";

/**
 * Inline-SVG chart primitives. No charting dependency: the forms here are simple
 * enough that a library would cost more than it saves, and hand-drawn marks let
 * every colour come from the themed CSS custom properties in globals.css so light
 * and dark are each a selected palette rather than an automatic flip.
 *
 * Categorical hues are assigned in fixed order and never cycled — a series past
 * slot 6 folds into "Other" rather than inventing a hue.
 */

import { useId, useState, type ReactNode } from "react";

export const SERIES_VARS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
];

export function seriesColor(index: number) {
  return SERIES_VARS[index] ?? "var(--viz-axis)";
}

function useTooltip() {
  const [tip, setTip] = useState<{ x: number; y: number; content: ReactNode } | null>(null);
  const node = tip ? (
    <div
      className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[11px] leading-snug shadow-lg backdrop-blur-md"
      style={{ left: tip.x, top: tip.y - 8 }}
    >
      {tip.content}
    </div>
  ) : null;
  return { show: setTip, hide: () => setTip(null), node };
}

export function ChartFrame({
  title,
  hint,
  children,
  action,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="surface-card p-5 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-foreground/50">
            {title}
          </h3>
          {hint && <p className="text-[11px] text-foreground/40 mt-0.5">{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function EmptyChart({ message }: { message: string }) {
  return <p className="py-6 text-center text-xs text-foreground/40 italic">{message}</p>;
}

/** Horizontal bars. The right form for "which of these is biggest" when the
 *  category labels are words rather than time. */
export function BarList({
  data,
  colorIndex = 0,
  valueLabel,
}: {
  data: { label: string; value: number; detail?: string }[];
  colorIndex?: number;
  valueLabel?: (value: number) => string;
}) {
  const max = Math.max(...data.map((d) => d.value), 1);
  const format = valueLabel ?? ((v: number) => String(v));
  return (
    <ul className="space-y-2">
      {data.map((d) => (
        <li key={d.label} className="group">
          <div className="flex items-baseline justify-between gap-3 text-xs">
            <span className="truncate text-foreground/80" title={d.label}>
              {d.label}
            </span>
            <span className="shrink-0 tabular-nums text-foreground/50">
              {format(d.value)}
              {d.detail ? <span className="ml-2 text-foreground/35">{d.detail}</span> : null}
            </span>
          </div>
          <div className="mt-1 h-2 w-full rounded-full bg-surface-2">
            <div
              className="h-2 rounded-full transition-[width] duration-500"
              style={{
                width: `${Math.max((d.value / max) * 100, 2)}%`,
                background: seriesColor(colorIndex),
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

type LinePoint = { x: string; y: number };
export type LineSeries = { name: string; points: LinePoint[] };

/** Multi-series line chart over a shared categorical x (weeks). One y-axis, always
 *  — two measures of different scale get two charts, never a second axis. */
export function LineChart({
  series,
  height = 180,
  yLabel,
}: {
  series: LineSeries[];
  height?: number;
  yLabel?: string;
}) {
  const clipId = useId();
  const tooltip = useTooltip();
  const [hovered, setHovered] = useState<number | null>(null);

  const xs = Array.from(new Set(series.flatMap((s) => s.points.map((p) => p.x)))).sort();
  const maxY = Math.max(...series.flatMap((s) => s.points.map((p) => p.y)), 1);
  if (xs.length === 0) return <EmptyChart message="No data in this window yet." />;

  const pad = { top: 12, right: 16, bottom: 26, left: 34 };
  const width = 640;
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const xAt = (x: string) =>
    pad.left + (xs.length === 1 ? plotW / 2 : (xs.indexOf(x) / (xs.length - 1)) * plotW);
  const yAt = (y: number) => pad.top + plotH - (y / maxY) * plotH;

  const ticks = [0, 0.5, 1].map((t) => Math.round(maxY * t));

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label={`Line chart of ${series.map((s) => s.name).join(", ")}`}
        onMouseLeave={() => {
          setHovered(null);
          tooltip.hide();
        }}
      >
        <clipPath id={clipId}>
          <rect x={pad.left} y={pad.top} width={plotW} height={plotH} />
        </clipPath>

        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={yAt(t)}
              y2={yAt(t)}
              stroke="var(--viz-grid)"
              strokeWidth={1}
            />
            <text x={4} y={yAt(t) + 4} fontSize={10} fill="var(--viz-axis)">
              {t}
            </text>
          </g>
        ))}

        {xs.map((x, i) =>
          i % Math.ceil(xs.length / 6) === 0 ? (
            <text
              key={x}
              x={xAt(x)}
              y={height - 8}
              fontSize={10}
              textAnchor="middle"
              fill="var(--viz-axis)"
            >
              {x.slice(5)}
            </text>
          ) : null
        )}

        {hovered !== null && (
          <line
            x1={xAt(xs[hovered])}
            x2={xAt(xs[hovered])}
            y1={pad.top}
            y2={pad.top + plotH}
            stroke="var(--viz-axis)"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}

        <g clipPath={`url(#${clipId})`}>
          {series.map((s, i) => {
            const byX = new Map(s.points.map((p) => [p.x, p.y]));
            const path = xs
              .filter((x) => byX.has(x))
              .map((x, j) => `${j === 0 ? "M" : "L"}${xAt(x)},${yAt(byX.get(x)!)}`)
              .join(" ");
            return (
              <path
                key={s.name}
                d={path}
                fill="none"
                stroke={seriesColor(i)}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            );
          })}
        </g>

        {/* invisible hit columns — bigger targets than the marks themselves */}
        {xs.map((x, i) => (
          <rect
            key={x}
            x={xAt(x) - plotW / Math.max(xs.length, 1) / 2}
            y={pad.top}
            width={plotW / Math.max(xs.length, 1)}
            height={plotH}
            fill="transparent"
            onMouseEnter={(e) => {
              setHovered(i);
              const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
              tooltip.show({
                x: ((xAt(x) / width) * box.width),
                y: box.height * 0.5,
                content: (
                  <div className="space-y-0.5">
                    <p className="font-medium">{x}</p>
                    {series.map((s, si) => {
                      const point = s.points.find((p) => p.x === x);
                      if (!point) return null;
                      return (
                        <p key={s.name} className="flex items-center gap-1.5">
                          <span
                            className="inline-block size-2 rounded-full"
                            style={{ background: seriesColor(si) }}
                          />
                          <span className="text-foreground/60">{s.name}</span>
                          <span className="tabular-nums">{point.y}</span>
                        </p>
                      );
                    })}
                  </div>
                ),
              });
            }}
          />
        ))}
      </svg>
      {tooltip.node}

      {/* identity is never colour alone: a legend is always present for >= 2 series */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {series.map((s, i) => (
          <span key={s.name} className="flex items-center gap-1.5 text-[11px] text-foreground/60">
            <span
              className="inline-block h-0.5 w-3 rounded-full"
              style={{ background: seriesColor(i) }}
            />
            {s.name}
          </span>
        ))}
        {yLabel && <span className="text-[11px] text-foreground/35">{yLabel}</span>}
      </div>
    </div>
  );
}

/** Distribution of a single measure across fixed buckets. */
export function Histogram({
  bins,
  height = 140,
}: {
  bins: { from: number; to: number; items: number }[];
  height?: number;
}) {
  const tooltip = useTooltip();
  if (bins.length === 0) return <EmptyChart message="No scored items yet." />;

  const max = Math.max(...bins.map((b) => b.items), 1);
  const width = 640;
  const pad = { top: 10, right: 8, bottom: 22, left: 28 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const slot = plotW / bins.length;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Impact distribution">
        <line
          x1={pad.left}
          x2={width - pad.right}
          y1={pad.top + plotH}
          y2={pad.top + plotH}
          stroke="var(--viz-grid)"
        />
        <text x={2} y={pad.top + 8} fontSize={10} fill="var(--viz-axis)">
          {max}
        </text>
        {bins.map((b, i) => {
          const h = Math.max((b.items / max) * plotH, 2);
          // impact bands mirror the badge colours used on the finding cards
          const color =
            b.from >= 8 ? "var(--viz-critical)" : b.from >= 5 ? "var(--viz-warning)" : "var(--series-1)";
          return (
            <g key={`${b.from}-${b.to}`}>
              <rect
                x={pad.left + i * slot + 1}
                y={pad.top + plotH - h}
                width={Math.max(slot - 2, 1)} /* 2px surface gap between adjacent bars */
                height={h}
                rx={4}
                fill={color}
                onMouseEnter={(e) => {
                  const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                  tooltip.show({
                    x: ((pad.left + i * slot + slot / 2) / width) * box.width,
                    y: box.height * 0.5,
                    content: (
                      <span>
                        impact {b.from}–{b.to}: <strong>{b.items}</strong>
                      </span>
                    ),
                  });
                }}
                onMouseLeave={tooltip.hide}
              />
              <text
                x={pad.left + i * slot + slot / 2}
                y={height - 6}
                fontSize={9}
                textAnchor="middle"
                fill="var(--viz-axis)"
              >
                {b.from}
              </text>
            </g>
          );
        })}
      </svg>
      {tooltip.node}
    </div>
  );
}

export type ScatterPoint = {
  label: string;
  x: number;
  y: number;
  size?: number;
  detail?: string;
};

/** Single-series scatter. Deliberately one colour: the all-pairs colour floors cap
 *  a scatter at three hues, and here position and radius already carry the data. */
export function Scatter({
  points,
  xLabel,
  yLabel,
  height = 200,
}: {
  points: ScatterPoint[];
  xLabel: string;
  yLabel: string;
  height?: number;
}) {
  const tooltip = useTooltip();
  if (points.length === 0) return <EmptyChart message="Not enough items to compare yet." />;

  const width = 640;
  const pad = { top: 12, right: 16, bottom: 28, left: 34 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs, xMin + 0.001);
  const yMin = Math.min(...ys, 0);
  const yMax = Math.max(...ys, yMin + 0.001);
  const maxSize = Math.max(...points.map((p) => p.size ?? 1), 1);

  const xAt = (x: number) => pad.left + ((x - xMin) / (xMax - xMin)) * plotW;
  const yAt = (y: number) => pad.top + plotH - ((y - yMin) / (yMax - yMin)) * plotH;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={`${yLabel} against ${xLabel}`}>
        <line x1={pad.left} x2={width - pad.right} y1={pad.top + plotH} y2={pad.top + plotH} stroke="var(--viz-grid)" />
        <line x1={pad.left} x2={pad.left} y1={pad.top} y2={pad.top + plotH} stroke="var(--viz-grid)" />
        <text x={width - pad.right} y={height - 6} fontSize={10} textAnchor="end" fill="var(--viz-axis)">
          {xLabel} →
        </text>
        <text x={2} y={pad.top + 8} fontSize={10} fill="var(--viz-axis)">
          {yLabel}
        </text>
        {points.map((p) => (
          <circle
            key={p.label + p.x + p.y}
            cx={xAt(p.x)}
            cy={yAt(p.y)}
            r={Math.max(5, Math.sqrt((p.size ?? 1) / maxSize) * 11)}
            fill="var(--series-1)"
            fillOpacity={0.75}
            stroke="var(--viz-surface)"
            strokeWidth={2} /* 2px surface ring keeps overlapping marks separable */
            onMouseEnter={(e) => {
              const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
              tooltip.show({
                x: (xAt(p.x) / width) * box.width,
                y: (yAt(p.y) / height) * box.height,
                content: (
                  <div className="max-w-56 space-y-0.5">
                    <p className="font-medium line-clamp-2">{p.label}</p>
                    {p.detail && <p className="text-foreground/50">{p.detail}</p>}
                  </div>
                ),
              });
            }}
            onMouseLeave={tooltip.hide}
          />
        ))}
      </svg>
      {tooltip.node}
    </div>
  );
}
