"""CRUD / upsert helpers (Postgres + SQLite)."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    DailyBrief,
    Feedback,
    Item,
    ItemMetric,
    PipelineRun,
    Story,
    StorySummary,
)
from app.db.types_compat import is_sqlite


def content_hash(title: str, url: str, description: str = "") -> str:
    raw = f"{title}|{url}|{description[:500]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _insert_stmt(model):
    if is_sqlite():
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    return dialect_insert(model)


def upsert_item(session: Session, data: dict[str, Any]) -> Item:
    """Insert or update item by (source_key, external_id)."""
    payload = dict(data)
    payload.setdefault(
        "content_hash",
        content_hash(
            payload.get("title", ""),
            payload.get("url", ""),
            payload.get("description", "") or "",
        ),
    )
    payload.setdefault("canonical_url", payload.get("url", ""))
    payload.setdefault("extra", {})
    payload.setdefault("authors", [])
    now = datetime.now(timezone.utc)
    payload.setdefault("first_seen_at", now)
    payload["last_seen_at"] = now

    stmt = _insert_stmt(Item).values(**payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_key", "external_id"],
        set_={
            "last_seen_at": now,
            "description": stmt.excluded.description,
            "extra": stmt.excluded.extra,
            "title": stmt.excluded.title,
            "url": stmt.excluded.url,
            "canonical_url": stmt.excluded.canonical_url,
            "authors": stmt.excluded.authors,
            "organization": stmt.excluded.organization,
            "published_at": stmt.excluded.published_at,
            "content_hash": stmt.excluded.content_hash,
        },
    )
    if is_sqlite():
        session.execute(stmt)
        session.flush()
        item = session.scalar(
            select(Item).where(
                Item.source_key == payload["source_key"],
                Item.external_id == payload["external_id"],
            )
        )
        assert item is not None
        return item

    stmt = stmt.returning(Item.id)
    item_id = session.execute(stmt).scalar_one()
    session.flush()
    return session.get(Item, item_id)


def upsert_metric(
    session: Session,
    item_id: int,
    snapshot_date: date,
    metric_name: str,
    value: float,
) -> None:
    stmt = _insert_stmt(ItemMetric).values(
        item_id=item_id,
        snapshot_date=snapshot_date,
        metric_name=metric_name,
        value=value,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["item_id", "snapshot_date", "metric_name"],
        set_={"value": stmt.excluded.value},
    )
    session.execute(stmt)


def get_items_by_date(
    session: Session,
    target_date: date,
    window_hours: int = 48,
) -> list[Item]:
    start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc) - timedelta(
        hours=window_hours
    )
    end = datetime.combine(target_date, datetime.max.time(), tzinfo=timezone.utc) + timedelta(
        hours=1
    )
    # SQLite often stores naive datetimes — compare without forcing tz mismatch
    if is_sqlite():
        start_n = start.replace(tzinfo=None)
        end_n = end.replace(tzinfo=None)
        stmt: Select[tuple[Item]] = (
            select(Item)
            .where(
                ((Item.published_at >= start_n) & (Item.published_at <= end_n))
                | ((Item.first_seen_at >= start_n) & (Item.first_seen_at <= end_n))
            )
            .options(joinedload(Item.metrics))
        )
    else:
        stmt = (
            select(Item)
            .where(
                ((Item.published_at >= start) & (Item.published_at <= end))
                | ((Item.first_seen_at >= start) & (Item.first_seen_at <= end))
            )
            .options(joinedload(Item.metrics))
        )
    return list(session.scalars(stmt).unique().all())


def get_stories_by_date(session: Session, target_date: date) -> list[Story]:
    stmt = (
        select(Story)
        .where(Story.story_date == target_date)
        .options(joinedload(Story.summary), joinedload(Story.items))
        .order_by(Story.importance_score.desc())
    )
    return list(session.scalars(stmt).unique().all())


def get_story(session: Session, story_id: int) -> Optional[Story]:
    stmt = (
        select(Story)
        .where(Story.id == story_id)
        .options(joinedload(Story.summary), joinedload(Story.items))
    )
    return session.scalars(stmt).unique().first()


def save_brief(session: Session, data: dict[str, Any]) -> DailyBrief:
    stmt = _insert_stmt(DailyBrief).values(**data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["brief_date"],
        set_={
            "tldr": stmt.excluded.tldr,
            "top_story_ids": stmt.excluded.top_story_ids,
            "rising": stmt.excluded.rising,
            "big_tech": stmt.excluded.big_tech,
            "poc_candidates": stmt.excluded.poc_candidates,
            "stats": stmt.excluded.stats,
            "cdo_brief": stmt.excluded.cdo_brief,
            "markdown": stmt.excluded.markdown,
            "theme_of_the_day": stmt.excluded.theme_of_the_day,
        },
    )
    if is_sqlite():
        session.execute(stmt)
        session.flush()
        brief = session.scalar(
            select(DailyBrief).where(DailyBrief.brief_date == data["brief_date"])
        )
        assert brief is not None
        return brief

    stmt = stmt.returning(DailyBrief.id)
    brief_id = session.execute(stmt).scalar_one()
    session.flush()
    return session.get(DailyBrief, brief_id)


def get_brief(session: Session, brief_date: date) -> Optional[DailyBrief]:
    return session.scalar(select(DailyBrief).where(DailyBrief.brief_date == brief_date))


def get_latest_brief(session: Session) -> Optional[DailyBrief]:
    return session.scalar(select(DailyBrief).order_by(DailyBrief.brief_date.desc()).limit(1))


def add_feedback(
    session: Session, story_id: int, vote: int, note: Optional[str] = None
) -> Feedback:
    fb = Feedback(story_id=story_id, vote=vote, note=note)
    session.add(fb)
    session.flush()
    return fb


def upsert_story_summary(session: Session, story_id: int, data: dict[str, Any]) -> StorySummary:
    existing = session.scalar(select(StorySummary).where(StorySummary.story_id == story_id))
    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        session.flush()
        return existing
    summary = StorySummary(story_id=story_id, **data)
    session.add(summary)
    session.flush()
    return summary


def start_pipeline_run(session: Session, run_date: date) -> PipelineRun:
    run = PipelineRun(
        run_date=run_date,
        started_at=datetime.now(timezone.utc),
        status="running",
        step_status={},
    )
    session.add(run)
    session.flush()
    return run


def finish_pipeline_run(
    session: Session,
    run: PipelineRun,
    status: str,
    step_status: dict[str, Any],
    error: Optional[str] = None,
) -> None:
    run.status = status
    run.step_status = step_status
    run.error = error
    run.finished_at = datetime.now(timezone.utc)
    session.flush()


def get_latest_pipeline_run(session: Session) -> Optional[PipelineRun]:
    return session.scalar(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1))


def semantic_search_items(
    session: Session, embedding: list[float], limit: int = 30
) -> list[Item]:
    """Cosine search: pgvector on Postgres, numpy on SQLite."""
    if is_sqlite():
        items = list(
            session.scalars(select(Item).where(Item.embedding.is_not(None))).all()
        )
        if not items:
            return []
        q = np.asarray(embedding, dtype=np.float32)
        q = q / (np.linalg.norm(q) + 1e-9)
        scored: list[tuple[float, Item]] = []
        for it in items:
            vec = np.asarray(it.embedding, dtype=np.float32)
            if vec.size == 0:
                continue
            vec = vec / (np.linalg.norm(vec) + 1e-9)
            # pad/truncate
            n = min(len(q), len(vec))
            sim = float(np.dot(q[:n], vec[:n]))
            scored.append((sim, it))
        scored.sort(key=lambda x: -x[0])
        return [it for _, it in scored[:limit]]

    from sqlalchemy import text

    vec = "[" + ",".join(str(float(x)) for x in embedding) + "]"
    rows = session.execute(
        text(
            """
            SELECT id FROM items
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :lim
            """
        ),
        {"vec": vec, "lim": limit},
    ).scalars().all()
    if not rows:
        return []
    stmt = select(Item).where(Item.id.in_(rows)).options(joinedload(Item.metrics))
    found = {i.id: i for i in session.scalars(stmt).unique().all()}
    return [found[i] for i in rows if i in found]
