import json
import os
from datetime import date, datetime

import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
        await _migrate(_pool)
    return _pool


async def _migrate(pool: asyncpg.Pool):
    # self-healing schema bump — safe to run against a DB created before these
    # columns existed, and a no-op on a fresh one (schema.sql already has them).
    # schema.sql only runs on an empty data volume, so every column added there
    # has to be repeated here or existing deployments never get it.
    await pool.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await pool.execute("ALTER TABLE run_log ADD COLUMN IF NOT EXISTS context TEXT")
    await pool.execute("ALTER TABLE run_log ADD COLUMN IF NOT EXISTS final JSONB")
    for column, ddl in (
        ("run_id", "UUID REFERENCES run_log(id) ON DELETE SET NULL"),
        ("published_at", "DATE"),
        ("organization", "TEXT"),
        ("engagement", "INT"),
        ("relevance_reason", "TEXT"),
        ("competitor", "TEXT"),
        ("embedding", "vector(768)"),
    ):
        await pool.execute(f"ALTER TABLE seen_items ADD COLUMN IF NOT EXISTS {column} {ddl}")
    await pool.execute("CREATE INDEX IF NOT EXISTS seen_items_run_idx ON seen_items (run_id)")
    await pool.execute("CREATE INDEX IF NOT EXISTS seen_items_org_idx ON seen_items (organization)")
    await pool.execute(
        "CREATE INDEX IF NOT EXISTS seen_items_competitor_idx ON seen_items (competitor)"
    )
    await pool.execute(
        "CREATE INDEX IF NOT EXISTS seen_items_published_idx ON seen_items (published_at DESC)"
    )
    await pool.execute(
        """CREATE INDEX IF NOT EXISTS seen_items_embedding_idx
           ON seen_items USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"""
    )
    await pool.execute(
        """CREATE INDEX IF NOT EXISTS seen_items_fts_idx ON seen_items
           USING gin (to_tsvector('english',
               coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' ||
               coalesce(relevance_reason,'') || ' ' || coalesce(organization,'')))"""
    )


def _as_date(value) -> date | None:
    """The agent is asked for YYYY-MM-DD but sources hand it all sorts of things —
    full ISO timestamps, empty strings, bare years. Parse what's parseable, drop
    the rest rather than failing the whole insert."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _as_int(value) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _as_vector(value) -> str | None:
    """pgvector's text input format. asyncpg has no native codec for `vector`, so
    the value is sent as a string and cast in SQL."""
    if not value:
        return None
    return "[" + ",".join(f"{float(x):.6f}" for x in value) + "]"


async def get_known_ids() -> list[str]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT source, external_id FROM seen_items")
    return [f"{r['source']}:{r['external_id']}" for r in rows]


async def save_items(items: list[dict], run_id: str | None = None) -> int:
    pool = await get_pool()
    inserted = 0
    for it in items:
        external_id = it.get("external_id") or it.get("url") or it.get("title") or ""
        result = await pool.execute(
            """INSERT INTO seen_items (source, external_id, title, url, summary, impact_score,
                                       run_id, published_at, organization, engagement,
                                       relevance_reason, competitor, embedding)
               VALUES ($1,$2,$3,$4,$5,$6,$7::uuid,$8,$9,$10,$11,$12,$13::vector)
               ON CONFLICT (source, external_id) DO NOTHING""",
            it.get("source") or "unknown",
            external_id,
            it.get("title"),
            it.get("url"),
            it.get("summary", ""),
            it.get("impact_1_10", 0),
            run_id,
            _as_date(it.get("date")),
            it.get("organization") or None,
            _as_int(it.get("engagement")),
            it.get("relevance_reason"),
            it.get("competitor") or None,
            _as_vector(it.get("_embedding")),
        )
        if result.endswith("1"):
            inserted += 1
    return inserted


async def start_run(goal: str, context: str) -> str:
    """Opens the run row up front so items can reference it and the frontend gets a
    run id at the start of the stream instead of only at the end."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "INSERT INTO run_log (goal, context) VALUES ($1, $2) RETURNING id", goal, context
    )
    return str(row["id"])


async def save_progress(run_id: str, trace: list) -> None:
    """Persists the trace so far without marking the run finished. If the process
    dies mid-run, GET /runs/{id} still shows real progress — which phase it
    reached, what each researcher had found — instead of nothing at all. Cheap:
    the same `trace` column finish_run writes, just written earlier and more
    than once over the run's life."""
    pool = await get_pool()
    await pool.execute(
        "UPDATE run_log SET trace = $2::jsonb WHERE id = $1::uuid",
        run_id,
        json.dumps(trace, default=str),
    )


async def finish_run(run_id: str, trace: list, final: dict, new_items_count: int):
    pool = await get_pool()
    await pool.execute(
        """UPDATE run_log
           SET trace = $2::jsonb, final = $3::jsonb, new_items_count = $4, finished_at = now()
           WHERE id = $1::uuid""",
        run_id,
        json.dumps(trace, default=str),
        json.dumps(final, default=str),
        new_items_count,
    )


async def list_runs(limit: int = 30) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT id, goal, context, final, new_items_count, started_at, finished_at
           FROM run_log ORDER BY started_at DESC LIMIT $1""",
        limit,
    )
    out = []
    for r in rows:
        final = json.loads(r["final"]) if r["final"] else {}
        out.append(
            {
                "id": str(r["id"]),
                "goal": r["goal"],
                "context": r["context"],
                "coverage_ok": final.get("coverage_ok", False),
                "coverage_gaps": final.get("coverage_gaps", []),
                "item_count": len(final.get("items", [])),
                "new_items_count": r["new_items_count"],
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
            }
        )
    return out


async def get_run(run_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """SELECT id, goal, context, trace, final, new_items_count, started_at, finished_at
           FROM run_log WHERE id = $1::uuid""",
        run_id,
    )
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "goal": row["goal"],
        "context": row["context"],
        "trace": json.loads(row["trace"]) if row["trace"] else [],
        "final": json.loads(row["final"]) if row["final"] else {"items": [], "coverage_ok": False},
        "new_items_count": row["new_items_count"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
    }
