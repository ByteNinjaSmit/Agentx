# n8n workflow build — copy-paste reference

Ported from the working Python build (`backend/`). Endpoints/queries below are the
exact ones already verified working this session — don't re-derive them.

## Credentials to add first

**Postgres** (matches `docker-compose.yml`, already running):
- Host: `localhost`
- Port: `5433`
- Database: `compintel`
- User: `compintel`
- Password: `devpass`

**Google Gemini(PaLM) Api**: paste your key in n8n's credential dialog directly —
don't put it in any file in this repo. If the key that got pasted into this chat
earlier is your real one, rotate it at aistudio.google.com first — it's exposed in
this conversation's history.

## 1. Webhook trigger

- Node: **Webhook**
- Method: `POST`
- Path: `compintel-run`
- Response Mode: `Using 'Respond to Webhook' node`
- Expected body: `{"goal": "...", "context": "..."}`

## 2. AI Agent node

- Node: **AI Agent** (Tools Agent)
- Prompt (User Message): `={{ "Goal: " + $json.body.goal + "\nProject context:\n" + $json.body.context }}`
- System Message (paste as-is):

```
You are an autonomous competitive-intelligence agent.
Ground every finding against the user's project context — explain WHY it matters to
this specific project, not generic relevance.

Before searching, always call the "check_known_items" tool first to see what's
already been found in past runs. Do not report those items again — only new signals.

Use the search tools (papers, patents, news, social) as needed. If coverage in a
category looks thin, call it again with a narrower or different query instead of
settling for a weak result. Don't repeat an identical query twice.

Once you have enough evidence, call "save_item" once per new finding to persist it,
then output ONLY a final JSON object (no prose around it, no markdown fences):

{"items": [{"source": "research|patent|news|social", "external_id": "...",
"title": "...", "url": "...", "summary": "...", "relevance_reason": "...",
"date": "YYYY-MM-DD or null"}], "coverage_ok": true}
```

- Options → **Return Intermediate Steps**: ON (this is what gives you the
  Thought/Action trace for the dashboard — the whole point of using the Agent node
  over a fixed chain)

### Sub-node: Google Gemini Chat Model
- Model: `gemini-2.5-flash`
- Credential: the Google Gemini(PaLM) Api one above

## 3. Tool nodes (connect to AI Agent's tool input)

### Tool: search_papers (HTTP Request Tool)
- Tool description: `Search academic research papers relevant to a query. Input: query (string).`
- Method: GET
- URL: `https://api.semanticscholar.org/graph/v1/paper/search`
- Query params: `query={query}`, `limit=5`, `fields=title,abstract,url,year,citationCount,externalIds`

### Tool: search_patents (Code Tool — no live API, avoids USPTO's MFA-gated ODP)
- Tool description: `Search granted US patents relevant to a query. Input: query (string).`
- JS body:
```javascript
const patents = [
  {patent_id:"11847836", patent_title:"Facial recognition system using edge-deployed neural networks", patent_date:"2023-12-19", assignee:"Qualcomm Incorporated"},
  {patent_id:"11783135", patent_title:"Real-time crowd anomaly detection via distributed camera networks", patent_date:"2023-10-10", assignee:"Motorola Solutions Inc"},
  {patent_id:"11710390", patent_title:"Privacy-preserving face recognition using homomorphic encryption", patent_date:"2023-07-25", assignee:"Samsung Electronics Co Ltd"},
  {patent_id:"11636720", patent_title:"Edge AI inference accelerator for low-power surveillance cameras", patent_date:"2023-04-25", assignee:"NVIDIA Corporation"},
  {patent_id:"11594079", patent_title:"Multi-camera person re-identification for public safety systems", patent_date:"2023-02-28", assignee:"Hanwha Techwin Co Ltd"}
];
const q = (query || "").toLowerCase();
const hit = patents.filter(p => JSON.stringify(p).toLowerCase().includes(q));
return JSON.stringify(hit.length ? hit : patents);
```
(same fixture data as `backend/fixtures/patents.json` — keep in sync if you edit one)

