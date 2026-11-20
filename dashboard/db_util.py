"""Dashboard DB helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from typing import Iterator, Optional

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import DailyBrief, Item, PipelineRun, Story
from app.db.session import SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@st.cache_data(ttl=300)
def load_brief_dates() -> list[date]:
    with session_scope() as session:
        rows = session.scalars(select(DailyBrief.brief_date).order_by(DailyBrief.brief_date.desc())).all()
        return list(rows)


@st.cache_data(ttl=300)
def load_brief(d: date) -> Optional[dict]:
    with session_scope() as session:
        brief = session.scalar(select(DailyBrief).where(DailyBrief.brief_date == d))
        if not brief:
            return None
        return {
            "brief_date": brief.brief_date,
            "tldr": brief.tldr,
            "top_story_ids": brief.top_story_ids or [],
            "rising": brief.rising or {},
            "big_tech": brief.big_tech or {},
            "poc_candidates": brief.poc_candidates or [],
            "stats": brief.stats or {},
            "cdo_brief": brief.cdo_brief or {},
            "markdown": brief.markdown or "",
            "theme_of_the_day": brief.theme_of_the_day or "",
        }


@st.cache_data(ttl=300)
def load_stories_for_date(d: date) -> list[dict]:
    with session_scope() as session:
        stories = session.scalars(
            select(Story)
            .where(Story.story_date == d)
            .options(joinedload(Story.summary), joinedload(Story.items))
            .order_by(Story.importance_score.desc())
        ).unique().all()
        return [_story_dict(s) for s in stories]


@st.cache_data(ttl=300)
def load_stories_range(start: date, end: date) -> list[dict]:
    with session_scope() as session:
        stories = session.scalars(
            select(Story)
            .where(Story.story_date >= start, Story.story_date <= end)
            .options(joinedload(Story.summary), joinedload(Story.items))
            .order_by(Story.importance_score.desc())
        ).unique().all()
        return [_story_dict(s) for s in stories]


@st.cache_data(ttl=300)
def load_latest_pipeline() -> Optional[dict]:
    with session_scope() as session:
        run = session.scalar(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1))
        if not run:
            return None
        return {
            "run_date": run.run_date,
            "status": run.status,
            "started_at": str(run.started_at),
            "finished_at": str(run.finished_at) if run.finished_at else None,
            "step_status": run.step_status,
            "error": run.error,
        }


def _story_dict(s: Story) -> dict:
    return {
        "id": s.id,
        "story_date": s.story_date,
        "title": s.title,
        "canonical_url": s.canonical_url,
        "source_count": s.source_count,
        "topics": s.topics or [],
        "importance_score": s.importance_score,
        "score_breakdown": s.score_breakdown or {},
        "is_big_tech": s.is_big_tech,
        "organization": s.organization,
        "watchlist_matches": s.watchlist_matches or [],
        "summary": None
        if not s.summary
        else {
            "title_vi": s.summary.title_vi,
            "summary": s.summary.summary,
            "why_it_matters": s.summary.why_it_matters,
            "maturity": s.summary.maturity,
            "action": s.summary.action,
            "categories": s.summary.categories or [],
        },
        "items": [
            {
                "id": it.id,
                "source_key": it.source_key,
                "title": it.title,
                "url": it.url,
                "description": it.description,
            }
            for it in (s.items or [])
        ],
    }


def empty_state() -> None:
    st.info("Chưa có dữ liệu, vào Admin để chạy pipeline")
