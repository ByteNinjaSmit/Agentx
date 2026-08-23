import type { Metadata, Viewport } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import CommandPalette from "@/components/CommandPalette";

export const metadata: Metadata = {
  title: "AgentX — Autonomous Competitive Intelligence",
  description:
    "AgentX autonomously researches scientific developments, patents, competitors, news and industry signals — then determines what matters.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F7F8FA" },
    { media: "(prefers-color-scheme: dark)", color: "#F7F8FA" }, // Force light theme color
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      data-theme="light" // Force light theme for the redesign
    >
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />
      </head>
      <body className="min-h-full bg-[var(--background)] text-[var(--foreground)] font-sans antialiased">
        <div className="flex min-h-screen">
          <Sidebar />
          <div className="flex-1 flex flex-col min-w-0">
            <TopBar />
            <main className="flex-1 w-full max-w-[1400px] mx-auto px-6 py-8">
              {children}
            </main>
          </div>
        </div>
        <CommandPalette />
      </body>
    </html>
  );
}
