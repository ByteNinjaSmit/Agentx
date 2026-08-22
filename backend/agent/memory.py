import os
import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    return _pool


async def get_known_ids() -> list[str]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT source, external_id FROM seen_items")
    return [f"{r['source']}:{r['external_id']}" for r in rows]


async def save_items(items: list[dict]) -> int:
    pool = await get_pool()
    inserted = 0
    for it in items:
        result = await pool.execute(
            """INSERT INTO seen_items (source, external_id, title, url, summary, impact_score)
               VALUES ($1,$2,$3,$4,$5,$6)
               ON CONFLICT (source, external_id) DO NOTHING""",
            it.get("source", "unknown"),
            it.get("external_id", it.get("url", it.get("title", ""))),
            it.get("title"),
            it.get("url"),
            it.get("summary", ""),
            it.get("impact_1_10", 0),
        )
        if result.endswith("1"):
            inserted += 1
    return inserted


async def log_run(goal: str, trace: list, new_items_count: int):
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO run_log (goal, trace, new_items_count, finished_at)
           VALUES ($1, $2::jsonb, $3, now())""",
        goal,
        __import__("json").dumps(trace, default=str),
        new_items_count,
    )
