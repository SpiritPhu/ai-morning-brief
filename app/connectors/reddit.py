"""Reddit top posts connector."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from loguru import logger

from app.connectors.base import BaseConnector, NormalizedItem


def parse_reddit_listing(data: dict[str, Any], subreddit: str, target_date: date) -> list[NormalizedItem]:
    items: list[NormalizedItem] = []
    children = (data.get("data") or {}).get("children") or []
    for child in children:
        post = child.get("data") or {}
        if post.get("stickied"):
            continue
        post_id = post.get("id")
        if not post_id:
            continue
        permalink = post.get("permalink") or ""
        url = post.get("url_overridden_by_dest") or post.get("url") or f"https://reddit.com{permalink}"
        created = post.get("created_utc")
        published_at = (
            datetime.fromtimestamp(created, tz=timezone.utc)
            if created
            else datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
        )
        items.append(
            NormalizedItem(
                source_key="reddit",
                external_id=f"{subreddit}:{post_id}",
                item_type="community",
                title=post.get("title") or "",
                url=url,
                description=(post.get("selftext") or "")[:2000],
                published_at=published_at,
                metrics={
                    "upvotes": float(post.get("score") or 0),
                    "comments": float(post.get("num_comments") or 0),
                },
                extra={
                    "subreddit": subreddit,
                    "permalink": f"https://reddit.com{permalink}",
                },
            )
        )
    return items


class RedditConnector(BaseConnector):
    key = "reddit"
    item_type = "community"

    def fetch(self, target_date: date) -> list[NormalizedItem]:
        subs = self.params.get("subreddits") or ["MachineLearning", "LocalLLaMA"]
        limit = int(self.params.get("limit", 25))
        headers = {"User-Agent": self.settings.reddit_user_agent or self.settings.user_agent}
        out: list[NormalizedItem] = []
        for sub in subs:
            url = f"https://www.reddit.com/r/{sub}/top.json"
            try:
                resp = self.http.get(url, params={"t": "day", "limit": limit}, headers=headers)
            except Exception as exc:
                logger.warning("reddit r/{} failed: {}", sub, exc)
                continue
            if resp.status_code in (403, 429):
                logger.warning("reddit r/{} HTTP {} — skip", sub, resp.status_code)
                continue
            if resp.status_code != 200:
                logger.warning("reddit r/{} HTTP {}", sub, resp.status_code)
                continue
            out.extend(parse_reddit_listing(resp.json(), sub, target_date))
        return out
