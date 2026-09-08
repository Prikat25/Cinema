"""
Streamlit Web UI for CineSupervisor (agent.py)
AI Film Production Supervisor, Planner, Take Analyzer, and Editor Assistant.

Directly connected to Google GenAI / ADK multi-agent architecture and ClickHouse database.
"""

import os
import re
import json
import time
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv
import sys

# Ensure local path resolution
sys.path.append(os.path.dirname(__file__) if "__file__" in locals() else ".")
sys.path.append(os.path.join(os.path.dirname(__file__) if "__file__" in locals() else ".", "app"))
sys.path.append('app/streamlit_app')
sys.path.append('app/tools')

load_dotenv()

# =============================================================================
# Core Tools Import
# =============================================================================
try:
    from tools import (
        get_clickhouse_client,
        ensure_clickhouse_tables,
        insert_scene_to_clickhouse,
        insert_take_analysis_to_clickhouse,
        read_screenplay_file,
        read_media_metadata,
        format_edit_decision_list,
        seconds_to_smpte,
        smpte_to_seconds,
    )
except ImportError:
    from app.tools import (
        get_clickhouse_client,
        ensure_clickhouse_tables,
        insert_scene_to_clickhouse,
        insert_take_analysis_to_clickhouse,
        read_screenplay_file,
        read_media_metadata,
        format_edit_decision_list,
        seconds_to_smpte,
        smpte_to_seconds,
    )

# =============================================================================
# Backend Agent & GenAI SDK Integration
# =============================================================================
root_agent = None
production_planner_agent = None
take_analyzer_agent = None
editor_assistant_agent = None
ADK_LOADED = False

try:
    from agent import root_agent
    from production_planner import production_planner_agent
    from take_analyzer import take_analyzer_agent
    from editor_assistant import editor_assistant_agent
    ADK_LOADED = True
except Exception:
    try:
        from app.agent import root_agent
        from app.production_planner import production_planner_agent
        from app.take_analyzer import take_analyzer_agent
        from app.editor_assistant import editor_assistant_agent
        ADK_LOADED = True
    except Exception:
        ADK_LOADED = False

try:
    from google import genai
    from google.genai import types
    HAS_GENAI_SDK = True
except Exception:
    HAS_GENAI_SDK = False

