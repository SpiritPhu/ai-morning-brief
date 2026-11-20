"""Weekly review + LLM summary."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.llm.client import LLMClient
from app.llm.prompts import WEEKLY_SUMMARY_SYSTEM, WEEKLY_SUMMARY_USER
from dashboard.db_util import empty_state, load_stories_range

st.set_page_config(page_title="Weekly Review", layout="wide")
st.title("Weekly Review")

week_end = st.date_input("Tuần kết thúc", value=date.today())
week_start = week_end - timedelta(days=6)
stories = load_stories_range(week_start, week_end)
if not stories:
    empty_state()
    st.stop()

top = stories[:10]
st.subheader("Top 10 story của tuần")
for s in top:
    title = (s.get("summary") or {}).get("title_vi") or s.get("title")
    st.markdown(
        f"- **{s.get('importance_score', 0):.2f}** [{title}]({s.get('canonical_url')}) "
        f"— {', '.join(s.get('topics') or [])}"
    )

# topic delta vs previous week
prev = load_stories_range(week_start - timedelta(days=7), week_start - timedelta(days=1))
from collections import Counter

cur_t = Counter(t for s in stories for t in (s.get("topics") or []))
prev_t = Counter(t for s in prev for t in (s.get("topics") or []))
delta = {k: cur_t[k] - prev_t.get(k, 0) for k in set(cur_t) | set(prev_t)}
st.subheader("Topic tăng/giảm")
st.write(dict(sorted(delta.items(), key=lambda x: -x[1])[:15]))

st.subheader("PoC candidates")
for s in stories:
    summary = s.get("summary") or {}
    if summary.get("action") == "try-poc" or summary.get("maturity") in (
        "early-oss",
        "production-ready",
    ):
        st.markdown(f"- [{summary.get('title_vi') or s.get('title')}]({s.get('canonical_url')})")

class WeeklyOut(BaseModel):
    markdown: str = Field(default="")

if st.button("Generate weekly summary"):
    client = LLMClient()
    payload = [
        {
            "title": (s.get("summary") or {}).get("title_vi") or s.get("title"),
            "summary": (s.get("summary") or {}).get("summary"),
            "topics": s.get("topics"),
            "score": s.get("importance_score"),
        }
        for s in top
    ]
    out = client.chat_json(
        WEEKLY_SUMMARY_SYSTEM,
        WEEKLY_SUMMARY_USER.format(
            week_label=f"{week_start} → {week_end}",
            stories_json=json.dumps(payload, ensure_ascii=False),
        ),
        WeeklyOut,
        fallback={
            "markdown": "\n".join(
                f"- {(s.get('summary') or {}).get('title_vi') or s.get('title')}" for s in top
            )
        },
    )
    st.session_state["weekly_md"] = out.markdown

md = st.session_state.get("weekly_md", "")
if md:
    st.markdown(md)
    st.download_button("Tải Markdown", data=md, file_name=f"weekly-{week_end}.md")
