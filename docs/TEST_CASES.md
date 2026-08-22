# Test cases

Manual test cases for the dashboard (`frontend/`) and the two agent backends.
No automated test suite exists yet — this is the checklist to run by hand after a
change. IDs are stable references for bug reports / PR descriptions.

## Setup

```bash
docker-compose up -d                 # postgres on :5433
cd backend && uvicorn main:app --reload --port 8000
cd frontend && npm run dev           # http://localhost:3000
```

Optional, for n8n-mode tests: follow `n8n/WORKFLOW.md`, workflow active on `:5678`.

---

## Frontend — form & validation

| ID | Steps | Expected |
|----|-------|----------|
| TC-01 | Load dashboard fresh (no prior run) | Goal field pre-filled with default prompt, context empty, Run button enabled (goal non-empty), no trace/results panels shown |
| TC-02 | Clear the Goal field entirely | Run button becomes disabled |
| TC-03 | Type in Goal, focus Context textarea, press `Ctrl+Enter` (`Cmd+Enter` on Mac) | Run starts, same as clicking "Run agent" |
| TC-04 | Click "Run agent" while `running` | Button swaps to red "Stop"; Goal/Context/mode toggle become disabled; pulsing "running" indicator shows next to the button |
| TC-05 | Click "Stop" mid-run | Stream/fetch is cancelled (`EventSource.close()` or `AbortController.abort()`), `running` clears, no further steps or final result appear even if the backend keeps producing them |

## Frontend — source mode toggle

| ID | Steps | Expected |
|----|-------|----------|
| TC-06 | Fresh load, no `NEXT_PUBLIC_API_URL` set at build time | Mode defaults to `n8n` |
| TC-07 | Fresh load, `NEXT_PUBLIC_API_URL` set | Mode defaults to `backend` |
| TC-08 | Switch mode toggle, reload page | Chosen mode persists (read from `localStorage["agentx-mode"]`) |
| TC-09 | Select "Local backend (SSE)", run with backend **not** running on `:8000` | Error banner: `Could not reach agent backend at http://localhost:8000. Is it running?`; `running` clears |
| TC-10 | Select "n8n webhook", run with n8n workflow inactive | Error banner: `Could not reach n8n webhook at .... Is the workflow active? (...)`; `running` clears |

## Frontend — reasoning trace

| ID | Steps | Expected |
|----|-------|----------|
| TC-11 | Start a run (backend mode) | Trace panel appears immediately with "waiting for first thought" + blinking cursor before the first SSE `trace` event arrives |
| TC-11a | Watch a backend run with slow tools (e.g. no S2 key, several sources) | The thought and its tool badges appear **before** the tools finish; a "calling search_papers, search_news…" line shows underneath until the `observation` event lands. If every step only appears after the whole run finishes, streaming has regressed |
| TC-12 | Backend emits a `trace` event with `tools_called: [{name:"search_papers", input:{query:"..."}}]` | New trace line renders: thought text (if present) + a colored `search_papers(...)` badge; badge color is consistent for repeated calls to the same tool |
| TC-13 | n8n mode run completes | Steps from `data.trace` appear one at a time, ~350ms apart (not all at once) — this simulates streaming since n8n returns the whole run in one response |
| TC-14 | Trace grows past the panel's visible height | Panel auto-scrolls to keep the latest step in view |
| TC-15 | Tool call `input` is a long object | Badge label truncates with `…`; full JSON available via the badge's `title` tooltip |
| TC-16 | Screen reader / accessibility check | Trace container has `role="log"` and `aria-live="polite"` — new steps are announced without needing focus |
| TC-16a | Backend run, after a step's tools return | One collapsible observation row per tool call: `↳ tool "query"`, result count and latency on the right. Expanding it shows the pretty-printed result preview |
| TC-16b | Force a tool failure (unset network, or hammer Semantic Scholar until it 429s) | That observation row renders red with `✕`, shows the exact error text (e.g. `HTTPStatusError: ... 429`), and the step's left border turns red. The run continues — one dead source must not end the run |
| TC-16c | Open a past backend run under History | The stored trace replays with the same collapsible observations, not just the thoughts and tool badges |

## Frontend — results

| ID | Steps | Expected |
|----|-------|----------|
| TC-17 | Run completes with `final.items = []` | "no new items — already known" message shown, no source filter chips |
| TC-18 | Run completes with items across 2+ sources | Source filter chips appear (one per distinct source), all active by default; item cards sorted by `impact_1_10` descending |
| TC-19 | Click a source chip to deselect it | Items from that source hide; chip dims; if all chips end up deselected for the visible set, "no items match the selected sources" shows |
| TC-20 | `final.coverage_ok === true` vs `false` | Badge reads "coverage ok" (teal) vs "coverage thin" (amber) accordingly |
| TC-20a | Backend run where a source failed after a retry | The amber "Coverage gaps" panel lists the gap (e.g. `news: rate-limited after retry`) **in backend mode as well as n8n mode** — the backend used to drop this field on the way to the UI |
| TC-20b | Any completed backend run | The "Executive summary" panel renders above the item list, and an `N new` chip (plus `· M alerted` when Slack fired) sits next to the coverage badge |
| TC-21 | Item with `impact_1_10 >= 8` | Impact badge renders in the high-impact (red-tinted) color band; `5–7.9` amber; `<5` neutral |
| TC-22 | Click an item's title | Opens `item.url` in a new tab (`target="_blank"`, `rel="noreferrer"`) |
| TC-23 | Run the same goal twice in a row (backend or n8n, DB has memory) | Second run's `final.items` is smaller or empty — proves `seen_items` dedup is working end to end |

