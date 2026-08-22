import json
import os
import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
        await _migrate(_pool)
    return _pool


async def _migrate(pool: asyncpg.Pool):
    # self-healing schema bump — safe to run against a DB created before
    # these columns existed, and a no-op on a fresh one (schema.sql already has them)
    await pool.execute("ALTER TABLE run_log ADD COLUMN IF NOT EXISTS context TEXT")
    await pool.execute("ALTER TABLE run_log ADD COLUMN IF NOT EXISTS final JSONB")


async def get_known_ids() -> list[str]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT source, external_id FROM seen_items")
    return [f"{r['source']}:{r['external_id']}" for r in rows]


async def save_items(items: list[dict]) -> int:
    pool = await get_pool()
    inserted = 0
    for it in items:
        external_id = it.get("external_id") or it.get("url") or it.get("title") or ""
        result = await pool.execute(
            """INSERT INTO seen_items (source, external_id, title, url, summary, impact_score)
               VALUES ($1,$2,$3,$4,$5,$6)
               ON CONFLICT (source, external_id) DO NOTHING""",
            it.get("source") or "unknown",
            external_id,
            it.get("title"),
            it.get("url"),
            it.get("summary", ""),
            it.get("impact_1_10", 0),
        )
        if result.endswith("1"):
            inserted += 1
    return inserted


async def log_run(goal: str, context: str, trace: list, final: dict, new_items_count: int):
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO run_log (goal, context, trace, final, new_items_count, finished_at)
           VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, now())""",
        goal,
        context,
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
           FROM run_log WHERE id = $1""",
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
