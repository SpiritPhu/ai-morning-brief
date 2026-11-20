"""Classify stories into taxonomy topics and watchlist matches."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import numpy as np
from loguru import logger
from sqlalchemy.orm import Session

from app.config import load_yaml
from app.db.repository import get_stories_by_date
from app.embeddings import embed_texts


def _iter_labels() -> list[dict[str, Any]]:
    taxonomy = load_yaml("taxonomy")
    labels: list[dict[str, Any]] = []
    for group_labels in (taxonomy.get("groups") or {}).values():
        labels.extend(group_labels)
    return labels


def _rule_match(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    for kw in keywords:
        if re.search(rf"\b{re.escape(kw.lower())}\b", lower):
            return True
    return False


_label_embeddings: dict[str, np.ndarray] | None = None
_watchlist_embeddings: dict[str, np.ndarray] | None = None


def _get_label_embeddings() -> dict[str, np.ndarray]:
    global _label_embeddings
    if _label_embeddings is not None:
        return _label_embeddings
    labels = _iter_labels()
    texts = [f"{l['name']}. {l.get('description', '')}" for l in labels]
    vectors = embed_texts(texts) if texts else np.zeros((0, 1))
    _label_embeddings = {labels[i]["name"]: vectors[i] for i in range(len(labels))}
    return _label_embeddings


def _get_watchlist_embeddings() -> dict[str, np.ndarray]:
    global _watchlist_embeddings
    if _watchlist_embeddings is not None:
        return _watchlist_embeddings
    watchlist = load_yaml("watchlist") or []
    texts = [f"{w['name']}. {w.get('description', '')}" for w in watchlist]
    vectors = embed_texts(texts) if texts else np.zeros((0, 1))
    _watchlist_embeddings = {watchlist[i]["name"]: vectors[i] for i in range(len(watchlist))}
    return _watchlist_embeddings


def classify(session: Session, target_date: date) -> dict[str, int]:
    stories = get_stories_by_date(session, target_date)
    labels = _iter_labels()
    watchlist = load_yaml("watchlist") or []

    # Try embedding-based; fall back to rules only if model unavailable
    try:
        label_emb = _get_label_embeddings()
        wl_emb = _get_watchlist_embeddings()
        use_emb = True
    except Exception as exc:
        logger.warning("classify embeddings unavailable: {}", exc)
        label_emb, wl_emb, use_emb = {}, {}, False

    for story in stories:
        blob = " ".join(
            f"{it.title} {it.description or ''}" for it in (story.items or [])
        ) or story.title

        rule_hits: list[str] = []
        for label in labels:
            if _rule_match(blob, label.get("keywords") or []):
                rule_hits.append(label["name"])

        emb_hits: list[tuple[str, float]] = []
        if use_emb and story.items:
            vecs = [np.asarray(it.embedding, dtype=np.float32) for it in story.items if it.embedding]
            if vecs:
                story_vec = np.mean(np.stack(vecs), axis=0)
                story_vec = story_vec / (np.linalg.norm(story_vec) + 1e-9)
                for name, lev in label_emb.items():
                    sim = float(np.dot(story_vec, lev))
                    if sim > 0.45:
                        emb_hits.append((name, sim))
                emb_hits.sort(key=lambda x: -x[1])

        topics: list[str] = []
        for name in rule_hits:
            if name not in topics:
                topics.append(name)
        for name, _ in emb_hits:
            if name not in topics:
                topics.append(name)
        story.topics = topics[:3]

        matches: list[str] = []
        for w in watchlist:
            if _rule_match(blob, w.get("keywords") or []):
                matches.append(w["name"])
                continue
            if use_emb and story.items:
                vecs = [np.asarray(it.embedding, dtype=np.float32) for it in story.items if it.embedding]
                if vecs and w["name"] in wl_emb:
                    story_vec = np.mean(np.stack(vecs), axis=0)
                    story_vec = story_vec / (np.linalg.norm(story_vec) + 1e-9)
                    if float(np.dot(story_vec, wl_emb[w["name"]])) > 0.5:
                        matches.append(w["name"])
        story.watchlist_matches = list(dict.fromkeys(matches))

    session.commit()
    logger.info("classify: {} stories", len(stories))
    return {"stories": len(stories)}
