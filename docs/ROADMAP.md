# AgentX — Depth & Interactivity Roadmap

This plan was written against the pre-phase-1 code, and the numbered sections below
are kept as written so the reasoning stays legible. **See "Progress" at the bottom for
what has since been built and what is still open** — sections 0, 2a, 2b, 3, 5 and the
trace parts of 6 are done; section 2b's LangGraph rebuild (dynamic fan-out, conditional
routing, replanning, fallback, conflict resolution, resource budgets, checkpointing —
see "Why LangGraph" in [ARCHITECTURE.md](ARCHITECTURE.md)) is also done; **section 8's
evaluation harness is built with a 53-case dataset across 7 categories, every case
scripted for both `pipeline=fleet` and `pipeline=single`** — an LLM-judge layer and
CI wiring are what's left there; sections 1, 2c, 2d and 4 are not done.

---

## 0. Blockers found in the current code (fix before anything else)

| # | Where | Problem | Why it blocks the rest |
|---|-------|---------|------------------------|
| 1 | `backend/main.py:33-38` | `run_agent()` is fully awaited, *then* the trace is replayed into the SSE stream. Nothing streams live. | Every "live trace / replay / timing" feature depends on real incremental emission. |
| 2 | `frontend/lib/agent-client.ts:81` | `onFinal` builds `{items, coverage_ok}` only — drops `coverage_gaps` and `executive_summary` that the backend actually sends. | `ResultsList` already renders both; backend mode silently loses them. |
| 3 | `frontend/lib/agent-client.ts:32` (`normalizeBackendStep`) | Never sets `observation`. | "Thought → Action → **Grounded Observation**" is impossible on the backend path; `TraceLog`'s observation branch is dead code there. |
| 4 | `backend/alerts/slack.py` | `send_alert()` has no caller anywhere in `backend/`. | Slack alerting is a README claim the Python path does not implement. |
| 5 | `backend/agent/scoring.py:78` | Embeddings are computed for every item, used once for cosine, then discarded. | RAG Q&A, clustering, novelty, "related items" all need them persisted. |
| 6 | `db/schema.sql` | `seen_items` has no `run_id`, `date`, `organization`, `engagement`, `embedding`. | No time series, no competitor stats, no vector search. |
| 7 | orchestrator vs n8n | Python is one agent; n8n is two. `README.md` describes the two-agent pipeline as if it were both. | Divergent behaviour between the local and production demos. |

---

## 1. Research depth — the depth ladder

The current system sits at **L0**. Each level is independently shippable.

- **L0 — snippet.** Search API result fields only. What exists today.
- **L1 — structured metadata.** Sources that return citation counts, institutions,
  assignees, concepts, funders.
- **L2 — full text.** New `fetch_page(url)` tool: httpx + `trafilatura` extraction of
  the top-N URLs. Findings become quotable evidence, not paraphrased snippets.
- **L3 — chunk + embed + store.** pgvector. Enables citation-grounded Q&A,
  related-item lookup, novelty scoring, clustering.
- **L4 — entity resolution.** Normalize `Meta` / `Facebook` / `Meta Platforms, Inc.`
  to one org id. Every competitor statistic is wrong until this exists.
- **L5 — multi-hop.** The agent follows references: competitor → their patents →
  their papers → who cites them. Depth via graph traversal, not more queries.

### Sources to add

| Source | API | Key | Gives |
|---|---|---|---|
| arXiv | `export.arxiv.org/api/query` | none | preprints, days-fresh |
| OpenAlex | `api.openalex.org/works` | none (polite email) | 250M works, citations, institutions, concepts |
| Crossref | `api.crossref.org` | none | DOI metadata, funder |
| Europe PMC | REST | none | bio/medical |
| **Google Scholar** | no official API | SerpAPI `engine=google_scholar` (paid) | citation graph, "cited by" |
| PatentsView | `search.patentsview.org` | free key | **replaces `fixtures/patents.json` with real data** |
| EPO OPS / Google Patents | OPS OAuth / SerpAPI | key | non-US patents, families |
| Reddit | OAuth app | free | sentiment beyond HN |
| Product Hunt | GraphQL | free token | product launches |
| RSS (competitor eng blogs) | `feedparser` | none | first-party announcements |
| Job postings | Greenhouse / Lever public boards | none | hiring as an investment signal |
| Wikidata / OpenCorporates | REST | none | org canonicalization for L4 |

**Google Scholar honesty note:** there is no official API. `scholarly` (scraping)
gets IP-blocked within minutes and will fail during a demo. Use SerpAPI's Scholar
engine if budget allows; otherwise OpenAlex covers most of the same citation graph
legitimately — and the run should say so in `coverage_gaps` rather than pretend
Scholar was searched.

