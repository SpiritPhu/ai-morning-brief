#!/usr/bin/env python
"""Seed sources table from config/sources.yaml."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.config import load_yaml, reload_configs
from app.db.models import Source
from app.db.repository import _insert_stmt
from app.db.session import SessionLocal, reset_engine


def main() -> None:
    reload_configs()
    reset_engine()
    sources = load_yaml("sources")
    connectors = sources.get("connectors") or {}
    session = SessionLocal()
    try:
        for key, cfg in connectors.items():
            stmt = _insert_stmt(Source).values(
                key=key,
                name=key.replace("_", " ").title(),
                type=cfg.get("type", "community"),
                weight=float(cfg.get("weight", 0.5)),
                enabled=bool(cfg.get("enabled", True)),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "type": stmt.excluded.type,
                    "weight": stmt.excluded.weight,
                    "enabled": stmt.excluded.enabled,
                },
            )
            session.execute(stmt)
        session.commit()
        count = len(list(session.scalars(select(Source)).all()))
        print(f"Seeded sources: {count}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