### Tool: search_news (HTTP Request Tool — GDELT, no key needed)
- Tool description: `Search recent news and competitor announcements. Input: query (string).`
- Method: GET
- URL: `https://api.gdeltproject.org/api/v2/doc/doc`
- Query params: `query={query}`, `mode=artlist`, `maxrecords=5`, `format=json`

### Tool: search_social (HTTP Request Tool)
- Tool description: `Search Hacker News discussion/sentiment for a topic. Input: query (string).`
- Method: GET
- URL: `https://hn.algolia.com/api/v1/search`
- Query params: `query={query}`, `tags=story`, `hitsPerPage=5`

## 4. Memory tool nodes (Postgres, connected as AI Agent tools)

### Tool: check_known_items (Postgres Tool)
- Tool description: `Call this first, before searching, to see which item IDs are already known from past runs.`
- Query:
```sql
SELECT source, external_id FROM seen_items;
```

### Tool: save_item (Postgres Tool)
- Tool description: `Persist one new finding so future runs don't report it again. Call once per new item found.`
- Query (parameterize source/external_id/title/url/summary/impact_score from the
  tool call args you define on the node):
```sql
INSERT INTO seen_items (source, external_id, title, url, summary, impact_score)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (source, external_id) DO NOTHING;
```

## 5. Scoring (Code node, after AI Agent, before Respond to Webhook)

```javascript
const SOURCE_AUTHORITY = { research: 0.9, patent: 0.8, news: 0.5, social: 0.3 };

function keywordOverlap(text, context) {
  const t = new Set(text.toLowerCase().split(/\s+/));
  const c = new Set(context.toLowerCase().split(/\s+/));
  if (c.size === 0) return 0.5;
  let hits = 0;
  for (const w of c) if (t.has(w)) hits++;
  return Math.min((hits / c.size) * 3, 1.0);
}

function scoreItem(item, projectContext) {
  const authority = SOURCE_AUTHORITY[item.source] ?? 0.4;

  let daysOld = 3;
  if (item.date) {
    const diffMs = Date.now() - new Date(item.date).getTime();
    daysOld = Math.max(Math.floor(diffMs / 86400000), 0);
  }
  const recency = Math.exp(-daysOld / 14);
  const relevance = keywordOverlap((item.summary || "") + " " + (item.title || ""), projectContext);

  return Math.round(10 * (0.3 * authority + 0.25 * recency + 0.3 * relevance + 0.15 * 0.5) * 10) / 10;
}

const parsed = JSON.parse($json.output); // AI Agent's final text output
const context = $('Webhook').item.json.body.context;
parsed.items = parsed.items.map(it => ({ ...it, impact_1_10: scoreItem(it, context) }));
return [{ json: parsed }];
```

## 6. Alert branch

- **IF** node: `{{ $json.items }}` → Split in Batches or a Filter first if you want
  per-item alerts, condition `impact_1_10 >= 8`
- **Slack** node (Webhook credential or OAuth): message
  `*High-impact signal* ({{$json.source}}, {{$json.impact_1_10}}/10)\n{{$json.title}}\n{{$json.url}}\n_{{$json.relevance_reason}}_`

## 7. Respond to Webhook

Return body:
```javascript
{
  "trace": $json.intermediateSteps || [],
  "final": $json
}
```
(`intermediateSteps` comes from the AI Agent node when "Return Intermediate Steps" is
ON — each entry has `.action` (tool name + input) and `.observation` (tool result);
there's no separate free-text "Thought" field like the Anthropic version had, since
Gemini's tool-calling doesn't expose it the same way — the action/observation pairs
are still a real reasoning trace, just render them as "Called X with Y → got Z"
instead of a Thought sentence.)

## Frontend wiring

Set in `frontend/.env.local`:
```
NEXT_PUBLIC_N8N_WEBHOOK_URL=http://localhost:5678/webhook/compintel-run
```
(`TraceView.tsx` already updated to call this — see below.)

## Sanity test once wired

```bash
curl -X POST http://localhost:5678/webhook/compintel-run \
  -H "Content-Type: application/json" \
  -d '{"goal":"find new developments","context":"edge AI face recognition for public safety cameras"}'
```

Run it twice — second run should return fewer/no items in `final.items` (the delta
proof) since `check_known_items` now sees what `save_item` wrote the first time.
