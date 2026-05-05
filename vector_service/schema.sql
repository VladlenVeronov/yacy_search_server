-- YACY semantic-search vector store
-- Database: yacy_pages
--
-- Holds a per-document embedding for the pages YaCy has crawled, mirroring
-- a subset of fields from YaCy's Solr collection so the vector layer can
-- score independently and be JOINed back to Solr by `id`.
--
-- IMPORTANT: this is a SEPARATE database from `yacy_vectors` (which stores
-- embeddings of YaCy's *source code* for the dev tool). Don't conflate them.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS pages (
    id              text PRIMARY KEY,           -- YaCy doc id (URL hash; == Solr `id`)
    url             text NOT NULL,
    host            text,
    title           text,
    -- Truncated visible-text content used for embedding generation.
    -- Caps at config.max_summary_chars to keep embedding latency bounded.
    summary         text,
    -- sha256 of the embedded `summary`. Lets /index skip re-embedding when
    -- a page's content hasn't changed.
    content_hash    text,
    last_modified   timestamptz,
    lang            text,
    embedding       vector(768),                -- intfloat/multilingual-e5-base
    indexed_at      timestamptz NOT NULL DEFAULT now(),
    embedded_at     timestamptz
);

CREATE INDEX IF NOT EXISTS pages_host_idx          ON pages (host);
CREATE INDEX IF NOT EXISTS pages_last_modified_idx ON pages (last_modified DESC NULLS LAST);

-- HNSW for cosine similarity. Empty table is fine — pgvector builds lazily.
CREATE INDEX IF NOT EXISTS pages_embedding_hnsw_idx
    ON pages USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Query log: every search the public UI performs. Used for autocomplete and
-- to detect "unsatisfied" queries (zero results or zero clicks) so the
-- crawler can be steered toward gaps in the index.
CREATE TABLE IF NOT EXISTS query_logs (
    id              bigserial PRIMARY KEY,
    query           text NOT NULL,
    result_count    int  NOT NULL DEFAULT 0,
    clicked_count   int  NOT NULL DEFAULT 0,
    ts              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS query_logs_query_idx ON query_logs (lower(query));
CREATE INDEX IF NOT EXISTS query_logs_ts_idx    ON query_logs (ts DESC);

-- Per-result click events. One row per click.
CREATE TABLE IF NOT EXISTS query_clicks (
    id          bigserial PRIMARY KEY,
    query       text NOT NULL,
    doc_id      text,
    url         text,
    position    int,
    ts          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS query_clicks_query_idx ON query_clicks (lower(query));
CREATE INDEX IF NOT EXISTS query_clicks_ts_idx    ON query_clicks (ts DESC);

-- Services menu: rendered in the public drawer (right-side bottomsheet).
-- Managed via vector_service /admin/services* behind a Bearer ADMIN_TOKEN.
-- Icon is a URL (favicon, CDN-free hosted asset, etc.).
CREATE TABLE IF NOT EXISTS services_menu (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,
    url         text NOT NULL,
    icon_url    text,
    sort_order  int  NOT NULL DEFAULT 0,
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS services_menu_sort_idx ON services_menu (sort_order, id);

-- Cabinet/OIDC tables removed in Phase 1 (custom user cabinet replaced by
-- native YaCy UserDB). Drop legacy tables on existing deployments — these
-- statements are no-ops on fresh installs.
DROP TABLE IF EXISTS cabinet_oidc_state;
DROP TABLE IF EXISTS cabinet_subscriptions;
DROP TABLE IF EXISTS cabinet_saved_queries;
DROP TABLE IF EXISTS cabinet_bookmarks;
DROP TABLE IF EXISTS cabinet_sessions;
DROP TABLE IF EXISTS cabinet_users;

-- Webmaster submissions: moved to YaCy native WorkTables (`crawl_requests`)
-- in Phase 3 so authenticated YaCy users (digest auth + WEBMASTER_RIGHT)
-- own them. Drop the pgvector copy on existing deployments.
DROP TABLE IF EXISTS webmaster_submissions;
