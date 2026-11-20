"""Score stories by importance."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Optional

import numpy as np
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_yaml
from app.db.models import Item, ItemMetric
from app.db.repository import get_stories_by_date


def percentile_rank(values: list[float], value: float) -> float:
    if not values:
        return 0.0
    arr = np.asarray(values, dtype=np.float64)
    return float((arr <= value).sum() / len(arr))


def freshness_score(age_hours: float, half_life: float) -> float:
    return float(0.5 ** (age_hours / half_life)) if half_life > 0 else 0.0


def _metric_for_item(
    session: Session, item: Item, target_date: date
) -> float:
    metrics = {
        m.metric_name: m.value
        for m in (item.metrics or [])
        if m.snapshot_date == target_date
    }
    if not metrics:
        rows = session.scalars(
            select(ItemMetric).where(
                ItemMetric.item_id == item.id, ItemMetric.snapshot_date == target_date
            )
        ).all()
        metrics = {m.metric_name: m.value for m in rows}

    sk = item.source_key
    if sk in ("github_trending", "github_search"):
        if "stars_today" in metrics:
            return metrics["stars_today"]
        # delta vs previous day
        prev = session.scalar(
            select(ItemMetric).where(
                ItemMetric.item_id == item.id,
                ItemMetric.metric_name == "stars",
                ItemMetric.snapshot_date < target_date,
            ).order_by(ItemMetric.snapshot_date.desc()).limit(1)
        )
        stars = metrics.get("stars", 0.0)
        return max(0.0, stars - (prev.value if prev else 0.0))
    if sk == "hf_papers":
        return metrics.get("upvotes", 0.0)
    if sk in ("hf_models", "hf_spaces"):
        if "likes" in metrics:
            return metrics["likes"]
        rank = metrics.get("trending_rank", 50.0)
        return max(0.0, 51.0 - rank)
    if sk == "hackernews":
        return metrics.get("points", 0.0)
    if sk == "reddit":
        return metrics.get("upvotes", 0.0)
    return 0.0


def score(session: Session, target_date: date) -> dict[str, int]:
    scoring = load_yaml("scoring")
    weights = scoring.get("weights") or {}
    half_life = float(scoring.get("freshness_half_life_hours", 36))
    sources_cfg = load_yaml("sources")
    connectors = sources_cfg.get("connectors") or {}
    big_tech_orgs = {o.lower() for o in (sources_cfg.get("big_tech_orgs") or [])}
    watchlist = load_yaml("watchlist") or []
    wl_priority = {w["name"]: int(w.get("priority", 2)) for w in watchlist}

    stories = get_stories_by_date(session, target_date)

    # Precompute velocity raw values per source
    raw_by_source: dict[str, list[float]] = {}
    item_velocity: dict[int, float] = {}
    all_items: list[Item] = []
    for story in stories:
        all_items.extend(story.items or [])

    for item in all_items:
        raw = _metric_for_item(session, item, target_date)
        item_velocity[item.id] = raw
        raw_by_source.setdefault(item.source_key, []).append(math.log1p(raw))

    now = datetime.combine(target_date, datetime.max.time(), tzinfo=timezone.utc)

    for story in stories:
        items = story.items or []
        # velocity
        vel_scores = []
        for item in items:
            raw = item_velocity.get(item.id, 0.0)
            pool = raw_by_source.get(item.source_key) or [0.0]
            vel_scores.append(percentile_rank(pool, math.log1p(raw)))
        velocity = max(vel_scores) if vel_scores else 0.0

        cross_source = min(max(story.source_count - 1, 0), 4) / 4.0

        source_weight = 0.0
        for item in items:
            cfg = connectors.get(item.source_key) or {}
            w = float(cfg.get("weight", 0.5))
            if item.source_key == "rss" and (item.extra or {}).get("is_big_tech"):
                w = float((item.extra or {}).get("weight", 1.0))
            source_weight = max(source_weight, w)

        # relevance via watchlist match + priority
        relevance = 0.0
        for name in story.watchlist_matches or []:
            # priority 1 → 1.0, 2 → 0.66, 3 → 0.33
            p = wl_priority.get(name, 2)
            relevance = max(relevance, (4 - p) / 3.0)

        # freshness from newest item
        ages = []
        for item in items:
            ts = item.published_at or item.first_seen_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ages.append(max(0.0, (now - ts).total_seconds() / 3600.0))
        age_hours = min(ages) if ages else half_life
        fresh = freshness_score(age_hours, half_life)

        importance = (
            weights.get("velocity", 0.3) * velocity
            + weights.get("cross_source", 0.25) * cross_source
            + weights.get("source_weight", 0.2) * source_weight
            + weights.get("relevance", 0.15) * relevance
            + weights.get("freshness", 0.1) * fresh
        )
        story.importance_score = float(importance)
        story.score_breakdown = {
            "velocity": round(velocity, 4),
            "cross_source": round(cross_source, 4),
            "source_weight": round(source_weight, 4),
            "relevance": round(relevance, 4),
            "freshness": round(fresh, 4),
            "importance": round(float(importance), 4),
        }

        is_big = False
        org: Optional[str] = story.organization
        for item in items:
            if (item.extra or {}).get("is_big_tech"):
                is_big = True
            o = (item.organization or "").lower()
            if o in big_tech_orgs:
                is_big = True
                org = item.organization
        story.is_big_tech = is_big
        if org:
            story.organization = org

    session.commit()
    logger.info("score: {} stories", len(stories))
    return {"stories": len(stories)}
