# AgentX — Depth & Interactivity Roadmap

This plan was written against the pre-phase-1 code, and the numbered sections below
are kept as written so the reasoning stays legible. **See "Progress" at the bottom for
what has since been built and what is still open** — sections 0, 2a, 2b, 3, 5 and the
trace parts of 6 are done; section 2b's LangGraph rebuild (dynamic fan-out, conditional
routing, replanning, fallback, conflict resolution, resource budgets, checkpointing —
see "Why LangGraph" in [ARCHITECTURE.md](ARCHITECTURE.md)) is also done; **section 8's
evaluation harness is built with a 53-case dataset across 7 categories, every case
scripted for both `pipeline=fleet` and `pipeline=single`, and its LLM-judge tier
(`evaluation/llm_judge.py` / `judge_runner.py`) and human-eval tier
(`evaluation/human_eval.py`, tooling built, no scores collected yet) are also
built** — CI wiring is what's left there; **section 9's observability closed loop
(trace diagnosis → controlled failure → automatic optimization → before/after
benchmark) is also built**, proven on one scenario (a `search_papers` circuit
breaker); **section 10's loop/deadlock detection and section 11's LangGraph
checkpoint/resume are also built** (checkpoint/resume verified offline via
LangGraph's `InMemorySaver`, not yet against a live Postgres this session) — see
[ARCHITECTURE.md](ARCHITECTURE.md) for all four writeups; sections 1, 2c, 2d and 4
are not done.

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
| ~~PatentsView~~ | ~~`search.patentsview.org`~~ | — | **dead — the domain no longer resolves; PatentsView migrated into USPTO's Open Data Portal. Done via USPTO ODP instead, see below.** |
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

Cost meter and per-run budget cap; exponential backoff (on top of the existing TTL
cache in `tools.py`); OpenTelemetry spans per tool call feeding the Source health
page. The eval harness itself is now its own section (8) rather than a line item
here, because it needs a dataset and evaluator design, not just a script.

**Circuit breaker per source — done, for `search_papers`.** Not the always-on
kind this section originally sketched — an explicitly diagnosed one. See section 9
below: `observability/optimizer.py` opens it only when `trace_analyzer.py` has
actually found `search_papers` falling back on its primary source repeatedly in a
run's trace, never automatically. Extending the same mechanism to the other tools
(`search_news`, `search_patents`'s two-tier fallback, ...) is straightforward — each
just needs its own leaf-function split like `_search_papers_semantic_scholar` and a
`policy.CURRENT.circuit_open` check — but only `search_papers` is wired up today.

---

## 8. Evaluation (Ladder 6) — built, 53-case dataset + LLM-judge + human-eval tiers

Everything the fleet already tracks — coverage score, replan rationale, conflicts,
resource usage, rejected count, tokens, per-source reliability, p95 latency — is
operational telemetry: numbers about one run, read from the stored trace. It was not
an evaluation framework: nothing ran the same fixed task twice and checked the agent
behaved correctly. `backend/evaluation/` now closes that gap for the framework-
mechanics half of the problem (see [ARCHITECTURE.md § Evaluation](ARCHITECTURE.md)
for the implementation writeup); all three evaluator tiers below are built — the
open item is collecting actual human scores on the generated sheet.

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
├── runner.py                   # CLI: python -m evaluation.runner [--pipeline fleet|single|both] [--repeat N]
├── llm_judge.py                  # judge(): grades a scripted case's final result via a real LLM call
└── judge_runner.py                 # CLI: python -m evaluation.judge_runner [--pipeline ...] [--provider ...]
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
2. **LLM judge — built.** `evaluation/llm_judge.py`'s `judge()`, run over scripted
   cases by `judge_runner.py`. For things a regex can't grade (answer quality,
   whether a stated assumption on an ambiguous goal was *reasonable*, not just
   present). Goal, evidence, coverage gaps, and the candidate answer are fed in as
   separate, clearly labeled fields — the candidate's own output never gets to
   phrase its own grading criteria — and the judge is required to return structured
   JSON, not prose. `python -m evaluation.judge_runner` needs a real
   `GEMINI_API_KEY`/`ANTHROPIC_API_KEY`; the *agent* run it grades stays fully
   deterministic (same `FakeProvider`-scripted cases as `runner.py`) — only the
   judge call is live. `tests/test_llm_judge.py` (offline, a fake judge provider)
   covers the parsing/prompt/aggregation logic; `judge_smoke_test.py` (backend root,
   same manual-probe convention as `test_patents.py`) is the one real, billed call —
   confirmed working against live Gemini on `normal-001`: correctly scored
   `overall` as low as 0.2-0.5 across runs for a scripted case whose executive
   summary was fully grounded and accurate but whose (unscripted, default) strategy
   section was empty — the judge is actually grading, not rubber-stamping.
3. **Human — tooling built, no scores collected yet.** `evaluation/human_eval.py`
   generates a rating sheet (one case per category × both pipelines, 13-14 rows —
   `evaluation/results/human_eval_sheet.csv`, real and currently unscored) with a
   1-5 rubric (accuracy, groundedness, completeness, evidence quality, useful
   recommendation, uncertainty handling, overall) documented in
   [docs/HUMAN_EVAL_PROTOCOL.md](HUMAN_EVAL_PROTOCOL.md), and a scorer that computes
   mean scores plus inter-rater agreement (mean absolute difference and % of pairs
   within 1 point, for any case rated by 2+ people) once someone fills it in.
   `--score` on the unscored sheet correctly reports `rows_scored: 0` rather than
   fabricating a result — spot-checking strategic usefulness this way needed real
   tooling for a project this size after all, just not a fabricated result from it.

**What's still open**

- Wire `python -m evaluation.runner`, `judge_runner`, and `human_eval` into CI —
  `runner` is free and deterministic; `judge_runner` needs a real key so it would
  be a separate, opt-in job; `human_eval --score` is a good CI check that a
  filled-in sheet parses and aggregates correctly, but obviously can't itself
  produce ratings.
- Actual human ratings on the generated sheet — the protocol and tooling are
  built; nobody has rated the 13-14 rows yet.
- Only one LLM-judge use case is exercised so far (grading a fixed
  scripted case's output); it hasn't yet been pointed at a *live*, non-scripted
  fleet run's real output, which is where the "answer quality" grading matters most
  in production, not just in the harness.
- The `fleet` vs `single` comparison currently reports pass/fail per check, not a
  side-by-side score table — `report.py` could add a dedicated "why fleet wins"
  section reading the `replanning`/`adversarial` categories' now-different
  pipeline-specific expectations directly.
- Dataset is 53 cases (in the 40-60 target range) but still hand-authored one domain
  at a time — could keep growing per category if a specific mechanic needs more
  coverage.

---

## 9. Observability closed loop — built

Section 8 above checks whether the fleet behaves correctly on a fixed case; nothing
turned a completed run's *own* trace into a diagnosis, applied a fix, and proved the
fix helped. `backend/observability/` now does exactly that — see
[ARCHITECTURE.md § Observability closed loop](ARCHITECTURE.md) for the full
writeup. In short: `trace_analyzer.py` runs eight rule-based detectors over any
trace/final pair (unreliable primary source, slow tool, tool failure, duplicate
call, low-yield tool, replanning overhead, verifier rejections, budget pressure);
`root_cause.py` ranks them deterministically into one diagnosis; `optimizer.py` maps
the dominant finding to one of a small fixed set of policy actions (today, exactly
one is actually enforced — a per-run circuit breaker on `search_papers`, closing
section 7's circuit-breaker item); `evaluation/full_benchmark.py`
(`python -m evaluation.full_benchmark`) runs a scripted Semantic-Scholar-outage
scenario through the real `agent.fleet` graph before and after the fix and prints a
real before/after table (a representative run: 96% lower elapsed time, same items
found, `coverage_ok` unchanged).

**What's still open**

- Only one finding category (`unreliable_primary_source`) maps to an enforced
  action. `duplicate_tool_call` and `replanning_overhead`/`low_yield_tool` have
  reserved `Policy` knobs (`suppress_duplicate_tool_calls`,
  `research_max_steps_override`) but no call site reads them yet.
- One controlled-failure scenario (`fault_injection.semantic_scholar_timeout`).
  The rest of the fault menu from the original ask (GitHub 429, a news provider
  outage, a slow tool, conflicting/incomplete evidence) is not yet built —
  `evaluation/fakes.py`'s existing `tool_failure`/`contradictory`/`incomplete`
  category cases already exercise most of those *behaviorally* (section 8), just
  not through this diagnosis/optimization loop.
- Human evaluation remains open from section 8; LLM-as-judge is now built there
  (see section 8's own "What's still open" — it hasn't yet been pointed at this
  section's before/after runs specifically, only at the base scripted dataset).

The general-purpose loop/deadlock detector and native LangGraph checkpoint/resume
originally listed as open here are now built — see sections 10 and 11.

---

## 10. Loop / deadlock detection — built

`agent/loop_guard.py`'s `LoopGuard` is the live, in-run counterpart to this
section's `duplicate_tool_call` finding — that one only sees a repeated call after
the run is over; this one blocks the repeat before it's issued. `RESEARCH_MAX_STEPS`
already bounds a researcher's ReAct loop; `LoopGuard` adds the missing piece —
detecting "same tool + same normalized query + no new evidence" *within* that
bound, not just eventually capping it.

Same tool signature (`call_signature`) called again and getting back the identical
raw result — that's the whole definition of "no new evidence," deterministic, no
downstream join required. Two blocking paths, wired identically into both
`fleet.py::_research()` (per research lane) and `orchestrator.py::run_agent_stream()`
(the single loop, which has no verifier/self-eval safety net so this matters even
more there): duplicate calls in the *same* turn are deduplicated immediately (the
second can never help — decided before either executes); duplicate calls *across*
turns (a model ignoring the system prompt's "never repeat an identical query"
instruction) hit `LoopGuard.should_block()`. A blocked call is never re-issued — the
model gets a synthetic `is_error=True` tool result explaining why and suggesting it
try something else, and a `runtime`-agent trace step makes the intervention visible
live. `final["loop_events"]` (new `FleetState` field, merged across every parallel
lane) lists every intervention.

Tested in `tests/test_loop_guard.py` — unit tests on the blocking semantics, plus
one integration test per pipeline scripting a lane that issues the identical
`(tool, query)` twice in one turn and confirming the second is blocked. Full
Ladder 6 suite stayed 714/714 after wiring this into both pipelines' core loops —
confirmed no behavior change for a run that never hits the guard.

**What's still open:** only the intra-turn and cross-turn *identical-call*
patterns are covered — a broader state-signature cycle detector (same agent state
reached twice via *different* call sequences) is not built; `duplicate_tool_call`
in `observability/trace_analyzer.py` remains the only post-hoc, aggregate view
across a whole run (how often this fired, which tools).

---

## 11. Checkpoint / resume — built (verified offline; live Postgres unconfirmed)

`agent/memory.py::save_progress` (mid-run trace persistence to `run_log.trace`,
read by `GET /runs/{id}`) is application-level — "what has this run found so
far." It was never LangGraph's own checkpoint mechanism: `fleet.py`'s compiled
graph carried no checkpointer, so the graph itself had no durable, resumable
execution state.

`fleet.py::_build_graph(checkpointer=None)` now takes an optional checkpointer.
`checkpointer=None` (the default) compiles exactly as before — the module-level
`_GRAPH` singleton every normal run uses is unchanged, confirmed by
`tests/test_checkpointing.py` and by the full Ladder 6 suite staying 714/714.
Passed a real checkpointer, the graph gains a checkpoint written after every
superstep, resumable with the same `thread_id` via `graph.astream(None, config)` —
even from a different compiled graph object (a fresh process), because the state
lives in the checkpointer's store, not the Python object.

- **Verified**: `tests/test_checkpointing.py`, fully offline, using LangGraph's own
  `InMemorySaver` — the same `BaseCheckpointSaver` interface `AsyncPostgresSaver`
  implements, so this genuinely exercises `_build_graph`'s checkpoint/resume
  mechanics, not a mock of them. Interrupts a run after 1 superstep, builds a
  *second, independent* graph object against the same checkpointer + `thread_id`,
  and confirms it resumes (not restarts) and completes.
- **Not verified**: `checkpoint_demo.py` (backend root, manual probe — same
  convention as `test_patents.py`/`judge_smoke_test.py`) does the identical proof
  against a real `AsyncPostgresSaver`/`DATABASE_URL`, but `DATABASE_URL` was
  unreachable this session (`docker compose up -d db` was not running). The script
  fails fast and clearly rather than hanging. Run it once Postgres is up:
  `docker compose up -d db && cd backend && python checkpoint_demo.py`.
- Windows needs `asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())`
  before using `AsyncPostgresSaver` — psycopg's async mode cannot run under
  Windows' default `ProactorEventLoop`. `checkpoint_demo.py` sets this itself;
  worth knowing if this ever gets wired into the FastAPI app's own event loop.

**What's still open:** `run_fleet_stream` (the production/SSE path) does not use a
checkpointer at all — this is deliberately scoped to `_build_graph`'s own
capability plus a standalone demo, not yet wired into the live API. Doing so would
mean picking a `thread_id` convention (reusing `run_id`?), deciding when a crash
should actually resume vs. start fresh, and confirming `docker-compose.prod.yml`'s
Postgres is reachable from wherever the checkpointer runs.

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

**Still open from section 1:** every new source (arXiv, OpenAlex, Crossref, Reddit,
Product Hunt, RSS, job boards) and depth levels L2, L4 and L5. `search_patents` now
calls the live USPTO Open Data Portal when `USPTO_ODP_API_KEY` is set (see
"Patent source" below), falling back to `backend/fixtures/patents.json` — unset or
on any live-call failure — same as it always did. Chunk-level embedding (L3) is
item-level today — Q&A retrieves whole findings, not passages.

**Patent source — live, three-tier.** `search_patents` tries, in order
(`_PATENT_LIVE_SOURCES` in `agent/tools.py`):

1. **USPTO Open Data Portal** (`_search_patents_uspto_odp()`) — `GET
   https://api.uspto.gov/api/v1/patent/applications/search` with an `X-Api-Key`
   header. The most structured source (assignee, filing/grant date), but the key
   requires a USPTO.gov account with **MFA identity verification** — friction
   heavy enough that a real key was never obtained to test this session, so while
   the endpoint path and header name are confirmed empirically against the live
   API Gateway (no key → 401 `Unauthorized`; wrong header name → also 401, proving
   it isn't read; `X-Api-Key` with a bad value → 403 `Forbidden`, proving that
   header is read), **the response field-parsing (`inventionTitle`,
   `patentNumber`, `assigneeBag`, under `applicationMetaData`) is best-effort from
   third-party client docs, not verified against a real 200**. Degrades safely
   (falls to the next source, `fallback_used` marks it) on any parse/request
   failure. Whoever gets a key should run `cd backend && python test_patents.py`
   and fix any field-name mismatch.
2. **SerpAPI's Google Patents engine** (`_search_patents_serpapi()`) — the
   recommended easy path: email-only signup, 250 free searches/month, no identity
   verification, and the response schema is publicly documented
   (https://serpapi.com/google-patents-api) without needing an account to view
   it — unlike USPTO's docs. Higher-confidence than the ODP parsing above for
   that reason, though still not exercised against a real key this session (one
   wasn't obtained).
3. **Google Programmable Search restricted to `patents.google.com`**
   (`_search_patents_google_cse()`) — kept as a fallback for anyone who already
   has a *working* `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_CX` pair, but **not
   recommended as something to newly set up**: reproduced directly against a
   fresh Google Cloud project (correct project selected, Custom Search API shown
   "Enabled," billing linked, key correctly scoped) and it consistently returned
   `403 "This project does not have the access to Custom Search JSON API"` —
   Google has stopped granting this specific API to new Cloud projects (per
   multiple independent reports of the same error), not a configuration mistake
   on our side. `search_google` (the general web-search tool) uses the same
   underlying API and has the identical limitation for a new project.

All three unset, or all fail: the curated fixture, same as before any were added.

**Still open from section 2:** MCP in both directions, and publishing to Agent Router.

**Still open from section 8 (evaluation):** CI wiring and actual human ratings —
dataset breadth (53 cases), the `single`-pipeline baseline (every case now scripted
for both pipelines), the LLM-judge layer, and the human-eval sheet/scorer are all
built. See "What's still open" under section 8 above for the full list — the
harness plumbing (fakes, evaluators, runner, report, judge, human_eval) is built
and does not need to change shape to absorb any of these.

**Still open from sections 4, 6 and 7:** the virtualized findings grid, knowledge
graph, brushable timeline, run diff, watchlist, command palette, replay scrubber,
export, cost caps, and extending the circuit breaker (section 7/9) beyond
`search_papers` to the rest of the tools.

**Still open from section 9 (observability closed loop):** see "What's still open"
under section 9 above — the mechanism (trace_analyzer → root_cause → optimizer →
comparison) is built and proven on one scenario; extending it to more finding
categories and more fault scenarios is what's left there (loop/deadlock detection
and checkpoint/resume moved out to their own sections 10-11, both built).

**Still open from sections 10-11:** a broader state-signature loop detector beyond
identical-call blocking (10); wiring a checkpointer into the live `run_fleet_stream`
API path, and confirming `checkpoint_demo.py` against a real, reachable Postgres —
untested this session (11).

## Suggested order from here

1. **Wire the deterministic harnesses into CI.** `python -m evaluation.runner`
   (section 8: 318 runs, 714/714 checks), `python -m evaluation.full_benchmark`
   (section 9), and `tests/` via `python -m unittest discover -s tests` (sections
   8-11's offline suites, 55+ tests) as regression gates on
   `fleet.py`/`orchestrator.py`/`tools.py` changes — all deterministic and
   network-free, so none needs secrets in CI. `python -m evaluation.judge_runner`
   (section 8's LLM-judge tier) would be a separate, opt-in CI job since it needs a
   real API key. Then get actual human ratings on `evaluation/results/
   human_eval_sheet.csv` (section 8) — tooling's ready, nobody's rated it yet.
2. **Confirm checkpoint/resume against a real Postgres (section 11).** Run
   `docker compose up -d db && cd backend && python checkpoint_demo.py` —
   currently only verified offline via `InMemorySaver`
   (`tests/test_checkpointing.py`); this closes the one "not yet executed" gap in
   that section.
3. **Extend the observability closed loop (section 9).** Wire
   `suppress_duplicate_tool_calls`/`research_max_steps_override` into real call
   sites so `duplicate_tool_call`/`replanning_overhead` findings map to enforced
   actions too, not just `unreliable_primary_source`; add 2-3 more
   `fault_injection.py` scenarios (a GitHub 429, a slow tool) so
   `full_benchmark.py` isn't single-scenario.
4. **Verify a live patent source against real data.** Easiest: get a free
   SerpAPI key (email signup, no identity verification —
   https://serpapi.com/users/sign_up) and run `python backend/test_patents.py` —
   the parsing was written against SerpAPI's public docs, not guessed, so this
   should just work. (Don't bother with `GOOGLE_SEARCH_API_KEY`/`CX` for a *new*
   setup — see "Patent source" above, Google no longer grants that API to new
   Cloud projects.) Higher-value but higher-friction: get a USPTO ODP key
   (MFA-gated account) and fix any field-name mismatch `test_patents.py` surfaces
   for the more structured source.
5. Sources and depth: arXiv + OpenAlex, then `fetch_page` (L2) and chunk-level
   embeddings (L3).
6. Entity resolution (L4). Every competitor statistic is approximate until two
   spellings of one company stop counting as two organizations.
7. MCP server and client, and the Agent Router builder publish.
8. The findings grid, knowledge graph and replay scrubber.