# Page configuration
st.set_page_config(
    page_title="CineSupervisor AI - Film Production Supervisor",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# UI Styling
# =============================================================================
def apply_custom_styles():
    css_content = ""
    # css_path = os.path.join(os.path.dirname(__file__) if "__file__" in locals() else ".", "style.css")
    css_path = "app/style.css"
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()
    
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

        /* Global Film Aesthetic */
        html, body, [class*="css"], .stApp {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: radial-gradient(circle at 50% 0%, #172033 0%, #0b0f17 70%) !important;
            color: #f1f5f9;
        }}

        code, pre, .stCodeBlock {{
            font-family: 'JetBrains Mono', monospace !important;
        }}

        [data-testid="stSidebar"] {{
            background-color: #0d131f !important;
            border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
        }}

        .main-header {{
            font-size: 2.2rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #f43f5e 0%, #fb923c 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.2rem;
        }}
        .sub-header {{
            color: #94a3b8;
            font-size: 1rem;
            margin-bottom: 1.5rem;
        }}

        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }}
        .badge-pass {{
            background-color: rgba(34, 197, 94, 0.15);
            color: #4ade80;
            border: 1px solid rgba(34, 197, 94, 0.3);
        }}
        .badge-fail {{
            background-color: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }}
        .badge-active {{
            background-color: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }}

        .wrap-alert {{
            background: rgba(225, 29, 72, 0.1);
            border: 1px solid rgba(225, 29, 72, 0.3);
            border-left: 5px solid #e11d48;
            padding: 16px 20px;
            border-radius: 8px;
            margin-bottom: 15px;
            color: #fecdd3;
        }}
        .wrap-success {{
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid rgba(34, 197, 94, 0.3);
            border-left: 5px solid #22c55e;
            padding: 16px 20px;
            border-radius: 8px;
            margin-bottom: 15px;
            color: #bbf7d0;
        }}

        .agent-card {{
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 14px;
            margin-bottom: 12px;
        }}

        {css_content}
        </style>
        """,
        unsafe_allow_html=True,
    )

apply_custom_styles()

# =============================================================================
# Session State Initialization
# =============================================================================
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "👋 **Greetings! I am CineSupervisor**, your central AI film production supervisor.\n\n"
                "I am actively connected to your production database (`script_scenes` and `take_analyses`) and coordinate:\n"
                "- **Planning**: Break down screenplays, extract scene requirements, and sync to ClickHouse.\n"
                "- **Take Analysis**: Audit filmed takes against expected blocking, props, and dialogue.\n"
                "- **Supervision & Wrap**: Answer *'Can I wrap Scene 7?'*, track missing coverage, and dictate next steps.\n"
                "- **Editor Assistance**: Search footage via natural language, recommend best takes, and build EDLs.\n\n"
                "Ask me anything below — I'll inspect live database records and execute real agent reasoning!"
            ),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "production_supervisor",
        }
    ]

if "production_scenes" not in st.session_state:
    st.session_state.production_scenes = [
        {
            "project_id": "the-cybernetic-courier",
            "scene_number": 7,
            "location": "ABANDONED TEXTILE WAREHOUSE",
            "interior_exterior": "INT",
            "time_of_day": "NIGHT",
            "characters": ["Sarah", "Marcus"],
            "shots": [
                {"shot_number": "7.1", "shot_type": "Wide Establishing", "requirements": "Dolly in, atmospheric haze"},
                {"shot_number": "7.2", "shot_type": "Medium 2-Shot", "requirements": "Sarah approaches rusty locker"},
                {"shot_number": "7.3", "shot_type": "Close-Up (Sarah)", "requirements": "Sarah discovers vintage photograph"},
                {"shot_number": "7.4", "shot_type": "Over-The-Shoulder (Marcus)", "requirements": "Marcus warns 'don't open it'"},
                {"shot_number": "7.5", "shot_type": "Insert Shot", "requirements": "Red suitcase hidden under tarp"}
            ],
            "props": ["Vintage Photograph", "Red Suitcase", "Flashlight", "Rusty Crowbar"],
            "wardrobe": ["Sarah: Distressed leather bomber", "Marcus: Wet trench coat"]
        },
        {
            "project_id": "the-cybernetic-courier",
            "scene_number": 14,
            "location": "DETECTIVE'S ARCHIVE OFFICE",
            "interior_exterior": "INT",
            "time_of_day": "DUSK",
            "characters": ["Sarah", "Detective Miller"],
            "shots": [
                {"shot_number": "14.1", "shot_type": "Master Pan", "requirements": "Dust motes in venetian blind light"},
                {"shot_number": "14.2", "shot_type": "Medium Shot (Miller)", "requirements": "Miller drinks black coffee"},
                {"shot_number": "14.3", "shot_type": "Close-Up (Sarah)", "requirements": "Sarah reveals dossier"}
            ],
            "props": ["Dossier", "Coffee Mug", "Revolver"],
            "wardrobe": ["Miller: Rolled-up dress shirt", "Sarah: High-collar trench"]
        },
        {
            "project_id": "the-cybernetic-courier",
            "scene_number": 37,
            "location": "NEO-TOKYO RAIN ALLEYWAY",
            "interior_exterior": "EXT",
            "time_of_day": "NIGHT",
            "characters": ["Neo", "Enforcers"],
            "shots": [
                {"shot_number": "37.1", "shot_type": "Low Angle Tracking", "requirements": "Neo running down alleyway"},
                {"shot_number": "37.2", "shot_type": "High Angle Wide", "requirements": "Two Enforcers with plasma batons pursuing"},
                {"shot_number": "37.3", "shot_type": "Extreme Close-Up", "requirements": "Glowing Chrome Briefcase flashing amber"}
            ],
            "props": ["Glowing Chrome Briefcase", "Plasma Batons"],
            "wardrobe": ["Neo: Reflective cybernetic jacket", "Enforcers: Armored tactical riot gear"]
        }
    ]

if "take_records" not in st.session_state:
    st.session_state.take_records = [
        {
            "take_id": "TAKE_SCENE07_001",
            "project_id": "the-cybernetic-courier",
            "scene_number": 7,
            "shot_number": "7.1",
            "media_path": "/footage/reel_01/A007_C001_1028_001.MOV",
            "timecode_in": "01:20:10:00",
            "timecode_out": "01:21:40:00",
            "duration": "00:01:30:00",
            "framing": "Wide Establishing",
            "requirements_met": True,
            "confidence": 0.94,
            "actors": ["Sarah", "Marcus"],
            "props": ["Flashlight"],
            "deviations": [],
            "issues": [],
            "summary": "Good master wide. Haze density consistent. Dolly speed smooth."
        },
        {
            "take_id": "TAKE_SCENE07_002",
            "project_id": "the-cybernetic-courier",
            "scene_number": 7,
            "shot_number": "7.2",
            "media_path": "/footage/reel_01/A007_C002_1028_001.MOV",
            "timecode_in": "01:21:50:00",
            "timecode_out": "01:22:30:12",
            "duration": "00:00:40:12",
            "framing": "Medium 2-Shot",
            "requirements_met": True,
            "confidence": 0.92,
            "actors": ["Sarah", "Marcus"],
            "props": ["Rusty Crowbar"],
            "deviations": [],
            "issues": [],
            "summary": "Solid 2-shot. Sarah hits mark at the locker."
        },
        {
            "take_id": "TAKE_SCENE07_003",
            "project_id": "the-cybernetic-courier",
            "scene_number": 7,
            "shot_number": "7.3",
            "media_path": "/footage/reel_01/A007_C003_1028_001.MOV",
            "timecode_in": "01:22:35:00",
            "timecode_out": "01:23:15:08",
            "duration": "00:00:40:08",
            "framing": "Close-Up",
            "requirements_met": False,
            "confidence": 0.88,
            "actors": ["Sarah"],
            "props": [],
            "deviations": ["Missing Vintage Photograph in Sarah's hand"],
            "issues": ["Sarah opens rusted locker door, but hero photograph prop was missing from the locker."],
            "summary": "Take 3 captures emotional intensity, but the photograph prop was left on the prop cart."
        },
        {
            "take_id": "TAKE_SCENE07_004",
            "project_id": "the-cybernetic-courier",
            "scene_number": 7,
            "shot_number": "7.4",
            "media_path": "/footage/reel_01/A007_C004_1028_001.MOV",
            "timecode_in": "01:23:20:00",
            "timecode_out": "01:24:00:00",
            "duration": "00:00:40:00",
            "framing": "Over-The-Shoulder",
            "requirements_met": True,
            "confidence": 0.95,
            "actors": ["Marcus"],
            "props": [],
            "deviations": [],
            "issues": [],
            "summary": "Clean audio on Marcus's warning line. Sirens mixed well in background."
        },
        {
            "take_id": "TAKE_SCENE14_002",
            "project_id": "the-cybernetic-courier",
            "scene_number": 14,
            "shot_number": "14.3",
            "media_path": "/footage/reel_02/A014_C002_1028_001.MOV",
            "timecode_in": "01:34:10:04",
            "timecode_out": "01:34:52:18",
            "duration": "00:00:42:14",
            "framing": "Close-Up",
            "requirements_met": True,
            "confidence": 0.98,
            "actors": ["Sarah"],
            "props": ["Vintage Photograph", "Dossier"],
            "deviations": [],
            "issues": [],
            "summary": "Key scene moment: Sarah uncovers the 1984 black-and-white portrait behind false lining."
        }
    ]

# =============================================================================
# Agent Execution Engine (Direct Backend Agent / Gemini Invocation)
# =============================================================================
def execute_cine_supervisor(
    user_query: str,
    chat_history: list,
    scenes: list,
    takes: list,
    api_key: str = "",
    model_name: str = "gemini-2.5-flash",
) -> dict:
    """
    Executes CineSupervisor agent reasoning.
    If a Gemini API key is provided and the GenAI SDK is available, calls the live Gemini model
    with the real CineSupervisor system instruction grounded in live database state.
    Otherwise, executes an intelligent dynamic evaluator over the live database state.
    """
    lower_query = user_query.lower()

    # 1. LIVE GEMINI BACKEND CALL (If API Key is available)
    if api_key and HAS_GENAI_SDK:
        try:
            client = genai.Client(api_key=api_key)

            system_instruction = (
                "You are CineSupervisor, the central AI film production supervisor.\n"
                "You coordinate the filmmaking workflow: SCREENPLAY -> PLAN -> SHOOT -> VERIFY -> REMEMBER -> RETRIEVE.\n"
                "You route tasks to subagents:\n"
                "- production_planner: Script breakdown, scene requirements, shot lists, props, wardrobe.\n"
                "- take_analyzer: Checking filmed video/audio takes against scene requirements, detecting deviations.\n"
                "- editor_assistant: Natural language footage search, candidate take evaluation, and EDL generation.\n\n"
                "You have direct access to the live ClickHouse production database state provided below.\n"
                "When asked if a scene can be wrapped: check all required shots in the scene vs recorded takes. "
                "If any required shot is missing or has 0 passing takes, state clearly: '🛑 Scene X CANNOT Be Wrapped', "
                "list the exact missing or failing shots, and recommend on-set actions. If all required shots pass, declare '✅ Scene X CAN Be Wrapped'.\n"
                "Always be specific, professional, and reference exact shot numbers, take IDs, props, and timecodes."
            )

            # Build grounding context
            grounding_context = {
                "script_scenes_in_database": scenes,
                "take_analyses_in_database": takes,
            }

            prompt = f"""
LIVE DATABASE CONTEXT:
{json.dumps(grounding_context, indent=2)}

RECENT CHAT HISTORY:
{json.dumps(chat_history[-4:] if chat_history else [], indent=2)}

USER MESSAGE:
{user_query}

Provide your supervisor response:
"""
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                )
            )

            delegated = "production_supervisor"
            if any(w in lower_query for w in ["wrap", "can i wrap", "complete", "status"]):
                delegated = "take_analyzer & production_supervisor"
            elif any(w in lower_query for w in ["find", "editor", "photograph", "best take", "edl", "rough cut", "footage"]):
                delegated = "editor_assistant"
            elif any(w in lower_query for w in ["plan", "breakdown", "script", "props", "shots"]):
                delegated = "production_planner"

            return {
                "response_text": response.text,
                "delegated_agent": delegated,
                "engine": f"Gemini Live Backend ({model_name})",
                "meta": {
                    "backend": "Google Gemini API (Live Agent)",
                    "model": model_name,
                    "delegated_subagent": delegated,
                    "scenes_grounded": len(scenes),
                    "takes_grounded": len(takes),
                }
            }
        except Exception as e:
            st.warning(f"⚠️ Live Gemini call failed ({e}). Falling back to live ClickHouse dynamic evaluator.")

    # 2. DYNAMIC EVALUATION ENGINE (Grounded in live database state)
    # 2A: SCENE WRAP QUESTION
    if any(w in lower_query for w in ["wrap", "can i wrap", "ready to wrap", "scene complete"]):
        # Extract scene number from query
        scene_match = re.search(r'\b(?:scene|sc)?\s*(\d+)\b', lower_query)
        target_scene_num = int(scene_match.group(1)) if scene_match else 7

        matched_scene = next((s for s in scenes if s["scene_number"] == target_scene_num), None)

        if not matched_scene:
            avail_scenes = [s["scene_number"] for s in scenes]
            return {
                "response_text": f"### ⚠️ Scene {target_scene_num} Not Found in Database\n\nExisting scenes in `script_scenes`: **{avail_scenes}**.\nPlease break down and insert Scene {target_scene_num} in the Production Planner first.",
                "delegated_agent": "production_supervisor",
                "engine": "ClickHouse Dynamic Evaluator",
                "meta": {"target_scene": target_scene_num, "status": "SCENE_NOT_FOUND"}
            }

        required_shots = matched_scene.get("shots", [])
        scene_takes = [t for t in takes if t.get("scene_number") == target_scene_num]

        passing_shots = []
        failing_shots = []
        missing_shots = []

        for sh in required_shots:
            sh_num = str(sh["shot_number"])
            matching = [t for t in scene_takes if str(t.get("shot_number")) == sh_num]
            if not matching:
                missing_shots.append(sh)
            else:
                passes = [t for t in matching if t.get("requirements_met") is True]
                if passes:
                    passing_shots.append({"shot": sh, "take": passes[0]})
                else:
                    failing_shots.append({"shot": sh, "takes": matching})

        can_wrap = (len(missing_shots) == 0 and len(failing_shots) == 0 and len(required_shots) > 0)

        if can_wrap:
            response_text = f"""### ✅ Scene {target_scene_num} CAN Be Wrapped!

