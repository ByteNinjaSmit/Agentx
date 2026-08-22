# Architecture

AgentX has **two implementations of the agent** sharing one frontend and one
Postgres schema:

- **Python backend** (`backend/`) — FastAPI + Google Gemini. Used for local dev.
  Streams over Server-Sent Events. **A single ReAct loop**: one agent plans, calls
  tools, and writes the final JSON, with `scoring.py` applying the impact formula
  afterwards.
- **n8n workflow** (`n8n/WORKFLOW.md`) — n8n + Google Gemini, used in the deployed
  environment (`docker-compose.prod.yml`). **Two agents with a real handoff**:
  a Research agent gathers, an Analyst agent judges, dedups, and summarizes.

The two are therefore not identical: the Research/Analyst split exists only in n8n.
Bringing the Python path up to a full specialist fleet is Phase 2b of
[ROADMAP.md](ROADMAP.md).

The frontend (`frontend/`) can talk to either — a source toggle in the dashboard
picks which one a run uses (see `frontend/lib/agent-client.ts`).

## Component diagram (both environments)

```mermaid
flowchart TB
    subgraph Client["Browser"]
        UI["Next.js Dashboard<br/>(Dashboard.tsx)"]
    end

    subgraph LocalDev["Local dev path"]
        API["FastAPI backend<br/>main.py :8000<br/>GET /run (SSE)"]
        GeminiB["Google Gemini<br/>(gemini-2.5-flash)"]
        Orchestrator["orchestrator.py<br/>run_agent_stream()<br/>ReAct loop, max 10 steps"]
        API --> Orchestrator
        Orchestrator <--> GeminiB
    end

    subgraph Prod["Production path (VPS, docker-compose.prod.yml)"]
        N8N["n8n workflow<br/>:5678<br/>POST /webhook/compintel-run"]
        Gemini["Google Gemini<br/>(gemini-2.5-flash)"]
        N8N <--> Gemini
    end

    subgraph Tools["Search tools (shared logic, ported)"]
        T1["search_papers<br/>Semantic Scholar"]
        T2["search_patents<br/>fixture data"]
        T3["search_news<br/>NewsAPI / GDELT"]
        T4["search_social<br/>HN Algolia"]
        T5["search_github<br/>GitHub search API"]
        T6["search_google<br/>Programmable Search"]
    end

    subgraph DB["Postgres"]
        Seen["seen_items<br/>dedup memory"]
        Runs["run_log<br/>trace history"]
    end

    Slack["Slack incoming webhook<br/>alerts, impact >= 8"]

    UI -- "mode: backend (EventSource)" --> API
    UI -- "mode: n8n (fetch POST)" --> N8N

    Orchestrator --> Tools
    N8N --> Tools

    Orchestrator <--> Seen
    Orchestrator --> Runs
    N8N <--> Seen

    Orchestrator -- "impact >= 8" --> Slack
    N8N -- "impact >= 8" --> Slack
```

## Request sequence — local backend (SSE)

Events are emitted **as they happen**. `run_agent_stream()` is an async generator and
`main.py` forwards each event straight to the client, so the thought for a step
reaches the browser before its tools have finished running.

```mermaid
sequenceDiagram
    participant U as User
    participant D as Dashboard (React)
    participant B as FastAPI /run
    participant G as Gemini API
    participant T as Search tools
    participant P as Postgres

    U->>D: enter goal + context, click Run
    D->>B: GET /run?goal=...&context=... (EventSource)
    B->>P: get_known_ids()
    B->>P: start_run() -> run_id
    B-->>D: SSE "run_started" {run_id, known_count, model}
    loop up to 10 steps
        B->>G: chat.send_message(history)
        G-->>B: thought text + function_call parts
        B-->>D: SSE "trace" {step, thought, tools_called}
        alt agent still calling tools
            B->>T: run tool calls (parallel, asyncio.gather, each timed)
            T-->>B: results (or a captured error)
            B-->>D: SSE "observation" {step, results[{tool, ok, count, latency_ms, preview, error}]}
            B->>G: function_response parts appended
        else agent has final JSON
            B-->>D: SSE "status" {phase: scoring}
            B->>B: extract_json() -> score_items() (one batched embedding call)
        end
    end
    B-->>D: SSE "status" {phase: saving}
    B->>P: save_items(items, run_id) [dedup on source+external_id, stores embedding]
    opt any item scores >= 8 and SLACK_WEBHOOK_URL is set
        B-->>D: SSE "status" {phase: alerting}
        B->>B: send_alert() per item
    end
    B->>P: finish_run(run_id, trace, final, new_count)
    B-->>D: SSE "final" {run_id, items, coverage_ok, coverage_gaps, executive_summary, new_items_count}
    D-->>U: render ranked brief, sorted by impact desc
```

## Request sequence — n8n webhook (production)

```mermaid
sequenceDiagram
    participant U as User
    participant D as Dashboard (React)
    participant N as n8n Webhook
    participant A as AI Agent node (Gemini)
    participant T as Tool nodes
    participant P as Postgres

    U->>D: enter goal + context, click Run
    D->>N: POST /webhook/compintel-run {goal, context}
    N->>A: run with system prompt + tools
    A->>T: check_known_items (Postgres tool, first)
    T-->>A: known source:external_id list
    loop agent reasoning
        A->>T: search_papers / patents / news / social
        T-->>A: results
        A->>T: save_item per new finding
    end
    A-->>N: final text + intermediateSteps (action/observation pairs)
    N->>N: score node: scoreItem() per item
    N->>N: IF impact_1_10 >= 8 -> Slack node
    N-->>D: 200 {trace: intermediateSteps, final: {items, coverage_ok}}
    D->>D: replay steps with 350ms delay (fakes live feel — n8n returns whole run at once)
    D-->>U: render trace, then ranked brief
```

