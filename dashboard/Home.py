"""AI Morning Brief – Home / Daily Brief."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_yaml
from app.db.repository import add_feedback
from dashboard.components.story_card import render_story_card
from dashboard.db_util import (
    empty_state,
    load_brief,
    load_brief_dates,
    load_latest_pipeline,
    load_stories_for_date,
    load_stories_range,
    session_scope,
)

st.set_page_config(page_title="AI Morning Brief", layout="wide")

st.sidebar.title("Filters")
dates = load_brief_dates()
default_date = dates[0] if dates else date.today()
selected = st.sidebar.date_input("Ngày", value=default_date)
mode = st.sidebar.radio("Chế độ", ["Daily", "Weekly", "Monthly"], horizontal=True)
source_filter = st.sidebar.multiselect(
    "Source",
    list((load_yaml("sources").get("connectors") or {}).keys()),
)
watchlist_only = st.sidebar.toggle("Chỉ watchlist", value=False)

brief = load_brief(selected)

# Date window for weekly/monthly
if mode == "Weekly":
    start, end = selected - timedelta(days=6), selected
    stories = load_stories_range(start, end)
elif mode == "Monthly":
    start, end = selected - timedelta(days=29), selected
    stories = load_stories_range(start, end)
else:
    stories = load_stories_for_date(selected)

if not stories and not brief:
    empty_state()
    st.stop()

all_topics = sorted({t for s in stories for t in (s.get("topics") or [])})
topic_filter = st.sidebar.multiselect("Topic", all_topics)

def _filter(slist):
    out = slist
    if topic_filter:
        out = [s for s in out if any(t in topic_filter for t in (s.get("topics") or []))]
    if source_filter:
        out = [
            s
            for s in out
            if any(it.get("source_key") in source_filter for it in (s.get("items") or []))
        ]
    if watchlist_only:
        out = [s for s in out if s.get("watchlist_matches")]
    return out

stories = _filter(stories)
brief = brief or {
    "tldr": [],
    "theme_of_the_day": "",
    "top_story_ids": [s["id"] for s in stories[:10]],
    "rising": {},
    "big_tech": {},
    "poc_candidates": [],
    "stats": {},
    "cdo_brief": {},
    "markdown": "",
}

st.title(f"AI Morning Brief – {selected}")

stats = brief.get("stats") or {}
pipe = load_latest_pipeline()
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Items", sum((stats.get("items_by_source") or {}).values()) if stats else len(stories))
m2.metric("Stories", stats.get("story_count", len(stories)))
m3.metric("Sources", len(stats.get("items_by_source") or {}))
m4.metric("Watchlist", sum(1 for s in stories if s.get("watchlist_matches")))
m5.metric("Pipeline", (pipe or {}).get("status", "n/a"))

cdo = brief.get("cdo_brief") or {}
if cdo:
    st.subheader("① CDO Brief — Tầm nhìn & xu hướng")
    if cdo.get("executive_headline"):
        st.markdown(f"### {cdo['executive_headline']}")
    if cdo.get("trend_summary"):
        st.write(cdo["trend_summary"])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Strategic signals**")
        for sig in cdo.get("strategic_signals") or []:
            st.markdown(f"- {sig}")
        st.markdown("**Decisions to consider**")
        for d in cdo.get("decisions_to_consider") or []:
            st.markdown(f"- {d}")
    with c2:
        st.markdown("**Technology radar**")
        for r in cdo.get("technology_radar") or []:
            if isinstance(r, dict):
                st.markdown(
                    f"- **{r.get('name', '')}** `{r.get('ring', 'assess')}` — {r.get('why', '')}"
                )
        if cdo.get("enterprise_implications"):
            st.markdown("**Enterprise implications**")
            st.write(cdo["enterprise_implications"])
    if cdo.get("watchlist_lens"):
        st.info(f"**Watchlist lens:** {cdo['watchlist_lens']}")
    g1, g2 = st.columns(2)
    if cdo.get("growth_nudge"):
        g1.success(f"**Growth nudge:** {cdo['growth_nudge']}")
    if cdo.get("deep_dive_suggestion"):
        g2.warning(f"**Deep dive tuần này:** {cdo['deep_dive_suggestion']}")
    st.divider()

st.subheader("② TL;DR")
if brief.get("theme_of_the_day"):
    st.markdown(f"**Theme of the day:** {brief['theme_of_the_day']}")
for t in brief.get("tldr") or []:
    st.markdown(f"- {t}")

def on_vote(story_id: int, vote: int):
    with session_scope() as session:
        add_feedback(session, story_id, vote)
    st.toast("Đã ghi feedback")

col_left, col_right = st.columns(2)
with col_left:
    st.subheader("③ Top Stories")
    by_id = {s["id"]: s for s in stories}
    top_ids = brief.get("top_story_ids") or [s["id"] for s in stories[:10]]
    for sid in top_ids:
        s = by_id.get(sid)
        if s:
            render_story_card(s, on_vote=on_vote)
            st.divider()

with col_right:
    st.subheader("④ Rising Now")
    rising = brief.get("rising") or {}
    tabs = st.tabs(["Repos", "Models & Spaces", "Papers"])
    for tab, key in zip(tabs, ["repos", "models_spaces", "papers"]):
        with tab:
            rows = rising.get(key) or []
            if not rows:
                st.caption("Không có dữ liệu")
            else:
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

c3, c4 = st.columns(2)
with c3:
    st.subheader("⑤ Big Tech Releases")
    for org, rows in (brief.get("big_tech") or {}).items():
        with st.expander(org):
            for r in rows:
                st.markdown(f"- [{r.get('title')}]({r.get('url')})")
with c4:
    st.subheader("⑥ My Watchlist")
    wl = load_yaml("watchlist") or []
    for w in wl:
        matched = [s for s in stories if w["name"] in (s.get("watchlist_matches") or [])]
        with st.expander(f"{w['name']} ({len(matched)})"):
            for s in matched:
                title = (s.get("summary") or {}).get("title_vi") or s.get("title")
                st.markdown(f"- [{title}]({s.get('canonical_url')})")

st.subheader("⑦ Topic Heatmap")
hist = load_stories_range(selected - timedelta(days=13), selected)
if hist:
    rows = []
    for s in hist:
        for t in s.get("topics") or ["(none)"]:
            rows.append({"date": s["story_date"], "topic": t, "importance": s["importance_score"]})
    df = pd.DataFrame(rows)
    if not df.empty:
        pivot = df.groupby(["topic", "date"], as_index=False)["importance"].sum()
        fig = px.density_heatmap(pivot, x="date", y="topic", z="importance", color_continuous_scale="Blues")
        st.plotly_chart(fig, use_container_width=True)
        # hot / cold
        mid = selected - timedelta(days=7)
        recent = df[df["date"] >= mid].groupby("topic")["importance"].sum()
        prev = df[df["date"] < mid].groupby("topic")["importance"].sum()
        delta = (recent - prev).fillna(0).sort_values(ascending=False)
        h1, h2 = st.columns(2)
        h1.write("Đang nóng lên")
        h1.write(delta.head(5))
        h2.write("Đang nguội")
        h2.write(delta.tail(5))
else:
    st.caption("Chưa đủ dữ liệu heatmap")

st.subheader("⑧ PoC Candidates")
for p in brief.get("poc_candidates") or []:
    st.markdown(
        f"**#{p.get('story_id')}** — {p.get('reason')}\n\n"
        f"*Experiment:* {p.get('suggested_experiment')}"
    )

st.download_button(
    "Tải brief Markdown",
    data=brief.get("markdown") or "",
    file_name=f"brief-{selected}.md",
    mime="text/markdown",
)
