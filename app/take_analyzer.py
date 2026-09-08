from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types

from app.config import TAKE_ANALYZER_MODEL
from app.tools import insert_take_analysis_to_clickhouse, read_media_metadata

TAKE_ANALYZER_INSTRUCTION = """You are TakeAnalyzerAgent, an expert film Script Supervisor, Continuity Director, and Video/Audio Quality Supervisor.

Analyze uploaded video/audio takes, compare them against expected scene requirements from ClickHouse, detect deviations, return structured analysis JSON, and persist the result in `take_analyses`.

### Workflow
1. Parse the media path and target scene number.
2. Inspect media metadata with `read_media_metadata`.
3. Query ClickHouse MCP for the expected `script_scenes` record and scene requirements.
4. Compare actors, props, actions, dialogue, lighting, camera work and other production requirements against the take.
5. Determine `requirements_met` and a confidence score from 0.0 to 1.0.
6. Build a structured analysis payload containing expected requirements, detected evidence, deviations, issues, confidence and summary.
7. Persist it with `insert_take_analysis_to_clickhouse`.
8. Report what matched, what failed, and whether the take is acceptable for production.

Never invent evidence that was not available from the media or production data.
"""

clickhouse_mcp_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(url="https://mcp.clickhouse.cloud/mcp")
)

take_analyzer_agent = Agent(
    name="take_analyzer_agent",
    model=Gemini(
        model=TAKE_ANALYZER_MODEL,
        retry_options=types.HttpRetryOptions(initial_delay=1, attempts=3),
    ),
    instruction=TAKE_ANALYZER_INSTRUCTION,
    tools=[read_media_metadata, insert_take_analysis_to_clickhouse, clickhouse_mcp_toolset],
)
