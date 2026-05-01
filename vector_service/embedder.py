from __future__ import annotations

import asyncio
import threading

import numpy as np
from sentence_transformers import SentenceTransformer

from config import settings

_model: SentenceTransformer | None = None
_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    """Lazy-load and cache the embedding model. First call may take several
    seconds (and downloads the model weights on the very first run). Pre-warm
    via this function in app startup so request latency isn't paying for it."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = SentenceTransformer(settings.embedding_model)
    return _model


def _embed_query(text: str) -> np.ndarray:
    # e5-style models require a "query: " / "passage: " prefix to distinguish
    # the two embedding roles — search quality drops noticeably without it.
    return get_model().encode(f"query: {text}", normalize_embeddings=True)


# e5-base accepts ~512 tokens. ~1500 chars stays safely inside that.
_CHUNK_CHARS = 1500


def _split_chunks(text: str) -> list[str]:
    if len(text) <= _CHUNK_CHARS:
        return [text]
    # Prefer paragraph boundaries; fall back to fixed-width slices.
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 2 <= _CHUNK_CHARS:
            buf = (buf + "\n\n" + p) if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= _CHUNK_CHARS:
                buf = p
            else:
                for i in range(0, len(p), _CHUNK_CHARS):
                    chunks.append(p[i : i + _CHUNK_CHARS])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _embed_passages(texts: list[str]) -> list[np.ndarray]:
    """Mean-pool per-chunk embeddings so long passages aren't silently
    truncated to the model's 512-token window. Each input text is split into
    ~1500-char chunks (paragraph-aware), embedded together in one batch,
    then averaged and L2-renormalized."""
    flat: list[str] = []
    spans: list[tuple[int, int]] = []
    for t in texts:
        chunks = _split_chunks(t)
        start = len(flat)
        flat.extend(f"passage: {c}" for c in chunks)
        spans.append((start, start + len(chunks)))

    arr = get_model().encode(flat, normalize_embeddings=True, batch_size=16)
    out: list[np.ndarray] = []
    for s, e in spans:
        if e - s == 1:
            out.append(arr[s])
        else:
            v = np.mean(arr[s:e], axis=0)
            n = np.linalg.norm(v)
            out.append(v / n if n > 0 else v)
    return out


async def embed_query(text: str) -> np.ndarray:
    return await asyncio.to_thread(_embed_query, text)


async def embed_passages(texts: list[str]) -> list[np.ndarray]:
    return await asyncio.to_thread(_embed_passages, texts)
