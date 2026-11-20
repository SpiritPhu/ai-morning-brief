"""Lightweight schema patches (SQLite ALTER for new columns)."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import inspect, text

from app.db.session import get_engine
from app.db.types_compat import is_sqlite


def ensure_schema() -> None:
    """Add missing columns on existing SQLite DBs without wiping data."""
    if not is_sqlite():
        return
    engine = get_engine()
    insp = inspect(engine)
    if "daily_briefs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("daily_briefs")}
    if "cdo_brief" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE daily_briefs ADD COLUMN cdo_brief JSON"))
        logger.info("Added daily_briefs.cdo_brief column")
