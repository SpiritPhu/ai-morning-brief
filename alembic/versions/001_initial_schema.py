"""Initial schema with pgvector.

Revision ID: 001
Revises:
Create Date: 2026-11-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.config import get_settings

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DIM = get_settings().embedding_dim


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("weight", sa.Float(), server_default="0.5"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
    )

    op.create_table(
        "stories",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("story_date", sa.Date(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("primary_item_id", sa.BigInteger(), nullable=True),
        sa.Column("source_count", sa.Integer(), server_default="1"),
        sa.Column("item_count", sa.Integer(), server_default="1"),
        sa.Column("topics", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("importance_score", sa.Float(), server_default="0"),
        sa.Column("score_breakdown", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_big_tech", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("organization", sa.String(256), nullable=True),
        sa.Column("watchlist_matches", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_stories_story_date", "stories", ["story_date"])
    op.create_index(
        "ix_stories_date_score",
        "stories",
        ["story_date", sa.text("importance_score DESC")],
    )

    op.create_table(
        "items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("authors", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("organization", sa.String(256), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("extra", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("embedding", Vector(_DIM), nullable=True),
        sa.Column("story_id", sa.BigInteger(), sa.ForeignKey("stories.id", ondelete="SET NULL")),
        sa.UniqueConstraint("source_key", "external_id", name="uq_items_source_external"),
    )
    op.create_index("ix_items_published_at", "items", ["published_at"])
    op.create_index("ix_items_story_id", "items", ["story_id"])
    op.create_index("ix_items_source_key", "items", ["source_key"])
    op.create_index("ix_items_content_hash", "items", ["content_hash"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_items_embedding_hnsw "
        "ON items USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "item_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("item_id", sa.BigInteger(), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.UniqueConstraint(
            "item_id", "snapshot_date", "metric_name", name="uq_item_metrics_snapshot"
        ),
    )
    op.create_index("ix_item_metrics_item_date", "item_metrics", ["item_id", "snapshot_date"])

    op.create_table(
        "story_summaries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "story_id",
            sa.BigInteger(),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("title_vi", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), server_default=""),
        sa.Column("maturity", sa.String(32), server_default="research"),
        sa.Column("action", sa.String(32), server_default="read"),
        sa.Column("categories", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("related_watchlist", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("llm_model", sa.String(128), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "daily_briefs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("brief_date", sa.Date(), unique=True, nullable=False),
        sa.Column("tldr", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("top_story_ids", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("rising", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("big_tech", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("poc_candidates", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("stats", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("markdown", sa.Text(), server_default=""),
        sa.Column("theme_of_the_day", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("story_id", sa.BigInteger(), sa.ForeignKey("stories.id", ondelete="CASCADE")),
        sa.Column("vote", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), server_default="running"),
        sa.Column("step_status", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_pipeline_runs_run_date", "pipeline_runs", ["run_date"])


def downgrade() -> None:
    op.drop_table("pipeline_runs")
    op.drop_table("feedback")
    op.drop_table("daily_briefs")
    op.drop_table("story_summaries")
    op.drop_table("item_metrics")
    op.execute("DROP INDEX IF EXISTS ix_items_embedding_hnsw")
    op.drop_table("items")
    op.drop_table("stories")
    op.drop_table("sources")
