"""Sentence-transformer embeddings with lazy load."""

from __future__ import annotations

from typing import Optional

import numpy as np
from loguru import logger

from app.config import get_settings

_model = None
_model_name: Optional[str] = None


def get_model():
    global _model, _model_name
    settings = get_settings()
    name = settings.embedding_model
    if _model is not None and _model_name == name:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model {}", name)
        _model = SentenceTransformer(name)
        _model_name = name
    except Exception as exc:
        fallback = "intfloat/multilingual-e5-small"
        logger.warning("Failed to load {}: {}. Falling back to {}", name, exc, fallback)
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(fallback)
        _model_name = fallback
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, get_settings().embedding_dim), dtype=np.float32)
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vectors, dtype=np.float32)


def item_text(title: str, description: str = "") -> str:
    return f"{title} . {(description or '')[:500]}"


def embed_items_missing(session) -> int:
    """Embed items that lack embeddings. Returns count updated."""
    from sqlalchemy import select

    from app.db.models import Item

    rows = list(
        session.scalars(select(Item).where(Item.embedding.is_(None)).limit(500)).all()
    )
    if not rows:
        return 0
    texts = [item_text(r.title, r.description or "") for r in rows]
    vectors = embed_texts(texts)
    dim = get_settings().embedding_dim
    for row, vec in zip(rows, vectors):
        if len(vec) != dim:
            # pad / truncate to configured dim
            out = np.zeros(dim, dtype=np.float32)
            n = min(dim, len(vec))
            out[:n] = vec[:n]
            row.embedding = out.tolist()
        else:
            row.embedding = vec.tolist()
    session.flush()
    return len(rows)
