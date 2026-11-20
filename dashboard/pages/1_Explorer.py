"""Story / item explorer with text + semantic search."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.models import Item, Story, StorySummary
from app.db.repository import semantic_search_items
from app.embeddings import embed_texts, item_text
from dashboard.components.story_card import render_story_card
from dashboard.db_util import _story_dict, empty_state, session_scope

st.set_page_config(page_title="Explorer", layout="wide")
st.title("Explorer")

q = st.text_input("Search")
mode = st.radio("Search mode", ["Full-text", "Semantic"], horizontal=True)
c1, c2, c3 = st.columns(3)
start = c1.date_input("From", value=date.today() - timedelta(days=7))
end = c2.date_input("To", value=date.today())
maturity = c3.multiselect("Maturity", ["research", "early-oss", "production-ready"])

try:
    with session_scope() as session:
        stories = []
        if mode == "Semantic" and q.strip():
            vec = embed_texts([q])[0].tolist()
            items = semantic_search_items(session, vec, limit=30)
            story_ids = [i.story_id for i in items if i.story_id]
            if story_ids:
                rows = session.scalars(
                    select(Story)
                    .where(Story.id.in_(story_ids))
                    .options(joinedload(Story.summary), joinedload(Story.items))
                ).unique().all()
                stories = [_story_dict(s) for s in rows]
        else:
            stmt = (
                select(Story)
                .outerjoin(StorySummary)
                .where(Story.story_date >= start, Story.story_date <= end)
                .options(joinedload(Story.summary), joinedload(Story.items))
                .order_by(Story.importance_score.desc())
                .limit(100)
            )
            if q.strip():
                like = f"%{q}%"
                stmt = stmt.where(
                    or_(
                        Story.title.ilike(like),
                        StorySummary.summary.ilike(like),
                        StorySummary.title_vi.ilike(like),
                    )
                )
            rows = session.scalars(stmt).unique().all()
            stories = [_story_dict(s) for s in rows]
            if maturity:
                stories = [
                    s
                    for s in stories
                    if (s.get("summary") or {}).get("maturity") in maturity
                ]

        if not stories:
            empty_state()
        else:
            for s in stories:
                render_story_card(s)
                with st.expander("Items"):
                    for it in s.get("items") or []:
                        st.markdown(f"- **{it['source_key']}**: [{it['title']}]({it['url']})")
                st.divider()
except Exception as exc:
    st.warning(f"DB chưa sẵn sàng: {exc}")
    empty_state()
