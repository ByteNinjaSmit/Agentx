"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchRuns } from "@/lib/history-client";
import type { RunSummary } from "@/lib/types";

function timeAgo(iso: string | null) {
  if (!iso) return "unknown time";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function RunRow({ run }: { run: RunSummary }) {
  return (
    <Link
      href={`/intelligence/${run.id}`}
      className="surface-card overflow-hidden p-4 flex items-start justify-between gap-3 hover:bg-surface-2/60 transition-colors block"
    >
      <div className="min-w-0">
        <p className="text-sm font-medium truncate">{run.goal}</p>
        {run.context && (
          <p className="text-xs text-foreground/40 truncate mt-0.5">{run.context}</p>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span
          className={`text-[11px] rounded px-1.5 py-0.5 ${
            run.coverage_ok
              ? run.coverage_gaps.length > 0
                ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                : "bg-teal-500/10 text-teal-600 dark:text-teal-400"
              : "bg-danger/10 text-danger"
          }`}
        >
          {run.item_count} item{run.item_count === 1 ? "" : "s"}
        </span>
        <span className="text-[11px] text-foreground/40">{timeAgo(run.started_at)}</span>
        <span className="text-foreground/40">›</span>
      </div>
    </Link>
  );
}

export default function HistoryPanel() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRuns()
      .then(setRuns)
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div className="space-y-3">
      <p className="text-xs text-foreground/40">
        Past runs made via the FastAPI backend. n8n webhook runs aren&apos;t logged here yet —
        history is per-implementation, not shared.
      </p>

      {error && (
        <p role="alert" className="text-sm text-danger bg-danger/10 rounded-lg px-3 py-2.5 border border-danger/20">
          {error}
        </p>
      )}
      {!error && runs === null && (
        <p className="text-sm text-foreground/40">Loading history…</p>
      )}
      {runs && runs.length === 0 && (
        <div className="surface-card p-8 text-center">
          <p className="text-sm text-foreground/50">No runs yet. Run the agent once to see it here.</p>
        </div>
      )}
      {runs && runs.length > 0 && (
        <div className="space-y-2">
          {runs.map((r) => (
            <RunRow key={r.id} run={r} />
          ))}
        </div>
      )}
    </div>
  );
}
