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
