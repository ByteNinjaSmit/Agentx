"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Compass,
  Lightbulb,
  Radar,
  Database,
  Activity,
  FlaskConical,
  Cpu,
  Info,
  ChevronsLeft,
  ChevronsRight,
  X,
  type LucideIcon,
} from "lucide-react";
import { usePersistedValue } from "@/lib/client-state";
import { useActiveRun } from "@/lib/active-run";
import { fetchEvaluation } from "@/lib/evaluation-client";

const PRIMARY = [
  { name: "Overview", href: "/overview", icon: LayoutDashboard },
  { name: "Investigate", href: "/", icon: Compass },
  { name: "Intelligence", href: "/intelligence", icon: Lightbulb },
  { name: "Monitor", href: "/monitor", icon: Radar },
  { name: "Memory", href: "/memory", icon: Database },
  { name: "Activity", href: "/activity", icon: Activity },
  { name: "Evaluation", href: "/evaluation", icon: FlaskConical },
];

const SECONDARY = [
  { name: "Agent Runtime", href: "/settings", icon: Cpu },
  { name: "About", href: "/about", icon: Info },
];

const COLLAPSE_KEY = "agentx-sidebar-collapsed";

function isActiveHref(pathname: string | null, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || !!pathname?.startsWith(href + "/");
}

function NavItem({
  name,
  href,
  icon: Icon,
  active,
  collapsed,
  badge,
  onNavigate,
}: {
  name: string;
  href: string;
  icon: LucideIcon;
  active: boolean;
  collapsed: boolean;
  badge?: React.ReactNode;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      title={collapsed ? name : undefined}
      className={`relative flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium transition-colors ${
        active
          ? "bg-[var(--surface)] text-[var(--foreground)] border border-[var(--border)] shadow-[var(--shadow-sm)]"
          : "text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] border border-transparent"
      } ${collapsed ? "justify-center" : ""}`}
    >
      <Icon className="w-[18px] h-[18px] shrink-0" strokeWidth={1.8} />
      {!collapsed && <span className="flex-1 truncate">{name}</span>}
      {!collapsed && badge}
      {collapsed && badge && <span className="absolute top-1 right-1">{badge}</span>}
    </Link>
  );
}

function SidebarContent({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate: () => void;
}) {
  const pathname = usePathname();
  const activeRun = useActiveRun();
  const [hasBenchmark, setHasBenchmark] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchEvaluation()
      .then((d) => {
        if (!cancelled) setHasBenchmark(!!d.benchmark);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <nav className="flex flex-col h-full py-4" aria-label="Primary">
      <div className={`px-2.5 mb-1 flex items-center gap-2 ${collapsed ? "justify-center" : ""}`}>
        <div className="w-8 h-8 shrink-0 rounded bg-[var(--foreground)] flex items-center justify-center text-[var(--surface)] font-bold text-sm">
          AX
        </div>
        {!collapsed && <span className="font-semibold text-[var(--foreground)] tracking-tight">AGENTX</span>}
      </div>

      <div className="flex-1 overflow-y-auto px-2 mt-4 space-y-0.5">
        {PRIMARY.map((item) => (
          <NavItem
            key={item.href}
            {...item}
            collapsed={collapsed}
            active={isActiveHref(pathname, item.href)}
            onNavigate={onNavigate}
            badge={
              item.href === "/" && activeRun ? (
                <span className="relative flex h-2 w-2" title={`Live: ${activeRun.goal}`}>
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--accent)] opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--accent)]" />
                </span>
              ) : item.href === "/evaluation" && hasBenchmark ? (
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-[var(--accent-secondary)]" title="Benchmark available" />
              ) : undefined
            }
          />
        ))}
      </div>

      <div className="px-2 pt-3 mt-3 border-t border-[var(--border)] space-y-0.5">
        {SECONDARY.map((item) => (
          <NavItem
            key={item.href}
            {...item}
            collapsed={collapsed}
            active={isActiveHref(pathname, item.href)}
            onNavigate={onNavigate}
          />
        ))}
      </div>
    </nav>
  );
}

/** Persistent left app shell nav. Desktop: fixed rail, collapsible to icons-only
 *  (state persisted per-browser). Below `lg`: hidden by default, opens as an
 *  off-canvas drawer via the hamburger in TopBar (same window-event pattern as
 *  CommandPalette, so the two components don't need a shared parent). */
export default function Sidebar() {
  const [collapsedStr, setCollapsedStr] = usePersistedValue<"1" | "0">(
    COLLAPSE_KEY,
    "0",
    (v) => v === "1" || v === "0"
  );
  const collapsed = collapsedStr === "1";
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    function onToggle() {
      setMobileOpen((v) => !v);
    }
    window.addEventListener("agentx:toggle-sidebar", onToggle);
    return () => window.removeEventListener("agentx:toggle-sidebar", onToggle);
  }, []);

  return (
    <>
      {/* Desktop rail */}
      <aside
        className={`hidden md:flex sticky top-0 h-screen shrink-0 flex-col border-r border-[var(--border)] bg-[var(--background)] transition-[width] duration-200 ${
          collapsed ? "w-[68px]" : "w-[228px]"
        }`}
      >
        <SidebarContent collapsed={collapsed} onNavigate={() => {}} />
        <button
          type="button"
          onClick={() => setCollapsedStr(collapsed ? "0" : "1")}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="mx-2 mb-3 flex items-center justify-center gap-2 rounded-md border border-[var(--border)] py-1.5 text-xs font-medium text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] transition-colors"
        >
          {collapsed ? <ChevronsRight className="w-3.5 h-3.5" /> : <ChevronsLeft className="w-3.5 h-3.5" />}
        </button>
      </aside>

      {/* Mobile off-canvas drawer */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-[90]">
          <div className="absolute inset-0 bg-[rgba(16,24,40,0.35)]" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-64 bg-[var(--background)] border-r border-[var(--border)] shadow-lg flex flex-col">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
              className="absolute top-3 right-3 p-1.5 text-[var(--foreground-secondary)] hover:text-[var(--foreground)]"
            >
              <X className="w-4 h-4" />
            </button>
            <SidebarContent collapsed={false} onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}
    </>
  );
}
