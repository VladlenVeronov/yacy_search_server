-- Code-RAG: yacy-fork source tree embeddings. Separate table from `pages`
-- so web-doc scores and code-search scores never cross-contaminate.
-- Same DB (yacy_pages) for backup simplicity — same embedding model
-- (intfloat/multilingual-e5-base, 768d), so schema reuses vector(768).

CREATE TABLE IF NOT EXISTS code_chunks (
    id           bigserial PRIMARY KEY,
    path         text NOT NULL,               -- relative to yacy-fork/ root
    file_type    text NOT NULL,               -- java, html, template, css, js, lng, xml, md, properties
    chunk_num    int  NOT NULL,               -- 0-based chunk index within the file
    line_start   int,
    line_end     int,
    content      text NOT NULL,
    content_hash text NOT NULL,               -- sha256 of content; skip re-embed on unchanged
    embedding    vector(768),
    file_mtime   timestamptz,
    indexed_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (path, chunk_num)
);

CREATE INDEX IF NOT EXISTS code_chunks_type_idx ON code_chunks (file_type);
CREATE INDEX IF NOT EXISTS code_chunks_path_idx ON code_chunks (path);
CREATE INDEX IF NOT EXISTS code_chunks_mtime_idx ON code_chunks (file_mtime DESC NULLS LAST);

-- HNSW for cosine similarity. Empty table is fine — pgvector builds lazily.
CREATE INDEX IF NOT EXISTS code_chunks_embedding_hnsw_idx
    ON code_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
