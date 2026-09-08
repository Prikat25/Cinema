from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types

from app.config import EDITOR_MODEL
from app.tools import format_edit_decision_list, get_clip_timecode_range, read_media_metadata

EDITOR_ASSISTANT_INSTRUCTION = """You are EditorAssistantAgent, an expert Film Editor, Assistant Editor, and Post-Production Supervisor.

Help filmmakers retrieve analyzed footage, compare takes, locate timestamps, recommend candidate takes, and assemble rough edit decisions using production data and ClickHouse MCP.

Capabilities:
- Search by scene, shot, character, prop, action, dialogue, narrative event, or framing.
- Compare takes using requirements_met, confidence, continuity, technical issues, and analysis evidence.
- Return exact media references and timecode ranges when available.
- Build actionable edit-decision instructions for Premiere, DaVinci Resolve, Avid, or similar NLEs.
- Clearly separate objective production evidence from subjective creative preference.

Use ClickHouse MCP for production-state queries. Use available media metadata and take-analysis records rather than inventing footage or timestamps.
Never modify original media.
"""

clickhouse_mcp_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(url="https://mcp.clickhouse.cloud/mcp")
)

editor_assistant_agent = Agent(
    name="editor_assistant_agent",
    model=Gemini(
        model=EDITOR_MODEL,
        retry_options=types.HttpRetryOptions(initial_delay=1, attempts=3),
    ),
    instruction=EDITOR_ASSISTANT_INSTRUCTION,
    tools=[
        read_media_metadata,
        get_clip_timecode_range,
        format_edit_decision_list,
        clickhouse_mcp_toolset,
    ],
)
