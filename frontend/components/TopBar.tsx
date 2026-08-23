"use client";

import Link from "next/link";
import { Search, Bell, User, Menu } from "lucide-react";

/** Thin top bar for the sidebar shell — primary navigation now lives in
 *  Sidebar, so this only holds the command palette trigger, activity and
 *  profile shortcuts, and (below `md`) the button that opens the sidebar as
 *  an off-canvas drawer. */
export default function TopBar() {
  return (
    <header className="w-full bg-[var(--background)] border-b border-[var(--border)] sticky top-0 z-40">
      <div className="h-16 flex items-center justify-between px-4 md:px-6">
        <div className="flex items-center gap-3 md:hidden">
          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event("agentx:toggle-sidebar"))}
            aria-label="Open menu"
            className="p-2 -ml-2 text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] rounded-md transition-colors"
          >
            <Menu className="w-5 h-5" />
          </button>
          <span className="font-semibold text-[var(--foreground)] tracking-tight">AGENTX</span>
        </div>

        <div className="hidden md:block" />

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event("agentx:open-command-palette"))}
            aria-label="Open command palette"
            title="Search (⌘K)"
            className="flex items-center gap-1.5 px-2 py-1.5 text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] rounded-md transition-colors"
          >
            <Search className="w-5 h-5" />
            <kbd className="hidden lg:inline text-[10px] font-mono border border-[var(--border)] rounded px-1 py-0.5">
              ⌘K
            </kbd>
          </button>
          <Link
            href="/activity"
            aria-label="Activity"
            className="p-2 text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] rounded-md transition-colors"
          >
            <Bell className="w-5 h-5" />
          </Link>
          <Link
            href="/settings"
            aria-label="Agent Runtime"
            className="p-2 text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] rounded-md transition-colors"
          >
            <User className="w-5 h-5" />
          </Link>
        </div>
      </div>
    </header>
  );
}
