"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, Bell, User } from "lucide-react";

export default function TopNav() {
  const pathname = usePathname();

  const mainLinks = [
    { name: "Investigate", href: "/" },
    { name: "Monitor", href: "/monitor" },
    { name: "Intelligence", href: "/intelligence" },
    { name: "Memory", href: "/memory" },
    { name: "Activity", href: "/activity" },
    { name: "About", href: "/about" },
    { name: "Settings", href: "/settings" },
  ];

  return (
    <header className="w-full bg-[var(--background)] border-b border-[var(--border)] sticky top-0 z-50">
      <div className="max-w-[1400px] mx-auto px-6 h-16 flex items-center justify-between">
        
        {/* Left side: Brand + Nav Links */}
        <div className="flex items-center gap-10">
          <Link href="/" className="flex items-center gap-2 group">
            <div className="w-8 h-8 rounded bg-[var(--foreground)] flex items-center justify-center text-[var(--surface)] font-bold text-lg group-hover:bg-[var(--accent)] transition-colors">
              AX
            </div>
            <span className="font-semibold text-[var(--foreground)] tracking-tight">AGENTX</span>
          </Link>

          <nav className="hidden md:flex items-center gap-1">
            {mainLinks.map((link) => {
              const isActive = pathname === link.href || (link.href !== '/' && pathname?.startsWith(link.href));
              
              // Add a tiny divider before "About" visually
              const isDivider = link.name === "About";

              return (
                <div key={link.name} className="flex items-center">
                  {isDivider && <div className="w-[1px] h-4 bg-[var(--border)] mx-3" />}
                  <Link
                    href={link.href}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                      isActive 
                        ? "text-[var(--foreground)] bg-[var(--surface)] border border-[var(--border)] shadow-[var(--shadow-sm)]" 
                        : "text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)]"
                    }`}
                  >
                    {link.name}
                  </Link>
                </div>
              );
            })}
          </nav>
        </div>

        {/* Right side: Actions */}
        <div className="flex items-center gap-4">
          <Link
            href="/"
            aria-label="New investigation"
            className="p-2 text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] rounded-md transition-colors"
          >
            <Search className="w-5 h-5" />
          </Link>
          <Link
            href="/activity"
            aria-label="Activity"
            className="p-2 text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] rounded-md transition-colors"
          >
            <Bell className="w-5 h-5" />
          </Link>
          <Link
            href="/settings"
            aria-label="Settings"
            className="p-2 text-[var(--foreground-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] rounded-md transition-colors"
          >
            <User className="w-5 h-5" />
          </Link>
        </div>

      </div>
    </header>
  );
}