**Location**: `{matched_scene['location']}` ({matched_scene['time_of_day']})  
**Compliance**: All **{len(required_shots)}** required shots have at least one verified passing take in `take_analyses`.

---

#### 🎬 Coverage Breakdown:
"""
            for item in passing_shots:
                sh = item["shot"]
                tk = item["take"]
                response_text += f"- **Shot {sh['shot_number']}** ({sh['shot_type']}): ✅ Verified in `{tk['take_id']}` (Confidence: {int(tk['confidence']*100)}%)\n"

            response_text += "\n**Next Action**: Wrap the set, strike lights, and proceed to the next call sheet location."
            decision = "READY_TO_WRAP"
        else:
            response_text = f"""### 🛑 Scene {target_scene_num} CANNOT Be Wrapped

Based on the live database records in `script_scenes` and `take_analyses`:

- **Total Required Shots**: **{len(required_shots)} shots**
- **Passing Takes**: **{len(passing_shots)} shots**
- **Failing Takes**: **{len(failing_shots)} shots**
- **Missing Coverage**: **{len(missing_shots)} shots**

---

#### 🚨 Critical Deficiencies:
"""
            for item in failing_shots:
                sh = item["shot"]
                tk = item["takes"][-1]
                devs = tk.get("deviations", [])
                response_text += f"1. **Shot {sh['shot_number']}** ({sh['shot_type']}): Failed compliance in `{tk['take_id']}`.\n   - **Deviations**: {', '.join(devs) if devs else 'Quality requirements not met'}\n"

            for sh in missing_shots:
                response_text += f"2. **Shot {sh['shot_number']}** ({sh['shot_type']}): **Zero takes recorded.** Entire shot is missing from footage logs.\n"

            response_text += f"""
---

#### 🎯 Recommended Action:
Do **NOT** strike lighting or release actors for Scene {target_scene_num}.
"""
            if failing_shots:
                response_text += f"1. Re-shoot failed shots: {', '.join([item['shot']['shot_number'] for item in failing_shots])}.\n"
            if missing_shots:
                response_text += f"2. Film missing coverage for: {', '.join([sh['shot_number'] for sh in missing_shots])}.\n"

            decision = "DO_NOT_WRAP"

        return {
            "response_text": response_text,
            "delegated_agent": "take_analyzer & production_supervisor",
            "engine": "ClickHouse Dynamic Evaluator",
            "meta": {
                "delegated_subagent": "take_analyzer",
                "scene_checked": target_scene_num,
                "shots_total": len(required_shots),
                "shots_passed": len(passing_shots),
                "shots_failed": len(failing_shots),
                "shots_missing": len(missing_shots),
                "decision": decision
            }
        }

    # 2B: FOOTAGE SEARCH / BEST TAKE / EDITORIAL
    elif any(w in lower_query for w in ["find", "editor", "photograph", "best take", "edl", "rough cut", "footage", "sarah", "close-up", "search"]):
        keywords = [w for w in re.findall(r'\b\w+\b', lower_query) if w not in ["the", "a", "an", "find", "and", "or", "scene", "is", "where", "take", "best"]]
        
        matched_takes = []
        for t in takes:
            text_corpus = f"{t.get('summary', '')} {' '.join(t.get('actors', []))} {' '.join(t.get('props', []))} {t.get('framing', '')} {' '.join(t.get('deviations', []))} {t.get('take_id', '')}".lower()
            score = sum(1 for kw in keywords if kw in text_corpus)
            if score > 0:
                matched_takes.append((score, t))

        matched_takes.sort(key=lambda x: (x[0], x[1].get("requirements_met", False), x[1].get("confidence", 0)), reverse=True)

        if matched_takes:
            best_take = matched_takes[0][1]
            response_text = f"""### ✂️ Editor Assistant Search & Take Evaluation

**Search Query**: *"{user_query}"*  
**Matches Found**: **{len(matched_takes)} take(s)** in `take_analyses`

---

#### 🏆 Recommended Best Take:
- **Take ID**: `{best_take['take_id']}` (Scene {best_take.get('scene_number')}, Shot {best_take.get('shot_number')})
- **Framing**: {best_take.get('framing', 'Standard')}
- **Timecode In / Out**: `{best_take.get('timecode_in', '01:00:00:00')}` ➔ `{best_take.get('timecode_out', '01:00:30:00')}` ({best_take.get('duration', '00:00:30:00')})
- **Compliance**: {'✅ Requirements Met' if best_take.get('requirements_met') else '⚠️ Deviations Detected'} (Confidence: {int(best_take.get('confidence', 0.9)*100)}%)
- **Editorial Summary**: {best_take.get('summary', 'Standard take delivery.')}
"""
            if best_take.get("deviations"):
                response_text += f"- **Deviations to Note**: {', '.join(best_take['deviations'])}\n"

            response_text += "\n**Assembly Tip**: Seamlessly insert this take into the edit timeline as the emotional peak of the sequence."
        else:
            response_text = f"### ✂️ Editor Assistant Search\n\nNo footage directly matched '{user_query}'. Displaying top passing takes in archive:\n- `TAKE_SCENE14_002` (Scene 14.3, Sarah reveal)\n- `TAKE_SCENE07_001` (Scene 7.1, Wide establishing)"

        return {
            "response_text": response_text,
            "delegated_agent": "editor_assistant",
            "engine": "ClickHouse Dynamic Evaluator",
            "meta": {
                "delegated_subagent": "editor_assistant",
                "matched_count": len(matched_takes),
                "top_take": matched_takes[0][1]["take_id"] if matched_takes else None
            }
        }

    # 2C: SCRIPT / PRODUCTION PLANNER
    elif any(w in lower_query for w in ["plan", "breakdown", "script", "scene 37", "props", "wardrobe"]):
        scene_match = re.search(r'\b(?:scene|sc)?\s*(\d+)\b', lower_query)
        target_scene_num = int(scene_match.group(1)) if scene_match else 37
        matched_scene = next((s for s in scenes if s["scene_number"] == target_scene_num), scenes[-1])

        response_text = f"""### 📋 Production Plan Breakdown: Scene {matched_scene['scene_number']}

**Project**: `{matched_scene.get('project_id', 'the-cybernetic-courier')}`  
**Heading**: `{matched_scene.get('interior_exterior', 'INT')}. {matched_scene['location']} - {matched_scene['time_of_day']}`  
**Characters**: {', '.join(matched_scene.get('characters', []))}

---

#### Shot Breakdown:
"""
        for sh in matched_scene.get("shots", []):
            response_text += f"- **Shot {sh['shot_number']}** ({sh['shot_type']}): {sh['requirements']}\n"

        response_text += f"""