## Frontend — theme & responsive

| ID | Steps | Expected |
|----|-------|----------|
| TC-24 | First visit, OS set to dark mode | Page renders dark with no flash of light theme on load |
| TC-25 | Click theme toggle | Instantly flips light/dark; persists across reload via `localStorage["agentx-theme"]` |
| TC-26 | Resize viewport to mobile width (<1024px) | Layout stacks to a single column (form above trace/results) instead of the two-column grid |
| TC-27 | Resize to a wide desktop viewport | Content stays capped at the readable `max-w-5xl` container, doesn't stretch edge-to-edge |

## Backend — FastAPI (`backend/`)

| ID | Steps | Expected |
|----|-------|----------|
| TC-28 | `curl http://localhost:8000/health` | `{"status": "ok"}`, HTTP 200 |
| TC-29 | `curl -N "http://localhost:8000/run?goal=find+new+developments&context=edge+AI+face+recognition+for+public+safety+cameras"` | `text/event-stream`; frames arrive progressively in the order `run_started` → (`trace` → `observation`)* → `status` → `final`. `run_started` carries `run_id`, `known_count`, `model`; `final` carries `items`, `coverage_ok`, `coverage_gaps`, `executive_summary`, `new_items_count`, `alerted_count` |
| TC-29a | Watch the timestamps of the frames from TC-29 | The first `trace` frame arrives well before the run ends. If everything arrives in one burst at the end, `run_agent_stream` is being drained before the response starts |
| TC-30 | Call `/run` twice with the same goal/context | Second call's `final.items` excludes IDs returned/persisted by the first (verify against `SELECT * FROM seen_items`) |
| TC-31 | Kill Postgres, then call `/run` | Request fails (500) — `get_pool()`/`asyncpg` raises since `DATABASE_URL` is required with no fallback |
| TC-32 | Search tool APIs unreachable (e.g. no network) | Each failing call is captured as an observation with `ok: false` and the exception text — the run still completes, and the agent is instructed to retry once and then record the failure in `coverage_gaps`. Only `search_patents` reads from `backend/fixtures/` (its disclosed primary source); the live tools do **not** silently fall back to fixture data |
| TC-32a | Set `SLACK_WEBHOOK_URL`, run a goal that produces an item scoring ≥ 8 | A Slack message is posted per high-impact item, and `final.alerted_count` matches the number sent. With the variable unset, no alert is attempted and `alerted_count` is 0 |
| TC-32b | `SELECT run_id, published_at, organization, engagement, embedding IS NOT NULL FROM seen_items ORDER BY first_seen_at DESC LIMIT 5;` after a run | All five populated for newly-inserted rows — `run_id` matching the run, and a non-null 768-dim embedding |
| TC-32c | Point `DATABASE_URL` at a database created before this change (existing volume, old schema) | The first request runs `_migrate()`: the `vector` extension and the new `seen_items` columns are added in place, and the run succeeds without a manual migration |

## n8n workflow (production path)

| ID | Steps | Expected |
|----|-------|----------|
| TC-33 | `curl -X POST http://localhost:5678/webhook/compintel-run -H "Content-Type: application/json" -d '{"goal":"find new developments","context":"edge AI face recognition for public safety cameras"}'` | HTTP 200, JSON body `{trace: [...], final: {items, coverage_ok}}` |
| TC-34 | Run TC-33 twice | Second run returns fewer/no items — `check_known_items` tool sees rows `save_item` wrote on the first run |
| TC-35 | Inspect `trace` entries from TC-33 | Each entry has `action.tool`, `action.toolInput`, `observation`; `action.log` may be absent (Gemini doesn't expose free-text thought the way Claude does) — dashboard must still render the tool badge and observation without it |
| TC-36 | An item scores `impact_1_10 >= 8` | Slack message posted to the configured webhook: `*High-impact signal* (<source>, <score>/10)` + title/url/reason |

## Regression checklist (run before merging any frontend change)

- [ ] `npx tsc --noEmit` — no type errors
- [ ] `npm run lint` — no eslint errors
- [ ] `npm run build` — production build succeeds
- [ ] TC-01, TC-04, TC-05 (basic run/stop lifecycle)
- [ ] TC-09, TC-10 (both error paths surface a readable message)
- [ ] TC-17–TC-19 (empty/filtered results states)
- [ ] TC-24–TC-26 (theme + responsive)
