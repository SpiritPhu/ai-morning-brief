"""arXiv API connector."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import feedparser
from loguru import logger

from app.connectors.base import BaseConnector, NormalizedItem


def parse_arxiv_feed(feed_text: str, target_date: date, hours_window: int = 36) -> list[NormalizedItem]:
    feed = feedparser.parse(feed_text)
    start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc) - timedelta(
        hours=hours_window
    )
    end = datetime.combine(target_date, datetime.max.time(), tzinfo=timezone.utc) + timedelta(hours=12)
    items: list[NormalizedItem] = []
    for entry in feed.entries:
        arxiv_id = (entry.get("id") or "").split("/abs/")[-1]
        arxiv_id = arxiv_id.split("v")[0] if arxiv_id else ""
        if not arxiv_id:
            continue
        published = _entry_dt(entry)
        if published and not (start <= published <= end):
            continue
        authors = [a.get("name") for a in (entry.get("authors") or []) if a.get("name")]
        items.append(
            NormalizedItem(
                source_key="arxiv",
                external_id=arxiv_id,
                item_type="paper",
                title=entry.get("title", "").replace("\n", " ").strip(),
                url=f"https://arxiv.org/abs/{arxiv_id}",
                description=(entry.get("summary") or "").replace("\n", " ")[:2000],
                authors=authors,
                published_at=published,
                metrics={},
                extra={"arxiv_id": arxiv_id},
            )
        )
    return items


def _entry_dt(entry: dict) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            return datetime(*st[:6], tzinfo=timezone.utc)
    return None


class ArxivConnector(BaseConnector):
    key = "arxiv"
    item_type = "paper"

    def fetch(self, target_date: date) -> list[NormalizedItem]:
        cats = self.params.get("categories") or ["cs.AI", "cs.CL", "cs.LG"]
        max_results = int(self.params.get("max_results", 200))
        hours_window = int(self.params.get("hours_window", 36))
        query = "+OR+".join(f"cat:{c}" for c in cats)
        url = (
            "http://export.arxiv.org/api/query"
            f"?search_query={query}&sortBy=submittedDate&sortOrder=descending"
            f"&max_results={max_results}"
        )
        # single request for all cats; sleep once to be polite
        time.sleep(3)
        resp = self.http.get(url)
        if resp.status_code != 200:
            logger.warning("arxiv HTTP {}", resp.status_code)
            return []
        return parse_arxiv_feed(resp.text, target_date, hours_window=hours_window)