**Market parameters — what is honestly derivable** from these sources: patent filing
rate per assignee, publication rate per org, GitHub star velocity, HN comment volume
and sentiment, funding rounds mentioned in news, headcount signal from job boards.
TAM and market-size numbers are **not** derivable — do not synthesize them. Label the
panel "market signals", not "market size".

---

## 2. Agent architecture

### 2a. Provider abstraction

Add `backend/agent/providers/{anthropic,gemini,router}.py` behind one `LLMProvider`
protocol (`stream_turn(messages, tools) -> parts`). The orchestrator stops importing
`google.genai` directly. The Anthropic path uses the Messages API tool-use loop —
`claude-opus-5` for the Planner and Strategist, `claude-sonnet-5` for the parallel
Researchers. Provider becomes a per-run request parameter, and therefore also a
comparison axis: same goal, two providers, diff the findings.

### 2b. Specialist fleet (replaces the single loop)

```
Planner      decompose goal -> sub-questions + source plan + budget
  |-- Researcher x N   parallel, one per source cluster, fan-out
Verifier     every item must map to a real observation; drop unsupported ones
Analyst      score + relevance_reason (current scoring.py, kept)
Strategist   threat level, SWOT, recommended action per competitor
Critic       adversarial pass on the executive summary
```

Each stage emits typed trace events so the UI can render swimlanes.

### 2c. MCP — both directions

- **AgentX as an MCP server.** Wrap `backend/agent/tools.py` plus a new
  `query_findings` in FastMCP. Claude Desktop and Claude Code can then query the
  intel DB directly. Small change, large demo value.
