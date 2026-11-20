"""Deduplicate items into stories (exact link + semantic)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

import numpy as np
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_yaml
from app.db.models import Item, Story
from app.db.repository import get_items_by_date


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


_PRIMARY_RANK = {
    "rss": 0,
    "hf_papers": 1,
    "arxiv": 2,
    "github_trending": 3,
    "github_search": 3,
    "hf_models": 4,
    "hf_spaces": 5,
    "hackernews": 6,
    "reddit": 7,
}


def _link_keys(item: Item) -> set[str]:
    keys: set[str] = set()
    if item.canonical_url:
        keys.add(f"url:{item.canonical_url}")
    extra = item.extra or {}
    if extra.get("arxiv_id"):
        keys.add(f"arxiv:{extra['arxiv_id']}")
    if extra.get("github_repo"):
        keys.add(f"gh:{str(extra['github_repo']).lower()}")
    if extra.get("hf_model_id"):
        keys.add(f"hf:{extra['hf_model_id']}")
    return keys


def _pick_primary(items: list[Item]) -> Item:
    return sorted(items, key=lambda i: (_PRIMARY_RANK.get(i.source_key, 99), i.id))[0]


def cluster_items(items: list[Item], threshold: float) -> list[list[Item]]:
    n = len(items)
    if n == 0:
        return []
    uf = UnionFind(n)

    # Exact link keys
    key_to_idx: dict[str, int] = {}
    for i, item in enumerate(items):
        for k in _link_keys(item):
            if k in key_to_idx:
                uf.union(i, key_to_idx[k])
            else:
                key_to_idx[k] = i

    # Semantic within remaining components
    embeddings: list[Optional[np.ndarray]] = []
    for item in items:
        if item.embedding is not None:
            embeddings.append(np.asarray(item.embedding, dtype=np.float32))
        else:
            embeddings.append(None)

    for i in range(n):
        if embeddings[i] is None:
            continue
        for j in range(i + 1, n):
            if embeddings[j] is None:
                continue
            if uf.find(i) == uf.find(j):
                continue
            sim = float(np.dot(embeddings[i], embeddings[j]))
            if sim >= threshold:
                uf.union(i, j)

    groups: dict[int, list[Item]] = defaultdict(list)
    for i, item in enumerate(items):
        groups[uf.find(i)].append(item)
    return list(groups.values())


def dedup(session: Session, target_date: date) -> dict[str, int]:
    scoring = load_yaml("scoring")
    threshold = float(scoring.get("dedup_similarity_threshold", 0.88))
    items = get_items_by_date(session, target_date, window_hours=48)
    clusters = cluster_items(items, threshold)
    created = updated = 0

    for cluster in clusters:
        primary = _pick_primary(cluster)
        source_keys = {i.source_key for i in cluster}
        # Idempotent: reuse story with same date + primary_item_id
        story = session.scalar(
            select(Story).where(
                Story.story_date == target_date,
                Story.primary_item_id == primary.id,
            )
        )
        if not story:
            # also match by canonical url same day
            story = session.scalar(
                select(Story).where(
                    Story.story_date == target_date,
                    Story.canonical_url == primary.canonical_url,
                )
            )
        if story:
            updated += 1
        else:
            story = Story(story_date=target_date, title=primary.title)
            session.add(story)
            session.flush()
            created += 1

        story.title = primary.title
        story.canonical_url = primary.canonical_url
        story.primary_item_id = primary.id
        story.source_count = len(source_keys)
        story.item_count = len(cluster)
        story.organization = primary.organization
        for item in cluster:
            item.story_id = story.id

    session.commit()
    logger.info("dedup: {} clusters ({} new, {} updated)", len(clusters), created, updated)
    return {"clusters": len(clusters), "created": created, "updated": updated}
