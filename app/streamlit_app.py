"""Streamlit entrypoint for CineSupervisor.

The UI intentionally stays thin: presentation lives here and production
logic stays in the shared tools and ADK agents.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.genai import types

from app.agent import app as adk_app
from app.config import APP_NAME, DEFAULT_MODEL
from app.tools import (
    ensure_clickhouse_tables,
    format_edit_decision_list,
    get_clickhouse_client,
    parse_screenplay_text,
    read_media_metadata,
)
from app.ui import load_styles, page_header, render_metric_row, status_badge

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

st.set_page_config(
    page_title="CineSupervisor AI",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)
load_styles()


def db_status() -> tuple[bool, str]:
    """Check ClickHouse without making the UI crash when it is not configured."""
    try:
        client = get_clickhouse_client()
        client.command("SELECT 1")
        ensure_clickhouse_tables(client)
        return True, "ClickHouse connected"
    except Exception as exc:
        return False, f"ClickHouse unavailable: {exc}"


async def run_supervisor(prompt: str) -> str:
    """Run the central ADK agent for one Streamlit request."""
    from google.adk.sessions import InMemorySessionService

    runner = Runner(
        app=adk_app,
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    response_text = ""
    async for event in runner.run_async(
        user_id="streamlit-user",
        session_id="streamlit-session",
        new_message=content,
    ):
        if event.is_final_response() and event.content:
            response_text = "\n".join(
                part.text for part in event.content.parts if getattr(part, "text", None)
            )
    return response_text or "The supervisor returned no text response."


def ask_supervisor(prompt: str) -> str:
    """Bridge Streamlit's synchronous callbacks to the async ADK runner."""
    return asyncio.run(run_supervisor(prompt))


if "project_id" not in st.session_state:
    st.session_state.project_id = "the-cybernetic-courier"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "plan" not in st.session_state:
    st.session_state.plan = []

with st.sidebar:
    st.markdown("### 🎬 CineSupervisor")
    st.caption("AI film-production control room")
    st.session_state.project_id = st.text_input(
        "Project ID", value=st.session_state.project_id
    ).strip() or "the-cybernetic-courier"
    connected, message = db_status()
    status_badge("● LIVE" if connected else "● OFFLINE", "active" if connected else "fail")
    st.caption(message)
    st.caption(f"Model: `{DEFAULT_MODEL}`")
    st.caption(f"Agent app: `{APP_NAME}`")

page_header(
    "CineSupervisor",
    "Plan the shoot, verify takes, make wrap decisions, and support the edit.",
)

render_metric_row(
    [
        ("Agents", "Supervisor + 3"),
        ("Database", "ClickHouse" if connected else "Not configured"),
        ("Model", DEFAULT_MODEL),
        ("Deployment", "Cloud Run ready"),
    ]
)

planner_tab, take_tab, editor_tab, chat_tab = st.tabs(
    ["📋 Production Plan", "🎥 Take Analyzer", "✂️ Editor", "🤖 Supervisor"]
)

with planner_tab:
    st.subheader("Screenplay → production plan")
    upload = st.file_uploader("Upload screenplay", type=["txt", "md"])
    default_file = PROJECT_ROOT / "sample_screenplay.txt"
    text = (
        upload.getvalue().decode("utf-8", errors="replace")
        if upload
        else default_file.read_text(encoding="utf-8") if default_file.exists() else ""
    )
    if text:
        st.caption(f"{len(text):,} characters loaded")
        if st.button("Build production plan", type="primary"):
            with st.spinner("Parsing screenplay…"):
                st.session_state.plan = parse_screenplay_text(
                    text, st.session_state.project_id
                )
            st.success(f"Parsed {len(st.session_state.plan)} scene(s).")
    for scene in st.session_state.plan:
        with st.expander(
            f"Scene {scene.get('scene_number', '?')} — {scene.get('location', 'Unknown')}",
        ):
            st.json(scene)

with take_tab:
    st.subheader("Take metadata intake")
    media_path = st.text_input("Media path", placeholder="/footage/reel_01/A007_C001_1028_001.MOV")
    if st.button("Inspect media", type="primary"):
        if not media_path.strip():
            st.warning("Enter a media path first.")
        else:
            with st.spinner("Reading media metadata…"):
                st.session_state.media_metadata = read_media_metadata(media_path.strip())
    if st.session_state.get("media_metadata"):
        st.json(st.session_state.media_metadata)
        st.info("Metadata is intake evidence. Compliance still requires visual/audio evidence and stored scene requirements.")

with editor_tab:
    st.subheader("CMX 3600 editorial decision list")
    events = st.text_area(
        "Editorial events as JSON",
        value='[{"clip_name":"A007_C001_1028_001.MOV","src_in":"01:20:10:00","src_out":"01:20:20:00","comment":"Use clean master opening"}]',
        height=180,
    )
    if st.button("Generate EDL", type="primary"):
        try:
            parsed = json.loads(events)
            if not isinstance(parsed, list):
                raise ValueError("Expected a JSON array")
            st.session_state.edl = format_edit_decision_list(parsed)
        except (ValueError, json.JSONDecodeError) as exc:
            st.error(f"Invalid editorial events: {exc}")
    if st.session_state.get("edl"):
        st.code(st.session_state.edl, language="text")
        st.download_button(
            "Download EDL",
            st.session_state.edl,
            "cine_supervisor_assembly.edl",
            "text/plain",
        )

with chat_tab:
    st.subheader("Ask CineSupervisor")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    prompt = st.chat_input("e.g. Can I wrap Scene 7?")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("CineSupervisor is coordinating the agents…"):
                answer = ask_supervisor(f"Project: {st.session_state.project_id}\n\n{prompt}")
            st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})

st.divider()
st.caption(f"CineSupervisor • {datetime.now():%Y-%m-%d %H:%M:%S} • original media is never modified")
