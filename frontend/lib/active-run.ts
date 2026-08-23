"use client";

import { useSyncExternalStore } from "react";

/** The one investigation currently streaming, if any — set by the page that owns
 *  the live SSE connection so the sidebar can show a status dot from anywhere in
 *  the app. Deliberately in-memory only: a reload has no connection to resume, so
 *  persisting this across refreshes would just be a stale flag. */
export type ActiveRun = { goal: string } | null;

let state: ActiveRun = null;
const listeners = new Set<() => void>();

export function setActiveRun(run: ActiveRun) {
  state = run;
  listeners.forEach((l) => l());
}

export function useActiveRun(): ActiveRun {
  return useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    () => state,
    () => null
  );
}
