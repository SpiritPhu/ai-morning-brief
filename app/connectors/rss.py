"""RSS feed connector for blogs."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
from loguru import logger

from app.connectors.base import BaseConnector, NormalizedItem, canonicalize_url


def parse_rss_feed(
    feed_text: str,
    *,
    feed_name: str,
    organization: str | None,
    is_big_tech: bool,
    weight: float,
    target_date: date,
    hours_window: int = 48,
) -> list[NormalizedItem]:
    feed = feedparser.parse(feed_text)
    start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc) - timedelta(
        hours=hours_window
    )
    end = datetime.combine(target_date, datetime.max.time(), tzinfo=timezone.utc) + timedelta(hours=12)
    items: list[NormalizedItem] = []
    for entry in feed.entries:
        link = entry.get("link") or ""
        if not link:
            continue
        published = _entry_dt(entry)
        if published and not (start <= published <= end):
            continue
        external_id = entry.get("id") or canonicalize_url(link) or link
        items.append(
            NormalizedItem(
                source_key="rss",
                external_id=str(external_id),
                item_type="blog",
                title=(entry.get("title") or "").strip(),
                url=link,
                description=(entry.get("summary") or entry.get("description") or "")[:2000],
                authors=[a.get("name") for a in (entry.get("authors") or []) if a.get("name")],
                organization=organization,
                published_at=published,
                metrics={},
                extra={
                    "feed_name": feed_name,
                    "is_big_tech": is_big_tech,
                    "weight": weight,
                },
            )
        )
    return items


def _entry_dt(entry: dict[str, Any]) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            return datetime(*st[:6], tzinfo=timezone.utc)
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            try:
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


class RSSConnector(BaseConnector):
    key = "rss"
    item_type = "blog"

    def fetch(self, target_date: date) -> list[NormalizedItem]:
        feeds = self.params.get("feeds") or []
        hours_window = int(self.params.get("hours_window", 48))
        out: list[NormalizedItem] = []
        for feed in feeds:
            url = (feed.get("url") or "").strip()
            name = feed.get("name") or url
            if not url:
                logger.info("rss skip empty url: {}", name)
                continue
            try:
                resp = self.http.get(url)
                if resp.status_code != 200:
                    logger.warning("rss HTTP {} for {}", resp.status_code, name)
                    continue
                out.extend(
                    parse_rss_feed(
                        resp.text,
                        feed_name=name,
                        organization=feed.get("organization"),
                        is_big_tech=bool(feed.get("is_big_tech")),
                        weight=float(feed.get("weight", 1.0)),
                        target_date=target_date,
                        hours_window=hours_window,
                    )
                )
            except Exception as exc:
                logger.warning("rss feed {} failed: {}", name, exc)
        return out
