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


def _embed_passages(texts: list[str]) -> list[np.ndarray]:
    prefixed = [f"passage: {t}" for t in texts]
    arr = get_model().encode(prefixed, normalize_embeddings=True, batch_size=16)
    return list(arr)


async def embed_query(text: str) -> np.ndarray:
    return await asyncio.to_thread(_embed_query, text)


async def embed_passages(texts: list[str]) -> list[np.ndarray]:
    return await asyncio.to_thread(_embed_passages, texts)
