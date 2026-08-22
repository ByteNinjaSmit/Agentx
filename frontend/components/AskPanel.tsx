"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { askQuestion, fetchSuggestions } from "@/lib/insight-client";
import type { Answer, Citation } from "@/lib/types";

type Exchange = { question: string; answer: Answer | null; error?: string };

const MATCH_LABEL: Record<Citation["matched_by"], string> = {
  both: "keyword + semantic",
  semantic: "semantic",
  keyword: "keyword",
};

/** Splits an answer on its [n] markers so each one can become a clickable chip. */
function renderWithCitations(text: string, onJump: (n: number) => void) {
  const parts = text.split(/(\[\d{1,2}\])/g);
  return parts.map((part, i) => {
    const match = /^\[(\d{1,2})\]$/.exec(part);
    if (!match) return <span key={i}>{part}</span>;
    const n = Number(match[1]);
    return (
      <button
        key={i}
        onClick={() => onJump(n)}
        className="mx-0.5 rounded bg-accent/10 px-1.5 py-0.5 align-baseline text-[11px] font-medium text-accent transition-colors hover:bg-accent/20"
        title={`Jump to source ${n}`}
      >
        {n}
      </button>
    );
  });
}

function CitationCard({
  index,
  citation,
  used,
  highlighted,
}: {
  index: number;
  citation: Citation;
  used: boolean;
  highlighted: boolean;
}) {
  return (
    <li
      id={`citation-${index}`}
      className={`surface-card p-4 transition-shadow ${
        highlighted ? "ring-2 ring-accent/50" : ""
      } ${used ? "" : "opacity-60"}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="mr-2 rounded bg-accent/10 px-1.5 py-0.5 text-[11px] font-medium text-accent">
            {index}
          </span>
          <a
            href={citation.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-semibold text-foreground/90 hover:text-accent hover:underline underline-offset-4"
          >
            {citation.title}
          </a>
        </div>
        <span className="shrink-0 text-[10px] font-bold uppercase tracking-wider text-foreground/40">
          {citation.source}
          {citation.impact_1_10 != null ? ` · ${citation.impact_1_10}/10` : ""}
        </span>
      </div>
      <p className="mt-1.5 line-clamp-3 text-xs text-foreground/55">{citation.summary}</p>
      <p className="mt-2 text-[11px] text-foreground/35">
        {citation.organization ? `${citation.organization} · ` : ""}
        matched by {MATCH_LABEL[citation.matched_by]}
        {citation.date ? ` · ${citation.date}` : ""}
        {used ? "" : " · retrieved but not cited"}
      </p>
    </li>
  );
}

export default function AskPanel({ runId }: { runId?: string | null }) {
  const [question, setQuestion] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [history, setHistory] = useState<Exchange[]>([]);
  const [asking, setAsking] = useState(false);
  const [scopeToRun, setScopeToRun] = useState(false);
  const [highlighted, setHighlighted] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchSuggestions().then(setSuggestions).catch(() => setSuggestions([]));
  }, []);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (!trimmed || asking) return;
    setAsking(true);
    setQuestion("");
    setHistory((h) => [...h, { question: trimmed, answer: null }]);

    abortRef.current = new AbortController();
    try {
      const answer = await askQuestion(trimmed, {
        runId: scopeToRun ? runId : null,
        signal: abortRef.current.signal,
      });
      setHistory((h) => h.map((e, i) => (i === h.length - 1 ? { ...e, answer } : e)));
    } catch (e) {
      const message = (e as Error).message;
      setHistory((h) => h.map((e2, i) => (i === h.length - 1 ? { ...e2, error: message } : e2)));
    } finally {
      setAsking(false);
    }
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(question);
    }
  }

  function jumpTo(n: number) {
    setHighlighted(n);
    document.getElementById(`citation-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-sm font-semibold">Interactive strategy Q&amp;A</h2>
        <p className="mt-1 text-xs text-foreground/50">
          Ask analytical questions over the retrieved competitor signals, patents, and
          research. Retrieval is keyword and semantic search fused together; the model is
          instructed to cite or refuse, so an answer with no sources means the corpus does
          not hold one — not that the model is being coy.
        </p>
      </div>

      <div className="surface-card p-4 space-y-3">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="e.g. Which competitor is furthest ahead on on-device inference, and what's the evidence?"
          className="interactive-input w-full resize-y rounded-lg border border-border bg-surface-2/50 px-3 py-2 text-sm outline-none"
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-2 text-[11px] text-foreground/50">
            <input
              type="checkbox"
              checked={scopeToRun}
              disabled={!runId}
              onChange={(e) => setScopeToRun(e.target.checked)}
              className="accent-[var(--accent)]"
            />
            {runId ? "Only this run's findings" : "Run the agent first to scope to one run"}
          </label>
          <button
            onClick={() => ask(question)}
            disabled={asking || !question.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity disabled:opacity-40"
          >
            {asking ? "Thinking…" : "Ask"}
          </button>
        </div>
      </div>

      {history.length === 0 && suggestions.length > 0 && (
        <div className="space-y-2">
          <p className="text-[11px] font-medium uppercase tracking-wide text-foreground/40">
            Grounded in what the corpus already holds
          </p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => ask(s)}
                className="rounded-full border border-border bg-surface-2 px-3 py-1.5 text-xs text-foreground/70 transition-colors hover:border-accent/30 hover:text-accent"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {history.map((exchange, i) => (
        <div key={i} className="space-y-3">
          <p className="text-sm font-medium">{exchange.question}</p>

          {exchange.error && (
            <p role="alert" className="rounded-lg border border-danger/20 bg-danger/10 px-3 py-2.5 text-sm text-danger">
              {exchange.error}
            </p>
          )}

          {!exchange.answer && !exchange.error && (
            <p className="text-sm text-foreground/40 italic">Retrieving and answering…</p>
          )}

          {exchange.answer && (
            <>
              <div className="rounded-xl border border-accent/25 bg-accent/5 px-4 py-3.5">
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/85">
                  {renderWithCitations(exchange.answer.answer, jumpTo)}
                </p>
                <p className="mt-2 text-[11px] text-foreground/40">
                  {exchange.answer.model} · {exchange.answer.citations.length} retrieved ·{" "}
                  {exchange.answer.cited.length} cited
                </p>
              </div>

              {exchange.answer.citations.length > 0 && (
                <ul className="space-y-2">
                  {exchange.answer.citations.map((c, idx) => (
                    <CitationCard
                      key={c.id}
                      index={idx + 1}
                      citation={c}
                      used={exchange.answer!.cited.includes(idx + 1)}
                      highlighted={highlighted === idx + 1}
                    />
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  );
}