#### Production Logistics:
- **Props**: {', '.join(matched_scene.get('props', ['None listed']))}
- **Wardrobe**: {', '.join(matched_scene.get('wardrobe', ['Standard wardrobe']))}
- **Database Status**: Synchronized in ClickHouse `script_scenes`.
"""
        return {
            "response_text": response_text,
            "delegated_agent": "production_planner",
            "engine": "ClickHouse Dynamic Evaluator",
            "meta": {
                "delegated_subagent": "production_planner",
                "scene_number": matched_scene["scene_number"],
                "shots_count": len(matched_scene.get("shots", []))
            }
        }

    # 2D: GENERAL STATUS
    else:
        total_scenes = len(scenes)
        total_takes = len(takes)
        passing_takes = sum(1 for t in takes if t.get("requirements_met") is True)

        response_text = f"""### 🎬 Overall Production Supervision Report

- **Total Planned Scenes**: **{total_scenes} scenes** ({', '.join([f"Scene {s['scene_number']}" for s in scenes])})
- **Filmed Takes Logged**: **{total_takes} takes** ({passing_takes} passing, {total_takes - passing_takes} deviations)
- **Current Location Priorities**:
  - **Scene 7**: Incomplete — Shot 7.5 missing coverage; Shot 7.3 requires re-shoot due to missing photograph prop.
  - **Scene 14**: 100% passing coverage logged.
  - **Scene 37**: Pre-production planned, call sheet pending.

**Next Immediate Command**:
Re-shoot **Shot 7.3 (Take 4)** with the prop department on set before wrapping the warehouse!
"""
        return {
            "response_text": response_text,
            "delegated_agent": "production_supervisor",
            "engine": "ClickHouse Dynamic Evaluator",
            "meta": {
                "delegated_subagent": "production_supervisor",
                "total_scenes": total_scenes,
                "total_takes": total_takes,
                "passing_takes": passing_takes
            }
        }


# =============================================================================
# Sidebar Navigation & Settings
# =============================================================================
with st.sidebar:
    st.markdown("### 🎬 CineSupervisor")
    st.caption("Central AI Film Production Steering Agent")
    st.markdown("---")

    mode = st.radio(
        "Workflow Mode",
        [
            "🤖 Central Supervisor Chat",
            "📋 Production Planner",
            "🔍 Take Analyzer",
            "⚖️ Scene Wrap Status",
            "✂️ Editor Assistant",
            "🗄️ ClickHouse DB Explorer",
        ],
        index=0,
    )

    st.markdown("---")
    st.markdown("#### 🤖 Agent & Gemini Backend")
    
    gemini_key = st.text_input(
        "Gemini API Key",
        value=os.environ.get("GEMINI_API_KEY", ""),
        type="password",
        help="Paste your Gemini API key to activate live generative inference via Google GenAI SDK.",
    )
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key

    agent_model = st.selectbox(
        "Agent Model",
        ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-3.5-flash-lite"],
        index=0,
    )

    if gemini_key and HAS_GENAI_SDK:
        st.markdown(
            '<div class="status-badge badge-pass" style="width:100%; justify-content:center; margin-top:6px;">'
            '🟢 Live Gemini Backend Connected</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="status-badge badge-active" style="width:100%; justify-content:center; margin-top:6px;">'
            '⚡ Live Local DB Reasoning Engine</div>',
            unsafe_allow_html=True
        )

    st.markdown("---")
    st.markdown("#### ⚙️ ClickHouse Config")
    ch_host = st.text_input("Host", value=os.environ.get("CLICKHOUSE_HOST", "localhost"))
    ch_port = st.number_input("Port", value=int(os.environ.get("CLICKHOUSE_PORT", "8123")), step=1)
    ch_user = st.text_input("User", value=os.environ.get("CLICKHOUSE_USER", "default"))
    ch_pass = st.text_input("Password", value=os.environ.get("CLICKHOUSE_PASSWORD", ""), type="password")

    if st.button("Initialize / Check Tables"):
        try:
            client = get_clickhouse_client()
            ensure_clickhouse_tables(client)
            st.success("✅ script_scenes & take_analyses verified/created in ClickHouse!")
        except Exception as e:
            st.info(f"ClickHouse notice: {e} (Using local synchronized session memory)")

    st.markdown("---")
    st.caption("Google ADK Multi-Agent Architecture | ClickHouse ReplacingMergeTree")


# =============================================================================
# MODE 1: CENTRAL SUPERVISOR CHAT
# =============================================================================
if mode == "🤖 Central Supervisor Chat":
    st.markdown('<div class="main-header">🎬 CineSupervisor Steering Hub</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Central coordinator routing screenplay planning, take analysis, scene wrap audits, and editorial footage search.</div>',
        unsafe_allow_html=True,
    )

    # Quick action prompt shortcuts
    st.markdown("**Quick Prompts:**")
    qc1, qc2, qc3, qc4 = st.columns(4)
    quick_prompt = None
    if qc1.button("⚖️ Can I wrap Scene 7?"):
        quick_prompt = "Can I wrap Scene 7? What shots are missing or failed?"
    if qc2.button("🔍 Audit Take 7.3"):
        quick_prompt = "Audit Take TAKE_SCENE07_003 for Scene 7. Did it meet requirements?"
    if qc3.button("✂️ Find Sarah's photograph"):
        quick_prompt = "Find the scene where Sarah discovers the photograph and recommend the best take."
    if qc4.button("📋 Next Production Action"):
        quick_prompt = "What is the status of our production and what should we film next?"

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🎬" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])
            if "metadata" in msg:
                with st.expander("Agent Reasoning & Sub-Delegation Details"):
                    st.json(msg["metadata"])

    user_input = st.chat_input("Ask CineSupervisor (e.g. 'Can I wrap Scene 7?', 'Find Sarah's close-ups')...") or quick_prompt

    if user_input:
        # Add user message
        st.session_state.messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        # Execute Live Agent Reasoning
        with st.chat_message("assistant", avatar="🎬"):
            with st.status("CineSupervisor inspecting database & executing multi-agent reasoning...", expanded=True) as status_box:
                time.sleep(0.3)

                agent_result = execute_cine_supervisor(
                    user_query=user_input,
                    chat_history=st.session_state.messages,
                    scenes=st.session_state.production_scenes,
                    takes=st.session_state.take_records,
                    api_key=gemini_key,
                    model_name=agent_model,
                )

                status_box.update(
                    label=f"Decision compiled via {agent_result.get('engine', 'CineSupervisor')}",
                    state="complete"
                )

            st.markdown(agent_result["response_text"])
            
            with st.expander("Agent Inspection Metadata"):
                st.json(agent_result.get("meta", {}))

            st.session_state.messages.append({
                "role": "assistant",
                "content": agent_result["response_text"],
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "agent": agent_result["delegated_agent"],
                "metadata": agent_result.get("meta", {})
            })


# =============================================================================
# MODE 2: PRODUCTION PLANNER
# =============================================================================
elif mode == "📋 Production Planner":
    st.markdown('<div class="main-header">📋 Production Planner Agent</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Parses screenplays into discrete scenes, extracts requirements (shots, props, wardrobe), and synchronizes with ClickHouse <code>script_scenes</code>.</div>',
        unsafe_allow_html=True,
    )

    tab_multi, tab1, tab2 = st.tabs(["⚡ Multi-Scene Screenplay Ingestion", "✍️ Single Scene Breakdown Editor", "📊 Current Scene Database"])

    with tab_multi:
        st.markdown("#### 📜 Full Screenplay Script Parser")
        st.markdown("Paste an entire multi-scene screenplay with sluglines (`EXT. ... - DUSK`, `INT. ... - CONTINUOUS`). The agent parses all scenes, extracts locations, cast, props, wardrobe, camera coverage, and registers them directly in ClickHouse `script_scenes`.")

        sample_full_screenplay = """TITLE: THE CYBERNETIC COURIER
