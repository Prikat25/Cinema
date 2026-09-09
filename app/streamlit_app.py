"""Streamlit production-control workspace for CineSupervisor."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
import streamlit as st
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.genai import types

from app.agent import app as adk_app
from app.config import APP_NAME, DEFAULT_MODEL
from app.tools import (
    ensure_clickhouse_tables,
    get_clickhouse_client,
    list_scenes_from_clickhouse,
    list_take_analyses_from_clickhouse,
)
from app.ui import load_styles, page_header, render_metric_row, render_scene, status_badge

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = Path(tempfile.gettempdir()) / "cine-supervisor-uploads"

st.set_page_config(
    page_title="CineSupervisor",
    page_icon="CS",
    layout="wide",
    initial_sidebar_state="expanded",
)
load_styles()

def init_state() -> None:
    defaults: dict[str, Any] = {
        "project_id": "the-cybernetic-courier",
        "production_scenes": [],
        "take_records": [],
        "messages": [],
        "media_metadata": None,
        "workflow_responses": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def db_status() -> tuple[bool, str]:
    try:
        client = get_clickhouse_client()
        client.command("SELECT 1")
        ensure_clickhouse_tables(client)
        return True, "Connected"
    except Exception:
        return False, "Offline"


def refresh_records() -> None:
    """Load the agent-owned production state for display only."""
    project_id = st.session_state.project_id
    st.session_state.production_scenes = list_scenes_from_clickhouse(project_id)
    st.session_state.take_records = list_take_analyses_from_clickhouse(project_id)


def save_upload(filename: str, data: bytes) -> Path:
    """Give the agent a stable local file reference for this Streamlit session."""
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "upload.bin"
    destination = UPLOAD_ROOT / f"{uuid.uuid4().hex}_{safe_name}"
    destination.write_bytes(data)
    return destination


def audit_scene(scene: dict, takes: list[dict]) -> tuple[list[dict], int, int]:
    rows: list[dict] = []
    missing = 0
    failing = 0
    for shot in scene.get("shots", []):
        shot_id = str(shot.get("shot_number"))
        matching = [take for take in takes if str(take.get("shot_number")) == shot_id]
        passing = [take for take in matching if take.get("requirements_met")]
        if passing:
            status = "Pass"
            evidence = passing[0]["take_id"]
        elif matching:
            failing += 1
            status = "Failed"
            evidence = "; ".join(matching[-1].get("deviations", []) or ["Requirements not met"])
        else:
            missing += 1
            status = "Missing"
            evidence = "No take logged"
        rows.append(
            {
                "Shot": shot_id,
                "Coverage": shot.get("shot_type", "Unspecified"),
                "Requirement": shot.get("requirements", "Unspecified"),
                "Takes": len(matching),
                "Status": status,
                "Evidence": evidence,
            }
        )
    return rows, missing, failing


async def run_supervisor(
    prompt: str, attachment: tuple[bytes, str] | None = None
) -> str:
    from google.adk.sessions import InMemorySessionService

    runner = Runner(
        app=adk_app,
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
    parts = [types.Part(text=prompt)]
    if attachment:
        data, mime_type = attachment
        parts.append(types.Part.from_bytes(data=data, mime_type=mime_type))
    content = types.Content(role="user", parts=parts)
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


def ask_supervisor(
    prompt: str, attachment: tuple[bytes, str] | None = None
) -> str:
    context = {
        "project_id": st.session_state.project_id,
        "scenes": st.session_state.production_scenes,
        "takes": st.session_state.take_records,
    }
    try:
        return asyncio.run(
            run_supervisor(
                f"Production context:\n{json.dumps(context)}\n\nRequest:\n{prompt}",
                attachment,
            )
        )
    except Exception as exc:
        return f"The supervisor could not complete this request: {exc}"


def run_workflow_task(
    workflow: str, request: str, attachment: tuple[bytes, str] | None = None
) -> str:
    """Route every workspace action through the central supervisor agent."""
    prompt = (
        f"Workflow: {workflow}\n"
        "You are CineSupervisor. Delegate this task to the appropriate specialist "
        "agent, ground the result in the supplied production context, and give a "
        "concise operational response with the next action.\n\n"
        f"Task:\n{request}"
    )
    with st.spinner("CineSupervisor is coordinating the task..."):
        response = ask_supervisor(prompt, attachment)
    st.session_state.workflow_responses[workflow] = response
    return response


def render_workflow_response(workflow: str, response: str | None = None) -> None:
    """Show the latest central-agent response without replacing structured UI data."""
    response = response or st.session_state.workflow_responses.get(workflow)
    if response:
        with st.expander("CineSupervisor response", expanded=True):
            st.markdown(response)

def render_planner() -> None:
    page_header("Production Planner", "Send screenplay planning to CineSupervisor and view its persisted registry.")
    ingest_tab, registry_tab = st.tabs(["Screenplay ingestion", "Scene registry"])
    with ingest_tab:
        uploaded = st.file_uploader("Screenplay", type=["txt", "md"])
        screenplay = st.text_area(
            "Screenplay text",
            value=uploaded.getvalue().decode("utf-8", errors="replace") if uploaded else "",
            height=300,
        )
        if st.button("Send to CineSupervisor", type="primary"):
            if not screenplay.strip():
                st.warning("Upload or paste a screenplay first.")
                return
            source_file = save_upload("screenplay.txt", screenplay.encode("utf-8"))
            response = run_workflow_task(
                "Production planning",
                "Delegate to ProductionPlannerAgent. Read the screenplay at this path, "
                "create and persist the scene breakdown in ClickHouse, then summarize the "
                f"created records and production risks.\n\nScreenplay path: {source_file}",
            )
            refresh_records()
            render_workflow_response("Production planning", response)
    with registry_tab:
        scenes = st.session_state.production_scenes
        if not scenes:
            st.info("No persisted scenes are available for this project yet.")
        for scene in scenes:
            with st.expander(f"Scene {scene['scene_number']}: {scene['location']} ({scene['time_of_day']})"):
                render_scene(scene)

def render_take_analyzer() -> None:
    page_header("Take Analyzer", "Upload a take for Gemini analysis and review the persisted take metrics.")
    analysis_tab, metrics_tab = st.tabs(["Analyze uploaded take", "Saved take metrics"])
    scenes = st.session_state.production_scenes
    with analysis_tab:
        if not scenes:
            st.warning("Create and persist a production plan before analyzing a take.")
        else:
            scene_numbers = [scene["scene_number"] for scene in scenes]
            selected_scene = st.selectbox("Scene", scene_numbers)
            scene = next(item for item in scenes if item["scene_number"] == selected_scene)
            shot_number = st.selectbox("Shot", [str(shot["shot_number"]) for shot in scene["shots"]])
            take_id = st.text_input("Take ID", value=f"TAKE_SCENE{selected_scene:02d}_001")
            take_file = st.file_uploader("Take media", type=["mov", "mp4", "mxf", "wav", "mp3"])
            if st.button("Analyze and persist take", type="primary"):
                if not take_file:
                    st.warning("Upload a take before requesting analysis.")
                else:
                    media_bytes = take_file.getvalue()
                    media_path = save_upload(take_file.name, media_bytes)
                    mime_type = take_file.type or mimetypes.guess_type(take_file.name)[0] or "application/octet-stream"
                    response = run_workflow_task(
                        "Take analysis",
                        "Delegate to TakeAnalyzerAgent. Analyze the attached take with Gemini "
                        "against the persisted requirements, then persist a complete take analysis "
                        "to ClickHouse. Do not mark requirements as passed when evidence is missing.\n\n"
                        f"Project: {st.session_state.project_id}\nScene: {selected_scene}\nShot: {shot_number}\n"
                        f"Take ID: {take_id}\nMedia path: {media_path}",
                        (media_bytes, mime_type),
                    )
                    refresh_records()
                    render_workflow_response("Take analysis", response)
    with metrics_tab:
        takes = st.session_state.take_records
        if not takes:
            st.info("No take analyses are stored in ClickHouse for this project.")
        else:
            render_metric_row(
                [
                    ("Saved takes", str(len(takes))),
                    ("Approved", str(sum(take["requirements_met"] for take in takes))),
                    ("Needs review", str(sum(not take["requirements_met"] for take in takes))),
                    ("Mean confidence", f"{sum(take['confidence'] for take in takes) / len(takes):.0%}"),
                ]
            )
            st.dataframe(
                [
                    {
                        "Take": take["take_id"],
                        "Scene": take["scene_number"],
                        "Shot": take["shot_number"],
                        "Status": "Approved" if take["requirements_met"] else "Review required",
                        "Confidence": f"{take['confidence']:.0%}",
                        "Summary": take["summary"],
                    }
                    for take in takes
                ],
                hide_index=True,
                use_container_width=True,
            )

def render_supervisor() -> None:
    page_header("CineSupervisor", "Central coordination for planning, coverage, wrap, and editorial decisions.")
    scenes = st.session_state.production_scenes
    takes = st.session_state.take_records
    render_metric_row(
        [
            ("Scenes", str(len(scenes))),
            ("Takes", str(len(takes))),
            ("Approved", str(sum(bool(take["requirements_met"]) for take in takes))),
        ]
    )
    st.subheader("Supervisor chat")
    prompts = {
        "Review Scene 7": "Can Scene 7 be wrapped? List any missing or failed coverage.",
        "Next action": "What is the next production action based on current coverage?",
        "Find a take": "Find the best available take for the Sarah photograph reveal.",
        "Plan review": "Summarize the production requirements for the current scenes.",
    }
    columns = st.columns(len(prompts))
    selected_prompt = None
    for column, (label, prompt) in zip(columns, prompts.items()):
        if column.button(label, use_container_width=True):
            selected_prompt = prompt
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    prompt = st.chat_input("Ask about scene coverage, a take, wrap status, or an editorial decision") or selected_prompt
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Reviewing the production state..."):
                answer = ask_supervisor(prompt)
            st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})

def render_wrap_status() -> None:
    page_header("Scene Wrap Status", "Verify every required shot before releasing a set or moving locations.")
    scenes = st.session_state.production_scenes
    if len(scenes) < 1:
        st.info("At least one persisted scene is required for comparison.")
        return
    selected = st.selectbox("Scene", [scene["scene_number"] for scene in scenes])
    # scene = next(item for item in scenes if item["scene_number"] == selected)
    scene = next((item for item in scenes if str(item["scene_number"]) == str(selected)), None)
    rows, missing, failing = audit_scene(scene, st.session_state.take_records)
    can_wrap = not missing and not failing and bool(rows)
    render_metric_row(
        [
            ("Required shots", str(len(rows))),
            ("Missing", str(missing)),
            ("Failed", str(failing)),
            ("Decision", "Ready" if can_wrap else "Hold"),
        ]
    )
    if can_wrap:
        st.success(f"Scene {selected} is ready to wrap. Every required shot has a passing take.")
    else:
        st.error(f"Scene {selected} must remain active: {missing} missing and {failing} failed coverage item(s).")
    
    st.dataframe(rows, hide_index=True, use_container_width=True)
    if st.button("Request supervisor wrap decision", type="primary"):
        response = run_workflow_task(
            "Scene wrap review",
            f"Determine whether Scene {selected} can be wrapped. Use this coverage audit "
            f"and list any required next actions.\n\n{json.dumps(rows)}",
        )
        render_workflow_response("Scene wrap review", response)
    else:
        render_workflow_response("Scene wrap review")

def take_summary(take: dict) -> None:
    status_badge("APPROVED" if take["requirements_met"] else "REVIEW REQUIRED", "pass" if take["requirements_met"] else "fail")
    st.markdown(f"**{take['take_id']}**")
    st.caption(f"Scene {take['scene_number']} | Shot {take['shot_number']} | {take['framing']}")
    st.code(f"{take['timecode_in']} -> {take['timecode_out']}", language="text")
    st.caption(f"Confidence: {take['confidence']:.0%}")
    st.write(take["summary"])
    if take["deviations"]:
        st.caption("Deviations: " + "; ".join(take["deviations"]))

def render_editorial() -> None:
    page_header("Editorial Assistant", "Use CineSupervisor and Gemini to compare persisted take analyses and build an edit decision list.")
    takes = st.session_state.take_records
    compare_tab, assembly_tab = st.tabs(["Dual-deck comparison", "Search and EDL"])
    with compare_tab:
        if len(takes) < 2:
            st.info("At least two persisted take analyses are required for comparison.")
            return
        options = {take["take_id"]: take for take in takes}
        ids = list(options)
        first, second = st.columns(2)
        take_a = options[first.selectbox("Deck A", ids, key="deck_a")]
        take_b = options[second.selectbox("Deck B", ids, index=min(1, len(ids) - 1), key="deck_b")]
        left, right = st.columns(2)
        with left:
            take_summary(take_a)
        with right:
            take_summary(take_b)
        if st.button("Request supervisor editorial decision", type="primary"):
            response = run_workflow_task(
                "Editorial review",
                "Delegate to EditorAssistantAgent. Query the persisted take analyses, compare "
                "the selected takes, and return a recommended take, objective evidence, and "
                "an editorial next action.\n\n"
                + json.dumps({"deck_a_take_id": take_a["take_id"], "deck_b_take_id": take_b["take_id"]}),
            )
            render_workflow_response("Editorial review", response)
        else:
            render_workflow_response("Editorial review")
    with assembly_tab:
        if not takes:
            st.info("No persisted take analyses are available for editorial search.")
            return
        query = st.text_input("Search take notes", placeholder="photograph, close-up, Scene 7")
        if st.button("Ask supervisor to search and build EDL", type="primary"):
            response = run_workflow_task(
                "Editorial search and EDL",
                "Delegate to EditorAssistantAgent. Search persisted take analyses for this "
                "request, recommend verified takes, and return a CMX 3600 EDL when the evidence "
                f"supports it.\n\nEditorial request: {query or 'Recommend the best available takes for a rough cut.'}",
            )
            render_workflow_response("Editorial search and EDL", response)
        else:
            render_workflow_response("Editorial search and EDL")

def render_database() -> None:
    page_header("Production Data", "Inspect the scene and take records currently loaded in this workspace.")
    scene_tab, take_tab = st.tabs(["Scenes", "Take analyses"])
    with scene_tab:
        st.dataframe(
            [
                {
                    "Project": scene["project_id"],
                    "Scene": scene["scene_number"],
                    "Location": scene["location"],
                    "Time": scene["time_of_day"],
                    "Characters": ", ".join(scene["characters"]),
                    "Shots": len(scene["shots"]),
                }
                for scene in st.session_state.production_scenes
            ],
            hide_index=True,
            use_container_width=True,
        )
    with take_tab:
        st.dataframe(
            [
                {
                    "Take": take["take_id"],
                    "Scene": take["scene_number"],
                    "Shot": take["shot_number"],
                    "Status": "Pass" if take["requirements_met"] else "Failed",
                    "Confidence": f"{take['confidence']:.0%}",
                    "Summary": take["summary"],
                }
                for take in st.session_state.take_records
            ],
            hide_index=True,
            use_container_width=True,
        )
    if st.button("Request supervisor data review", type="primary"):
        response = run_workflow_task(
            "Production data review",
            "Review the current scene and take records. Identify the highest-priority "
            "production risk and the next action.",
        )
        render_workflow_response("Production data review", response)
    else:
        render_workflow_response("Production data review")

init_state()
connected, connection_label = db_status()

with st.sidebar:
    st.markdown("### CineSupervisor")
    st.caption("Film production control room")
    st.session_state.project_id = st.text_input("Project ID", value=st.session_state.project_id).strip() or "untitled-production"
    status_badge("DATABASE CONNECTED" if connected else "SESSION MODE", "pass" if connected else "active")
    st.caption(connection_label if connected else "Changes are available in this browser session and can be persisted when ClickHouse is configured.")
    st.divider()
    workflow = st.radio(
        "Workspace",
        ["Production Planner", "Take Analyzer", "Supervisor", "Wrap Status", "Editorial", "Production Data"],
    )
    st.divider()
    st.caption(f"Model: `{DEFAULT_MODEL}`")
    st.caption(f"App: `{APP_NAME}`")

if workflow == "Supervisor":
    render_supervisor()
elif workflow == "Production Planner":
    render_planner()
elif workflow == "Take Analyzer":
    render_take_analyzer()
elif workflow == "Wrap Status":
    render_wrap_status()
elif workflow == "Editorial":
    render_editorial()
else:
    render_database()

st.divider()
st.caption(f"CineSupervisor | {datetime.now():%Y-%m-%d %H:%M:%S} | Original media is never modified")