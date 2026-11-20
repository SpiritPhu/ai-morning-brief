"""Build daily brief + CDO executive outlook."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings, load_yaml
from app.db.models import Item, ItemMetric
from app.db.repository import get_stories_by_date, save_brief
from app.db.schema_utils import ensure_schema
from app.llm.client import LLMClient
from app.llm.prompts import (
    CDO_BRIEF_SYSTEM,
    CDO_BRIEF_USER,
    DAILY_TLDR_SYSTEM,
    DAILY_TLDR_USER,
)


class DailyTldrOut(BaseModel):
    tldr: list[str] = Field(default_factory=list)
    theme_of_the_day: str = ""
    poc_candidates: list[dict[str, Any]] = Field(default_factory=list)


class TechRadarItem(BaseModel):
    name: str
    ring: str = "assess"
    why: str = ""


class CdoBriefOut(BaseModel):
    executive_headline: str = ""
    trend_summary: str = ""
    strategic_signals: list[str] = Field(default_factory=list)
    technology_radar: list[TechRadarItem] = Field(default_factory=list)
    enterprise_implications: str = ""
    decisions_to_consider: list[str] = Field(default_factory=list)
    watchlist_lens: str = ""
    growth_nudge: str = ""
    deep_dive_suggestion: str = ""


def _select_top_stories(stories: list, top_n: int = 10) -> list:
    selected = []
    topic_counts: Counter[str] = Counter()
    watchlist_picked = False
    for s in stories:
        if s.watchlist_matches and not watchlist_picked:
            selected.append(s)
            topic_counts[(s.topics or ["?"])[0] if s.topics else "?"] += 1
            watchlist_picked = True
            break
    for s in stories:
        if s in selected:
            continue
        primary_topic = (s.topics or ["?"])[0] if s.topics else "?"
        if topic_counts[primary_topic] >= 3:
            continue
        selected.append(s)
        topic_counts[primary_topic] += 1
        if len(selected) >= top_n:
            break
    for s in stories:
        if len(selected) >= top_n:
            break
        if s not in selected:
            selected.append(s)
    return selected


def _rising(session: Session, target_date: date) -> dict[str, list[dict[str, Any]]]:
    def top_metric(source_keys: list[str], metric: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = session.execute(
            select(Item, ItemMetric)
            .join(ItemMetric, ItemMetric.item_id == Item.id)
            .where(
                Item.source_key.in_(source_keys),
                ItemMetric.snapshot_date == target_date,
                ItemMetric.metric_name == metric,
            )
            .order_by(ItemMetric.value.desc())
            .limit(limit)
        ).all()
        out = []
        for item, met in rows:
            appeared_candidates = []
            for ts in (item.published_at, item.first_seen_at):
                if ts is None:
                    continue
                appeared_candidates.append(
                    ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
                )
            desc = (item.description or "").strip().replace("\n", " ")
            if len(desc) > 160:
                desc = desc[:159].rstrip() + "…"
            out.append(
                {
                    "title": item.title,
                    "url": item.url,
                    "description": desc,
                    "first_appeared": min(appeared_candidates) if appeared_candidates else "",
                    "metric": metric,
                    "value": met.value,
                    "source": item.source_key,
                }
            )
        return out

    return {
        "repos": top_metric(["github_trending", "github_search"], "stars_today"),
        "models_spaces": top_metric(["hf_models", "hf_spaces"], "likes"),
        "papers": top_metric(["hf_papers"], "upvotes"),
    }


def _cdo_fallback(theme: str, top: list, topic_dist: Counter[str]) -> dict[str, Any]:
    top_topics = ", ".join(t for t, _ in topic_dist.most_common(3)) or "AI"
    return {
        "executive_headline": theme or f"Tín hiệu ngày xoay quanh {top_topics}",
        "trend_summary": (
            f"Hôm nay các tín hiệu tập trung ở {top_topics}. "
            "Ưu tiên đọc các story có maturity early-oss/production-ready và khớp watchlist."
        ),
        "strategic_signals": [
            (s.summary.title_vi if s.summary else s.title)[:120] for s in top[:3]
        ],
        "technology_radar": [],
        "enterprise_implications": (
            "Rà soát AI roadmap xem tín hiệu hôm nay có đổi thứ tự ưu tiên PoC, "
            "platform, hay risk/governance không."
        ),
        "decisions_to_consider": [
            "Story nào đáng share với leadership tuần này?",
            "Có tín hiệu nào cần trial trong 2 tuần tới?",
        ],
        "watchlist_lens": "Đối chiếu tin nóng với watchlist SOC AI / RAG / Agents / ASR.",
        "growth_nudge": "Với mỗi tin lớn, hỏi: đây là noise, capability mới, hay đổi luật chơi?",
        "deep_dive_suggestion": top_topics,
    }


def _render_markdown(
    target_date: date,
    tldr: list[str],
    theme: str,
    top_stories: list,
    rising: dict,
    big_tech: dict,
    pocs: list,
    cdo: dict[str, Any],
) -> str:
    lines = [f"# AI Morning Brief – {target_date.isoformat()}", ""]
    if cdo.get("executive_headline"):
        lines += ["## CDO Brief", f"**{cdo['executive_headline']}**", ""]
        if cdo.get("trend_summary"):
            lines += [cdo["trend_summary"], ""]
        if cdo.get("strategic_signals"):
            lines.append("### Strategic signals")
            for s in cdo["strategic_signals"]:
                lines.append(f"- {s}")
            lines.append("")
        if cdo.get("technology_radar"):
            lines.append("### Technology radar")
            for r in cdo["technology_radar"]:
                if isinstance(r, dict):
                    lines.append(
                        f"- **{r.get('name')}** `{r.get('ring', 'assess')}` — {r.get('why', '')}"
                    )
            lines.append("")
        if cdo.get("enterprise_implications"):
            lines += ["### Enterprise implications", cdo["enterprise_implications"], ""]
        if cdo.get("decisions_to_consider"):
            lines.append("### Decisions to consider")
            for d in cdo["decisions_to_consider"]:
                lines.append(f"- {d}")
            lines.append("")
        if cdo.get("watchlist_lens"):
            lines += [f"**Watchlist lens:** {cdo['watchlist_lens']}", ""]
        if cdo.get("growth_nudge"):
            lines += [f"**Growth nudge:** {cdo['growth_nudge']}", ""]
        if cdo.get("deep_dive_suggestion"):
            lines += [f"**Deep dive:** {cdo['deep_dive_suggestion']}", ""]

    if theme:
        lines += [f"**Theme:** {theme}", ""]
    lines.append("## TL;DR")
    for t in tldr:
        lines.append(f"- {t}")
    lines += ["", "## Top Stories"]
    for s in top_stories:
        title = s.summary.title_vi if s.summary else s.title
        lines.append(f"### [{title}]({s.canonical_url or '#'})")
        if s.summary:
            lines.append(s.summary.summary)
            if s.summary.why_it_matters:
                lines.append(f"*Vì sao quan trọng:* {s.summary.why_it_matters}")
        lines.append("")
    lines.append("## Rising Now")
    for section, rows in rising.items():
        lines.append(f"### {section}")
        for r in rows:
            lines.append(f"- [{r['title']}]({r['url']}) — {r['metric']}={r['value']}")
    lines += ["", "## Big Tech"]
    for org, rows in big_tech.items():
        lines.append(f"### {org}")
        for r in rows:
            lines.append(f"- [{r['title']}]({r['url']})")
    if pocs:
        lines += ["", "## PoC Candidates"]
        for p in pocs:
            lines.append(
                f"- **#{p.get('story_id')}**: {p.get('reason')} — {p.get('suggested_experiment')}"
            )
    return "\n".join(lines)


def build_daily_brief(session: Session, target_date: date) -> dict[str, Any]:
    ensure_schema()
    stories = get_stories_by_date(session, target_date)
    top = _select_top_stories(stories, top_n=10)
    rising = _rising(session, target_date)

    big_tech: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in stories:
        if not s.is_big_tech:
            continue
        org = s.organization or "other"
        big_tech[org].append(
            {"story_id": s.id, "title": s.title, "url": s.canonical_url or ""}
        )

    client = LLMClient(get_settings())
    stories_payload = []
    for s in stories[:15]:
        stories_payload.append(
            {
                "story_id": s.id,
                "title_vi": s.summary.title_vi if s.summary else s.title,
                "summary": s.summary.summary if s.summary else "",
                "why_it_matters": s.summary.why_it_matters if s.summary else "",
                "categories": (s.summary.categories if s.summary else s.topics) or [],
                "score": s.importance_score,
                "action": s.summary.action if s.summary else "read",
                "maturity": s.summary.maturity if s.summary else "research",
                "watchlist": s.watchlist_matches or [],
            }
        )
    fallback = {
        "tldr": [
            f"{(s.summary.title_vi if s.summary else s.title)[:60]} [#{s.id}]"
            for s in top[:5]
        ],
        "theme_of_the_day": "Cập nhật công nghệ AI trong ngày",
        "poc_candidates": [],
    }
    for s in stories[:15]:
        if s.summary and (
            s.summary.action == "try-poc"
            or s.summary.maturity in ("early-oss", "production-ready")
        ):
            if len(fallback["poc_candidates"]) < 3:
                fallback["poc_candidates"].append(
                    {
                        "story_id": s.id,
                        "reason": s.summary.why_it_matters or s.summary.summary,
                        "suggested_experiment": f"Thử PoC với: {s.title}",
                    }
                )

    tldr_out = client.chat_json(
        DAILY_TLDR_SYSTEM,
        DAILY_TLDR_USER.format(stories_json=json.dumps(stories_payload, ensure_ascii=False)),
        DailyTldrOut,
        fallback=fallback,
    )

    topic_dist: Counter[str] = Counter()
    for s in stories:
        for t in s.topics or []:
            topic_dist[t] += 1

    source_counts: Counter[str] = Counter()
    for s in stories:
        for it in s.items or []:
            source_counts[it.source_key] += 1

    watchlist = [w.get("name") for w in (load_yaml("watchlist") or [])]
    cdo_fallback = _cdo_fallback(tldr_out.theme_of_the_day, top, topic_dist)
    cdo_out = client.chat_json(
        CDO_BRIEF_SYSTEM,
        CDO_BRIEF_USER.format(
            brief_date=target_date.isoformat(),
            theme=tldr_out.theme_of_the_day,
            watchlist=json.dumps(watchlist, ensure_ascii=False),
            topic_stats=json.dumps(dict(topic_dist.most_common(12)), ensure_ascii=False),
            stories_json=json.dumps(stories_payload, ensure_ascii=False),
            rising_json=json.dumps(rising, ensure_ascii=False),
        ),
        CdoBriefOut,
        fallback=cdo_fallback,
    )
    cdo_brief = cdo_out.model_dump()

    stats = {
        "items_by_source": dict(source_counts),
        "story_count": len(stories),
        "topic_distribution": dict(topic_dist),
    }

    md = _render_markdown(
        target_date,
        tldr_out.tldr,
        tldr_out.theme_of_the_day,
        top,
        rising,
        dict(big_tech),
        tldr_out.poc_candidates,
        cdo_brief,
    )

    brief = save_brief(
        session,
        {
            "brief_date": target_date,
            "tldr": tldr_out.tldr,
            "top_story_ids": [s.id for s in top],
            "rising": rising,
            "big_tech": dict(big_tech),
            "poc_candidates": tldr_out.poc_candidates,
            "stats": stats,
            "cdo_brief": cdo_brief,
            "markdown": md,
            "theme_of_the_day": tldr_out.theme_of_the_day,
        },
    )
    session.commit()
    logger.info("brief saved for {} (with CDO section)", target_date)
    return {"brief_id": brief.id, "markdown": md, "cdo_brief": cdo_brief}
