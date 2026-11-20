"""ORM models for AI Morning Brief (Postgres + SQLite lite)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db.base import Base
from app.db.types_compat import EmbeddingType, is_sqlite

_DIM = get_settings().embedding_dim


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=0.5)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("source_key", "external_id", name="uq_items_source_external"),
        Index("ix_items_published_at", "published_at"),
        Index("ix_items_story_id", "story_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    organization: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    embedding: Mapped[Optional[list[float]]] = mapped_column(EmbeddingType(_DIM), nullable=True)
    story_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("stories.id", ondelete="SET NULL"), nullable=True
    )

    metrics: Mapped[list[ItemMetric]] = relationship(back_populates="item", cascade="all, delete")
    story: Mapped[Optional[Story]] = relationship(back_populates="items", foreign_keys=[story_id])


class ItemMetric(Base):
    __tablename__ = "item_metrics"
    __table_args__ = (
        UniqueConstraint(
            "item_id", "snapshot_date", "metric_name", name="uq_item_metrics_snapshot"
        ),
        Index("ix_item_metrics_item_date", "item_id", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)

    item: Mapped[Item] = relationship(back_populates="metrics")


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (Index("ix_stories_date_score", "story_date", "importance_score"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_item_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    item_count: Mapped[int] = mapped_column(Integer, default=1)
    topics: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    importance_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_big_tech: Mapped[bool] = mapped_column(Boolean, default=False)
    organization: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    watchlist_matches: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    items: Mapped[list[Item]] = relationship(
        back_populates="story", foreign_keys="Item.story_id"
    )
    summary: Mapped[Optional[StorySummary]] = relationship(
        back_populates="story", uselist=False, cascade="all, delete-orphan"
    )
    feedback: Mapped[list[Feedback]] = relationship(back_populates="story")


class StorySummary(Base):
    __tablename__ = "story_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stories.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    title_vi: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, default="")
    maturity: Mapped[str] = mapped_column(String(32), default="research")
    action: Mapped[str] = mapped_column(String(32), default="read")
    categories: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    related_watchlist: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    llm_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    story: Mapped[Story] = relationship(back_populates="summary")


class DailyBrief(Base):
    __tablename__ = "daily_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brief_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    tldr: Mapped[list[Any]] = mapped_column(JSON, default=list)
    top_story_ids: Mapped[Optional[list[int]]] = mapped_column(JSON, default=list)
    rising: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    big_tech: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    poc_candidates: Mapped[list[Any]] = mapped_column(JSON, default=list)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cdo_brief: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    markdown: Mapped[str] = mapped_column(Text, default="")
    theme_of_the_day: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    vote: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    story: Mapped[Story] = relationship(back_populates="feedback")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    step_status: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# silence unused import warning in type checkers
_ = is_sqlite
