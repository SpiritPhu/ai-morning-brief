"""Hacker News Algolia connector."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from loguru import logger

from app.connectors.base import BaseConnector, NormalizedItem


def parse_hn_hits(data: dict[str, Any], target_date: date) -> list[NormalizedItem]:
    items: list[NormalizedItem] = []
    for hit in data.get("hits") or []:
        object_id = hit.get("objectID")
        if not object_id:
            continue
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
        created = hit.get("created_at")
        published_at = None
        if created:
            try:
                published_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                published_at = None
        items.append(
            NormalizedItem(
                source_key="hackernews",
                external_id=str(object_id),
                item_type="community",
                title=hit.get("title") or "",
                url=url,
                description="",
                published_at=published_at
                or datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc),
                metrics={
                    "points": float(hit.get("points") or 0),
                    "comments": float(hit.get("num_comments") or 0),
                },
                extra={"hn_url": f"https://news.ycombinator.com/item?id={object_id}"},
            )
        )
    return items


class HackerNewsConnector(BaseConnector):
    key = "hackernews"
    item_type = "community"

    def fetch(self, target_date: date) -> list[NormalizedItem]:
        keywords = self.params.get("keywords") or ["LLM", "GPT"]
        min_points = int(self.params.get("min_points", 10))
        ts = int(
            (
                datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
                - timedelta(hours=36)
            ).timestamp()
        )
        seen: set[str] = set()
        out: list[NormalizedItem] = []
        for kw in keywords:
            url = "https://hn.algolia.com/api/v1/search_by_date"
            try:
                resp = self.http.get(
                    url,
                    params={
                        "tags": "story",
                        "query": kw,
                        "numericFilters": f"created_at_i>{ts},points>{min_points}",
                        "hitsPerPage": 30,
                    },
                )
            except Exception as exc:
                logger.warning("hackernews kw={} failed: {}", kw, exc)
                continue
            if resp.status_code != 200:
                logger.warning("hackernews HTTP {} for {}", resp.status_code, kw)
                continue
            for item in parse_hn_hits(resp.json(), target_date):
                if item.external_id in seen:
                    continue
                seen.add(item.external_id)
                out.append(item)
        return out