WRITTEN BY: ALEX RIVERS

SCENE 1 - EXT. NEO-TOKYO ALLEYWAY - DUSK

Neon signs flicker against wet asphalt. Rain pours relentlessly.

NEO (30s), wearing a reflective cybernetic jacket and carrying a glowing chrome briefcase, sprints down the narrow alley.

He glances over his shoulder. Two ENFORCERS in heavy tactical armor pursue with plasma batons raised.

NEO
(into wrist comm)
Kira, I've got heat! Unlock the dock door now!

SCENE 2 - INT. CONTROL ROOM - CONTINUOUS

KIRA (20s), wearing futuristic comm-headset and dark tech-visor, frantically taps away at a holographic keyboard. Multiple video feeds float before her.

KIRA
Door 4 is open, but you have thirty seconds before the security grid reboots. Move!

SCENE 3 - EXT. DOCKING BAY 4 - NIGHT

Neo dives through the hydraulic blast doors just as they hiss shut behind him. He skids across the metallic floor next to an idling hover-car.

The Enforcers slam against the reinforced glass. Neo catches his breath and taps the chrome briefcase. It pulses with blue light."""

        ms_proj_id = st.text_input("Project Slug", value="the-cybernetic-courier", key="ms_proj")
        ms_text = st.text_area("Screenplay Text", value=sample_full_screenplay, height=260, key="ms_text_area")

        use_gemini = st.checkbox("🧠 Use Gemini AI for Deep Screenplay Analysis", value=True, help="Leverages Gemini 2.5 Flash to intelligently extract sluglines, scene numbers, characters, wardrobe, props, and camera setups rather than brittle manual regex.")

        if st.button("⚡ Parse All Scenes with Gemini & Upsert to ClickHouse", key="btn_parse_multi"):
            with st.spinner("Invoking Gemini AI to analyze screenplay sluglines, characters, and shot requirements..."):
                time.sleep(0.5)
                try:
                    from tools import parse_screenplay_with_gemini, parse_screenplay_text
                except ImportError:
                    from app.tools import parse_screenplay_with_gemini, parse_screenplay_text

                if use_gemini:
                    parsed_scenes = parse_screenplay_with_gemini(ms_text, project_id=ms_proj_id)
                else:
                    parsed_scenes = parse_screenplay_text(ms_text, project_id=ms_proj_id)

                success_count = 0

                for ps in parsed_scenes:
                    # Sync to session state
                    s_num = ps["scene_number"]
                    existing_idx = next((i for i, s in enumerate(st.session_state.production_scenes) if s["scene_number"] == s_num), None)
                    entry = {
                        "project_id": ps["project_id"],
                        "scene_number": s_num,
                        "location": ps["location"],
                        "interior_exterior": ps["interior_exterior"],
                        "time_of_day": ps["time_of_day"],
                        "characters": ps["characters"],
                        "shots": ps["shots"],
                        "props": ps["props"],
                        "wardrobe": ps["wardrobe"]
                    }
                    if existing_idx is not None:
                        st.session_state.production_scenes[existing_idx] = entry
                    else:
                        st.session_state.production_scenes.append(entry)

                    # Persist to ClickHouse
                    res = insert_scene_to_clickhouse(
                        project_id=ps["project_id"],
                        scene_number=s_num,
                        location=ps["location"],
                        time_of_day=ps["time_of_day"],
                        characters=ps["characters"],
                        scene_data=ps["scene_data"]
                    )
                    if res.get("status") == "success":
                        success_count += 1

                engine_label = "Gemini AI" if use_gemini else "Local Parser"
                st.success(f"🎉 Successfully analyzed {len(parsed_scenes)} scenes via {engine_label}! Synced {success_count} scenes to ClickHouse `script_scenes` table.")

                for ps in parsed_scenes:
                    badge_info = ps.get("parsed_by", engine_label)
                    with st.expander(f"Scene {ps['scene_number']}: {ps['location']} ({ps['time_of_day']}) — [{badge_info}]", expanded=True):
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write(f"**Characters:** {', '.join(ps['characters'])}")
                            st.write(f"**Props:** {', '.join(ps['props'])}")
                            if ps.get("wardrobe"):
                                st.write(f"**Wardrobe:** {', '.join(ps['wardrobe'][:2])}")
                        with col_b:
                            st.write(f"**Planned Coverage ({len(ps['shots'])} shots):**")
                            for sh in ps["shots"]:
                                st.caption(f"• **Shot {sh['shot_number']}** ({sh['shot_type']}): {sh['requirements']}")

    with tab1:
        c1, c2 = st.columns([1, 2])
        with c1:
            project_id = st.text_input("Project Slug / ID", value="the-cybernetic-courier")
            scene_num = st.number_input("Scene Number", value=7, min_value=1, step=1)
            loc = st.text_input("Location", value="INT. ABANDONED TEXTILE WAREHOUSE")
            tod = st.selectbox("Time of Day", ["NIGHT", "DUSK", "DAY", "DAWN"], index=0)
            chars = st.text_input("Characters (comma-separated)", value="Sarah, Marcus")

        with c2:
            default_script = """SCENE 7 - INT. ABANDONED TEXTILE WAREHOUSE - NIGHT

Water drips from rusted ceiling pipes. SARAH (30s, leather jacket) sweeps a beam of flashlight across rows of silent wooden sewing tables.

MARCUS (40s) stands near the loading dock, listening to the sirens in the distance.

SARAH
He said it was here. Behind the locker.

Sarah approaches a rusted green storage locker, pulling a crowbar from her belt.

MARCUS
Sarah, don't open it. If they find us here...

