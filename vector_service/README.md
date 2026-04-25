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

## Why not just YaCy's existing Solr?

Solr does BM25 + boost functions well, but ranks on lexical match.
"Schrödinger's cat" and "thought experiment about a feline in a box"
share zero token overlap; Solr returns nothing useful, the vector layer
ranks them as near-identical.

The plan (see `docs/yacy-project/PLAN.md`, Phase 2) is hybrid scoring:
60% semantic (this service) + 25% freshness + 15% domain quality.

## Production deploy

Deferred — service will run on `168.231.108.21` (port 8001, behind nginx)
once the local dev iteration converges. Postgres there is also self-hosted.
