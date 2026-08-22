"use client";

import { useEffect, useState } from "react";
import { Settings, CheckCircle2, XCircle } from "lucide-react";
import { API_URL, WEBHOOK_URL } from "@/lib/agent-client";
import { useRunSettings } from "@/lib/run-settings";

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
          <Settings className="w-5 h-5 text-[var(--foreground-secondary)]" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-[var(--foreground)]">Settings</h1>
          <p className="text-[var(--foreground-secondary)] text-sm">
            How new investigations run — saved to this browser and used everywhere else in the app.
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
      </div>
    </div>
  );
}
