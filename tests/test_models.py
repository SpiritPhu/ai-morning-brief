"""Schema smoke test — skips if DATABASE_URL unreachable."""

from __future__ import annotations

import os
import socket

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def _postgres_reachable(host: str = "localhost", port: int = 5432, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def engine():
    if not _postgres_reachable():
        pytest.skip("Postgres not available")
    url = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://brief:brief@localhost:5432/brief"
    )
    eng = create_engine(url, connect_args={"connect_timeout": 2})
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Postgres not available")
    return eng


def test_tables_exist(engine):
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        rows = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public'
                """
            )
        ).scalars().all()
    if not rows:
        from app.db import models  # noqa: F401
        from app.db.base import Base

        Base.metadata.create_all(engine)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema='public'
                    """
                )
            ).scalars().all()
    expected = {
        "items",
        "stories",
        "item_metrics",
        "story_summaries",
        "daily_briefs",
        "feedback",
        "pipeline_runs",
        "sources",
    }
    assert expected.issubset(set(rows))
