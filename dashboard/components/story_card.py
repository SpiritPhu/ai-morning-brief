"""Reusable story UI pieces."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import streamlit as st

TAXONOMY_COLORS = {
    "Models": "#1f77b4",
    "Agents": "#ff7f0e",
    "Techniques": "#2ca02c",
    "Infra": "#9467bd",
    "Risk": "#d62728",
    "Applied": "#8c564b",
}

TOPIC_GROUP = {
    "LLM": "Models",
    "Multimodal/VLM": "Models",
    "Speech/ASR/TTS": "Models",
    "Vision": "Models",
    "Embedding": "Models",
    "Small/On-device": "Models",
    "Agent framework": "Agents",
    "Coding agent": "Agents",
    "MCP/Tool use": "Agents",
    "Multi-agent": "Agents",
    "Agent memory": "Agents",
    "Fine-tuning/RLHF": "Techniques",
    "Reasoning": "Techniques",
    "RAG/Retrieval": "Techniques",
    "Long context": "Techniques",
    "Quantization/Distillation": "Techniques",
    "Inference/Serving": "Infra",
    "Training infra": "Infra",
    "LLMOps/Observability": "Infra",
    "Evaluation/Benchmark": "Infra",
    "AI Security": "Risk",
    "Safety/Governance": "Risk",
    "License": "Risk",
    "Cybersecurity": "Applied",
    "Document AI/OCR": "Applied",
    "Customer support": "Applied",
    "Finance": "Applied",
    "Healthcare": "Applied",
}


def format_appeared(value: Any) -> str:
    """Normalize datetime/date/str → YYYY-MM-DD."""
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def render_source_badges(items: list[dict]) -> None:
    if not items:
        return
    parts = []
    for it in items:
        label = it.get("source_key")
        url = it.get("url")
        appeared = format_appeared(it.get("first_appeared") or it.get("first_seen_at") or it.get("published_at"))
        suffix = f" · xuất hiện {appeared}" if appeared else ""
        parts.append(f"[{label}]({url}){suffix}")
    st.markdown(" · ".join(parts))


def render_score_bar(breakdown: Optional[dict]) -> None:
    if not breakdown:
        st.caption("No score breakdown")
        return
    for k, v in breakdown.items():
        if k == "importance":
            continue
        try:
            st.progress(min(max(float(v), 0.0), 1.0), text=f"{k}: {float(v):.2f}")
        except Exception:
            st.write(f"{k}: {v}")


def render_story_card(story: dict[str, Any], on_vote=None) -> None:
    summary = story.get("summary") or {}
    title = summary.get("title_vi") or story.get("title")
    url = story.get("canonical_url") or "#"
    st.markdown(f"### [{title}]({url})")

    appeared = format_appeared(story.get("first_appeared"))
    meta_bits = []
    if appeared:
        meta_bits.append(f"Xuất hiện lần đầu: **{appeared}**")
    if story.get("story_date"):
        meta_bits.append(f"Brief ngày: `{story.get('story_date')}`")
    if meta_bits:
        st.caption(" · ".join(meta_bits))

    badges = []
    for t in summary.get("categories") or story.get("topics") or []:
        group = TOPIC_GROUP.get(t, "Models")
        color = TAXONOMY_COLORS.get(group, "#666")
        badges.append(
            f'<span style="background:{color};color:white;padding:2px 6px;'
            f'border-radius:4px;margin-right:4px;font-size:0.8em">{t}</span>'
        )
    if summary:
        if summary.get("maturity"):
            badges.append(
                f'<span style="background:#555;color:white;padding:2px 6px;'
                f'border-radius:4px;margin-right:4px;font-size:0.8em">{summary["maturity"]}</span>'
            )
        if summary.get("action"):
            badges.append(
                f'<span style="background:#333;color:white;padding:2px 6px;'
                f'border-radius:4px;font-size:0.8em">{summary["action"]}</span>'
            )
    if badges:
        st.markdown("".join(badges), unsafe_allow_html=True)
    if summary.get("summary"):
        st.write(summary["summary"])
        if summary.get("why_it_matters"):
            st.markdown(f"**Vì sao quan trọng:** {summary['why_it_matters']}")
    render_source_badges(story.get("items") or [])
    with st.expander("Vì sao xếp hạng"):
        render_score_bar(story.get("score_breakdown"))
    if on_vote:
        c1, c2 = st.columns(2)
        sid = story["id"]
        if c1.button("👍", key=f"up_{sid}"):
            on_vote(sid, 1)
        if c2.button("👎", key=f"down_{sid}"):
            on_vote(sid, -1)
