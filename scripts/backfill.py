#!/usr/bin/env python
"""Backfill pipeline for N past days."""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loguru import logger

from app.pipeline.runner import run_pipeline, today_in_tz


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    today = today_in_tz()
    for i in range(args.days, 0, -1):
        d = today - timedelta(days=i)
        logger.info("Backfill {}", d)
        # connectors that don't support historical dates will still run "current" views
        result = run_pipeline(target_date=d)
        print(d, result["status"])


if __name__ == "__main__":
    main()
