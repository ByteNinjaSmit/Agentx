"use client";

import StatsPanel from "@/components/StatsPanel";

export default function MemoryPage() {
  return (
    <div className="max-w-5xl mx-auto pb-12 animate-slide-up">
      <div className="mb-10">
        <h1 className="text-3xl font-semibold text-[var(--foreground)] mb-2">Agent Memory</h1>
        <p className="text-[var(--foreground-secondary)] text-lg">
          What AgentX remembers about your intelligence landscape — computed straight from what
          past runs actually stored.
        </p>
      </div>

      <StatsPanel />
    </div>
  );
}
