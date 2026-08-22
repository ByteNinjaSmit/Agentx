"use client";

import { useEffect, useState } from "react";
import { defaultAgentMode, fetchProviders } from "./agent-client";
import { usePersistedValue } from "./client-state";
import type { AgentMode, Pipeline, ProviderInfo } from "./types";

// Shared localStorage keys — writing them on /settings and reading them on
// /investigate (or anywhere else) keeps every page in sync via the `storage`
// event usePersistedValue already listens for.
export const MODE_KEY = "agentx-mode";
export const PIPELINE_KEY = "agentx-pipeline";
export const PROVIDER_KEY = "agentx-provider";

/** The agent source/pipeline/provider a run should use, persisted per-browser
 *  and shared across every page that can kick off or configure a run. */
export function useRunSettings() {
  const [mode, setMode] = usePersistedValue<AgentMode>(
    MODE_KEY,
    defaultAgentMode,
    (v) => v === "backend" || v === "n8n"
  );
  const [pipeline, setPipeline] = usePersistedValue<Pipeline>(
    PIPELINE_KEY,
    "fleet",
    (v) => v === "fleet" || v === "single"
  );
  const [storedProvider, setStoredProvider] = usePersistedValue<string>(PROVIDER_KEY, "", () => true);
  const [providers, setProviders] = useState<ProviderInfo | null>(null);
  const [providersError, setProvidersError] = useState<string | null>(null);

  useEffect(() => {
    fetchProviders()
      .then(setProviders)
      .catch((e) => setProvidersError((e as Error).message));
  }, []);

  const provider = storedProvider || providers?.default || null;

  return {
    mode,
    setMode,
    pipeline,
    setPipeline,
    provider,
    setProvider: setStoredProvider,
    providers,
    providersError,
  };
}
