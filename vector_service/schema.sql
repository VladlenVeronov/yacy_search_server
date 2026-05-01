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

-- Webmaster submissions: public form lets anyone submit a site for indexing.
-- Auto-validated against the blacklist on insert; admin approves/rejects.
CREATE TABLE IF NOT EXISTS webmaster_submissions (
    id              bigserial PRIMARY KEY,
    url             text NOT NULL,
    host            text NOT NULL,
    contact_email   text,
    description     text,
    status          text NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|crawled
    reject_reason   text,
    submitted_at    timestamptz NOT NULL DEFAULT now(),
    processed_at    timestamptz,
    submitter_ip    inet
);
CREATE INDEX IF NOT EXISTS webmaster_status_idx ON webmaster_submissions (status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS webmaster_host_idx   ON webmaster_submissions (host);

-- Services menu: rendered in the public drawer (right-side bottomsheet).
-- Managed via /admin-services.html behind the Authorization: Bearer header
-- (ADMIN_TOKEN env). Icon is a URL (favicon, CDN-free hosted asset, etc.).
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

-- USER CABINET tables (Phase 3)
CREATE TABLE IF NOT EXISTS cabinet_users (
    id              bigserial PRIMARY KEY,
    sub             text UNIQUE NOT NULL,    -- OIDC subject from Authentik
    email           text NOT NULL,
    display_name    text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_login_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cabinet_users_email_idx ON cabinet_users (lower(email));

CREATE TABLE IF NOT EXISTS cabinet_sessions (
    id              text PRIMARY KEY,         -- random 32-byte hex
    user_id         bigint NOT NULL REFERENCES cabinet_users(id) ON DELETE CASCADE,
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS cabinet_sessions_user_idx ON cabinet_sessions (user_id);
CREATE INDEX IF NOT EXISTS cabinet_sessions_exp_idx  ON cabinet_sessions (expires_at);

CREATE TABLE IF NOT EXISTS cabinet_bookmarks (
    id              bigserial PRIMARY KEY,
    user_id         bigint NOT NULL REFERENCES cabinet_users(id) ON DELETE CASCADE,
    url             text NOT NULL,
    title           text,
    note            text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE(user_id, url)
);
CREATE INDEX IF NOT EXISTS cabinet_bookmarks_user_idx ON cabinet_bookmarks (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS cabinet_saved_queries (
    id              bigserial PRIMARY KEY,
    user_id         bigint NOT NULL REFERENCES cabinet_users(id) ON DELETE CASCADE,
    query           text NOT NULL,
    label           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE(user_id, query)
);
CREATE INDEX IF NOT EXISTS cabinet_saved_queries_user_idx ON cabinet_saved_queries (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS cabinet_subscriptions (
    id              bigserial PRIMARY KEY,
    user_id         bigint NOT NULL REFERENCES cabinet_users(id) ON DELETE CASCADE,
    query           text NOT NULL,
    last_seen_id    text,
    last_check      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE(user_id, query)
);
CREATE INDEX IF NOT EXISTS cabinet_subs_user_idx ON cabinet_subscriptions (user_id);

-- OIDC short-lived state (CSRF protection during auth code flow)
CREATE TABLE IF NOT EXISTS cabinet_oidc_state (
    state           text PRIMARY KEY,
    nonce           text NOT NULL,
    code_verifier   text,
    return_to       text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE webmaster_submissions ADD COLUMN IF NOT EXISTS priority text NOT NULL DEFAULT 'normal';
