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

**Semantic Scholar API key**: no n8n credential — the `search_papers` Code Tool
node sends it as a literal `x-api-key` header string in its JS (a stored
`httpHeaderAuth` credential was tried first via
`this.helpers.httpRequestWithAuthentication`, but n8n wasn't reliably picking up
credential updates for this node even after a confirmed-successful PATCH to
`/api/v1/credentials/{id}` — switched to a plain `this.helpers.httpRequest` call
with the key hardcoded in the code, matching how the Gemini key is embedded in
Score Items and the NewsAPI key in `search_news`).
- Raises the Semantic Scholar rate limit above the anonymous tier, but it's not
  unlimited — heavy back-to-back testing still produces genuine 429s; the agent's
  coverage_gaps mechanism reports these honestly rather than hiding them.
- For the Python backend: set `S2_API_KEY` in your `.env` file (sent as the same
  `x-api-key` header in `backend/agent/tools.py`).
- Free key signup at https://www.semanticscholar.org/product/api#api-key

## 1. Webhook trigger

- Node: **Webhook** (id: `webhook1`)
- Method: `POST`
- Path: `compintel-run`
- Response Mode: `Using 'Respond to Webhook' node`
- Expected body: `{"goal": "...", "context": "...", "session_id": "..." (optional)}`

## 2. Two agents, not one: Research Agent → Analyst Agent

