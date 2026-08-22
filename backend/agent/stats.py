"""Aggregate statistics over everything the agent has ever found.

Every number here is computed in SQL from `seen_items` and `run_log` — nothing is
modelled, estimated, or asked of an LLM. Where a signal genuinely is not derivable
from the sources (market size, revenue, headcount), it is absent rather than
invented; see docs/ROADMAP.md on what counts as an honest market signal.
"""

from .memory import get_pool

# Any observation record inside any stored trace, flattened to one row per tool call.
# Guarded on jsonb_typeof so an n8n-shaped trace (which has no "observations" key)
# is skipped rather than raising.
_TOOL_CALLS_CTE = """
WITH calls AS (
    SELECT obs->>'tool'            AS tool,
           (obs->>'ok')::boolean   AS ok,
           (obs->>'latency_ms')::int AS latency_ms,
           r.started_at
    FROM run_log r,
         LATERAL jsonb_array_elements(r.trace) AS step,
         LATERAL jsonb_array_elements(step->'observations') AS obs
    WHERE jsonb_typeof(r.trace) = 'array'
      AND jsonb_typeof(step->'observations') = 'array'
)
"""


async def overview() -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        """SELECT count(*)                                        AS items,
                  count(DISTINCT source)                          AS sources,
                  count(DISTINCT organization)
                      FILTER (WHERE organization <> '')           AS organizations,
                  round(avg(impact_score)::numeric, 2)            AS avg_impact,
                  count(*) FILTER (WHERE impact_score >= 8)       AS high_impact,
                  count(*) FILTER (WHERE first_seen_at > now() - interval '7 days') AS new_this_week
           FROM seen_items"""
    )
    runs = await pool.fetchrow(
        """SELECT count(*)                                   AS runs,
                  count(*) FILTER (WHERE finished_at IS NULL) AS unfinished,
                  round(avg(EXTRACT(EPOCH FROM (finished_at - started_at)))::numeric, 1)
                      AS avg_seconds,
                  coalesce(sum((final->>'input_tokens')::bigint), 0)  AS input_tokens,
                  coalesce(sum((final->>'output_tokens')::bigint), 0) AS output_tokens
           FROM run_log"""
    )
    return {**dict(row), **dict(runs)}


async def by_source() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT source,
                  count(*)                             AS items,
                  round(avg(impact_score)::numeric, 2) AS avg_impact,
                  max(impact_score)                    AS max_impact,
                  round(avg(engagement)::numeric, 1)   AS avg_engagement
           FROM seen_items
           GROUP BY source
           ORDER BY items DESC"""
    )
    return [dict(r) for r in rows]


async def by_organization(limit: int = 20) -> list[dict]:
    """Who keeps showing up. Note that organization is whatever the analyst
    normalized it to — entity resolution (roadmap L4) is not implemented yet, so
    two spellings of one company can still appear as two rows."""
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT organization,
                  count(*)                             AS items,
                  round(avg(impact_score)::numeric, 2) AS avg_impact,
                  max(impact_score)                    AS max_impact,
                  max(first_seen_at)                   AS last_seen,
                  array_agg(DISTINCT source)           AS sources
           FROM seen_items
           WHERE organization IS NOT NULL AND organization <> ''
           GROUP BY organization
           ORDER BY count(*) DESC, avg(impact_score) DESC
           LIMIT $1""",
        limit,
    )
    return [
        {**dict(r), "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None}
        for r in rows
    ]


async def momentum(weeks: int = 12) -> list[dict]:
    """Items per week per source. The slope of this is what "rising / flat /
    declining" means for a topic; the frontend draws it rather than the agent
    asserting a trend it cannot measure."""
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT date_trunc('week', coalesce(published_at::timestamptz, first_seen_at))::date AS week,
                  source,
                  count(*)                             AS items,
                  round(avg(impact_score)::numeric, 2) AS avg_impact
           FROM seen_items
           WHERE coalesce(published_at::timestamptz, first_seen_at) > now() - ($1 || ' weeks')::interval
           GROUP BY 1, 2
           ORDER BY 1""",
        str(weeks),
    )
    return [{**dict(r), "week": r["week"].isoformat()} for r in rows]


async def impact_distribution() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT width_bucket(impact_score, 0, 10, 10) AS bucket,
                  count(*)                              AS items
           FROM seen_items
           WHERE impact_score IS NOT NULL
           GROUP BY 1
           ORDER BY 1"""
    )
    # bucket N covers [N-1, N) on a 0..10 scale with 10 buckets
    return [
        {"from": max(r["bucket"] - 1, 0), "to": min(r["bucket"], 10), "items": r["items"]}
        for r in rows
    ]


