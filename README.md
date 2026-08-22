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

- **Python backend** (`backend/`) — FastAPI + Google Gemini, used for local dev. A **single ReAct loop**: one agent plans, calls tools, and writes the final JSON; `scoring.py` applies the impact formula afterwards.
- **n8n workflow** (`n8n/WORKFLOW.md`) — n8n + Google Gemini, used for the deployed/production version (see `docker-compose.prod.yml`). **Two agents with a real handoff**: a Research agent gathers, an Analyst agent judges, dedups, and summarizes.

They are not identical — the Research/Analyst split exists only in n8n today. Bringing the Python path up to a full specialist fleet is Phase 2 of [docs/ROADMAP.md](docs/ROADMAP.md).

## Technologies Used

- **Backend**: Python, FastAPI, `sse-starlette` (streaming), Google Gemini API (`google-genai`), `asyncpg`, `httpx`
- **Frontend**: Next.js 16, React 19, TypeScript, Tailwind CSS
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
- Dockerized production deployment with CI/CD to a VPS behind HTTPS

## Installation / Setup

### Prerequisites

- Docker + Docker Compose
- Node.js 20+ (for local frontend dev outside Docker)
- Python 3.11+ (for local backend dev outside Docker)
- A Google Gemini API key (for the Python backend agent and the embedding-based scorer)

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
curl "http://localhost:8000/run?goal=find+new+developments&context=edge+AI+face+recognition+for+public+safety+cameras"
```

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
