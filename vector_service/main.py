from __future__ import annotations

import hashlib
import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import settings
from db import close_pool, init_pool, pool
from embedder import embed_passages, embed_query, get_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_model()  # warm the embedding model so the first /search isn't slow
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="YACY Vector Service", version="0.1.0", lifespan=lifespan)


class IndexRequest(BaseModel):
    id: str = Field(..., min_length=1)
    url: str
    title: Optional[str] = None
    summary: str
    host: Optional[str] = None
    lang: Optional[str] = None
    last_modified: Optional[datetime] = None  # ISO8601 in JSON


class IndexResponse(BaseModel):
    id: str
    embedded: bool


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=20, ge=1, le=200)


class SearchHit(BaseModel):
    id: str
    url: str
    title: Optional[str] = None
    host: Optional[str] = None
    score: float


@app.get("/health")
async def health():
    async with pool().acquire() as con:
        await con.execute("SELECT 1")
    return {"ok": True, "model": settings.embedding_model, "dim": settings.embedding_dim}


@app.post("/index", response_model=IndexResponse)
async def index(req: IndexRequest):
    summary = req.summary[: settings.max_summary_chars]
    if not summary.strip():
        raise HTTPException(status_code=400, detail="summary is empty")
    chash = hashlib.sha256(summary.encode("utf-8")).hexdigest()

    async with pool().acquire() as con:
        existing = await con.fetchrow(
            "SELECT content_hash FROM pages WHERE id=$1", req.id
        )
        if existing is not None and existing["content_hash"] == chash:
            return IndexResponse(id=req.id, embedded=False)

        embedding = (await embed_passages([summary]))[0]
        await con.execute(
            """
            INSERT INTO pages (id, url, host, title, summary, content_hash,
                               last_modified, lang, embedding, embedded_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
            ON CONFLICT (id) DO UPDATE SET
                url = EXCLUDED.url,
                host = EXCLUDED.host,
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                content_hash = EXCLUDED.content_hash,
                last_modified = EXCLUDED.last_modified,
                lang = EXCLUDED.lang,
                embedding = EXCLUDED.embedding,
                embedded_at = now()
            """,
            req.id, req.url, req.host, req.title, summary, chash,
            req.last_modified, req.lang, embedding,
        )
    return IndexResponse(id=req.id, embedded=True)


@app.post("/search", response_model=list[SearchHit])
async def search(req: SearchRequest):
    qvec = await embed_query(req.query)
    async with pool().acquire() as con:
        rows = await con.fetch(
            """
            SELECT id, url, title, host,
                   1 - (embedding <=> $1) AS score
              FROM pages
             WHERE embedding IS NOT NULL
             ORDER BY embedding <=> $1
             LIMIT $2
            """,
            qvec, req.limit,
        )
    return [SearchHit(**dict(row)) for row in rows]


@app.delete("/doc/{doc_id}")
async def delete(doc_id: str):
    async with pool().acquire() as con:
        result = await con.execute("DELETE FROM pages WHERE id=$1", doc_id)
    deleted = result.split()[-1] if result else "0"
    return {"deleted": int(deleted)}


# ---------------------------------------------------------------------------
# Hybrid re-ranking
# ---------------------------------------------------------------------------


class RankCandidate(BaseModel):
    id: str = Field(..., min_length=1)
    url: Optional[str] = None
    last_modified: Optional[datetime] = None


class RankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    candidates: list[RankCandidate] = Field(..., min_length=1, max_length=500)
    limit: Optional[int] = Field(default=None, ge=1, le=500)


class RankHit(BaseModel):
    id: str
    score: float
    semantic: float
    freshness: float
    quality: float
    embedded: bool


def _freshness_score(last_modified: Optional[datetime]) -> float:
    """Exponential decay on document age. Missing date → neutral 0.5 so the
    component neither helps nor hurts."""
    if last_modified is None:
        return 0.5
    if last_modified.tzinfo is None:
        last_modified = last_modified.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - last_modified).total_seconds() / 86400.0
    if age_days <= 0:
        return 1.0
    decay = math.exp(-age_days / settings.freshness_half_life_days)
    return max(0.0, min(1.0, decay))


def _quality_score(url: Optional[str]) -> float:
    """Lightweight URL-only quality signal — HTTPS gets full credit, HTTP a
    sharp penalty. Real signals (page speed, ad/tracker presence) need
    crawl-time data not yet available here; this is a placeholder slot in
    the hybrid weight so adding them later is a one-line change."""
    if not url:
        return 0.5
    try:
        scheme = urlparse(url).scheme.lower()
    except ValueError:
        return 0.3
    if scheme == "https":
        return 1.0
    if scheme == "http":
        return 0.3
    return 0.5


@app.post("/rank", response_model=list[RankHit])
async def rank(req: RankRequest):
    qvec = await embed_query(req.query)
    ids = [c.id for c in req.candidates]
    by_id = {c.id: c for c in req.candidates}

    async with pool().acquire() as con:
        rows = await con.fetch(
            """
            SELECT id,
                   1 - (embedding <=> $1) AS sim,
                   url,
                   last_modified
              FROM pages
             WHERE id = ANY($2::text[])
               AND embedding IS NOT NULL
            """,
            qvec, ids,
        )
    pg = {r["id"]: r for r in rows}

    ws, wf, wq = settings.weight_semantic, settings.weight_freshness, settings.weight_quality
    hits: list[RankHit] = []
    for cand in req.candidates:
        row = pg.get(cand.id)
        if row is not None:
            # e5 cosine sim is ~[0, 1] for related pairs; clip negatives.
            semantic = max(0.0, min(1.0, float(row["sim"])))
            url = cand.url or row["url"]
            last_mod = cand.last_modified or row["last_modified"]
            embedded = True
        else:
            semantic = 0.0
            url = cand.url
            last_mod = cand.last_modified
            embedded = False

        freshness = _freshness_score(last_mod)
        quality = _quality_score(url)
        score = ws * semantic + wf * freshness + wq * quality
        hits.append(RankHit(
            id=cand.id,
            score=score,
            semantic=semantic,
            freshness=freshness,
            quality=quality,
            embedded=embedded,
        ))

    hits.sort(key=lambda h: h.score, reverse=True)
    if req.limit is not None:
        hits = hits[: req.limit]
    return hits
