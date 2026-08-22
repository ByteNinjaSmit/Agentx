"use client";

import { useEffect, useState } from "react";
import { Cpu, CheckCircle2, XCircle, GitBranch, RotateCcw, ShieldCheck, Gauge, Database } from "lucide-react";
import { API_URL, WEBHOOK_URL } from "@/lib/agent-client";
import { useRunSettings } from "@/lib/run-settings";

const BEHAVIORS = [
  {
    icon: GitBranch,
    color: "var(--accent)",
    name: "Dynamic replanning",
    detail:
      "Coverage is computed in code after the Analyst step. Below threshold (or with any reported gap), one bounded planner call decides whether to open up to two new sub-questions — capped at one round per run.",
  },
  {
    icon: RotateCcw,
    color: "var(--warning)",
    name: "Tool fallback",
    detail:
      "search_papers falls back from Semantic Scholar to Crossref on failure instead of surfacing a hard error. The switch is a real trace event tagged \"runtime\", not a buried log line.",
  },
  {
    icon: ShieldCheck,
    color: "var(--accent-secondary)",
    name: "Evidence conflict resolution",
    detail:
      "Flags an organization when kept findings from ≥2 source types disagree on impact by more than a threshold spread, then runs one resolver call to explain the disagreement and attach a confidence.",
  },
  {
    icon: Gauge,
    color: "var(--foreground-secondary)",
    name: "Resource-aware execution",
    detail:
      "Every run tracks tool calls and elapsed time against a budget (60 calls / 180s by default). When coverage is thin and the budget is spent, the fleet says so explicitly and skips the replan.",
  },
  {
    icon: Database,
    color: "var(--foreground-secondary)",
    name: "Checkpointing",
    detail:
      "The trace is persisted to Postgres after the research round and again after conflict resolution, not only at the end — a crashed process still leaves a real, inspectable partial trace.",
  },
];

const PIPELINE_INFO: Record<string, { label: string; hint: string }> = {
  fleet: {
    label: "Specialist fleet",
    hint: "Planner → parallel researchers → verifier → analyst → strategist. Slower, discards ungrounded findings.",
  },
  single: {
    label: "Single ReAct loop",
    hint: "One agent plans, searches and writes the brief. Fewer model calls, no verification pass.",
  },
};

const PROVIDER_LABEL: Record<string, string> = { anthropic: "Claude", gemini: "Gemini" };

