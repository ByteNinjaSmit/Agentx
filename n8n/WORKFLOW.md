# n8n workflow build — copy-paste reference

Ported from the working Python build (`backend/`). The live workflow on
`agentx.n8n.twistark.cloud` (workflow ID: `SD57byCMQcMazAvD`) matches this doc.

## Credentials to add first

**Postgres** (`CompIntel Postgres`, credential ID `Q7cvZbqsdC3oQsti`):
- Host: Compose-internal `postgres` (prod) or `localhost:5433` (local dev)
- Database: `compintel`
- User: `compintel`
- Password: from `POSTGRES_PASSWORD` env var (prod) or `devpass` (local dev)

**Google Gemini(PaLM) Api** (`Gemini API`, credential ID `BVQBgfG3auqnY32z`):
Paste your key in n8n's credential dialog directly —
don't put it in any file in this repo.

**Semantic Scholar API key** (eliminates 429 rate limits on the search_papers tool):
- For the Python backend: set `S2_API_KEY` in your `.env` file.
- For the n8n Code Tool node: the key is embedded in the `headers` object of the
  `this.helpers.httpRequest()` call inside the search_papers Code Tool node.
- Free key signup at https://www.semanticscholar.org/product/api#api-key

## 1. Webhook trigger

- Node: **Webhook** (id: `webhook1`)
- Method: `POST`
- Path: `compintel-run`
- Response Mode: `Using 'Respond to Webhook' node`
- Expected body: `{"goal": "...", "context": "..."}`

## 2. AI Agent node

- Node: **AI Agent** (id: `agent1`, Tools Agent, typeVersion 1.7)
- Prompt (User Message): `={{ "Goal: " + $json.body.goal + "\nProject context:\n" + $json.body.context }}`
- System Message (paste as-is):

```
You are an autonomous competitive-intelligence agent.
Ground every finding against the user's project context — explain WHY it matters to
this specific project, not generic relevance.

Before searching, always call the "check_known_items" tool first to see what's
already been found in past runs. Do not report those items again — only new signals.

Use the search tools (papers, patents, news, social) as needed.

COVERAGE RULES — read carefully, this is the most important part of your job:
- A tool call that returns an error (rate limit / 429, timeout, non-2xx status, or an
  observation starting with "HTTP" or "There was an error") means that source is NOT
  covered. A failed call is not the same as a checked source.
- If a source fails, retry that category ONCE with a different tool or a narrower/rephrased
  query before giving up on it. Don't repeat an identical query twice.
- If a source still fails after one retry, do NOT silently move on. Record it explicitly
  in the final JSON's "coverage_gaps" array, e.g. "news: rate-limited after retry".
- Only set "coverage_ok": true when every relevant category either returned usable results
  or has an explicit, honest entry in "coverage_gaps". Never claim full coverage while a
  gap array would be non-empty — that's dishonest and undermines the whole point of this
  reflect step.

Once you have enough evidence, call "save_item" once per new finding to persist it, then
output ONLY a final JSON object (no prose around it, no markdown fences):

{"items": [{"source": "research|patent|news|social", "external_id": "...", "title": "...",
"url": "...", "summary": "...", "relevance_reason": "...", "date": "YYYY-MM-DD or null"}],
"coverage_ok": true, "coverage_gaps": ["news: rate-limited after retry"]}

"coverage_gaps" should be an empty array [] when nothing failed.

"engagement" is a raw traction number pulled from the tool result you already saw for
that item — citationCount for research papers, points for Hacker News / social posts.
If the source type has no such number (patents, news articles), use null. Do not
estimate or invent a number — only report one you actually saw in the tool's output.
Include it in each item as "engagement": 42 (or null).
```

- Options → **Return Intermediate Steps**: ON
- Options → **Max Iterations**: 20

### Sub-node: Google Gemini Chat Model
- Model: `models/gemini-2.5-flash`
- Credential: `Gemini API` (ID `BVQBgfG3auqnY32z`)

## 3. Tool nodes (all Code Tools, connected to AI Agent's tool input)

All four search tools use **n8n Code Tool** nodes (not HTTP Request Tool) because
they need in-workflow caching via `$getWorkflowStaticData('global')`.

### Tool: search_papers (Code Tool, id: `toolpapers`)
- Tool description: `Search academic research papers relevant to a query. Input: query (string).`
- Sends `x-api-key` header with Semantic Scholar API key for authenticated rate limits.
- JS body uses `this.helpers.httpRequest()` to call:
  - URL: `https://api.semanticscholar.org/graph/v1/paper/search`
  - Query params: `query`, `limit=5`, `fields=title,abstract,url,year,citationCount,externalIds`
  - Header: `x-api-key: <S2_API_KEY>`
