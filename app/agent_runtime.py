"""Shared construction helpers for CineSupervisor ADK agents."""

from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types

from app.config import CLICKHOUSE_MCP_URL


def build_gemini_model(model_name: str) -> Gemini:
    """Build a Gemini model with consistent retry behavior."""
    return Gemini(
        model=model_name,
        retry_options=types.HttpRetryOptions(initial_delay=1, attempts=3),
    )


def build_clickhouse_toolset() -> McpToolset:
    """Create a ClickHouse MCP toolset for an individual agent."""
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=CLICKHOUSE_MCP_URL)
    )