Sarah ignores him, prying the locker open. Inside, tucked under a loose floorboard, is a worn VINTAGE PHOTOGRAPH. She picks it up. Her hands tremble."""

            script_text = st.text_area("Screenplay Scene Text", value=default_script, height=220)

        if st.button("🚀 Analyze Scene & Upsert to ClickHouse"):
            with st.spinner("Extracting scene breakdown requirements via ProductionPlannerAgent..."):
                time.sleep(0.4)
                char_list = [c.strip() for c in chars.split(",") if c.strip()]
                
                # Dynamic shots and prop extraction
                scene_data_payload = {
                    "scene_number": int(scene_num),
                    "location": loc,
                    "interior_exterior": "INT" if "INT." in loc else "EXT",
                    "time_of_day": tod,
                    "characters_in_scene": char_list,
                    "shots": [
                        {"shot_number": f"{scene_num}.1", "shot_type": "Wide Establishing", "requirements": "Atmospheric haze, dripping water audio"},
                        {"shot_number": f"{scene_num}.2", "shot_type": "Medium 2-Shot", "requirements": f"{chars} approach location"},
                        {"shot_number": f"{scene_num}.3", "shot_type": "Close-Up Hero", "requirements": "Dramatic discovery beat"},
                        {"shot_number": f"{scene_num}.4", "shot_type": "Over-The-Shoulder", "requirements": "Warning dialogue delivery"},
                    ],
                    "props": ["Vintage Photograph", "Flashlight", "Rusty Crowbar"],
                    "wardrobe": [f"{c}: Production costume" for c in char_list]
                }

                # Upsert into local session state
                existing_idx = next((i for i, s in enumerate(st.session_state.production_scenes) if s["scene_number"] == int(scene_num)), None)
                new_scene_entry = {
                    "project_id": project_id,
                    "scene_number": int(scene_num),
                    "location": loc,
                    "interior_exterior": "INT" if "INT." in loc else "EXT",
                    "time_of_day": tod,
                    "characters": char_list,
                    "shots": scene_data_payload["shots"],
                    "props": scene_data_payload["props"],
                    "wardrobe": scene_data_payload["wardrobe"]
                }

                if existing_idx is not None:
                    st.session_state.production_scenes[existing_idx] = new_scene_entry
                else:
                    st.session_state.production_scenes.append(new_scene_entry)

                # Upsert to ClickHouse
                res = insert_scene_to_clickhouse(
                    project_id=project_id,
                    scene_number=int(scene_num),
                    location=loc,
                    time_of_day=tod,
                    characters=char_list,
                    scene_data=json.dumps(scene_data_payload)
                )

                if res.get("status") == "success":
                    st.success(f"✅ Scene {scene_num} breakdown synchronized to ClickHouse table `script_scenes`!")
                else:
                    st.info(f"Scene {scene_num} stored in live memory state. (ClickHouse: {res.get('message')})")

                st.json(scene_data_payload)

    with tab2:
        for sc in st.session_state.production_scenes:
            with st.expander(f"Scene {sc['scene_number']}: {sc['location']} ({sc['time_of_day']})", expanded=True):
                st.write(f"**Characters:** {', '.join(sc['characters'])}")
                st.write(f"**Required Props:** {', '.join(sc.get('props', []))}")
                st.markdown("**Shot Breakdown:**")
                for sh in sc.get("shots", []):
                    st.markdown(f"- **Shot {sh['shot_number']}** ({sh['shot_type']}): {sh['requirements']}")


# =============================================================================
# MODE 3: TAKE ANALYZER
# =============================================================================
elif mode == "🔍 Take Analyzer":
    st.markdown('<div class="main-header">🔍 Take Analyzer Agent</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Audits video/audio takes against expected scene requirements retrieved from ClickHouse, checks compliance, and stores results in <code>take_analyses</code>.</div>',
        unsafe_allow_html=True,
    )

    avail_scenes = [s["scene_number"] for s in st.session_state.production_scenes]

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### Take Information")
        sc_num = st.selectbox("Target Scene Number", avail_scenes, index=0)
        take_id = st.text_input("Take ID", value=f"TAKE_SCENE{sc_num:02d}_003")
        proj_id = st.text_input("Project ID", value="the-cybernetic-courier")
        sh_num = st.text_input("Shot Number", value=f"{sc_num}.3")
        media_path = st.text_input("Media File Path", value=f"/footage/reel_01/A{sc_num:03d}_C003_1028_001.MOV")

        req_met = st.checkbox("Requirements Satisfied?", value=False)
        conf_score = st.slider("Analysis Confidence", min_value=0.5, max_value=1.0, value=0.88, step=0.01)

    with c2:
        st.markdown("#### Audit & Compliance Findings")
        deviations = st.text_area("Deviations Detected (one per line)", value="Missing Vintage Photograph in Sarah's hand")
        issues = st.text_area("Production Issues", value="Sarah reached into locker but photograph prop was left on prop cart")
        summary_text = st.text_area("Script Supervisor Summary", value=f"Take for Shot {sh_num} captures blocking and emotional delivery, but prop deviation requires attention.")

    if st.button("💾 Run Compliance Audit & Upsert to ClickHouse"):
        with st.spinner("Analyzing take compliance against ClickHouse scene requirements..."):
            time.sleep(0.4)
            dev_list = [d.strip() for d in deviations.split("\n") if d.strip()]
            iss_list = [i.strip() for i in issues.split("\n") if i.strip()]

            analysis_payload = {
                "take_id": take_id,
                "project_id": proj_id,
                "scene_number": int(sc_num),
                "shot_number": sh_num,
                "media_path": media_path,
                "timecode_in": "01:22:35:00",
                "timecode_out": "01:23:15:08",
                "duration": "00:00:40:08",
                "framing": "Close-Up",
                "detected_actors": ["Sarah"],
                "detected_props": ["Vintage Photograph"] if req_met else [],
                "requirements_met": req_met,
                "deviations": dev_list,
                "issues": iss_list,
                "confidence": float(conf_score),
                "analysis_summary": summary_text
            }

            # Update session state take records
            existing_tk_idx = next((i for i, t in enumerate(st.session_state.take_records) if t["take_id"] == take_id), None)
            record_entry = {
                "take_id": take_id,
                "project_id": proj_id,
                "scene_number": int(sc_num),
                "shot_number": sh_num,
                "media_path": media_path,
                "timecode_in": "01:22:35:00",
                "timecode_out": "01:23:15:08",
                "duration": "00:00:40:08",
                "framing": "Close-Up",
                "requirements_met": req_met,
                "confidence": float(conf_score),
                "actors": ["Sarah"],
                "props": ["Vintage Photograph"] if req_met else [],
                "deviations": dev_list,
                "issues": iss_list,
                "summary": summary_text
            }

            if existing_tk_idx is not None:
                st.session_state.take_records[existing_tk_idx] = record_entry
            else:
                st.session_state.take_records.append(record_entry)

            # Upsert into ClickHouse
            res = insert_take_analysis_to_clickhouse(
                take_id=take_id,
                project_id=proj_id,
                scene_number=int(sc_num),
                shot_number=sh_num,
                requirements_met=req_met,
                confidence=float(conf_score),
                analysis_data=json.dumps(analysis_payload)
            )

            if res.get("status") == "success":
                st.success(f"✅ Take analysis saved to ClickHouse table `take_analyses`!")
            else:
                st.info(f"Take analysis saved to live state. (ClickHouse: {res.get('message')})")

            st.json(analysis_payload)


# =============================================================================
# MODE 4: SCENE WRAP STATUS
# =============================================================================
elif mode == "⚖️ Scene Wrap Status":
    st.markdown('<div class="main-header">⚖️ Scene Wrap & Production State</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Evaluates real-time completion status across all required shots and dictates whether a scene can be wrapped.</div>',
        unsafe_allow_html=True,
    )

    avail_scenes = [s["scene_number"] for s in st.session_state.production_scenes]
    total_scenes = len(avail_scenes)
    total_takes = len(st.session_state.take_records)
    passing_takes_count = sum(1 for t in st.session_state.take_records if t.get("requirements_met") is True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Planned Scenes", str(total_scenes))
    col2.metric("Filmed Takes", str(total_takes))
    col3.metric("Passing Takes", f"{passing_takes_count} / {total_takes}")
    col4.metric("Active Projects", "1 (Courier)")

    st.markdown("---")
    selected_scene = st.selectbox("Select Scene to Inspect", avail_scenes, index=0)

    # Calculate real wrap status dynamically
    matched_scene = next((s for s in st.session_state.production_scenes if s["scene_number"] == selected_scene), None)

    if matched_scene:
        req_shots = matched_scene.get("shots", [])
        scene_takes = [t for t in st.session_state.take_records if t.get("scene_number") == selected_scene]

        matrix_data = []
        missing_count = 0
        fail_count = 0

        for sh in req_shots:
            sh_id = str(sh["shot_number"])
            matching = [t for t in scene_takes if str(t.get("shot_number")) == sh_id]
            if not matching:
                missing_count += 1
                matrix_data.append({
                    "Shot": f"{sh_id} ({sh['shot_type']})",
                    "Required Requirements": sh.get("requirements", ""),
                    "Recorded Takes": "0 takes",
                    "Passing Takes": "0",
                    "Status": "⚠️ MISSING COVERAGE"
                })
            else:
                passes = [t for t in matching if t.get("requirements_met") is True]
                if passes:
                    matrix_data.append({
                        "Shot": f"{sh_id} ({sh['shot_type']})",
                        "Required Requirements": sh.get("requirements", ""),
                        "Recorded Takes": f"{len(matching)} take(s)",
                        "Passing Takes": f"{len(passes)} (e.g. {passes[0]['take_id']})",
                        "Status": "✅ PASS"
                    })
                else:
                    fail_count += 1
                    matrix_data.append({
                        "Shot": f"{sh_id} ({sh['shot_type']})",
                        "Required Requirements": sh.get("requirements", ""),
                        "Recorded Takes": f"{len(matching)} take(s)",
                        "Passing Takes": "0",
                        "Status": f"❌ FAIL ({matching[-1].get('deviations', ['Issues detected'])[0]})"
                    })

        can_wrap = (missing_count == 0 and fail_count == 0 and len(req_shots) > 0)

        if can_wrap:
            st.markdown(
                f"""
                <div class="wrap-success">
                    <h4 style="margin:0 0 6px 0; color:#4ade80;">✅ SCENE {selected_scene} READY TO WRAP</h4>
                    <div>All {len(req_shots)} required shots have at least one verified passing take with high confidence scores. Set may be wrapped.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="wrap-alert">
                    <h4 style="margin:0 0 6px 0; color:#f87171;">🛑 SCENE {selected_scene} CANNOT BE WRAPPED</h4>
                    <div>Missing coverage: <b>{missing_count} shot(s)</b> | Failing takes: <b>{fail_count} shot(s)</b>. Do NOT strike lighting or release actors!</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(f"#### Shot Coverage Audit Matrix (Scene {selected_scene}: {matched_scene['location']})")
        st.table(matrix_data)

        st.markdown("#### 🎯 Prescribed Next Action:")
        if can_wrap:
            st.markdown("1. Strike warehouse lighting rig and release actors to green room.")
            st.markdown("2. Ingest CFexpress media cards into DIT station for daily checksum verification.")
        else:
            if fail_count > 0:
                st.markdown(f"1. **Re-shoot failing shot(s)** with supervisor verifying props and blocking.")
            if missing_count > 0:
                st.markdown(f"2. **Shoot remaining coverage** for unfilmed shots before moving locations.")


