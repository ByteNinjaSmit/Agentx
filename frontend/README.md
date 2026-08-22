# AgentX frontend

Next.js 16 (App Router) + React 19 + TypeScript + Tailwind CSS. Talks to the Python
backend (`../backend`, SSE) or the n8n webhook (`../n8n/WORKFLOW.md`) — see the root
[README](../README.md) and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for how
the two agent implementations plug into this UI.

## Pages

| Route | Page |
|---|---|
| `/` | Investigate — goal input, pillar story, mission-card shortcuts |
| `/investigate/new` | A run in progress — `AgentGraph` (live agent status) + full trace |
| `/intelligence/[id]` | A finished run's report — headline finding, self-evaluation, strategy, findings, Q&A |
| `/monitor` | Tracked competitors and recent momentum |
| `/memory` | Full statistics (`StatsPanel`) |
| `/activity` | Past runs (`HistoryPanel`) |
| `/settings` | Agent Runtime — source/pipeline/provider controls, backend health, behavior reference |
| `/about` | Static product description |

Nothing on these pages is mocked: every number comes from the backend's `/run` SSE
stream, `/stats`, `/runs`, or `/ask`. If a page has nothing to show, it says so rather
than inventing content.

## Development

```bash
npm install
npm run dev      # http://localhost:3000
npm run build    # production build + typecheck
npm run lint     # eslint
```

## Environment (`.env.local`)

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_N8N_WEBHOOK_URL=http://localhost:5678/webhook/compintel-run
```

`lib/agent-client.ts` falls back to `mode: "n8n"` when `NEXT_PUBLIC_API_URL` is unset,
and to `http://localhost:8000` / the local n8n webhook otherwise. The chosen agent
source, pipeline, and provider are saved to `localStorage` (`lib/run-settings.ts`) on
`/settings` and read everywhere else — there is no separate per-page config.

## Notes

- `AGENTS.md` documents this checkout's non-stock Next.js conventions; read it (and
  `node_modules/next/dist/docs/`) before assuming a standard App Router API.
- `components/charts/Charts.tsx` is hand-built inline SVG, not a charting library —
  see `docs/ARCHITECTURE.md` for why.
- Dark mode is intentionally not wired up in the current visual direction
  (`app/layout.tsx` force-locks `data-theme="light"`).
