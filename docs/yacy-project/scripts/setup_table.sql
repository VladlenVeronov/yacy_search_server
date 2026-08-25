-- Enable pgvector extension (if not already enabled)
create extension if not exists vector;

-- Main vector table for YACY project
-- Using 768 dimensions (intfloat/multilingual-e5-base via HuggingFace)
create table if not exists yacy_vectors (
  id           bigserial primary key,
  file_path    text not null,
  language     text not null,          -- 'java', 'html', 'xml', 'js', 'css'
  chunk_index  int  not null default 0,
  class_name   text,                   -- Java class name (if applicable)
  method_name  text,                   -- Java method name (if applicable)
  content      text not null,
  embedding    vector(768),            -- intfloat/multilingual-e5-base (HuggingFace)
  commit_hash  text,
  updated_at   timestamptz default now(),
  unique (file_path, chunk_index)
);

-- Index for vector similarity search (IVFFlat, cosine)
create index if not exists yacy_vectors_embedding_idx
  on yacy_vectors
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

-- Index for fast lookup by file_path
create index if not exists yacy_vectors_file_path_idx
  on yacy_vectors (file_path);

-- Semantic search function
create or replace function match_yacy_code(
  query_embedding vector(768),
  match_threshold float default 0.7,
  match_count     int   default 10,
  filter_language text  default null
)
returns table (
  id          bigint,
  file_path   text,
  language    text,
  class_name  text,
  method_name text,
  content     text,
  similarity  float
)
language sql stable
as $$
  select
    yv.id,
    yv.file_path,
    yv.language,
    yv.class_name,
    yv.method_name,
    yv.content,
    1 - (yv.embedding <=> query_embedding) as similarity
  from yacy_vectors yv
  where
    (filter_language is null or yv.language = filter_language)
    and 1 - (yv.embedding <=> query_embedding) > match_threshold
  order by yv.embedding <=> query_embedding
  limit match_count;
$$;