- Includes 10-minute in-memory cache (staticData).

### Tool: search_patents (Code Tool, id: `toolpatents`)
- Tool description: `Search granted US patents relevant to a query. Input: query (string).`
- Static 5-item fixture (no live API — USPTO ODP requires MFA). Same data as
  `backend/fixtures/patents.json`.

### Tool: search_news (Code Tool, id: `toolnews`)
- Tool description: `Search recent news and competitor announcements. Input: query (string).`
- Tries NewsAPI first (`https://newsapi.org/v2/everything`), falls back to GDELT
  (`https://api.gdeltproject.org/api/v2/doc/doc`) on failure.
- Includes 10-minute in-memory cache.

### Tool: search_social (Code Tool, id: `toolsocial`)
- Tool description: `Search Hacker News discussion/sentiment for a topic. Input: query (string).`
- URL: `https://hn.algolia.com/api/v1/search`
- Includes 10-minute in-memory cache.

## 4. Memory tool nodes (Workflow Tools, connected as AI Agent tools)

### Tool: check_known_items (Workflow Tool, id: `toolcheck`)
- Tool description: `Call this first, before searching, to see which item IDs are already known from past runs.`
- Calls sub-workflow `NDlt8rJCdHDTcRvU` ("CompIntel - Check Known Items") which runs:
```sql
SELECT source, external_id FROM seen_items;
```

### Tool: save_item (Workflow Tool, id: `toolsave`)
- Tool description: `Persist one new finding so future runs don't report it again. Call once per new item found, with source, external_id, title, url, summary, impact_score.`
- Calls sub-workflow `XxaTRbWFErdKkJna` ("CompIntel - Save Item")
- Uses `$fromAI()` expressions for parameters: source, external_id, title, url, summary, impact_score
- Has input schema defined for source, external_id, title, url, summary

## 5. Scoring (Code node `Score Items`, id: `code1`, after AI Agent)

Uses Gemini Embedding API (`gemini-embedding-001`) for semantic relevance scoring
instead of keyword overlap. Computes cosine similarity between project context and
each item's title+summary.

Scoring formula per item:
```
impact_1_10 = 10 × (0.30 × authority + 0.25 × recency + 0.30 × relevance + 0.15 × velocity)
```

Where:
- `authority`: source weight (research=0.9, patent=0.8, news=0.5, social=0.3)
- `recency`: `exp(-daysOld / 14)`
- `relevance`: cosine similarity of Gemini embeddings (context vs item text)
- `velocity`: `log1p(engagement) / log1p(scale)` per source type

Also extracts `intermediateSteps` from the AI Agent node for the trace.

Output shape: `{ trace: [...], final: { items: [...], coverage_ok, coverage_gaps } }`

## 6. Log Run (Postgres node, id: `logrun1`, after Score Items)

Persists every run to `run_log` table:
```sql
INSERT INTO run_log (goal, context, trace, final, new_items_count, finished_at)
VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, now())
```
- `alwaysOutputData`: true
- `onError`: continueRegularOutput (non-blocking — run still returns even if logging fails)

## 7. Respond to Webhook (id: `respond1`)

Returns the scored output from Score Items:
```
={{ $('Score Items').item.json }}
```

Shape:
```json
{
  "trace": [{ "action": "...", "observation": "..." }, ...],
  "final": {
    "items": [{ "source": "...", "title": "...", "impact_1_10": 7.2, ... }],
    "coverage_ok": true,
    "coverage_gaps": []
  }
}
```

## Flow connections

```
Webhook → AI Agent → Score Items → Log Run → Respond to Webhook
                ↑
    ┌───────────┼───────────────────────────┐
    │           │                           │
Gemini    search_papers              check_known_items
Chat      search_news                save_item
Model     search_social
          search_patents
```

## Frontend wiring

Set in `frontend/.env.local`:
```
NEXT_PUBLIC_N8N_WEBHOOK_URL=http://localhost:5678/webhook/compintel-run
```
Production URL (baked at build time via CI):
```
NEXT_PUBLIC_N8N_WEBHOOK_URL=https://agentx.n8n.twistark.cloud/webhook/compintel-run
```

## Sanity test once wired

```bash
curl -X POST https://agentx.n8n.twistark.cloud/webhook/compintel-run \
  -H "Content-Type: application/json" \
  -d '{"goal":"find new developments","context":"edge AI face recognition for public safety cameras"}'
```

Run it twice — second run should return fewer/no items in `final.items` (the delta
proof) since `check_known_items` now sees what `save_item` wrote the first time.
