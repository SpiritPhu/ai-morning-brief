"""Edit watchlist.yaml and view matches."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config import CONFIG_DIR, load_yaml, reload_configs
from dashboard.db_util import load_stories_range

st.set_page_config(page_title="Watchlist", layout="wide")
st.title("Watchlist")

path = CONFIG_DIR / "watchlist.yaml"
watchlist = load_yaml("watchlist") or []

st.subheader("Edit")
edited = []
for i, w in enumerate(watchlist):
    with st.expander(w.get("name", f"item-{i}"), expanded=False):
        name = st.text_input("Name", w.get("name", ""), key=f"name_{i}")
        desc = st.text_area("Description", w.get("description", ""), key=f"desc_{i}")
        kws = st.text_area(
            "Keywords (comma-separated)",
            ", ".join(w.get("keywords") or []),
            key=f"kw_{i}",
        )
        priority = st.slider("Priority", 1, 3, int(w.get("priority", 2)), key=f"p_{i}")
        remove = st.checkbox("Xóa mục này", key=f"rm_{i}")
        if not remove:
            edited.append(
                {
                    "name": name,
                    "description": desc,
                    "keywords": [k.strip() for k in kws.split(",") if k.strip()],
                    "priority": priority,
                }
            )

if st.button("Thêm mục mới"):
    edited.append(
        {"name": "New topic", "description": "", "keywords": [], "priority": 2}
    )
    st.session_state["_wl_added"] = True

if st.button("Lưu watchlist.yaml"):
    path.write_text(yaml.safe_dump(edited, allow_unicode=True, sort_keys=False), encoding="utf-8")
    reload_configs()
    load_yaml.cache_clear()
    st.success("Đã lưu")
    st.rerun()

st.subheader("Timeline 30 ngày")
stories = load_stories_range(date.today() - timedelta(days=30), date.today())
for w in edited or watchlist:
    matched = [s for s in stories if w["name"] in (s.get("watchlist_matches") or [])]
    st.markdown(f"### {w['name']} — {len(matched)} stories")
    for s in matched[:20]:
        title = (s.get("summary") or {}).get("title_vi") or s.get("title")
        appeared = s.get("first_appeared") or s.get("story_date")
        st.markdown(
            f"- brief `{s.get('story_date')}` · xuất hiện `{appeared}` "
            f"[{title}]({s.get('canonical_url')})"
        )
