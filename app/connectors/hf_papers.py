"""Hugging Face Daily Papers connector."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from loguru import logger

from app.connectors.base import BaseConnector, NormalizedItem, canonicalize_url


class HFPapersConnector(BaseConnector):
    key = "hf_papers"
    item_type = "paper"

    def fetch(self, target_date: date) -> list[NormalizedItem]:
        url = f"https://huggingface.co/api/daily_papers?date={target_date.isoformat()}"
        resp = self.http.get(url)
        if resp.status_code != 200:
            logger.warning("hf_papers HTTP {}: {}", resp.status_code, resp.text[:200])
            return []
        data = resp.json()
        if not isinstance(data, list):
            data = data.get("papers") or data.get("data") or []

        items: list[NormalizedItem] = []
        for entry in data:
            paper = entry.get("paper") or entry
            arxiv_id = (
                paper.get("id")
                or paper.get("arxiv_id")
                or entry.get("paperId")
                or ""
            )
            if not arxiv_id:
                continue
            title = paper.get("title") or entry.get("title") or arxiv_id
            abs_url = f"https://arxiv.org/abs/{arxiv_id}"
            authors = paper.get("authors") or []
            if authors and isinstance(authors[0], dict):
                author_names = [a.get("name", "") for a in authors]
            else:
                author_names = list(authors)

            github = None
            for link in paper.get("github") or paper.get("githubRepos") or []:
                if isinstance(link, str):
                    github = link
                    break
                if isinstance(link, dict) and link.get("url"):
                    github = link["url"]
                    break

            metrics: dict[str, float] = {}
            if "upvotes" in entry or "upvotes" in paper:
                metrics["upvotes"] = float(entry.get("upvotes") or paper.get("upvotes") or 0)
            if "numComments" in entry or "comments" in entry:
                metrics["comments"] = float(entry.get("numComments") or entry.get("comments") or 0)

            published = entry.get("publishedAt") or paper.get("publishedAt")
            published_at = _parse_dt(published) or datetime.combine(
                target_date, datetime.min.time(), tzinfo=timezone.utc
            )

            extra: dict[str, Any] = {"arxiv_id": str(arxiv_id)}
            if github:
                extra["github_repo"] = canonicalize_url(github)

            items.append(
                NormalizedItem(
                    source_key=self.key,
                    external_id=str(arxiv_id),
                    item_type=self.item_type,
                    title=title,
                    url=abs_url,
                    description=(paper.get("summary") or paper.get("abstract") or "")[:2000],
                    authors=author_names,
                    published_at=published_at,
                    metrics=metrics,
                    extra=extra,
                )
            )
        return items


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_hf_papers_payload(data: list[dict], target_date: date) -> list[NormalizedItem]:
    """Pure parse helper for unit tests."""
    conn = object.__new__(HFPapersConnector)
    conn.key = "hf_papers"
    conn.item_type = "paper"
    # reuse logic via temporary monkey: call fetch body
    items: list[NormalizedItem] = []
    for entry in data:
        paper = entry.get("paper") or entry
        arxiv_id = paper.get("id") or ""
        if not arxiv_id:
            continue
        items.append(
            NormalizedItem(
                source_key="hf_papers",
                external_id=str(arxiv_id),
                item_type="paper",
                title=paper.get("title") or arxiv_id,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                description=(paper.get("summary") or "")[:2000],
                authors=[a.get("name", a) if isinstance(a, dict) else a for a in (paper.get("authors") or [])],
                published_at=datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc),
                metrics={"upvotes": float(entry.get("upvotes") or 0)},
                extra={"arxiv_id": str(arxiv_id)},
            )
        )
    return items
