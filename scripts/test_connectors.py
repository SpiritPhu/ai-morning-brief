#!/usr/bin/env python
"""Smoke-test connectors without writing to DB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loguru import logger

from app.config import get_settings, load_yaml
from app.connectors.registry import get_connector, list_connectors
from app.pipeline.runner import today_in_tz


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=str, default=None)
    args = parser.parse_args()
    settings = get_settings()
    keys = [args.only] if args.only else list_connectors()
    target = today_in_tz()
    sources = load_yaml("sources")

    for key in keys:
        cfg = (sources.get("connectors") or {}).get(key) or {}
        try:
            conn = get_connector(key, settings, cfg)
            items = conn.safe_fetch(target)
            print(f"\n=== {key}: {len(items)} items ===")
            for it in items[:3]:
                print(f"- {it.title[:80]}")
                print(f"  url={it.url}")
                print(f"  metrics={it.metrics}")
        except Exception as exc:
            logger.error("{}: {}", key, exc)
            print(f"\n=== {key}: ERROR {exc} ===")


if __name__ == "__main__":
    main()
