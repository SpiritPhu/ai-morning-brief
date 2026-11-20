#!/usr/bin/env python
"""Run pipeline manually."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.repository import get_stories_by_date
from app.db.session import SessionLocal
from app.pipeline.runner import ALL_STEPS, run_pipeline, today_in_tz


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI Morning Brief pipeline")
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--only", type=str, default=None, help="comma-separated steps")
    parser.add_argument("--skip", type=str, default=None, help="comma-separated steps")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else today_in_tz()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    skip = [s.strip() for s in args.skip.split(",")] if args.skip else None
    if only:
        unknown = set(only) - set(ALL_STEPS)
        if unknown:
            raise SystemExit(f"Unknown steps: {unknown}")

    result = run_pipeline(target_date=target, steps=only, skip=skip)
    print(f"Status: {result['status']} date={result['date']}")
    if result.get("markdown"):
        print("\n===== BRIEF MARKDOWN =====\n")
        try:
            print(result["markdown"])
        except UnicodeEncodeError:
            out = ROOT / "data" / f"brief-{result['date']}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(result["markdown"], encoding="utf-8")
            print(f"(console encoding limited) wrote {out}")
            sys.stdout.buffer.write((result["markdown"][:1500] + "\n").encode("utf-8", errors="replace"))


    session = SessionLocal()
    try:
        stories = get_stories_by_date(session, target)[:15]
        print("\n===== TOP 15 STORIES =====")
        for s in stories:
            print(
                f"- [{s.importance_score:.3f}] {s.title[:80]} | "
                f"sources={s.source_count} topics={s.topics} breakdown={s.score_breakdown}"
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
