"use client";

import { Fragment, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, ArrowRight, Building2, Scale, BookOpen, TrendingUp, Target, Compass, ShieldCheck, Database, RotateCw } from "lucide-react";

const PILLARS = [
  { icon: Target, label: "PLAN", copy: "Splits the goal into independent lines of enquiry.", tint: "accent" as const },
  { icon: Compass, label: "INVESTIGATE", copy: "Specialist agents research in parallel, tools only.", tint: "accent" as const },
  { icon: ShieldCheck, label: "VERIFY", copy: "Drops anything not traceable to a real tool result.", tint: "secondary" as const },
  { icon: Database, label: "REMEMBER", copy: "Only reports what wasn't already known.", tint: "secondary" as const },
  { icon: RotateCw, label: "ADAPT", copy: "Replans on new evidence, recovers from failures.", tint: "warning" as const },
];

const TINT: Record<string, { bg: string; fg: string }> = {
  accent: { bg: "bg-[var(--accent)]/10", fg: "text-[var(--accent)]" },
  secondary: { bg: "bg-[var(--accent-secondary)]/10", fg: "text-[var(--accent-secondary)]" },
  warning: { bg: "bg-[var(--warning)]/10", fg: "text-[var(--warning)]" },
  danger: { bg: "bg-[var(--danger)]/10", fg: "text-[var(--danger)]" },
};

const MISSIONS = [
  {
    icon: Building2,
    tint: "accent" as const,
    label: "Competitive threat",
    goal: "Find emerging competitors in AI infrastructure.",
  },
  {
    icon: Scale,
    tint: "secondary" as const,
    label: "Patent intelligence",
    goal: "Identify recent patent activity around edge AI.",
  },
  {
    icon: BookOpen,
    tint: "warning" as const,
    label: "Research intelligence",
    goal: "Find important research developments in multimodal AI.",
  },
  {
    icon: TrendingUp,
    tint: "danger" as const,
    label: "Change detection",
    goal: "What changed in our tracked competitors this week?",
  },
];

export default function Home() {
  const [query, setQuery] = useState("");
  const router = useRouter();

  function investigate(goal: string) {
    const trimmed = goal.trim();
    if (!trimmed) return;
    // The goal travels in the query string; /investigate/new starts the real
    // agent run (backend SSE or n8n webhook, per the operator's saved settings)
    // against it.
    router.push(`/investigate/new?goal=${encodeURIComponent(trimmed)}`);
  }

  return (
    <div className="flex flex-col items-center max-w-3xl mx-auto px-4 pb-24">
      <div className="text-center mt-16 mb-10 animate-slide-up">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)] text-[11px] font-semibold uppercase tracking-wide text-[var(--foreground-secondary)] mb-7">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-secondary)]" />
          Autonomous intelligence, live
        </div>
        <h1 className="text-3xl font-semibold text-[var(--foreground)] mb-2">
          What should AgentX investigate?
        </h1>
        <p className="text-[var(--foreground-secondary)]">
          Give it an objective. It plans, researches across papers, patents, news and
          competitors, verifies what it finds, and tells you what changed.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          investigate(query);
        }}
        className="w-full surface-card p-2 mb-3 animate-slide-up"
        style={{ animationDelay: "100ms" }}
      >
        <div className="relative flex items-center">
          <Search className="absolute left-4 w-5 h-5 text-[var(--foreground-secondary)]" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Analyze emerging competitors in generative AI infrastructure..."
            className="w-full pl-12 pr-32 py-4 bg-transparent border-none focus:outline-none text-lg text-[var(--foreground)] placeholder:text-[var(--border-highlight)]"
          />
          <button
            type="submit"
            className="absolute right-2 px-4 py-2 bg-[var(--foreground)] text-[var(--surface)] font-medium rounded-lg hover:bg-[var(--accent)] transition-colors flex items-center gap-2"
          >
            Investigate
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>
      <p className="text-[13px] text-[var(--foreground-secondary)] italic mb-16 animate-slide-up" style={{ animationDelay: "150ms" }}>
        You define the objective. AgentX decides how to investigate it.
      </p>

      {/* Pillars */}
      <div className="w-full mb-16 animate-slide-up" style={{ animationDelay: "200ms" }}>
        <div className="flex items-stretch">
          {PILLARS.map((p, i) => (
            <Fragment key={p.label}>
              {i > 0 && (
                <div className="flex items-center pt-[22px] px-1 shrink-0">
                  <ArrowRight className="w-4 h-4 text-[var(--border-highlight)]" />
                </div>
              )}
              <div className="flex-1 flex flex-col items-center text-center px-1">
                <div className={`w-10 h-10 rounded-[11px] ${TINT[p.tint].bg} ${TINT[p.tint].fg} flex items-center justify-center mb-3`}>
                  <p.icon className="w-[18px] h-[18px]" strokeWidth={1.8} />
                </div>
                <div className="text-[11px] font-bold tracking-wide text-[var(--foreground)] mb-1">{p.label}</div>
                <div className="text-[11px] leading-snug text-[var(--foreground-secondary)]">{p.copy}</div>
              </div>
            </Fragment>
          ))}
        </div>
      </div>

      {/* Mission cards */}
      <div className="w-full animate-slide-up" style={{ animationDelay: "300ms" }}>
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground-secondary)] mb-4">
          Start with a question — click one
        </p>
        <div className="grid grid-cols-2 gap-3">
          {MISSIONS.map((m) => (
            <button
              key={m.label}
              onClick={() => investigate(m.goal)}
              className="text-left surface-card p-5 hover:border-[var(--border-highlight)] transition-all group"
            >
              <div className={`w-9 h-9 rounded-[10px] ${TINT[m.tint].bg} ${TINT[m.tint].fg} flex items-center justify-center mb-6`}>
                <m.icon className="w-[18px] h-[18px]" strokeWidth={1.8} />
              </div>
              <div className="text-[10.5px] font-bold uppercase tracking-wide text-[var(--foreground-secondary)] mb-2">
                {m.label}
              </div>
              <div className="text-sm text-[var(--foreground)] mb-4 leading-snug">{m.goal}</div>
              <div className="flex items-center gap-1.5 text-[12.5px] font-semibold text-[var(--accent)]">
                Explore
                <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
