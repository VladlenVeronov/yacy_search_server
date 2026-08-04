"""Code-RAG router for indexing and searching the yacy-fork source tree.

Companion to the /pages endpoints (which store crawled web docs). Uses the
same embedding model + pgvector DB, but a separate `code_chunks` table.

Chunking is done client-side by the indexer script — this service only
embeds+stores. Reason: chunking strategy varies by file type (java by
method, .lng by line, html by block) and keeping it in the indexer avoids
forcing every caller through a heavy service round-trip per file.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from config import settings
from db import pool
from embedder import embed_passages, embed_query


router = APIRouter(prefix="/code", tags=["code-rag"])


def _require_admin(auth: Optional[str]) -> None:
    if not settings.admin_token:
        return
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    if auth.split(" ", 1)[1] != settings.admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")


class CodeChunk(BaseModel):
    chunk_num: int = Field(..., ge=0)
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    content: str = Field(..., min_length=1)


class CodeIndexRequest(BaseModel):
    path: str = Field(..., min_length=1)
    file_type: str = Field(..., min_length=1, max_length=32)
    file_mtime: Optional[datetime] = None
    chunks: list[CodeChunk] = Field(..., min_length=1, max_length=200)


class CodeIndexResponse(BaseModel):
    path: str
    chunks_written: int
    chunks_skipped: int  # unchanged content_hash


class CodeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=20, ge=1, le=200)
    file_types: Optional[list[str]] = None
    path_prefix: Optional[str] = None


class CodeHit(BaseModel):
    path: str
    file_type: str
    chunk_num: int
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    content: str
    score: float


class CodeStats(BaseModel):
    total_chunks: int
    total_files: int
    per_type: dict[str, int]
    last_indexed_at: Optional[datetime] = None


class CodeDeleteRequest(BaseModel):
    path: Optional[str] = None
    path_prefix: Optional[str] = None


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


@router.post("/index", response_model=CodeIndexResponse)
async def code_index(req: CodeIndexRequest, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)

    # Fetch existing hashes for this path to skip re-embedding unchanged chunks.
    async with pool().acquire() as con:
        existing = await con.fetch(
            "SELECT chunk_num, content_hash FROM code_chunks WHERE path=$1",
            req.path,
        )
    existing_map = {r["chunk_num"]: r["content_hash"] for r in existing}

    to_embed: list[tuple[int, CodeChunk, str]] = []
    skipped = 0
    for c in req.chunks:
        h = _hash(c.content)
        if existing_map.get(c.chunk_num) == h:
            skipped += 1
            continue
        to_embed.append((c.chunk_num, c, h))

    written = 0
    if to_embed:
        vectors = await embed_passages([c.content for _, c, _ in to_embed])
        async with pool().acquire() as con:
            async with con.transaction():
                for (num, chunk, h), vec in zip(to_embed, vectors):
                    await con.execute(
                        """
                        INSERT INTO code_chunks
                            (path, file_type, chunk_num, line_start, line_end,
                             content, content_hash, embedding, file_mtime, indexed_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, now())
                        ON CONFLICT (path, chunk_num) DO UPDATE
                        SET file_type=EXCLUDED.file_type,
                            line_start=EXCLUDED.line_start,
                            line_end=EXCLUDED.line_end,
                            content=EXCLUDED.content,
                            content_hash=EXCLUDED.content_hash,
                            embedding=EXCLUDED.embedding,
                            file_mtime=EXCLUDED.file_mtime,
                            indexed_at=now()
                        """,
                        req.path, req.file_type, num,
                        chunk.line_start, chunk.line_end,
                        chunk.content, h, vec, req.file_mtime,
                    )
                    written += 1

    # Drop chunks that no longer exist in this file (file shrank).
    max_num = max(c.chunk_num for c in req.chunks)
    async with pool().acquire() as con:
        await con.execute(
            "DELETE FROM code_chunks WHERE path=$1 AND chunk_num>$2",
            req.path, max_num,
        )

    return CodeIndexResponse(path=req.path, chunks_written=written, chunks_skipped=skipped)


@router.post("/search", response_model=list[CodeHit])
async def code_search(req: CodeSearchRequest):
    vec = await embed_query(req.query)

    filters = ["1=1"]
    args: list = [vec, req.limit]
    if req.file_types:
        args.append(req.file_types)
        filters.append(f"file_type = ANY(${len(args)})")
    if req.path_prefix:
        args.append(req.path_prefix + "%")
        filters.append(f"path LIKE ${len(args)}")
    where = " AND ".join(filters)

    sql = f"""
        SELECT path, file_type, chunk_num, line_start, line_end, content,
               1 - (embedding <=> $1) AS score
          FROM code_chunks
         WHERE {where}
         ORDER BY embedding <=> $1
         LIMIT $2
    """
    async with pool().acquire() as con:
        rows = await con.fetch(sql, *args)

    return [
        CodeHit(
            path=r["path"], file_type=r["file_type"], chunk_num=r["chunk_num"],
            line_start=r["line_start"], line_end=r["line_end"],
            content=r["content"], score=float(r["score"]),
        )
        for r in rows
    ]


@router.get("/stats", response_model=CodeStats)
async def code_stats():
    async with pool().acquire() as con:
        total = await con.fetchval("SELECT COUNT(*) FROM code_chunks")
        files = await con.fetchval("SELECT COUNT(DISTINCT path) FROM code_chunks")
        rows = await con.fetch(
            "SELECT file_type, COUNT(*) AS n FROM code_chunks GROUP BY file_type ORDER BY n DESC"
        )
        last = await con.fetchval("SELECT MAX(indexed_at) FROM code_chunks")
    return CodeStats(
        total_chunks=total or 0,
        total_files=files or 0,
        per_type={r["file_type"]: r["n"] for r in rows},
        last_indexed_at=last,
    )


@router.delete("/delete")
async def code_delete(req: CodeDeleteRequest, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    async with pool().acquire() as con:
        if req.path:
            n = await con.fetchval(
                "WITH d AS (DELETE FROM code_chunks WHERE path=$1 RETURNING 1) SELECT COUNT(*) FROM d",
                req.path,
            )
        elif req.path_prefix:
            n = await con.fetchval(
                "WITH d AS (DELETE FROM code_chunks WHERE path LIKE $1 RETURNING 1) SELECT COUNT(*) FROM d",
                req.path_prefix + "%",
            )
        else:
            raise HTTPException(status_code=400, detail="path or path_prefix required")
    return {"deleted": n or 0}
