"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Reading browser-only state (localStorage, a DOM attribute) during render would
 * produce a different first paint on the server than on the client. The usual
 * workaround — read it in an effect and setState — costs a second render pass and
 * is exactly what React's `set-state-in-effect` rule warns about.
 *
 * `useSyncExternalStore` is the built-in answer: React renders the server snapshot
 * during hydration and swaps to the live one immediately afterwards, with no
 * mismatch and no cascading render.
 */

const LOCAL_EVENT = "agentx:local-store";

function subscribeToStorage(onChange: () => void) {
  // `storage` fires for other tabs; the custom event covers writes in this one.
  window.addEventListener("storage", onChange);
  window.addEventListener(LOCAL_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(LOCAL_EVENT, onChange);
  };
}

/** A localStorage-backed value, validated on read so a stale or hand-edited entry
 *  falls back rather than putting the UI into an impossible state. */
export function usePersistedValue<T extends string>(
  key: string,
  fallback: T,
  isValid: (value: string) => boolean
): [T, (value: T) => void] {
  const getSnapshot = useCallback(() => {
    try {
      return localStorage.getItem(key);
    } catch {
      return null; // private mode, or site data blocked
    }
  }, [key]);

  const raw = useSyncExternalStore(subscribeToStorage, getSnapshot, () => null);

  const set = useCallback(
    (value: T) => {
      try {
        localStorage.setItem(key, value);
      } catch {
        // the write failing is not a reason to refuse the interaction
      }
      window.dispatchEvent(new Event(LOCAL_EVENT));
    },
    [key]
  );

  return [raw !== null && isValid(raw) ? (raw as T) : fallback, set];
}

/** The theme currently stamped on <html> by the inline script in app/layout.tsx. */
export function useTheme(): ["light" | "dark", (next: "light" | "dark") => void] {
  const current = useSyncExternalStore(
    (onChange) => {
      const observer = new MutationObserver(onChange);
      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"],
      });
      return () => observer.disconnect();
    },
    () => document.documentElement.dataset.theme ?? "light",
    () => "light" // matches the inline script's default, so hydration agrees
  );

  const set = useCallback((next: "light" | "dark") => {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("agentx-theme", next);
    } catch {
      // theme still applies for this page view even if it can't be remembered
    }
  }, []);

  return [current === "dark" ? "dark" : "light", set];
}