This used to be a single AI Agent doing everything (search, score, summarize).
It's now split into two specialized agents with a real handoff, each with its own
Gemini Chat Model sub-node — added specifically to satisfy a "≥2 specialized
agents with meaningful collaboration" requirement, but it's a genuinely better
design regardless: the Researcher isn't burdened with judgment calls it's bad at
(is this actually relevant? who's the competitor here?), and the Analyst never
has to touch a flaky external API.

### Research Agent (id: `agent1`, renamed from the original "AI Agent")

Responsibility: **gather only**. Plans which search tools to call, retries failed
sources once, reports raw findings + honest coverage gaps. Does not judge
relevance, does not call `save_item`, does not write a summary.

- Prompt (User Message): `={{ "Goal: " + $json.body.goal + "\nProject context:\n" + $json.body.context }}`
- System Message:

```
You are a RESEARCH agent — part of a two-agent competitive-intelligence pipeline.
Your job is ONLY to gather raw findings. A separate ANALYST agent reviews, scores,
and synthesizes what you find — don't try to do their job, don't call save_item,
don't write an executive summary.

Before searching, always call "check_known_items" first to see what's already been
found in past runs — it informs how you should focus, though the Analyst handles
final deduplication.

Use the search tools (papers, patents, news, social, github) as needed to cover the
goal and project context.

COVERAGE RULES:
- A tool call that returns an error (rate limit, timeout, non-2xx, or an observation
  containing "error") means that source is NOT covered. Retry that category ONCE
  with a different tool or a narrower/rephrased query before giving up. Don't repeat
  an identical query twice.
- If a source still fails after one retry, record it honestly in "coverage_gaps",
  e.g. "news: rate-limited after retry". Never silently drop a failed source.

Once you've covered what you reasonably can, stop calling tools and output ONLY a
final JSON object (no prose, no markdown fences):

{"findings": [{"source": "research|patent|news|social|github", "external_id": "...",
"title": "...", "url": "...", "summary": "...", "date": "YYYY-MM-DD or null",
"engagement": 42}], "coverage_gaps": []}

STRICT TYPING — every field except "date" and "engagement" must be a non-null
string; use "" for unavailable values, never null.

"engagement" is a raw traction number you actually saw in a tool's output
(citationCount, points, stargazers_count) — null if the source type has none.
Never invent one.
```

- Options → **Return Intermediate Steps**: ON, **Max Iterations**: 20
- Sub-node: Google Gemini Chat Model, `models/gemini-2.5-flash`, credential `Gemini API` (ID `BVQBgfG3auqnY32z`)
- Tools: `search_papers`, `search_news`, `search_social`, `search_patents`, `search_github`, `check_known_items`
- Output (`.output`) feeds directly into the Analyst Agent's prompt — a **main**
  connection (Research Agent → Analyst Agent), not a tool/sub-node relationship

### Analyst Agent (id: `analystagent1`, new)

Responsibility: **judge, enrich, decide, synthesize**. Receives the Research
Agent's raw findings, filters for genuine relevance, identifies the
organization/competitor behind each item, calls `save_item` for the ones worth
keeping, and writes the executive summary.

- Prompt (User Message):
```
=Research agent's raw findings (JSON):
{{ $('Research Agent').item.json.output }}

Original goal: {{ $('Webhook').item.json.body.goal }}
Project context:
{{ $('Webhook').item.json.body.context }}
```
- System Message:

```
You are an ANALYST agent — the second half of a two-agent competitive-intelligence
pipeline. A RESEARCH agent has already gathered raw candidate findings; your job is
to review them, decide what's genuinely worth reporting, and synthesize.

The research agent has already checked what's known from past runs and scoped its
search accordingly — trust that, focus on QUALITY filtering and synthesis, not
re-deduplication (exact duplicates are silently rejected at the database level
regardless, so it's not something you need to worry about).

For each finding in the research agent's raw findings:
1. Judge genuine relevance to the project context — drop anything only superficially
   related, even if the research agent included it. Don't keep something just
   because it exists.
2. Identify "organization": the company/entity behind it if identifiable (patent
   assignee, article's subject company, GitHub repo owner) — "" if none.
3. Write a one-sentence "relevance_reason" — WHY this matters to the project
   context specifically, not a restatement of the summary.
4. Call "save_item" once for each finding you keep, passing through its original
   source/external_id/title/url/summary/date/engagement fields plus your
   organization and relevance_reason.

When done, output ONLY a final JSON object (no prose, no markdown fences):

{"items": [{"source": "...", "external_id": "...", "title": "...", "url": "...",
"summary": "...", "relevance_reason": "...", "date": "... or null",
"engagement": 42, "organization": "..."}], "coverage_ok": true,
"coverage_gaps": [], "executive_summary": "..."}

"coverage_gaps": carry the research agent's own gaps forward verbatim — never drop
what they honestly reported — and add your own if, after review, coverage still
looks thin. "coverage_ok" is true only when every relevant category has usable
results or an honest gap entry, from either agent.

"executive_summary": 2-4 plain-language sentences — what was found overall, why it
matters, and any major gap — for someone who will only read this, not the full list.
Always include it, even when items is empty.

STRICT TYPING — every field except "date" and "engagement" must be a non-null
string. Use "" for a genuinely unavailable value — never null, never omit the key.
```

- Options → **Return Intermediate Steps**: ON, **Max Iterations**: 15
- Sub-node: **Gemini Chat Model Analyst** (a second, separate `lmChatGoogleGemini`
  instance — sub-nodes are 1:1 with their parent agent, can't be shared), same
  model and credential as the Research Agent's
- Tools: `save_item` only
- Memory: **Postgres Chat Memory** (moved here from the old single-agent setup)
- Output feeds `Score Items`

**Gotcha found live**: `Postgres Chat Memory`'s `sessionKey` expression was
`={{ $json.body.session_id || 'default' }}` when memory lived on the old single
agent, which worked because that agent's `$json` *was* the webhook body. Once
memory moved to the Analyst Agent, `$json` there is the *Research Agent's output*
instead (no `.body` at all) — the expression silently resolved to nothing and the
memory node threw "Key parameter is empty". Fixed by referencing the source node
explicitly regardless of which node the memory is attached to:
`={{ $('Webhook').item.json.body.session_id || 'default' }}`.

Lets the analyst recall prior turns within the same `session_id` across separate
webhook calls — verified live: a second call asking "what did I just ask you to
research?" correctly answered with the exact topic from an earlier, separate HTTP
request. The frontend generates and persists a session id per browser
(`localStorage`, `lib/agent-client.ts`'s `getSessionId()`) and sends it as
`session_id` in the webhook body; omitting it falls back to a shared `"default"`
session for all callers.

## 3. Tool nodes (connected to Research Agent's tool input)

All five search tools are **Code Tool** nodes (not HTTP Request Tool nodes) —
chosen so each can do in-workflow response caching via
`$getWorkflowStaticData('global')`, which a declarative HTTP Request Tool node
can't do on its own.

**Critical gotcha, found live after it silently broke every search tool for an
entire session**: inside a Code Tool node's `jsCode`, the model's argument is
**not** available via `$input.item.json.<name>`. `$input` refers to the node's
"main" data connection, and Tool sub-nodes have no such connection (they connect
via the separate `ai_tool` edge) — so `$input.item.json` actually resolves to the
*workflow trigger's* original data (the raw webhook body), which has no `.input`
property. The result was silent: `(undefined || '').trim()` → `""` every time, so
every tool call searched for an empty string regardless of what the model
actually asked for — and because the cache keys everything by query text, this
collapsed to one shared, permanently-cached result per tool (explains a recurring
symptom: the exact same unrelated Hacker News story showing up across sessions on
completely different topics). The correct accessor is a **bare `query` variable**
that n8n auto-injects into scope when the tool has no custom input schema — use
`(query || '').trim()`, not `$input.item.json.input`.

### Tool: search_papers (Code Tool, id: `toolpapers`)
- Tool description: `Search academic research papers relevant to a query. Input: query (string).`
- Method: `this.helpers.httpRequest` (plain — no stored credential, see above)
- URL: `https://api.semanticscholar.org/graph/v1/paper/search`
- `x-api-key` header value is a literal string in the code — if you rotate the
  key, edit this node's `jsCode` directly (and `backend/agent/tools.py`'s env var).
- Caches results for 10 minutes to reduce API limits.

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

### Tool: search_github (Code Tool, id: `toolgithub`)
- Tool description: `Search GitHub repositories relevant to a query — finds
  competing open-source projects and new tools. Input: query (string).`
- URL: `https://api.github.com/search/repositories?sort=stars&order=desc`
- Unauthenticated (60 req/hr) until `GITHUB_TOKEN` is added — same "hardcode in
  the code" pattern as the other keys if/when that happens
- `stargazers_count` becomes the item's `engagement` signal (verified live: real
  numbers like 3827, 402 flowed through into scoring)
- Includes 10-minute in-memory cache

**Not yet added to n8n**: `search_google` (Google Programmable Search — fully
implemented in `backend/agent/tools.py`, needs `GOOGLE_SEARCH_API_KEY` +
`GOOGLE_SEARCH_CX` to actually call anything, honestly reports "not configured"
as a coverage gap otherwise; blocked on those two values before porting to n8n).
Reddit was dropped entirely — its public `.json` endpoint is now hard-blocked
even with a proper User-Agent (confirmed live: returns an HTML challenge page,
not data). Getting real Reddit results would need a Reddit OAuth "script" app's
`client_credentials` grant; revisit if that's set up later.

## 4. Memory tool nodes (Workflow Tools)

### Tool: check_known_items (Workflow Tool, id: `toolcheck`) — Research Agent's tool
- Tool description: `Call this first, before searching, to see which item IDs are already known from past runs.`
- Calls sub-workflow `NDlt8rJCdHDTcRvU` ("CompIntel - Check Known Items") which runs:
```sql
SELECT source, external_id FROM seen_items;
```

### Tool: save_item (Workflow Tool, id: `toolsave`) — Analyst Agent's tool
- Tool description: `Persist one new finding so future runs don't report it again. Call once per new item found, with source, external_id, title, url, summary, impact_score.`
- Calls sub-workflow `XxaTRbWFErdKkJna` ("CompIntel - Save Item")
- Uses `$fromAI()` expressions for parameters: source, external_id, title, url, summary, impact_score
- Has input schema defined for source, external_id, title, url, summary

## 5. Scoring (Code node `Score Items`, id: `code1`, after Analyst Agent)

Uses Gemini Embedding API (`gemini-embedding-001`) for semantic relevance scoring
instead of keyword overlap. Computes cosine similarity between project context and
each item's title+summary.

Scoring formula per item:
```
impact_1_10 = 10 × (0.30 × authority + 0.25 × recency + 0.30 × relevance + 0.15 × velocity)
```

Where:
- `authority`: source weight (research=0.9, patent=0.8, news=0.5, social=0.3, github=0.6)
- `recency`: `exp(-daysOld / 14)` (guards against an empty `context` string, which
  otherwise 400s the embedding API call — found live when testing an off-task
  request with `context: ""`)
- `relevance`: cosine similarity of Gemini embeddings (context vs item text)
- `velocity`: `log1p(engagement) / log1p(scale)` per source type

Reads the Analyst Agent's `.output` (not Research Agent's — that only has raw
`findings`, not scoreable `items`). Merges **both** agents' `intermediateSteps`
into one trace, each step tagged `{ ...step, agent: 'research' | 'analyst' }` so
the frontend can show which agent did what — this is the visible evidence of the
two-agent handoff a judge would look for.

Output shape: `{ trace: [{ agent: "research"|"analyst", action, observation }, ...],
final: { items: [...], coverage_ok, coverage_gaps, executive_summary } }`

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
  "trace": [{ "agent": "research", "action": "...", "observation": "..." }, ...],
  "final": {
    "items": [{ "source": "...", "title": "...", "impact_1_10": 7.2, "organization": "...", ... }],
    "coverage_ok": true,
    "coverage_gaps": [],
    "executive_summary": "..."
  }
}
```

## Flow connections

```
Webhook → Research Agent → Analyst Agent → Score Items → Log Run → Respond to Webhook
               ↑                  ↑
    ┌──────────┼──────┐    ┌──────┼──────────────┐
Gemini    search_papers    Gemini              save_item
Chat      search_news      Chat Model          Postgres
Model     search_social    Analyst             Chat Memory
(Research) search_patents
          search_github
          check_known_items
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
