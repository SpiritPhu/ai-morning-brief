#!/usr/bin/env python
"""Initialize database schema (SQLite create_all or Alembic on Postgres)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loguru import logger

from app.config import get_settings, reload_configs
from app.db.types_compat import is_sqlite


def main() -> None:
    reload_configs()
    settings = get_settings()
    logger.info("DATABASE_URL={}", settings.database_url)

    if is_sqlite():
        from app.db import models  # noqa: F401
        from app.db.base import Base
        from app.db.session import get_engine, reset_engine

        reset_engine()
        engine = get_engine()
        Base.metadata.create_all(engine)
        from app.db.schema_utils import ensure_schema

        ensure_schema()
        logger.info("SQLite schema created/updated")
    else:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])
        logger.info("Alembic upgrade head done")

    # seed sources
    from scripts.seed import main as seed_main

    seed_main()


if __name__ == "__main__":
    main()
