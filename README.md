# AgentX (CompIntel Agent)

An autonomous competitive-intelligence agent that researches a goal across academic papers, patents, news, and social discussion, scores each finding for relevance/impact against your project context, stores results so future runs only surface new signals, and alerts your team when something high-impact shows up.

## Team Members

- Smitraj Bankar
- Vedhanshu Khajone
- Sai Karpe
- Abhi Auti

## Problem Statement

Teams tracking a competitive space (new research, patents, competitor announcements, community sentiment) have to manually search multiple sources, re-check the same queries over and over, and manually judge whether a finding is actually relevant or urgent. This is slow, repetitive, and easy to miss important signals in.

## Project Description

AgentX runs an LLM-driven agent that, given a **goal** (what to look for) and a **project context** (what you're building/competing on), autonomously:

1. Searches research papers, patents, news, and social/forum discussion using a set of tools.
2. Reasons step-by-step about coverage gaps and refines its queries instead of settling for weak results.
3. De-duplicates against previously seen items (stored in Postgres) so repeat runs only report *new* signals.
4. Scores every finding 1–10 on authority, recency, and relevance to your project context.
5. Sends a Slack alert for any high-impact finding (score ≥ 8).
6. Streams its reasoning trace + final results to a Next.js dashboard in real time (via Server-Sent Events).

There are two implementations of the agent, sharing one frontend and one Postgres schema:

- **Python backend** (`backend/`) — FastAPI, provider-agnostic (Anthropic Claude or Google Gemini, selectable per run). Two pipelines:
  - **`pipeline=fleet`** (default) — a **specialist fleet**: a Planner splits the goal into independent sub-questions, one Researcher per sub-question runs **in parallel**, a **Verifier** discards any finding it cannot trace back to a real tool result, an Analyst judges relevance and normalizes organizations, and a Strategist assigns threat levels and recommended actions.
  - **`pipeline=single`** — the original one-agent ReAct loop, kept as the cheap path and as a baseline to compare the fleet against.
- **n8n workflow** (`n8n/WORKFLOW.md`) — n8n + Google Gemini, used for the deployed/production version (see `docker-compose.prod.yml`). Two agents with a real handoff: a Research agent gathers, an Analyst agent judges, dedups, and summarizes.

The Verifier is deliberately **not** a model: "did this item actually appear in a tool result" is a question code can answer and a model can only guess at, so it is a string match against the raw payloads the Researchers saw. Findings that fail it are dropped and counted, not quietly kept.

## Technologies Used

- **Backend**: Python, FastAPI, `sse-starlette` (streaming), Anthropic Claude (`anthropic`) and Google Gemini (`google-genai`) behind one provider protocol, `asyncpg`, `httpx`
- **Agent framework**: [LangGraph](https://github.com/langchain-ai/langgraph) — the fleet pipeline is a `StateGraph`, not a linear Python function. See "Why LangGraph" in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Frontend**: Next.js 16, React 19, TypeScript, Tailwind CSS, hand-built inline-SVG charts (no charting dependency)
- **Automation / Prod agent**: n8n (AI Agent node + Google Gemini)
- **Database**: PostgreSQL + pgvector (item embeddings)
- **Data sources**: Semantic Scholar API (papers), GDELT / NewsAPI (news), Hacker News Algolia API (social), curated fixture data (patents)
- **Alerts**: Slack incoming webhook
- **Infra / CI-CD**: Docker, Docker Compose, GitHub Actions (build + push image, SSH deploy to VPS), Nginx reverse proxy (HTTPS)

## Features

- Autonomous multi-step agent reasoning (thought → tool calls → refine → final answer)
- Multi-source search: research papers, patents, news, social discussion, GitHub, general web
- Relevance/impact scoring (0–10) combining source authority, recency, **embedding-based semantic relevance**, and engagement velocity
- Persistent memory in Postgres — avoids re-reporting the same item across runs; item embeddings are kept in pgvector for retrieval and analytics
- Slack alerts for high-impact findings (score ≥ 8), on both the Python and n8n paths
- Live streaming trace in the dashboard — thought, tool calls, and a **collapsible grounded observation per tool call** (result count, latency, raw preview, or the exact error), emitted as they happen rather than replayed at the end
- **Agent swimlanes** in the trace: which specialist produced each step, and which parallel researcher lane it belongs to, visualized live as an **agent graph** (Planner → parallel Researchers → Verifier → Analyst → Strategist) driven by the real SSE phase events, not a simulated timeline
- **Autonomous fleet behaviors** (`backend/agent/fleet.py`), each a real, bounded runtime decision rather than a prompt-only instruction:
  - **Dynamic replanning** — after the Analyst step, coverage (fraction of sub-questions with a kept finding) is computed in code; below threshold, one bounded planner call decides whether to open up to two new sub-questions, capped at one round per run
  - **Tool fallback** — `search_papers` recovers on Crossref when Semantic Scholar errors, surfaced as its own "runtime" trace event rather than a silent retry
  - **Evidence conflict resolution** — flags an organization when kept findings from ≥2 source types disagree on impact by more than a threshold spread, then runs one resolver call to explain the disagreement and attach a confidence
  - **Resource-aware execution** — every run tracks tool calls and elapsed time against a budget (60 calls / 180s by default); when coverage is thin and the budget is spent, the fleet says so explicitly and skips the replan
  - **Mid-run checkpointing** — the trace is persisted to Postgres after the research round and again after conflict resolution, not only at the end, so a crashed process still leaves a real, inspectable partial trace
- **Statistics** computed in SQL over everything ever found — competitor share, weekly momentum, impact distribution, per-source reliability (success rate, p95 latency), novelty against impact, and per-run token/latency economics
- **Interactive strategy Q&A** over the corpus: keyword and vector retrieval fused by reciprocal rank, answers carrying clickable `[n]` citations, and a cite-or-refuse instruction so an unsourced answer never gets written
- **Provider comparison** — run the same goal on Claude and on Gemini and diff the findings
- Dockerized production deployment with CI/CD to a VPS behind HTTPS
- **Evaluation harness** (`backend/evaluation/`) — runs the real fleet graph against scripted providers/tools (no network, no DB) across 53 cases in 7 categories (normal/tool-failure/contradictory/incomplete/adversarial/replanning/ambiguous), with 9 deterministic pass/fail checks and a `pipeline=fleet` vs `pipeline=single` baseline comparison; `cd backend && python -m evaluation.runner --pipeline both --repeat 3` (162 runs, 396 checks, 100% pass). See [docs/ROADMAP.md § 8](docs/ROADMAP.md#8-evaluation-ladder-6--built-53-case-dataset) for what's still open (LLM-judge layer, fuller single-pipeline baseline, CI wiring)

## Frontend pages

| Page | Route | What it shows |
|---|---|---|
| Investigate | `/` | Goal input, the Plan → Investigate → Verify → Remember → Adapt pillars, and mission-card shortcuts into common goals |
| Live investigation | `/investigate/new` | The agent graph and full reasoning trace for a run in progress |
| Intelligence report | `/intelligence/[id]` | A finished run's headline finding, executive summary, self-evaluation/conflicts, strategy, and ranked findings, plus grounded Q&A |
| Monitor | `/monitor` | Tracked competitors and recent momentum, built from `GET /stats` — not a separate watchlist store |
| Memory | `/memory` | The full statistics panel — organizations, sources, momentum, novelty, run economics |
| Activity | `/activity` | Past runs (`GET /runs`), expandable to their stored trace and results |
| Agent Runtime | `/settings` | Agent source / pipeline / provider controls, backend health, and a reference of the autonomous behaviors above |

## Installation / Setup

### Prerequisites

- Docker + Docker Compose
- Node.js 20+ (for local frontend dev outside Docker)
- Python 3.11+ (for local backend dev outside Docker)
- A Google Gemini API key (required — it powers the embeddings behind relevance scoring, Q&A retrieval and novelty, on every provider)
- Optionally an Anthropic API key, to run the agent on Claude

### 1. Clone the repo

```bash
git clone <repo-url>
cd Agentx
```

### 2. Configure environment variables

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

Fill in `.env`:

```
GEMINI_API_KEY=<your key>
GEMINI_MODEL=gemini-2.5-flash
ANTHROPIC_API_KEY=    # optional — enables the Claude provider
ANTHROPIC_MODEL=claude-opus-5
AGENT_PROVIDER=gemini # default provider when a run doesn't name one
DATABASE_URL=postgresql://compintel:devpass@localhost:5433/compintel
S2_API_KEY=             # optional — raises the Semantic Scholar rate limit
NEWSAPI_KEY=            # optional
GITHUB_TOKEN=           # optional
SLACK_WEBHOOK_URL=      # optional — enables high-impact alerts
NEXT_PUBLIC_API_URL=http://localhost:8000
```

See `.env.example` for the full list.

### 3. Start Postgres

```bash
docker-compose up -d
```

This starts Postgres (the `pgvector/pgvector:pg16` image, which carries the `vector`
extension) on `localhost:5433` and applies `db/schema.sql` automatically.

`db/schema.sql` only runs on an empty data volume. An existing database is upgraded
in place by the migration in `backend/agent/memory.py`, which runs once when the
connection pool is first opened.

### 4. Run the backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # macOS/Linux
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend health check: `http://localhost:8000/health`

### 5. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## How to Run the Project

1. Ensure Postgres (`docker-compose up -d`) and the backend (`uvicorn main:app --reload --port 8000`) are running.
2. Start the frontend (`npm run dev`) and open `http://localhost:3000`.
3. Trigger a run against the backend directly, or via the dashboard UI:

```bash
# specialist fleet (default), on the default provider
curl -N "http://localhost:8000/run?goal=find+new+developments&context=edge+AI+face+recognition+for+public+safety+cameras"

# the original single loop, explicitly on Claude
curl -N "http://localhost:8000/run?goal=find+new+developments&context=edge+AI&pipeline=single&provider=anthropic"
```

Other endpoints:

| Endpoint | What it gives you |
|---|---|
| `GET /providers` | which providers this deployment has keys for, and the pipelines available |
| `GET /stats` | every statistic at once; `GET /stats/{section}` for one |
| `POST /ask` | `{"question": "...", "run_id": null}` → an answer with `[n]` citations |
| `GET /ask/suggestions` | question starters grounded in what the corpus actually holds |

4. Watch the streamed trace (Thought → tool calls → final scored items) in the dashboard.
5. Run the same goal again — previously-seen items are skipped, so only new signals are reported.

### Optional: n8n / production workflow

For the n8n-based version (used in the deployed environment), follow `n8n/WORKFLOW.md` to rebuild the workflow node-by-node, or deploy via:

```bash
cp .env.prod.example .env.prod
docker-compose -f docker-compose.prod.yml up -d
```

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — architecture diagrams (Mermaid), request sequences, data model, deployment flow.
- [docs/TEST_CASES.md](docs/TEST_CASES.md) — manual test checklist.
- [docs/ROADMAP.md](docs/ROADMAP.md) — depth ladder, planned sources, specialist agent fleet, MCP / Agent Router integration, statistics layer, and the frontend build-out.
