"use client";

import { Activity } from "lucide-react";
import HistoryPanel from "@/components/HistoryPanel";

export default function ActivityPage() {
  return (
    <div className="max-w-4xl mx-auto pb-12 animate-slide-up">
      <div className="mb-10 flex items-center gap-3">
        <div className="w-10 h-10 bg-[var(--surface-2)] rounded-lg flex items-center justify-center border border-[var(--border)]">
          <Activity className="w-5 h-5 text-[var(--foreground-secondary)]" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-[var(--foreground)]">Activity</h1>
          <p className="text-[var(--foreground-secondary)] text-sm">
            Every run the agent has made — expand one to replay its reasoning trace and findings.
          </p>
        </div>
      </div>

      <HistoryPanel />
    </div>
  );
}
