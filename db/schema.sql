CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- pgvector — provided by the pgvector/pgvector:pg16 image in both compose files.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS run_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal TEXT,
    context TEXT,
    trace JSONB,
    final JSONB,
    new_items_count INT,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS seen_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,              -- 'research' | 'patent' | 'news' | 'social' | 'github' | 'web'
    external_id TEXT NOT NULL,         -- paper id / patent number / article url / post id
    title TEXT,
    url TEXT,
    summary TEXT,
    impact_score FLOAT,
    first_seen_at TIMESTAMPTZ DEFAULT now(),

    -- added for the statistics and Q&A layers: enough per-item structure to
    -- aggregate over time and to retrieve semantically, instead of re-deriving
    -- everything from the run_log JSON blob.
    run_id UUID REFERENCES run_log(id) ON DELETE SET NULL,
    published_at DATE,                 -- the item's own date, not when we saw it
    organization TEXT,                 -- assignee / repo owner / subject company
    engagement INT,                    -- citations | points | stars, source-dependent
    relevance_reason TEXT,
    embedding vector(768),             -- GEMINI_EMBED_DIM, see backend/agent/scoring.py

    UNIQUE(source, external_id)
);

CREATE INDEX IF NOT EXISTS seen_items_run_idx ON seen_items (run_id);
CREATE INDEX IF NOT EXISTS seen_items_org_idx ON seen_items (organization);
CREATE INDEX IF NOT EXISTS seen_items_published_idx ON seen_items (published_at DESC);

-- ivfflat needs rows before its lists are meaningful, and it caps out at 2000
-- dimensions — which is why the embedding is pinned to 768 rather than the
-- gemini-embedding-001 default of 3072.
CREATE INDEX IF NOT EXISTS seen_items_embedding_idx
    ON seen_items USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Lexical half of the Q&A hybrid retrieval (backend/agent/qa.py). Postgres
-- full-text is what catches exact model names and acronyms that an embedding
-- blurs away.
CREATE INDEX IF NOT EXISTS seen_items_fts_idx ON seen_items
    USING gin (to_tsvector('english',
        coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' ||
        coalesce(relevance_reason,'') || ' ' || coalesce(organization,'')));
