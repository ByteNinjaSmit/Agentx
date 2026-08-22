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
| TC-12 | Backend emits a `trace` event with `tools_called: [{name:"search_papers", input:{query:"..."}}]` | New trace line renders: thought text (if present) + a colored `search_papers(...)` badge; badge color is consistent for repeated calls to the same tool |
| TC-13 | n8n mode run completes | Steps from `data.trace` appear one at a time, ~350ms apart (not all at once) — this simulates streaming since n8n returns the whole run in one response |
| TC-14 | Trace grows past the panel's visible height | Panel auto-scrolls to keep the latest step in view |
| TC-15 | Tool call `input` is a long object | Badge label truncates with `…`; full JSON available via the badge's `title` tooltip |
| TC-16 | Screen reader / accessibility check | Trace container has `role="log"` and `aria-live="polite"` — new steps are announced without needing focus |

## Frontend — results

| ID | Steps | Expected |
|----|-------|----------|
| TC-17 | Run completes with `final.items = []` | "no new items — already known" message shown, no source filter chips |
| TC-18 | Run completes with items across 2+ sources | Source filter chips appear (one per distinct source), all active by default; item cards sorted by `impact_1_10` descending |
| TC-19 | Click a source chip to deselect it | Items from that source hide; chip dims; if all chips end up deselected for the visible set, "no items match the selected sources" shows |
| TC-20 | `final.coverage_ok === true` vs `false` | Badge reads "coverage ok" (teal) vs "coverage thin" (amber) accordingly |
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
| TC-29 | `curl "http://localhost:8000/run?goal=find+new+developments&context=edge+AI+face+recognition+for+public+safety+cameras"` | `text/event-stream` response; one or more `event: trace` frames, ending with one `event: final` frame containing valid JSON `{items, coverage_ok}` |
| TC-30 | Call `/run` twice with the same goal/context | Second call's `final.items` excludes IDs returned/persisted by the first (verify against `SELECT * FROM seen_items`) |
| TC-31 | Kill Postgres, then call `/run` | Request fails (500) — `get_pool()`/`asyncpg` raises since `DATABASE_URL` is required with no fallback |
| TC-32 | Search tool APIs unreachable (e.g. no network) | `search_papers`/`search_news`/`search_social` fall back to local fixtures in `backend/fixtures/*.json` instead of raising — run still completes |

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
