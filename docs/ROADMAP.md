# AgentX — Depth & Interactivity Roadmap

This plan was written against the pre-phase-1 code, and the numbered sections below
are kept as written so the reasoning stays legible. **See "Progress" at the bottom for
what has since been built and what is still open** — sections 0, 2a, 2b, 3, 5 and the
trace parts of 6 are done; sections 1, 2c, 2d, 4, 7 and most of 6 are not.

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
source (on top of the existing TTL cache in `tools.py`); an eval harness of fixed
goals with golden items, measuring recall/precision drift across prompt changes;
OpenTelemetry spans per tool call feeding the Source health page.

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

**Still open from section 1:** every new source (arXiv, OpenAlex, PatentsView,
Crossref, Reddit, Product Hunt, RSS, job boards) and depth levels L2, L4 and L5.
`search_patents` still reads `backend/fixtures/patents.json`. Chunk-level embedding
(L3) is item-level today — Q&A retrieves whole findings, not passages.

**Still open from section 2:** MCP in both directions, and publishing to Agent Router.

**Still open from sections 4, 6 and 7:** the virtualized findings grid, knowledge
graph, brushable timeline, run diff, watchlist, command palette, replay scrubber,
export, cost caps, circuit breakers, and the eval harness.

## Suggested order from here

1. Sources and depth: arXiv + OpenAlex + PatentsView, then `fetch_page` (L2) and
   chunk-level embeddings (L3). This is the largest remaining quality jump — the
   agent currently reasons over search snippets.
2. Entity resolution (L4). Every competitor statistic is approximate until two
   spellings of one company stop counting as two organizations.
3. MCP server and client, and the Agent Router builder publish.
4. The findings grid, knowledge graph and replay scrubber.
5. The eval harness, so prompt changes stop being judged by eye.
