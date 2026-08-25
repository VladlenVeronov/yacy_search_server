# YACY Vector Service

FastAPI service that holds per-document embeddings for the pages YaCy has
crawled, providing a semantic-search ranking layer alongside Solr's BM25.

- Embedding model: `intfloat/multilingual-e5-base` (768d, multilingual,
  loaded **locally** via `sentence-transformers` — no third-party API at
  runtime; weights are downloaded once and cached under `~/.cache/huggingface`).
- Vector store: PostgreSQL with `pgvector`, HNSW index, cosine similarity.
- Database: `yacy_pages` (separate from `yacy_vectors` which stores
  embeddings of YaCy's *source code* for the dev tool).

## Local dev setup (Mac)

```bash
# 1. Create the DB and schema (one-off)
psql -d postgres -c "CREATE DATABASE yacy_pages;"
psql -d yacy_pages -f schema.sql

# 2. Install deps in a venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Copy env
cp .env.example .env

# 4. Run
uvicorn main:app --reload --host 127.0.0.1 --port 8001
```

First start downloads the embedding model (~280 MB) and warms it before
the server begins accepting requests.

## Endpoints

| Method | Path                | Body / Params                    | Notes                              |
| ------ | ------------------- | -------------------------------- | ---------------------------------- |
| GET    | `/health`           | —                                | DB ping + model info               |
| POST   | `/index`            | `IndexRequest`                   | Upsert; skips re-embed if hash unchanged |
| POST   | `/search`           | `SearchRequest`                  | Cosine-ranked nearest neighbors    |
| POST   | `/rank`             | `RankRequest`                    | Hybrid re-rank for a Solr candidate set |
| DELETE | `/doc/{id}`         | —                                | Remove a single document           |

### Smoke test

```bash
curl -s localhost:8001/health | jq

curl -s -X POST localhost:8001/index -H 'content-type: application/json' -d '{
  "id": "test-doc-1",
  "url": "https://example.com/a",
  "title": "Cats and physics",
  "summary": "Schrödinger imagined a cat in a sealed box ..."
}' | jq

curl -s -X POST localhost:8001/search -H 'content-type: application/json' -d '{
  "query": "thought experiment about a feline in a box",
  "limit": 5
}' | jq
```

### Hybrid re-rank (`/rank`)

`/search` returns nearest-neighbours over the entire pgvector store. `/rank`
takes an existing candidate set (typically Solr's BM25 top-N) and re-orders
it using the Phase 2 hybrid formula:

```
score = 0.60 · semantic + 0.25 · freshness + 0.15 · quality
```

- **semantic** — cosine similarity of the candidate's embedding to the query.
  `0` for candidates not yet embedded; the candidate stays in the result list
  but rides only on freshness + quality.
- **freshness** — `exp(-age_days / 365)`. Falls back to `0.5` when
  `last_modified` is unknown.
- **quality** — URL-only placeholder: HTTPS = 1.0, HTTP = 0.3. Will be
  replaced by crawl-time signals (page speed, ad/tracker presence) once
  those are surfaced from the YaCy side.

Weights and the freshness half-life are tunable in `config.py` /
environment.

```bash
curl -s -X POST localhost:8001/rank -H 'content-type: application/json' -d '{
  "query": "thought experiment with a feline in a box",
  "candidates": [
    {"id": "doc-cat-recent-https"},
    {"id": "doc-cat-old-http"},
    {"id": "doc-missing-no-row", "url": "https://other.example/x", "last_modified": "2026-04-15T00:00:00Z"}
  ],
  "limit": 10
}' | jq
```

For each hit the response breaks the score into its three components plus
an `embedded` flag, so the caller can debug ordering or surface a
"semantic match" badge in the UI.

## Why not just YaCy's existing Solr?

Solr does BM25 + boost functions well, but ranks on lexical match.
"Schrödinger's cat" and "thought experiment about a feline in a box"
share zero token overlap; Solr returns nothing useful, the vector layer
ranks them as near-identical.

See `/rank` above for how the two layers combine.

## Production deploy

Deferred — service will run on `168.231.108.21` (port 8001, behind nginx)
once the local dev iteration converges. Postgres there is also self-hosted.