function Pill({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-1.5 text-xs font-medium rounded-md transition-colors ${
        active
          ? "bg-[var(--foreground)] text-[var(--surface)]"
          : "text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)]"
      }`}
    >
      {children}
    </button>
  );
}

type Health = "checking" | "ok" | "down";

export default function SettingsPage() {
  const settings = useRunSettings();
  const [health, setHealth] = useState<Health>("checking");

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/health`)
      .then((r) => {
        if (!cancelled) setHealth(r.ok ? "ok" : "down");
      })
      .catch(() => {
        if (!cancelled) setHealth("down");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="max-w-3xl mx-auto pb-12 animate-slide-up">
      <div className="mb-10 flex items-center gap-3">
        <div className="w-10 h-10 bg-[var(--surface-2)] rounded-lg flex items-center justify-center border border-[var(--border)]">
          <Cpu className="w-5 h-5 text-[var(--foreground-secondary)]" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-[var(--foreground)]">Agent Runtime</h1>
          <p className="text-[var(--foreground-secondary)] text-sm">
            Everything a normal investigation hides behind &ldquo;AgentX decides&rdquo; — how new runs are
            configured, and the autonomous behaviors the fleet pipeline actually implements.
          </p>
        </div>
      </div>

      <div className="space-y-6">
        <section className="surface-card p-5 space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground-secondary)] mb-2">
              Agent source
            </p>
            <div className="inline-flex rounded-lg border border-[var(--border)] p-1 bg-[var(--surface-2)]">
              <Pill active={settings.mode === "backend"} onClick={() => settings.setMode("backend")}>
                Local backend (SSE)
              </Pill>
              <Pill active={settings.mode === "n8n"} onClick={() => settings.setMode("n8n")}>
                n8n webhook
              </Pill>
            </div>
            <p className="mt-2 text-xs text-[var(--foreground-secondary)]">
              {settings.mode === "backend"
                ? `Streaming from ${API_URL}`
                : `Posting to ${WEBHOOK_URL}`}
            </p>
          </div>

          {settings.mode === "backend" && (
            <>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground-secondary)] mb-2">
                  Pipeline
                </p>
                <div className="inline-flex rounded-lg border border-[var(--border)] p-1 bg-[var(--surface-2)]">
                  {(["fleet", "single"] as const).map((p) => (
                    <Pill key={p} active={settings.pipeline === p} onClick={() => settings.setPipeline(p)}>
                      {PIPELINE_INFO[p].label}
                    </Pill>
                  ))}
                </div>
                <p className="mt-2 text-xs text-[var(--foreground-secondary)]">
                  {PIPELINE_INFO[settings.pipeline].hint}
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground-secondary)] mb-2">
                  Model provider
                </p>
                {settings.providersError ? (
                  <p className="text-sm text-[var(--danger)]">{settings.providersError}</p>
                ) : !settings.providers ? (
                  <p className="text-sm text-[var(--foreground-secondary)]">Loading available providers…</p>
                ) : settings.providers.providers.length === 0 ? (
                  <p className="text-sm text-[var(--danger)]">
                    No provider keys configured on the backend — runs will fail.
                  </p>
                ) : (
                  <div className="inline-flex rounded-lg border border-[var(--border)] p-1 bg-[var(--surface-2)]">
                    {settings.providers.providers.map((p) => (
                      <Pill
                        key={p}
                        active={(settings.provider ?? settings.providers?.default) === p}
                        onClick={() => settings.setProvider(p)}
                      >
                        {PROVIDER_LABEL[p] ?? p}
                      </Pill>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </section>

        <section className="surface-card p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground-secondary)] mb-3">
            Backend status
          </p>
          <div className="flex items-center gap-2 text-sm">
            {health === "checking" && <span className="text-[var(--foreground-secondary)]">Checking {API_URL}…</span>}
            {health === "ok" && (
              <>
                <CheckCircle2 className="w-4 h-4 text-[var(--accent-secondary)]" />
                <span className="text-[var(--foreground)]">Reachable at {API_URL}</span>
              </>
            )}
            {health === "down" && (
              <>
                <XCircle className="w-4 h-4 text-[var(--danger)]" />
                <span className="text-[var(--foreground)]">Could not reach {API_URL}</span>
              </>
            )}
          </div>
        </section>

        <section className="surface-card p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground-secondary)] mb-1">
            Framework
          </p>
          <p className="text-sm text-[var(--foreground-secondary)] mb-4 leading-relaxed">
            A custom stateful async runtime over FastAPI + SSE, not a chained-prompts script — the
            specialist fleet pipeline is Planner → parallel Researchers → Verifier → Analyst →
            Strategist, with coverage, budget and checkpoints threaded through as values the
            runtime reasons over. The single ReAct loop below is the simpler one-agent
            alternative and has none of the autonomous behaviors on this page.
          </p>
          <div className="space-y-0">
            {BEHAVIORS.map((b, i) => (
              <div
                key={b.name}
                className={`flex items-start gap-3 py-3 ${i > 0 ? "border-t border-[var(--border)]" : ""}`}
              >
                <b.icon className="w-4 h-4 shrink-0 mt-0.5" style={{ color: b.color }} />
                <div>
                  <p className="text-sm font-semibold text-[var(--foreground)]">{b.name}</p>
                  <p className="text-xs text-[var(--foreground-secondary)] mt-0.5 leading-relaxed">{b.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
