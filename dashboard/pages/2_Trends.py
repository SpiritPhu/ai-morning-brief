"""Trends charts."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.models import Item, ItemMetric
from dashboard.db_util import empty_state, load_stories_range, session_scope

st.set_page_config(page_title="Trends", layout="wide")
st.title("Trends")

days = st.selectbox("Window", [30, 90], index=0)
end = date.today()
start = end - timedelta(days=days)
stories = load_stories_range(start, end)
if not stories:
    empty_state()
    st.stop()

rows = []
for s in stories:
    for t in s.get("topics") or ["(none)"]:
        rows.append(
            {
                "date": s["story_date"],
                "topic": t,
                "stories": 1,
                "importance": s["importance_score"],
            }
        )
df = pd.DataFrame(rows)
agg = df.groupby(["date", "topic"], as_index=False).agg(
    stories=("stories", "sum"), importance=("importance", "sum")
)
fig1 = px.line(agg, x="date", y="stories", color="topic", title="Stories by topic")
st.plotly_chart(fig1, use_container_width=True)
fig2 = px.line(agg, x="date", y="importance", color="topic", title="Importance by topic")
st.plotly_chart(fig2, use_container_width=True)

st.subheader("Top repos by stars growth")
try:
    with session_scope() as session:
        window = st.selectbox("Stars window", [7, 30], index=0)
        d0 = end - timedelta(days=window)
        metrics = session.execute(
            select(Item.title, Item.url, ItemMetric.snapshot_date, ItemMetric.value)
            .join(ItemMetric, ItemMetric.item_id == Item.id)
            .where(
                Item.source_key.in_(["github_trending", "github_search"]),
                ItemMetric.metric_name == "stars",
                ItemMetric.snapshot_date >= d0,
            )
        ).all()
        if metrics:
            mdf = pd.DataFrame(metrics, columns=["title", "url", "date", "stars"])
            piv = mdf.groupby("title").agg(min_stars=("stars", "min"), max_stars=("stars", "max"), url=("url", "first"))
            piv["delta"] = piv["max_stars"] - piv["min_stars"]
            st.dataframe(piv.sort_values("delta", ascending=False).head(20), use_container_width=True)
        else:
            st.caption("Chưa có snapshot stars")
except Exception as exc:
    st.warning(str(exc))

st.subheader("Top organizations")
orgs = pd.DataFrame(
    [{"organization": s.get("organization") or "unknown"} for s in stories]
)
st.dataframe(orgs.value_counts().reset_index(name="stories").head(20), use_container_width=True)