- **AgentX as an MCP client.** The orchestrator mounts external MCP servers (Agent
  Router's among them) and merges their tools into `TOOL_MAP` at startup. The agent
  gains capabilities without you writing the integrations.

### 2d. Agent Router (per https://www.agent-router.org/docs)

- **Consumer side:** Agent Router exposes a single MCP server that routes tasks to
  specialized agents. Connect over SSE and register its tools into the tool map (2c).
- **Builder side:** publish AgentX itself. The webhook contract is
  `{task_id, caller_id, payload, callback_url}` inbound, and a callback POST to
  `callback_url` carrying header `X-Agent-Router-Token` with body
  `{task_id, status: "COMPLETED", result}`. **The existing n8n workflow is already a
  POST webhook** — this is one extra HTTP Request node plus a payload mapping, and
  the workflow must be toggled Active so the production URL is live (not the test
  URL). That turns the project into a published, monetizable agent.

---

## 3. Statistics layer

New tables: `items` (superset of `seen_items`, with `run_id`, `published_at`,
`org_id`, `engagement`, `embedding vector(768)`), `orgs`, `topics`, `item_topics`,
`tool_calls` (source, query, status, latency_ms, cached, tokens).

`GET /stats/*` endpoints and what each computes:

| Metric | Definition |
|---|---|
| competitor share | items and mean impact per org, bucketed weekly |
| momentum | items/week per topic; OLS slope → rising / flat / declining |
| citation velocity | citations ÷ months since publication |
| novelty | `1 - max cosine(item, all prior items)` — how unprecedented |
| topic clusters | HDBSCAN over stored embeddings; cluster label written by the LLM |
| threat matrix | org × topic heat, cell = sum(impact) |
| source reliability | success rate, p50/p95 latency, cache hit rate, 429 rate per tool |
| run economics | tokens, cost, wall-clock, tool calls, retry rate per run |
| alert precision | fraction of ≥8 alerts later pinned vs dismissed |

---

## 4. Grounded Intelligence Findings grid

Virtualized continuous grid (`@tanstack/react-virtual`) with faceted filters: source,
org, impact band, date range, topic cluster, novelty, and "new since last run".

Card anatomy: title → org chip → source chip → impact ring → date → engagement →
evidence snippet with query terms highlighted → "why it matters" (the existing
`relevance_reason`) → **provenance footer: tool name, exact query, fetched_at, HTTP
status** → actions: pin / dismiss / thumbs / "jump to the trace step that found this".

Click opens a side drawer: full extracted text (L2), related items by embedding (L3),
and a timeline of everything from the same org.

---

## 5. Interactive Strategy Q&A

Hybrid retrieval: Postgres `tsvector` BM25 plus pgvector cosine, reciprocal-rank
fused, scoped to one run or globally. Streaming answer with inline citation chips;
clicking a chip scrolls the grid to that card. Suggested questions generated from the
current topic clusters. Conversation keyed by the `session_id` already produced in
`frontend/lib/agent-client.ts:20`. System prompt rule: **cite or refuse** — a claim
without a retrieved chunk id is not emitted.

---

## 6. Frontend — how far this can go

New dependencies: `recharts` (or `visx`), `@tanstack/react-virtual`, `cmdk`,
`framer-motion`, `react-force-graph-2d`, `zustand`.

Shell: left rail — Overview / Run / Findings / Graph / Stats / Q&A / History /
Source health / Settings.

**Reasoning & Execution Trace (collapsible terminal, upgraded)**

- Thought → Action → Grounded Observation, each step collapsible, observation
  pretty-printed with syntax highlighting and a raw/parsed toggle
- per-step duration bar, token count, cumulative cost
- agent swimlanes (Planner | Researcher | Verifier | Analyst | Strategist)
- filters: failures only, one tool only, one agent only
- **replay scrubber** — re-play any historical run at 1×/4×/instant
- copy a step as JSON; deep-link `#step-7`

**Everything else**

- Command palette (⌘K): run a goal, jump to an org, apply a filter, open a run
- Knowledge graph: org ↔ topic ↔ item force layout; clicking a node cross-filters
  every other view
- Charts: topic momentum sparklines, org stacked area, source reliability bars,
  impact histogram, novelty scatter (x = recency, y = impact, r = engagement)
- Brushable timeline that cross-filters the grid, graph, and charts
- Run diff: run N vs N-1 → added / score changed / dropped
- Watchlist: pin orgs and topics; the next run's Planner prioritizes them
- Export: one-click Markdown/PDF brief from the executive summary plus top items
- Live: real SSE (blocker 1) plus a toast on any ≥8 alert
- Mobile: filters in a bottom sheet; the grid collapses to a single column

---

## 7. Ops

Cost meter and per-run budget cap; exponential backoff and a circuit breaker per
source (on top of the existing TTL cache in `tools.py`); OpenTelemetry spans per tool
call feeding the Source health page. The eval harness itself is now its own section
(8) rather than a line item here, because it needs a dataset and evaluator design,
not just a script.

---

## 8. Evaluation (Ladder 6) — built, 53-case dataset

Everything the fleet already tracks — coverage score, replan rationale, conflicts,
resource usage, rejected count, tokens, per-source reliability, p95 latency — is
operational telemetry: numbers about one run, read from the stored trace. It was not
an evaluation framework: nothing ran the same fixed task twice and checked the agent
behaved correctly. `backend/evaluation/` now closes that gap for the framework-
mechanics half of the problem (see [ARCHITECTURE.md § Evaluation](ARCHITECTURE.md)
for the implementation writeup); the dataset-size and LLM-judge/human-eval layers
below are what's still open.

**Layout (as built)**

```
backend/evaluation/
├── datasets.py       # 53 Case objects across 7 categories (8/8/8/8/8/6/7)
├── case_builders.py   # one factory function per category — a new case only needs
│                        # goal/context/org/titles/urls, not the script wiring
├── fakes.py             # FakeProvider (role-routed by system-prompt phrase), fake tools, fake memory
├── evaluators.py          # 9 deterministic checks — task_success, hallucination_rejected_by_verifier,
│                            #   recovery_run_completed, recovery_gap_reported, conflict_detected_and_resolved,
│                            #   replanning_triggered, refusal_on_insufficient_evidence,
│                            #   coverage_ok_matches_expected, states_assumption_on_ambiguous_goal
├── metrics.py               # aggregates outcomes -> per-category, per-check, and repeat-to-repeat consistency
├── report.py                 # plain-text console report, CI-safe (ASCII only)
└── runner.py                   # CLI: python -m evaluation.runner [--pipeline fleet|single|both] [--repeat N]
```

Categories: `normal` (8), `tool_failure` (8), `contradictory` (8), `incomplete` (8),
`adversarial` (8), `replanning` (6, added beyond the original sketch below — it's a
core Ladder-5 mechanic, not just an evidence scenario, and deserved its own
category), `ambiguous` (7). Every case carries both a `pipeline=fleet` and a
`pipeline=single` script (`case_builders.py`'s `_combine_for_single()` auto-derives
the `single` script from the same lane data, except `replanning` — where it
deliberately omits the follow-up lane the single loop has no mechanism to open —
and `adversarial` — where it omits the planted hallucination the single loop has no
verifier to catch, so its script is the honest best case rather than an exercised
failure mode).

Run it: `cd backend && python -m evaluation.runner --pipeline both --repeat 3` — no
network, no API keys, no `DATABASE_URL` required. 318 runs, 714 checks, 100% pass,
100% repeat-to-repeat consistency. Exits non-zero on any failing check, so it's
CI-usable as-is.

**Evaluator types, in order of trust**

1. **Deterministic/code — built.** All 9 evaluators in `evaluators.py`. No LLM
   involved in grading; each checks something the code can answer with certainty
   (was the planted ungrounded item in the verifier's `rejected` list; did
   `self_evaluation.replanned` come back true when coverage was thin; did
   `final.conflicts` name the organization a case deliberately set up to conflict;
   does the executive summary say it interpreted an ambiguous goal a certain way).
2. **LLM judge — not built.** For things a regex can't grade (answer quality,
   whether a stated assumption on an ambiguous goal was *reasonable*, not just
   present). Feed it the goal, ground truth, evidence, and agent output as separate
   structured fields — never let the agent's own output phrase the grading criteria
   — and require structured JSON back, not prose.
