CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS seen_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,              -- 'research' | 'patent' | 'news' | 'social'
    external_id TEXT NOT NULL,         -- paper id / patent number / article url / post id
    title TEXT,
    url TEXT,
    summary TEXT,
    impact_score FLOAT,
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(source, external_id)
);

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
