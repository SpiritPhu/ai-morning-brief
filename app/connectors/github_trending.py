"""GitHub Trending scraper."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from bs4 import BeautifulSoup
from loguru import logger

from app.config import load_yaml
from app.connectors.base import BaseConnector, NormalizedItem


def _collect_ai_keywords() -> set[str]:
    sources = load_yaml("sources")
    keywords = {k.lower() for k in (sources.get("ai_keywords") or [])}
    taxonomy = load_yaml("taxonomy")
    for group in (taxonomy.get("groups") or {}).values():
        for label in group:
            for kw in label.get("keywords") or []:
                keywords.add(str(kw).lower())
    return keywords


def _is_ai(text: str, keywords: set[str]) -> bool:
    lower = text.lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", lower) for kw in keywords if len(kw) > 1)


def parse_trending_html(html: str, target_date: date, since: str = "daily") -> list[NormalizedItem]:
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select("article.Box-row")
    if not rows:
        logger.warning("github_trending: no article.Box-row found — HTML structure may have changed")
        return []

    keywords = _collect_ai_keywords()
    items: list[NormalizedItem] = []
    for rank, row in enumerate(rows, start=1):
        link = row.select_one("h2 a")
        if not link:
            continue
        href = (link.get("href") or "").strip("/")
        parts = href.split("/")
        if len(parts) < 2:
            continue
        full_name = f"{parts[0]}/{parts[1]}"
        desc_el = row.select_one("p")
        description = desc_el.get_text(" ", strip=True) if desc_el else ""
        lang_el = row.select_one("[itemprop=programmingLanguage]")
        language = lang_el.get_text(strip=True) if lang_el else None

        stars = forks = stars_today = 0.0
        for a in row.select("a.Link--muted"):
            href_a = a.get("href") or ""
            text = a.get_text(" ", strip=True).replace(",", "")
            num_m = re.search(r"([\d.]+)", text)
            if not num_m:
                continue
            val = float(num_m.group(1))
            if href_a.endswith("/stargazers"):
                stars = val
            elif href_a.endswith("/forks"):
                forks = val

        today_el = row.select_one("span.d-inline-block.float-sm-right") or row.find(
            string=re.compile(r"stars? (today|this week|this month)", re.I)
        )
        if today_el:
            raw = today_el if isinstance(today_el, str) else today_el.get_text(" ", strip=True)
            m = re.search(r"([\d,]+)\s+stars?", raw.replace(",", ""))
            if m:
                stars_today = float(m.group(1).replace(",", ""))

        blob = f"{full_name} {description}"
        is_ai = _is_ai(blob, keywords)
        items.append(
            NormalizedItem(
                source_key="github_trending",
                external_id=full_name,
                item_type="repo",
                title=full_name,
                url=f"https://github.com/{full_name}",
                description=description,
                organization=parts[0],
                published_at=datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc),
                metrics={
                    "stars": stars,
                    "forks": forks,
                    "stars_today": stars_today,
                    "trending_rank": float(rank),
                },
                extra={
                    "github_repo": full_name,
                    "language": language,
                    "is_ai": is_ai,
                    "since": since,
                },
            )
        )
    # Prefer AI-related but keep all with is_ai flag; filter to AI for brief relevance
    ai_items = [i for i in items if i.extra.get("is_ai")]
    return ai_items or items[:15]


class GitHubTrendingConnector(BaseConnector):
    key = "github_trending"
    item_type = "repo"

    def fetch(self, target_date: date) -> list[NormalizedItem]:
        since = self.params.get("since", "daily")
        url = f"https://github.com/trending?since={since}"
        resp = self.http.get(url)
        if resp.status_code != 200:
            logger.warning("github_trending HTTP {}", resp.status_code)
            return []
        return parse_trending_html(resp.text, target_date, since=since)
