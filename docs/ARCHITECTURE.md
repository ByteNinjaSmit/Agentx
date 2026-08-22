# Architecture

AgentX has **two parallel implementations of the same agent** sharing one frontend
and one Postgres schema:

- **Python backend** (`backend/`) — FastAPI + Anthropic Claude. Used for local dev.
  Streams via Server-Sent Events (SSE).
- **n8n workflow** (`n8n/WORKFLOW.md`) — same logic rebuilt visually with n8n +
  Google Gemini. Used in the deployed/production environment
  (`docker-compose.prod.yml`).

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
        Claude["Anthropic Claude API<br/>(claude-sonnet-4-6)"]
        Orchestrator["orchestrator.py<br/>ReAct loop, max 6 steps"]
        API --> Orchestrator
        Orchestrator <--> Claude
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

    Orchestrator -.alert not wired in Python backend.-> Slack
    N8N -- "impact >= 8" --> Slack
```

## Request sequence — local backend (SSE)

```mermaid
sequenceDiagram
    participant U as User
    participant D as Dashboard (React)
    participant B as FastAPI /run
    participant C as Claude API
    participant T as Search tools
    participant P as Postgres

    U->>D: enter goal + context, click Run
    D->>B: GET /run?goal=...&context=... (EventSource)
    B->>P: get_known_ids()
    loop up to 6 steps
        B->>C: messages.create(tools, history)
        C-->>B: thought text + tool_use calls
        B-->>D: SSE event "trace" {thought, tools_called}
        alt agent still calling tools
            B->>T: run tool calls (parallel, asyncio.gather)
            T-->>B: results
            B->>C: tool_result appended to messages
        else agent has final JSON
            B->>B: extract_json(thought) -> {items, coverage_ok}
            B->>B: score_item() per item
        end
    end
    B->>P: save_items(final.items) [dedup on source+external_id]
    B->>P: log_run(goal, trace, new_count)
    B-->>D: SSE event "final" {items, coverage_ok}
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
    seen_items {
        uuid id PK
        text source "research | patent | news | social"
        text external_id "paper id / patent no / url / post id"
        text title
        text url
        text summary
        float impact_score
        timestamptz first_seen_at
    }
    run_log {
        uuid id PK
        text goal
        jsonb trace
        int new_items_count
        timestamptz started_at
        timestamptz finished_at
    }
```

`seen_items` has a unique constraint on `(source, external_id)` — this is the dedup
mechanism: a repeat run with the same goal only reports items not already in this
table (`ON CONFLICT DO NOTHING` on insert, `get_known_ids()`/`check_known_items`
tool on read).

## Scoring formula

Both implementations run the identical weighted formula (Python: `scoring.py`,
n8n: inline Code node):

```
score = 10 * (0.30 * source_authority + 0.25 * recency + 0.30 * keyword_relevance + 0.15 * 0.5)
```

- `source_authority`: fixed per source — research 0.9, patent 0.8, news 0.5, social 0.3
- `recency`: `exp(-days_old / 14)` — exponential decay, half-life ~10 days
- `keyword_relevance`: overlap between item text and project context word sets

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
    SSEfn --> Normalize["normalizeBackendStep()"]
    Webhookfn --> Normalize2["normalizeN8nStep()"]
    Normalize --> Step["Step (unified type)"]
    Normalize2 --> Step
    Step --> TraceLog
```
