"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Lightbulb, ArrowRight } from "lucide-react";
import { fetchRuns } from "@/lib/history-client";

/** No run id given — send the operator to their most recent report, or to an
 *  empty state if nothing has run yet. Every report otherwise lives at
 *  /intelligence/[id]. */
export default function IntelligenceIndexPage() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    fetchRuns(1)
      .then((runs) => {
        if (runs.length > 0) {
          router.replace(`/intelligence/${runs[0].id}`);
        } else {
          setChecked(true);
        }
      })
      .catch(() => {
        setLoadError(true);
        setChecked(true);
      });
  }, [router]);

  if (!checked) {
    return <p className="text-sm text-[var(--foreground-secondary)] max-w-4xl mx-auto py-20 text-center">Loading…</p>;
  }

  return (
    <div className="max-w-4xl mx-auto py-20 flex flex-col items-center text-center animate-slide-up">
      <div className="w-16 h-16 bg-[var(--surface-2)] rounded-full flex items-center justify-center mb-6 border border-[var(--border)]">
        <Lightbulb className="w-8 h-8 text-[var(--foreground-secondary)]" />
      </div>
      <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-3">No intelligence yet</h1>
      <p className="text-[var(--foreground-secondary)] max-w-md mb-6">
        {loadError
          ? "Couldn't reach the backend to load your latest run."
          : "Run an investigation and its report — findings, strategy, coverage — will appear here."}
      </p>
      <Link
        href="/"
        className="inline-flex items-center gap-2 px-6 py-3 bg-[var(--foreground)] text-[var(--surface)] font-semibold rounded-lg hover:bg-[var(--accent)] transition-colors"
      >
        Start an investigation
        <ArrowRight className="w-4 h-4" />
      </Link>
    </div>
  );
}
