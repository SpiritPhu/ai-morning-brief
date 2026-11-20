"""Admin: pipeline runs + manual trigger."""

from __future__ import annotations

import sys
import threading
from collections import Counter
from datetime import date
from pathlib import Path

import streamlit as st
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.models import Feedback, PipelineRun
from app.pipeline.runner import run_pipeline, today_in_tz
from dashboard.db_util import empty_state, session_scope

st.set_page_config(page_title="Admin", layout="wide")
st.title("Admin")

st.subheader("Pipeline history")
try:
    with session_scope() as session:
        runs = session.scalars(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(20)
        ).all()
        if not runs:
            empty_state()
        else:
            for r in runs:
                st.write(
                    {
                        "date": str(r.run_date),
                        "status": r.status,
                        "started": str(r.started_at),
                        "finished": str(r.finished_at),
                        "steps": r.step_status,
                        "error": r.error,
                    }
                )
except Exception as exc:
    st.warning(f"DB: {exc}")
    empty_state()

st.subheader("Run pipeline now")
log_box = st.empty()
if "pipeline_log" not in st.session_state:
    st.session_state["pipeline_log"] = ""

def _run():
    try:
        result = run_pipeline(today_in_tz())
        st.session_state["pipeline_log"] = str(result)
    except Exception as exc:
        st.session_state["pipeline_log"] = f"error: {exc}"

if st.button("Run pipeline now"):
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    st.info("Pipeline đang chạy trong background thread… refresh sau vài phút.")

if st.session_state["pipeline_log"]:
    st.code(st.session_state["pipeline_log"])

st.subheader("Feedback stats")
try:
    with session_scope() as session:
        votes = session.scalars(select(Feedback.vote)).all()
        c = Counter(votes)
        st.write({"up": c.get(1, 0), "down": c.get(-1, 0), "total": len(votes)})
except Exception as exc:
    st.caption(str(exc))
