"""Pipeline runner."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.repository import (
    finish_pipeline_run,
    get_brief,
    start_pipeline_run,
)
from app.db.schema_utils import ensure_schema
from app.db.session import SessionLocal
from app.embeddings import embed_items_missing
from app.pipeline.brief import build_daily_brief
from app.pipeline.classify import classify
from app.pipeline.collect import collect
from app.pipeline.dedup import dedup
from app.pipeline.notify import notify_brief
from app.pipeline.score import score
from app.pipeline.summarize import summarize

ALL_STEPS = ["collect", "embed", "dedup", "classify", "score", "summarize", "brief", "notify"]


def today_in_tz() -> date:
    tz = ZoneInfo(get_settings().tz)
    return datetime.now(tz).date()


def run_pipeline(
    target_date: Optional[date] = None,
    steps: Optional[list[str]] = None,
    skip: Optional[list[str]] = None,
    session: Optional[Session] = None,
) -> dict[str, Any]:
    target_date = target_date or today_in_tz()
    skip = set(skip or [])
    selected = steps or ALL_STEPS
    selected = [s for s in selected if s not in skip]

    own_session = session is None
    session = session or SessionLocal()
    ensure_schema()
    run = start_pipeline_run(session, target_date)
    session.commit()

    step_status: dict[str, Any] = {}
    errors: list[str] = []
    brief_payload: dict[str, Any] = {}

    def do(name: str, fn) -> None:
        if name not in selected:
            step_status[name] = "skipped"
            return
        try:
            result = fn()
            step_status[name] = {"ok": True, "result": result}
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("step {} failed", name)
            step_status[name] = {"ok": False, "error": str(exc)}
            errors.append(f"{name}: {exc}")

    try:
        do("collect", lambda: collect(session, target_date))
        do("embed", lambda: {"embedded": embed_items_missing(session)})
        do("dedup", lambda: dedup(session, target_date))
        do("classify", lambda: classify(session, target_date))
        do("score", lambda: score(session, target_date))
        do("summarize", lambda: summarize(session, target_date))

        def _brief():
            nonlocal brief_payload
            brief_payload = build_daily_brief(session, target_date)
            return {"brief_id": brief_payload.get("brief_id")}

        do("brief", _brief)

        def _notify():
            brief = get_brief(session, target_date)
            if not brief:
                return {"skipped": "no brief"}
            payload = {
                "brief_date": brief.brief_date,
                "tldr": brief.tldr,
                "top_story_ids": brief.top_story_ids,
                "markdown": brief.markdown,
            }
            return notify_brief(payload)

        do("notify", _notify)

        if errors:
            status = "partial" if any(v.get("ok") for v in step_status.values() if isinstance(v, dict)) else "failed"
        else:
            status = "success"
        finish_pipeline_run(session, run, status, step_status, error="; ".join(errors) or None)
        session.commit()
        return {
            "status": status,
            "step_status": step_status,
            "date": target_date.isoformat(),
            "markdown": brief_payload.get("markdown", ""),
        }
    finally:
        if own_session:
            session.close()