## Data model

```mermaid
erDiagram
    run_log ||--o{ seen_items : produced
    seen_items {
        uuid id PK
        text source "research | patent | news | social | github | web"
        text external_id "paper id / patent no / url / post id"
        text title
        text url
        text summary
        float impact_score
        timestamptz first_seen_at
        uuid run_id FK "run that first surfaced it"
        date published_at "the item's own date"
        text organization "assignee / repo owner / subject company"
        int engagement "citations | points | stars"
        text relevance_reason
        vector embedding "768-dim, ivfflat cosine index"
    }
    run_log {
        uuid id PK
        text goal
        text context
        jsonb trace "steps with thoughts, tool calls, observations"
        jsonb final
        int new_items_count
        timestamptz started_at
        timestamptz finished_at
    }
```

`seen_items` has a unique constraint on `(source, external_id)` — this is the dedup
mechanism: a repeat run with the same goal only reports items not already in this
table (`ON CONFLICT DO NOTHING` on insert, `get_known_ids()`/`check_known_items`
tool on read).

The row is opened by `start_run()` before the agent begins, so items can reference
their run and the dashboard receives a `run_id` at the start of the stream;
`finish_run()` fills in the trace, final payload, and `finished_at`.

The `embedding` column stores the vector `scoring.py` already computes for relevance
instead of discarding it — that is what the planned Q&A retrieval, related-item
lookup, novelty score, and topic clustering read from. It requires the `vector`
extension, which is why both compose files use the `pgvector/pgvector:pg16` image
rather than plain `postgres:16`.

## Scoring formula

```
score = 10 * (0.30 * source_authority + 0.25 * recency + 0.30 * relevance + 0.15 * velocity)
```

- `source_authority` — fixed per source: research 0.9, patent 0.8, github 0.6,
  news 0.5, web 0.4, social 0.3
- `recency` — `exp(-days_old / 14)`, half-life about 10 days
- `relevance` — **cosine similarity** between the item's embedding and the project
  context's embedding (`gemini-embedding-001`, pinned to 768 dimensions), computed
  in one batched call for the context plus every item
- `velocity` — `log1p(engagement) / log1p(scale)`, capped, where `scale` is the
  per-source count that counts as strong traction (research 50, social 200,
  news 100, patent 10, github 500). Sources with no engagement number score a
  neutral 0.5 rather than a fabricated one.

The Python path runs this in `backend/agent/scoring.py`. The n8n path runs the same
weights inline in its `Score Items` Code node.

## Deployment (production)

```mermaid
flowchart LR
    Push["git push main"] --> CI["GitHub Actions:<br/>build-and-push"]
    CI -- "docker build (frontend/)<br/>bake NEXT_PUBLIC_N8N_WEBHOOK_URL" --> Hub["Docker Hub<br/>byteninjasmit/agentx-frontend"]
    CI --> Deploy["SSH deploy job"]
    Deploy -- "sync secrets into .env<br/>docker compose pull && up -d" --> VPS

    subgraph VPS["VPS (docker-compose.prod.yml)"]
        Nginx["nginx reverse proxy<br/>HTTPS (agentx.twistark.cloud,<br/>agentx.n8n.twistark.cloud)"]
        FE["frontend container :3000"]
        N8Nc["n8n container :5678"]
        PG["postgres container"]
        Nginx --> FE
        Nginx --> N8Nc
        N8Nc --> PG
    end

    Hub -.pulled by.-> FE
```

## Frontend structure

```mermaid
flowchart TB
    Page["app/page.tsx"] --> Dashboard["components/Dashboard.tsx<br/>(state, orchestration)"]
    Dashboard --> RunForm["RunForm.tsx<br/>goal/context inputs, mode toggle"]
    Dashboard --> TraceLog["TraceLog.tsx<br/>live reasoning log"]
    Dashboard --> ResultsList["ResultsList.tsx<br/>ranked findings, source filters"]
    Dashboard --> ThemeToggle["ThemeToggle.tsx"]
    Dashboard --> Client["lib/agent-client.ts<br/>runAgent(mode, goal, context, handlers)"]
    Client -- "mode=backend" --> SSEfn["runBackend()<br/>EventSource"]
    Client -- "mode=n8n" --> Webhookfn["runWebhook()<br/>fetch + AbortController"]
    SSEfn --> Normalize["normalizeBackendStep()<br/>trace event"]
    SSEfn --> Obs["onObservation(step, results)<br/>observation event patches<br/>the step already on screen"]
    Webhookfn --> Normalize2["normalizeN8nStep()"]
    Normalize --> Step["Step (unified type)"]
    Normalize2 --> Step
    Obs --> Step
    Step --> TraceLog
    Dashboard --> HistoryPanel["HistoryPanel.tsx<br/>past runs, replays stored traces"]
    Dashboard --> Legend["Legend.tsx"]
```

`Step` carries two shapes of evidence because the two paths produce different
things: `observations` (backend — one structured record per tool call, with `ok`,
`count`, `latency_ms`, `preview`, `error`) and `observation` (n8n — one opaque
string per step). `TraceLog` renders the structured form as a collapsible
Thought -> Action -> Grounded Observation block and falls back to the string form.
