from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

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
