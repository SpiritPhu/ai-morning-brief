"""LLM summarize top stories."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings, load_yaml
from app.db.models import Story
from app.db.repository import get_stories_by_date, upsert_story_summary
from app.llm.client import LLMClient
from app.llm.prompts import STORY_SUMMARY_SYSTEM, STORY_SUMMARY_USER


class StorySummaryOut(BaseModel):
    title_vi: str
    summary: str
    why_it_matters: str = ""
    categories: list[str] = Field(default_factory=list)
    maturity: str = "research"
    action: str = "read"
    related_watchlist: list[str] = Field(default_factory=list)


def _story_hash(story: Story) -> str:
    parts = [story.title]
    for it in story.items or []:
        parts.append(it.content_hash or it.url)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _taxonomy_names() -> list[str]:
    names: list[str] = []
    for group in (load_yaml("taxonomy").get("groups") or {}).values():
        names.extend(l["name"] for l in group)
    return names


def _summarize_one(story: Story, client: LLMClient) -> dict[str, Any]:
    sources = []
    for it in story.items or []:
        sources.append(
            {
                "source": it.source_key,
                "title": it.title,
                "url": it.url,
                "description": (it.description or "")[:800],
                "metrics": {
                    m.metric_name: m.value for m in (it.metrics or [])
                },
            }
        )
    watchlist = [w["name"] for w in (load_yaml("watchlist") or [])]
    taxonomy = _taxonomy_names()
    user = STORY_SUMMARY_USER.format(
        sources_json=json.dumps(sources, ensure_ascii=False),
        taxonomy=json.dumps(taxonomy, ensure_ascii=False),
        watchlist=json.dumps(watchlist, ensure_ascii=False),
    )
    desc = (story.items[0].description if story.items else story.title) or story.title
    fallback = {
        "title_vi": story.title[:80],
        "summary": desc[:300],
        "why_it_matters": "",
        "categories": list(story.topics or [])[:3],
        "maturity": "research",
        "action": "read",
        "related_watchlist": list(story.watchlist_matches or []),
    }
    out = client.chat_json(STORY_SUMMARY_SYSTEM, user, StorySummaryOut, fallback=fallback)
    valid = set(taxonomy)
    categories = [c for c in out.categories if c in valid][:3]
    return {
        "title_vi": out.title_vi,
        "summary": out.summary,
        "why_it_matters": out.why_it_matters,
        "categories": categories or list(story.topics or [])[:3],
        "maturity": out.maturity,
        "action": out.action,
        "related_watchlist": [w for w in out.related_watchlist if w in watchlist],
        "llm_model": client.settings.llm_model if not client.no_llm else "no-llm",
        "content_hash": _story_hash(story),
    }


def summarize(session: Session, target_date: date) -> dict[str, int]:
    settings = get_settings()
    stories = get_stories_by_date(session, target_date)
    top = stories[: settings.llm_max_items_per_day]
    client = LLMClient(settings)

    to_process: list[Story] = []
    skipped = 0
    for story in top:
        ch = _story_hash(story)
        if story.summary and story.summary.content_hash == ch:
            skipped += 1
            continue
        to_process.append(story)

    results: dict[int, dict[str, Any]] = {}

    def work(s: Story) -> tuple[int, dict[str, Any]]:
        return s.id, _summarize_one(s, client)

    if client.no_llm or len(to_process) <= 1:
        for s in to_process:
            results[s.id] = _summarize_one(s, client)
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = [pool.submit(work, s) for s in to_process]
            for fut in as_completed(futs):
                sid, data = fut.result()
                results[sid] = data

    for story in to_process:
        data = results[story.id]
        upsert_story_summary(session, story.id, data)
        if data.get("categories"):
            story.topics = data["categories"]

    session.commit()
    logger.info("summarize: {} done, {} skipped", len(to_process), skipped)
    return {"summarized": len(to_process), "skipped": skipped}
