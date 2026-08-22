import type { FinalResult, Item } from "./types";

/** Everything on screen, as a file someone can paste into a doc or a PR.
 *  Deliberately built from the same `final` object the dashboard renders, so the
 *  exported brief can never claim something the UI doesn't show. */
export function briefMarkdown(final: FinalResult, track: string): string {
  const items = [...final.items].sort((a, b) => b.impact_1_10 - a.impact_1_10);
  const watched = final.competitors_watched ?? [];
  const lines: string[] = [];

  lines.push(`# Competitive brief — ${track || "market scan"}`);
  lines.push("");
  lines.push(
    `_${items.length} grounded signal${items.length === 1 ? "" : "s"}` +
      (watched.length ? ` across ${watched.length} watched competitor${watched.length === 1 ? "" : "s"}` : "") +
      `. Generated ${new Date().toISOString().slice(0, 10)}` +
      (final.model ? ` by ${final.model}` : "") +
      (final.pipeline ? ` on the ${final.pipeline} pipeline` : "") +
      "._"
  );
  lines.push("");

  if (final.executive_summary) {
    lines.push("## Executive summary");
    lines.push("");
    lines.push(final.executive_summary);
    lines.push("");
  }

  if (watched.length) {
    lines.push("## Signal share");
    lines.push("");
    lines.push("| Competitor | Signals | Top impact |");
    lines.push("| --- | --- | --- |");
    for (const name of watched) {
      const own = items.filter((it) => it.competitor === name);
      const top = own.length ? Math.max(...own.map((it) => it.impact_1_10)) : 0;
      lines.push(`| ${name} | ${own.length} | ${own.length ? `${top}/10` : "—"} |`);
    }
    const unattributed = items.filter((it) => !it.competitor);
    if (unattributed.length) {
      lines.push(`| _wider market_ | ${unattributed.length} | — |`);
    }
    lines.push("");
  }

  const strategy = final.strategy;
  if (strategy?.competitors?.length) {
    lines.push("## Threat assessment");
    lines.push("");
    for (const c of strategy.competitors) {
      lines.push(`### ${c.organization} — ${c.threat_level} threat`);
      if (c.assessment) lines.push("", c.assessment);
      for (const e of c.evidence ?? []) lines.push(`- evidence: ${e}`);
      lines.push("");
    }
  }

  if (strategy?.recommended_actions?.length) {
    lines.push("## Recommended actions");
    lines.push("");
    for (const a of strategy.recommended_actions) {
      lines.push(`- **[${a.horizon ?? "—"}]** ${a.action}${a.rationale ? ` — ${a.rationale}` : ""}`);
    }
    lines.push("");
  }

  lines.push("## Findings");
  lines.push("");
  if (!items.length) lines.push("_No new signals — everything found was already known._");
  for (const it of items) {
    lines.push(`### ${it.title}`);
    lines.push("");
    lines.push(
      `\`${it.source}\` · impact **${it.impact_1_10}/10**` +
        (it.competitor ? ` · ${it.competitor}` : "") +
        (it.organization && it.organization !== it.competitor ? ` · ${it.organization}` : "") +
        (it.date ? ` · ${it.date}` : "")
    );
    lines.push("");
    if (it.relevance_reason) lines.push(it.relevance_reason, "");
    if (it.url) lines.push(`<${it.url}>`, "");
  }

  if (final.coverage_gaps?.length) {
    lines.push("## Coverage gaps");
    lines.push("");
    // Named, not hidden — a gap the reader can't see is worse than one they can.
    for (const g of final.coverage_gaps) lines.push(`- ${typeof g === "string" ? g : JSON.stringify(g)}`);
    lines.push("");
  }

  if (final.rejected_count) {
    lines.push(
      `_${final.rejected_count} finding(s) were discarded by the verifier for not being traceable to a real tool result._`
    );
  }

  return lines.join("\n");
}

/** Item count per competitor, with the unattributed remainder last. */
export function signalShare(items: Item[], watched: string[]) {
  const share = watched.map((name) => ({
    name,
    items: items.filter((it) => it.competitor === name).length,
  }));
  const rest = items.filter((it) => !it.competitor || !watched.includes(it.competitor)).length;
  return rest > 0 ? [...share, { name: "wider market", items: rest }] : share;
}

export function downloadMarkdown(filename: string, markdown: string) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
