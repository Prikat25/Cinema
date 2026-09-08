"""Deployment-ready Streamlit UI for CineSupervisor.

The legacy UI remains available in app/streamlit_app.py while this entrypoint
provides a smaller, stable surface for Cloud Run deployment.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import streamlit as st
from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from app.agent import app as adk_app
from app.agent import root_agent
from app.config import APP_NAME, CLICKHOUSE_HOST, DEFAULT_MODEL
from app.tools import (
    ensure_clickhouse_tables,
    format_edit_decision_list,
    get_clickhouse_client,
    parse_screenplay_text,
    read_media_metadata,
)
from app.ui import load_styles, page_header, render_metric_row, status_badge

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent

st.set_page_config(
    page_title="CineSupervisor AI",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)
load_styles()


def _init_state() -> None:
    defaults = {
        "messages": [],
        "project_id": "the-cybernetic-courier",
        "plan": [],
        "metadata": None,
        "edl": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _db_status() -> tuple[bool, str]:
    if not CLICKHOUSE_HOST:
        return False, "ClickHouse not configured"
    try:
        client = get_clickhouse_client()
        client.command("SELECT 1")
        ensure_clickhouse_tables(client)
        return True, "ClickHouse connected"
    except Exception as exc:
        return False, f"ClickHouse unavailable: {exc}"


async def _run_supervisor(prompt: str, session_id: str) -> str:
    session_service = InMemorySessionService()
    runner = Runner(
        app=adk_app,
        session_service=session_service,
        auto_create_session=True,
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    final_text = ""
    async for event in runner.run_async(
        user_id="streamlit-user",
        session_id=session_id,
        new_message=message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "\n".join(
                part.text for part in event.content.parts if getattr(part, "text", None)
            )
    return final_text or "The supervisor returned no text response."


def supervisor_chat(prompt: str) -> str:
    try:
        return asyncio.run(_run_supervisor(prompt, "streamlit-production"))
    except RuntimeError:
        # Streamlit normally has no active event loop, but this keeps the UI
        # from crashing if an embedding/runtime supplies one.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                _run_supervisor(prompt, "streamlit-production")
            )
        finally:
            loop.close()


_init_state()

with st.sidebar:
    st.markdown("### 🎬 CineSupervisor")
    st.caption("AI production control room")
    st.session_state.project_id = st.text_input(
        "Project ID", value=st.session_state.project_id
    ).strip() or "the-cybernetic-courier"

    db_ok, db_message = _db_status()
    st.markdown(status_badge("● " + ("LIVE" if db_ok else "OFFLINE"), "active" if db_ok else "fail"), unsafe_allow_html=True)
    st.caption(db_message)
    st.caption(f"Model: `{DEFAULT_MODEL}`")
    st.caption(f"Agent app: `{APP_NAME}`")

page_header(
    "CineSupervisor",
    "Production planning, take verification, wrap decisions, and editorial assistance.",
)

render_metric_row(
    [
        ("Agent", "3 subagents"),
        ("Database", "ClickHouse" if db_ok else "Not configured"),
        ("Model", DEFAULT_MODEL),
        ("State", "Persistent data + session UI"),
    ]
)

planner_tab, take_tab, editor_tab, chat_tab = st.tabs(
    ["📋 Production Plan", "🎥 Take Analyzer", "✂️ Editor", "🤖 Supervisor"]
)

with planner_tab:
    st.subheader("Screenplay → production plan")
    uploaded = st.file_uploader("Upload screenplay", type=["txt", "md"])
    default_path = PROJECT_ROOT / "sample_screenplay.txt"
    screenplay_text = ""
    if uploaded is not None:
        screenplay_text = uploaded.getvalue().decode("utf-8", errors="replace")
    elif default_path.exists():
        screenplay_text = default_path.read_text(encoding="utf-8")

    if screenplay_text:
        st.caption(f"{len(screenplay_text):,} characters loaded")
        if st.button("Build production plan", type="primary"):
            with st.spinner("Parsing screenplay and preparing scene requirements…"):
                st.session_state.plan = parse_screenplay_text(
                    screenplay_text, st.session_state.project_id
                )
            st.success(f"Parsed {len(st.session_state.plan)} scene(s).")

    if st.session_state.plan:
        for scene in st.session_state.plan:
            with st.expander(
                f"Scene {scene.get('scene_number', '?')} — {scene.get('location', 'Unknown location')}",
                expanded=False,
            ):
                st.json(scene)

with take_tab:
    st.subheader("Take metadata and evidence intake")
    media_path = st.text_input(
        "Media path", placeholder="/footage/reel_01/A007_C001_1028_001.MOV"
    )
    if st.button("Inspect media", type="primary"):
        if not media_path.strip():
            st.warning("Enter a media path first.")
        else:
            with st.spinner("Reading media metadata…"):
                st.session_state.metadata = read_media_metadata(media_path.strip())

    if st.session_state.metadata:
        metadata = st.session_state.metadata
        st.json(metadata)
        st.info(
            "Metadata is intake evidence only. The Take Analyzer must use visual/audio evidence and stored scene requirements before marking a take as compliant."
        )

with editor_tab:
    st.subheader("Editorial decision list")
    events_text = st.text_area(
        "Editorial events (JSON array)",
        value='[{"clip_name":"A007_C001_1028_001.MOV","src_in":"01:20:10:00","src_out":"01:20:20:00","comment":"Use clean master opening"}]',
        height=180,
    )
    if st.button("Generate CMX 3600 EDL", type="primary"):
        try:
            events = json.loads(events_text)
            if not isinstance(events, list):
                raise ValueError("Expected a JSON array")
            st.session_state.edl = format_edit_decision_list(events)
        except (json.JSONDecodeError, ValueError) as exc:
            st.error(f"Invalid editorial events: {exc}")

    if st.session_state.edl:
        st.code(st.session_state.edl, language="text")
        st.download_button(
            "Download EDL",
            st.session_state.edl,
            file_name="cine_supervisor_assembly.edl",
            mime="text/plain",
        )

with chat_tab:
    st.subheader("Ask CineSupervisor")
    st.caption("The supervisor delegates planning, take analysis, and editorial work to the configured ADK subagents.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("e.g. Can I wrap Scene 7?")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("CineSupervisor is coordinating the production agents…"):
                answer = supervisor_chat(
                    f"Project: {st.session_state.project_id}\n\n{prompt}"
                )
            st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})

st.divider()
st.caption(
    f"CineSupervisor • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • originals are never modified by the assistant."
)
