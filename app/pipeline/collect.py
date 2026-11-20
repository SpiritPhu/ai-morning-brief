"""Collect step: run connectors and upsert items/metrics."""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.base import canonicalize_url
from app.connectors.registry import enabled_connectors
from app.db.repository import upsert_item, upsert_metric


def collect(session: Session, target_date: date) -> dict[str, Any]:
    settings = get_settings()
    stats: dict[str, Any] = {}
    for connector in enabled_connectors(settings):
        key = connector.key
        try:
            items = connector.safe_fetch(target_date)
            count = 0
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
                        "extra": ni.extra,
                    },
                )
                for metric_name, value in (ni.metrics or {}).items():
                    upsert_metric(session, row.id, target_date, metric_name, float(value))
                count += 1
            session.commit()
            stats[key] = count
            logger.info("collect {}: {} items", key, count)
        except Exception as exc:
            session.rollback()
            msg = f"error: {exc}"
            stats[key] = msg
            logger.error("collect {} failed: {}", key, exc)
    return stats