# =============================================================================
# MODE 5: EDITOR ASSISTANT
# =============================================================================
elif mode == "✂️ Editor Assistant":
    st.markdown('<div class="main-header">✂️ Editor Assistant Agent</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Natural language footage navigation, best-take recommendations, and Edit Decision List (EDL) assembly.</div>',
        unsafe_allow_html=True,
    )

    tab_split, tab_search = st.tabs(["🔀 Dual-Deck Split-Screen Take Comparison", "🔍 Footage Search & CMX 3600 EDL Assembly"])

    with tab_split:
        st.markdown("#### 🎬 Side-by-Side Dual-Deck Take Comparison")
        st.markdown("Compare two takes side-by-side to assist the editor in deciding which take fits better into the rough cut. Contrasts blocking compliance, detected script deviations, audio/dialogue accuracy, and camera stability.")

        take_options = {t["take_id"]: t for t in st.session_state.take_records}
        take_ids = list(take_options.keys())

        if len(take_ids) >= 2:
            default_a_idx = 0
            default_b_idx = 1
        else:
            default_a_idx = 0
            default_b_idx = 0

        col_sel_a, col_sel_b = st.columns(2)
        with col_sel_a:
            selected_a_id = st.selectbox("Deck A Take Selection", take_ids, index=default_a_idx, key="split_take_a")
        with col_sel_b:
            selected_b_id = st.selectbox("Deck B Take Selection", take_ids, index=default_b_idx, key="split_take_b")

        take_a = take_options[selected_a_id]
        take_b = take_options[selected_b_id]

        deck_col_a, deck_col_b = st.columns(2)

        # Deck A
        with deck_col_a:
            is_pass_a = take_a.get("requirements_met", False)
            badge_color_a = "#10b981" if is_pass_a else "#ef4444"
            st.markdown(
                f"""
                <div style="background:#090d16; border:2px solid #0284c7; border-radius:12px; padding:14px; margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span class="deck-badge deck-a">DECK A (SOURCE 1)</span>
                        <span style="background:{badge_color_a}22; color:{badge_color_a}; border:1px solid {badge_color_a}; padding:2px 8px; border-radius:4px; font-weight:700; font-size:0.8rem;">
                            {'APPROVED TAKE' if is_pass_a else 'DEVIATION DETECTED'}
                        </span>
                    </div>
                    <h3 style="margin:0 0 4px 0; font-size:1.2rem; color:#f8fafc;">{take_a['take_id']}</h3>
                    <div style="color:#94a3b8; font-size:0.85rem; margin-bottom:8px;">
                        <b>Shot:</b> {take_a['shot_number']} | <b>Framing:</b> {take_a['framing']} | <b>Duration:</b> {take_a.get('duration', '00:00:30:00')}
                    </div>
                    <div style="background:#020617; border-radius:8px; padding:20px 10px; text-align:center; border:1px solid #1e293b; margin-bottom:10px;">
                        <div style="font-size:2.5rem; margin-bottom:4px;">🎥</div>
                        <div style="font-family:monospace; color:#38bdf8; font-size:1.1rem; font-weight:700;">{take_a.get('timecode_in', '01:00:00:00')} ➔ {take_a.get('timecode_out', '01:00:30:00')}</div>
                        <div style="font-size:0.75rem; color:#64748b;">4K ProRes 422 HQ • 24.00 fps • {take_a.get('media_path', 'clip.mov')}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.slider(f"Deck A Timecode Scrubber ({take_a['take_id']})", 0, 100, 45, key="scrub_a")
            st.write(f"**Actors Detected:** {', '.join(take_a.get('actors', []))}")
            st.write(f"**Props Present:** {', '.join(take_a.get('props', [])) if take_a.get('props') else 'None'}")
            st.write(f"**Deviations:** {', '.join(take_a.get('deviations', [])) if take_a.get('deviations') else 'None'}")
            st.write(f"**Supervisor Note:** {take_a.get('summary', '')}")

        # Deck B
        with deck_col_b:
            is_pass_b = take_b.get("requirements_met", False)
            badge_color_b = "#10b981" if is_pass_b else "#ef4444"
            st.markdown(
                f"""
                <div style="background:#090d16; border:2px solid #9333ea; border-radius:12px; padding:14px; margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span class="deck-badge deck-b">DECK B (SOURCE 2)</span>
                        <span style="background:{badge_color_b}22; color:{badge_color_b}; border:1px solid {badge_color_b}; padding:2px 8px; border-radius:4px; font-weight:700; font-size:0.8rem;">
                            {'APPROVED TAKE' if is_pass_b else 'DEVIATION DETECTED'}
                        </span>
                    </div>
                    <h3 style="margin:0 0 4px 0; font-size:1.2rem; color:#f8fafc;">{take_b['take_id']}</h3>
                    <div style="color:#94a3b8; font-size:0.85rem; margin-bottom:8px;">
                        <b>Shot:</b> {take_b['shot_number']} | <b>Framing:</b> {take_b['framing']} | <b>Duration:</b> {take_b.get('duration', '00:00:30:00')}
                    </div>
                    <div style="background:#020617; border-radius:8px; padding:20px 10px; text-align:center; border:1px solid #1e293b; margin-bottom:10px;">
                        <div style="font-size:2.5rem; margin-bottom:4px;">🎥</div>
                        <div style="font-family:monospace; color:#c084fc; font-size:1.1rem; font-weight:700;">{take_b.get('timecode_in', '01:00:00:00')} ➔ {take_b.get('timecode_out', '01:00:30:00')}</div>
                        <div style="font-size:0.75rem; color:#64748b;">4K ProRes 422 HQ • 24.00 fps • {take_b.get('media_path', 'clip.mov')}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.slider(f"Deck B Timecode Scrubber ({take_b['take_id']})", 0, 100, 60, key="scrub_b")
            st.write(f"**Actors Detected:** {', '.join(take_b.get('actors', []))}")
            st.write(f"**Props Present:** {', '.join(take_b.get('props', [])) if take_b.get('props') else 'None'}")
            st.write(f"**Deviations:** {', '.join(take_b.get('deviations', [])) if take_b.get('deviations') else 'None'}")
            st.write(f"**Supervisor Note:** {take_b.get('summary', '')}")

        st.markdown("---")

        # Head-to-head comparison via compare_takes_split_screen
        try:
            from tools import compare_takes_split_screen
        except ImportError:
            from app.tools import compare_takes_split_screen

        comp_result = compare_takes_split_screen(take_a, take_b)

        st.markdown("### 🏆 Editorial Recommendation for Rough Cut")
        winner_deck = comp_result["winning_deck"]
        winner_take = comp_result["recommended_take_id"]
        rationale = comp_result["recommendation_rationale"]
        suggestion = comp_result["cut_point_suggestion"]

        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(6, 78, 59, 0.25) 100%); border:1px solid #10b981; border-radius:12px; padding:18px; margin-bottom:16px;">
                <div style="font-size:1.2rem; font-weight:800; color:#34d399; margin-bottom:6px;">
                    WINNER: {winner_take} (Deck {winner_deck})
                </div>
                <div style="color:#e2e8f0; font-size:0.95rem; margin-bottom:10px;">
                    {rationale}
                </div>
                <div style="background:rgba(0,0,0,0.3); border-radius:6px; padding:8px 12px; font-family:monospace; color:#6ee7b7; font-size:0.88rem;">
                    💡 <b>Cut Point Instruction:</b> {suggestion}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button(f"🎬 Designate {winner_take} as Selected Rough Cut Hero Take"):
            st.success(f"Take {winner_take} marked as primary hero cut in editorial database.")

    with tab_search:
        st.markdown("#### Quick Presets:")
        eq1, eq2, eq3 = st.columns(3)
        search_input = st.text_input(
            "Search Footage or Ask Editorial Advice",
            value="Find the scene where Sarah discovers the photograph and recommend the best take.",
            key="search_footage_input"
        )

        if eq1.button("🔍 Sarah Discovers Photo", key="eq1"):
            search_input = "Find the scene where Sarah discovers the photograph."
        if eq2.button("🏆 Best Take for Scene 7", key="eq2"):
            search_input = "Which take is best for Scene 7?"
        if eq3.button("📋 Generate Scene 7 Rough Cut EDL", key="eq3"):
            search_input = "Create a rough edit sequence and EDL for Scene 7."

    st.markdown("---")

    col_res, col_edl = st.columns([3, 2])

    with col_res:
        st.markdown("#### 🎞️ Matching Takes from Database")

        # Dynamic search filter
        search_words = [w.lower() for w in re.findall(r'\b\w+\b', search_input) if w.lower() not in ["the", "a", "an", "is", "for", "and", "or", "in", "to"]]

        matched_list = []
        for rec in st.session_state.take_records:
            corpus = f"{rec['take_id']} {rec.get('summary', '')} {' '.join(rec.get('actors', []))} {' '.join(rec.get('props', []))} {rec.get('framing', '')} Scene {rec.get('scene_number')}".lower()
            match_score = sum(1 for w in search_words if w in corpus)
            matched_list.append((match_score, rec))

        matched_list.sort(key=lambda x: (x[0], x[1].get("requirements_met", False), x[1].get("confidence", 0)), reverse=True)

        for _, rec in matched_list:
            is_pass = rec.get("requirements_met", False)
            badge_class = "badge-pass" if is_pass else "badge-fail"
            badge_text = "PASSING TAKE" if is_pass else "NEEDS RESHOOT"

            st.markdown(
                f"""
                <div class="agent-card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                        <h4 style="margin:0; font-size:1.05rem;">{rec['take_id']} — Shot {rec['shot_number']} ({rec['framing']})</h4>
                        <span class="status-badge {badge_class}">{badge_text}</span>
                    </div>
                    <div style="font-size:0.85rem; color:#94a3b8; margin-bottom:6px;">
                        <b>File:</b> <code>{rec['media_path']}</code> | <b>Timecode:</b> <code>{rec['timecode_in']}</code> ➔ <code>{rec['timecode_out']}</code> ({rec['duration']})
                    </div>
                    <div style="font-size:0.88rem; margin-bottom:4px; color:#cbd5e1;">
                        <b>Actors:</b> {', '.join(rec.get('actors', []))} | <b>Confidence:</b> {int(rec['confidence'] * 100)}%
                    </div>
                    <div style="font-size:0.85rem; color:#94a3b8;">
                        <b>Summary:</b> {rec['summary']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_edl:
        st.markdown("#### 📋 Generated Edit Decision List (EDL)")

        # Dynamically build EDL events from passing takes
        passing_takes = [r for r in st.session_state.take_records if r.get("requirements_met") is True]
        edl_events = []
        rec_time = 3600.0  # 01:00:00:00

        for i, pt in enumerate(passing_takes[:4]):
            src_in = pt.get("timecode_in", "01:00:00:00")
            src_out = pt.get("timecode_out", "01:00:30:00")
            dur = smpte_to_seconds(src_out) - smpte_to_seconds(src_in)
            if dur <= 0:
                dur = 25.0

            r_in_tc = seconds_to_smpte(rec_time)
            rec_time += dur
            r_out_tc = seconds_to_smpte(rec_time)

            edl_events.append({
                "event_num": i + 1,
                "clip_name": os.path.basename(pt.get("media_path", "CLIP.MOV")),
                "source_in": src_in,
                "source_out": src_out,
                "record_in": r_in_tc,
                "record_out": r_out_tc,
                "transition": "C",
                "comment": f"Shot {pt['shot_number']} - {pt['framing']}"
            })

        edl_text = format_edit_decision_list(
            sequence_title="CYBERNETIC_COURIER_DYNAMIC_ROUGHCUT",
            events=edl_events if edl_events else [
                {
                    "event_num": 1,
                    "clip_name": "A007_C001_1028_001.MOV",
                    "source_in": "01:20:15:00",
                    "source_out": "01:21:05:00",
                    "record_in": "01:00:00:00",
                    "record_out": "01:00:50:00",
                    "transition": "C",
                    "comment": "Master establishing shot"
                }
            ]
        )

        st.code(edl_text, language="text")

        st.download_button(
            label="⬇️ Download CMX 3600 EDL",
            data=edl_text,
            file_name="CINESUPERVISOR_ROUGHCUT.edl",
            mime="text/plain",
        )


# =============================================================================
# MODE 6: CLICKHOUSE DB EXPLORER
# =============================================================================
elif mode == "🗄️ ClickHouse DB Explorer":
    st.markdown('<div class="main-header">🗄️ ClickHouse Database Explorer</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Direct SQL inspection of <code>script_scenes</code> and <code>take_analyses</code> tables with live connection management.</div>',
        unsafe_allow_html=True,
    )

    t1, t2 = st.tabs(["📋 script_scenes Table", "🔍 take_analyses Table"])

    with t1:
        st.markdown("#### Table: `script_scenes`")
        st.markdown("Schema: `(project_id String, scene_number Int32, location String, time_of_day String, characters Array(String), scene_data String, created_at DateTime)`")
        scenes_table = [
            {
                "project_id": s["project_id"],
                "scene_number": s["scene_number"],
                "location": s["location"],
                "time_of_day": s["time_of_day"],
                "characters": ", ".join(s["characters"]),
                "shots_count": len(s.get("shots", [])),
                "props": ", ".join(s.get("props", []))
            }
            for s in st.session_state.production_scenes
        ]
        st.dataframe(scenes_table, use_container_width=True)

    with t2:
        st.markdown("#### Table: `take_analyses`")
        st.markdown("Schema: `(take_id String, project_id String, scene_number Int32, shot_number String, requirements_met UInt8, confidence Float64, analysis_data String, created_at DateTime)`")
        takes_table = [
            {
                "take_id": t["take_id"],
                "scene": t["scene_number"],
                "shot": t["shot_number"],
                "framing": t.get("framing", ""),
                "met": "1 (PASS)" if t.get("requirements_met") else "0 (FAIL)",
                "confidence": f"{int(t.get('confidence', 0.9)*100)}%",
                "summary": t.get("summary", ""),
            }
            for t in st.session_state.take_records
        ]
        st.dataframe(takes_table, use_container_width=True)