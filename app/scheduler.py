"""APScheduler entrypoint for worker."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.config import get_settings, load_yaml
from app.db.repository import get_brief
from app.db.session import SessionLocal
from app.pipeline.collect import collect
from app.pipeline.runner import run_pipeline, today_in_tz


def run_migrations() -> None:
    from app.db.types_compat import is_sqlite

    if is_sqlite():
        logger.info("SQLite mode: create_all")
        from app.db import models  # noqa: F401
        from app.db.base import Base
        from app.db.session import get_engine

        Base.metadata.create_all(get_engine())
        return
    logger.info("Running alembic upgrade head")
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])


def job_daily() -> None:
    logger.info("Daily pipeline job start")
    run_pipeline()


def job_metric_snapshot() -> None:
    logger.info("Evening metric snapshot")
    session = SessionLocal()
    try:
        collect(session, today_in_tz())
    finally:
        session.close()


def job_weekly_trending() -> None:
    logger.info("Monday weekly trending collect")
    # temporarily force weekly since via config mutation in-memory
    sources = load_yaml("sources")
    cfg = (sources.get("connectors") or {}).get("github_trending") or {}
    params = dict(cfg.get("params") or {})
    params["since"] = "weekly"
    from app.config import get_settings
    from app.connectors.github_trending import GitHubTrendingConnector
    from app.db.repository import upsert_item, upsert_metric
    from app.connectors.base import canonicalize_url

    settings = get_settings()
    connector = GitHubTrendingConnector(settings, {**cfg, "params": params})
    session = SessionLocal()
    try:
        items = connector.safe_fetch(today_in_tz())
        for ni in items:
            row = upsert_item(
                session,
                {
                    "source_key": ni.source_key,
                    "external_id": ni.external_id,
                    "item_type": ni.item_type,
                    "title": ni.title,
                    "url": ni.url,
                    "canonical_url": canonicalize_url(ni.url) or ni.url,
                    "description": ni.description or "",
                    "authors": ni.authors,
                    "organization": ni.organization,
                    "published_at": ni.published_at,
                    "extra": {**(ni.extra or {}), "since": "weekly"},
                },
            )
            for k, v in (ni.metrics or {}).items():
                upsert_metric(session, row.id, today_in_tz(), k, float(v))
        session.commit()
    finally:
        session.close()


def maybe_catchup() -> None:
    settings = get_settings()
    tz = ZoneInfo(settings.tz)
    now = datetime.now(tz)
    today = now.date()
    scheduled = now.replace(
        hour=settings.brief_schedule_hour,
        minute=settings.brief_schedule_minute,
        second=0,
        microsecond=0,
    )
    session = SessionLocal()
    try:
        brief = get_brief(session, today)
        if brief is None and now >= scheduled:
            logger.info("Catch-up: no brief for today and past schedule — running now")
            run_pipeline(today)
    finally:
        session.close()


def main() -> None:
    run_migrations()
    settings = get_settings()
    tz = settings.tz
    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        job_daily,
        CronTrigger(
            hour=settings.brief_schedule_hour,
            minute=settings.brief_schedule_minute,
            timezone=tz,
        ),
        id="daily_brief",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        job_weekly_trending,
        CronTrigger(day_of_week="mon", hour=6, minute=30, timezone=tz),
        id="weekly_trending",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        job_metric_snapshot,
        CronTrigger(hour=18, minute=0, timezone=tz),
        id="metric_snapshot",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    # monthly trending on day 1
    scheduler.add_job(
        job_weekly_trending,  # reuse with monthly override inside if needed
        CronTrigger(day=1, hour=6, minute=45, timezone=tz),
        id="monthly_trending",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    maybe_catchup()
    logger.info("Scheduler started (tz={})", tz)
    scheduler.start()


if __name__ == "__main__":
    main()