3. **Human — not built.** Spot-check strategic usefulness on a handful of cases;
   not worth building tooling around for a project this size.

**What's still open**

- The LLM-judge layer, for the parts deterministic checks can't fully grade (mainly
  whether an `ambiguous` case's stated assumption was actually *reasonable*, not
  just present).
- Wire `python -m evaluation.runner` into CI as a regression gate on `fleet.py`/
  `orchestrator.py` changes.
- The `fleet` vs `single` comparison currently reports pass/fail per check, not a
  side-by-side score table — `report.py` could add a dedicated "why fleet wins"
  section reading the `replanning`/`adversarial` categories' now-different
  pipeline-specific expectations directly.
- Dataset is 53 cases (in the 40-60 target range) but still hand-authored one domain
  at a time — could keep growing per category if a specific mechanic needs more
  coverage.

---

## Progress

**Phase 1 — done.** All seven blockers fixed: real incremental SSE, grounded
observations on the backend path, `coverage_gaps`/`executive_summary` no longer
dropped, Slack alerts wired into the Python path, embeddings persisted, pgvector
schema, and the docs corrected.

**Phase 2 — done.** `backend/agent/providers/` (Anthropic + Gemini behind one
protocol, selectable per run), `backend/agent/fleet.py` (planner → parallel
researchers → deterministic verifier → analyst → strategist), `backend/agent/stats.py`
(`/stats`), `backend/agent/qa.py` (`/ask`, hybrid RRF retrieval, cite-or-refuse), and
the frontend: agent swimlanes, a Statistics tab with hand-built inline-SVG charts, an
Ask tab with clickable citations, and a Strategist panel.

**Phase 3 — done.** `fleet.py` rebuilt as a LangGraph `StateGraph` (`_build_graph()`)
instead of a linear async function — dynamic fan-out per sub-question via
`Send()`/conditional edges, shared `FleetState` with reducers instead of closures,
dynamic replanning (capped at one round), tool fallback (`search_papers` ->
Crossref), evidence conflict resolution across source types, resource-aware execution
against a tool-call/time budget, and mid-run checkpointing to Postgres. All of it is
surfaced in the stored run (`self_evaluation`, `conflicts`, `resource_usage`) and in
the `SelfEvalPanel`, not trace-only. See "Why LangGraph" in
[ARCHITECTURE.md](ARCHITECTURE.md).

**Still open from section 1:** every new source (arXiv, OpenAlex, PatentsView,
Crossref, Reddit, Product Hunt, RSS, job boards) and depth levels L2, L4 and L5.
`search_patents` still reads `backend/fixtures/patents.json` — this is the one
un-upgraded data source and worth prioritizing since patents are explicit to the
problem statement. Chunk-level embedding (L3) is item-level today — Q&A retrieves
whole findings, not passages.

**Still open from section 2:** MCP in both directions, and publishing to Agent Router.

**Still open from section 8 (evaluation):** the LLM-judge layer and CI wiring —
dataset breadth (53 cases) and the `single`-pipeline baseline (every case now
scripted for both pipelines) are done. See "What's still open" under section 8 above
for the full list — the harness plumbing (fakes, evaluators, runner, report) is built
and does not need to change shape to absorb any of these.

**Still open from sections 4, 6 and 7:** the virtualized findings grid, knowledge
graph, brushable timeline, run diff, watchlist, command palette, replay scrubber,
export, cost caps, and circuit breakers.

## Suggested order from here

1. **Wire the evaluation harness into CI (section 8).** The harness, dataset (53
   cases, 7 categories), and fleet-vs-single baseline are done —
   `--pipeline both --repeat 3` is 318 runs, 714/714 checks, 100% pass, 100%
   consistency. Highest remaining value: make `python -m evaluation.runner` a CI
   gate on `fleet.py`/`orchestrator.py` changes, then the LLM-judge layer for what
   deterministic checks can't grade (mainly `ambiguous`).
2. Live patent source (PatentsView, free key) to replace the fixture — the one
   remaining source that is not real data.
3. Sources and depth: arXiv + OpenAlex, then `fetch_page` (L2) and chunk-level
   embeddings (L3).
4. Entity resolution (L4). Every competitor statistic is approximate until two
   spellings of one company stop counting as two organizations.
5. MCP server and client, and the Agent Router builder publish.
6. The findings grid, knowledge graph and replay scrubber.