async def source_reliability() -> list[dict]:
    """Per-tool success rate and latency, read back out of the stored traces. This
    is the number that tells you whether a "coverage gap" is a one-off or a source
    that is simply always down."""
    pool = await get_pool()
    rows = await pool.fetch(
        _TOOL_CALLS_CTE
        + """SELECT tool,
                    count(*)                                   AS calls,
                    count(*) FILTER (WHERE ok)                 AS ok_calls,
                    round(100.0 * count(*) FILTER (WHERE ok) / nullif(count(*), 0), 1)
                        AS success_rate,
                    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms)::numeric, 0)
                        AS p50_ms,
                    round(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)::numeric, 0)
                        AS p95_ms
             FROM calls
             GROUP BY tool
             ORDER BY calls DESC"""
    )
    return [dict(r) for r in rows]


async def run_economics(limit: int = 20) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT id, goal, started_at, finished_at,
                  final->>'pipeline'                  AS pipeline,
                  final->>'provider'                  AS provider,
                  final->>'model'                     AS model,
                  (final->>'input_tokens')::bigint    AS input_tokens,
                  (final->>'output_tokens')::bigint   AS output_tokens,
                  new_items_count,
                  jsonb_array_length(coalesce(final->'items', '[]'::jsonb))  AS item_count,
                  jsonb_array_length(coalesce(final->'coverage_gaps', '[]'::jsonb)) AS gap_count,
                  round(EXTRACT(EPOCH FROM (finished_at - started_at))::numeric, 1) AS seconds
           FROM run_log
           WHERE final IS NOT NULL
           ORDER BY started_at DESC
           LIMIT $1""",
        limit,
    )
    return [
        {
            **dict(r),
            "id": str(r["id"]),
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
        }
        for r in rows
    ]


async def novelty(limit: int = 10) -> list[dict]:
    """How unlike everything already seen each recent item is: the cosine distance
    to its nearest older neighbour (pgvector's `<=>` is distance, so nearest = the
    minimum). A high score means a genuinely new line of work rather than another
    paper on a topic already tracked. Null when there is nothing older to compare to."""
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT s.id, s.title, s.source, s.organization, s.impact_score, s.first_seen_at,
                  round((
                      SELECT min(s.embedding <=> o.embedding)
                      FROM seen_items o
                      WHERE o.embedding IS NOT NULL
                        AND o.id <> s.id
                        AND o.first_seen_at <= s.first_seen_at
                  )::numeric, 3) AS novelty
           FROM seen_items s
           WHERE s.embedding IS NOT NULL
           ORDER BY s.first_seen_at DESC
           LIMIT $1""",
        limit,
    )
    return [
        {
            **dict(r),
            "id": str(r["id"]),
            "first_seen_at": r["first_seen_at"].isoformat() if r["first_seen_at"] else None,
        }
        for r in rows
    ]


async def all_stats() -> dict:
    return {
        "overview": await overview(),
        "by_source": await by_source(),
        "by_organization": await by_organization(),
        "momentum": await momentum(),
        "impact_distribution": await impact_distribution(),
        "source_reliability": await source_reliability(),
        "run_economics": await run_economics(),
        "novelty": await novelty(),
    }
