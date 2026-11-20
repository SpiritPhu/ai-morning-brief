"""GitHub Search API connector."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from loguru import logger

from app.connectors.base import BaseConnector, NormalizedItem


def _format_query(template: str, target_date: date) -> str:
    def repl(days: int) -> str:
        return (target_date - timedelta(days=days)).isoformat()

    out = template
    out = out.replace("{d-7}", repl(7))
    out = out.replace("{d-1}", repl(1))
    out = out.replace("{d}", target_date.isoformat())
    return out


def parse_search_payload(data: dict[str, Any], target_date: date) -> list[NormalizedItem]:
    items: list[NormalizedItem] = []
    for row in data.get("items") or []:
        full_name = row.get("full_name")
        if not full_name:
            continue
        license_obj = row.get("license") or {}
        items.append(
            NormalizedItem(
                source_key="github_search",
                external_id=full_name,
                item_type="repo",
                title=full_name,
                url=row.get("html_url") or f"https://github.com/{full_name}",
                description=row.get("description") or "",
                organization=(full_name.split("/")[0]),
                published_at=_parse(row.get("created_at"))
                or datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc),
                metrics={
                    "stars": float(row.get("stargazers_count") or 0),
                    "forks": float(row.get("forks_count") or 0),
                    "open_issues": float(row.get("open_issues_count") or 0),
                },
                extra={
                    "github_repo": full_name,
                    "topics": row.get("topics") or [],
                    "license": license_obj.get("spdx_id") or license_obj.get("key"),
                    "created_at": row.get("created_at"),
                    "pushed_at": row.get("pushed_at"),
                },
            )
        )
    return items


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class GitHubSearchConnector(BaseConnector):
    key = "github_search"
    item_type = "repo"

    def fetch(self, target_date: date) -> list[NormalizedItem]:
        queries = self.params.get("queries") or []
        per_page = int(self.params.get("per_page", 30))
        headers = {"Accept": "application/vnd.github+json"}
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"

        seen: set[str] = set()
        out: list[NormalizedItem] = []
        for qtmpl in queries:
            q = _format_query(qtmpl, target_date)
            url = "https://api.github.com/search/repositories"
            try:
                resp = self.http.get(
                    url,
                    params={"q": q, "sort": "stars", "order": "desc", "per_page": per_page},
                    headers=headers,
                )
            except Exception as exc:
                logger.warning("github_search query failed {}: {}", q, exc)
                continue
            if resp.status_code != 200:
                logger.warning("github_search HTTP {} for {}", resp.status_code, q)
                continue
            for item in parse_search_payload(resp.json(), target_date):
                if item.external_id in seen:
                    continue
                seen.add(item.external_id)
                out.append(item)
        return out
