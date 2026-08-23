"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Compass,
  Radar,
  Lightbulb,
  Database,
  Activity,
  FlaskConical,
  Building2,
  Cpu,
  Search,
} from "lucide-react";

type Command = {
  id: string;
  label: string;
  hint?: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  keywords?: string;
};

const COMMANDS: Command[] = [
  { id: "new-investigation", label: "New investigation", hint: "Start", icon: Compass, href: "/", keywords: "investigate start objective" },
  { id: "search-intelligence", label: "Search intelligence", hint: "Reports", icon: Lightbulb, href: "/intelligence", keywords: "findings reports briefing" },
  { id: "open-monitor", label: "Search competitors", hint: "Monitor", icon: Building2, href: "/monitor", keywords: "watchlist competitors track" },
  { id: "open-memory", label: "Open memory", hint: "Memory", icon: Database, href: "/memory", keywords: "history recall knowledge" },
  { id: "view-activity", label: "View activity", hint: "Activity", icon: Activity, href: "/activity", keywords: "runs history log" },
  { id: "open-evaluation", label: "Open evaluation", hint: "Evaluation", icon: FlaskConical, href: "/evaluation", keywords: "benchmark scores tests" },
  { id: "open-settings", label: "Open settings", hint: "Agent Runtime", icon: Cpu, href: "/settings", keywords: "settings runtime pipeline provider" },
];

/** Global Cmd/Ctrl+K palette, mounted once in the root layout. Purely
 *  client-side navigation over the app's own routes — no new API calls. */
export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return COMMANDS;
    return COMMANDS.filter(
      (c) => c.label.toLowerCase().includes(q) || c.keywords?.toLowerCase().includes(q)
    );
  }, [query]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setActiveIndex(0);
  }, []);

  const go = useCallback(
    (cmd: Command) => {
      router.push(cmd.href);
      close();
    },
    [router, close]
  );

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) close();
        else setOpen(true);
      } else if (e.key === "Escape" && open) {
        close();
      }
    }
    function onOpenRequest() {
      setOpen(true);
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("agentx:open-command-palette", onOpenRequest);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("agentx:open-command-palette", onOpenRequest);
    };
  }, [open, close]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-[rgba(16,24,40,0.35)] pt-[15vh] px-4"
      onClick={close}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg surface-card overflow-hidden shadow-lg"
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border)]">
          <Search className="w-4 h-4 text-[var(--foreground-secondary)] shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIndex((i) => Math.min(i + 1, results.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIndex((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter" && results[activeIndex]) {
                e.preventDefault();
                go(results[activeIndex]);
              }
            }}
            placeholder="Jump to…"
            aria-label="Command search"
            className="w-full bg-transparent border-none focus:outline-none text-sm text-[var(--foreground)] placeholder:text-[var(--foreground-secondary)]"
          />
          <kbd className="hidden sm:inline text-[10px] font-mono text-[var(--foreground-secondary)] border border-[var(--border)] rounded px-1.5 py-0.5">
            Esc
          </kbd>
        </div>

        <ul role="listbox" aria-label="Commands" className="max-h-80 overflow-y-auto py-2">
          {results.length === 0 && (
            <li className="px-4 py-6 text-sm text-center text-[var(--foreground-secondary)]">No matches.</li>
          )}
          {results.map((cmd, i) => (
            <li key={cmd.id} role="option" aria-selected={i === activeIndex}>
              <button
                type="button"
                onClick={() => go(cmd)}
                onMouseEnter={() => setActiveIndex(i)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors ${
                  i === activeIndex
                    ? "bg-[var(--surface-2)] text-[var(--foreground)]"
                    : "text-[var(--foreground)] hover:bg-[var(--surface-2)]"
                }`}
              >
                <cmd.icon className="w-4 h-4 text-[var(--foreground-secondary)] shrink-0" />
                <span className="flex-1">{cmd.label}</span>
                {cmd.hint && <span className="text-xs text-[var(--foreground-secondary)]">{cmd.hint}</span>}
              </button>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-4 px-4 py-2 border-t border-[var(--border)] text-[11px] text-[var(--foreground-secondary)]">
          <span><kbd className="font-mono">↑↓</kbd> navigate</span>
          <span><kbd className="font-mono">↵</kbd> open</span>
          <span className="ml-auto flex items-center gap-1">
            <Radar className="w-3 h-3" /> AgentX
          </span>
        </div>
      </div>
    </div>
  );
}
