"""Central application configuration.

Environment variables are loaded here so agents, tools, and the UI share one
configuration source. Secrets should be supplied through Cloud Run/Secret
Manager rather than committed to the repository.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Google / Vertex AI
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
GOOGLE_GENAI_USE_VERTEXAI = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() in {"true", "1", "yes"}
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

# ClickHouse
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_SECURE = os.getenv("CLICKHOUSE_SECURE", "true").lower() in {"true", "1", "yes"}
CLICKHOUSE_MCP_URL = os.getenv("CLICKHOUSE_MCP_URL", "https://mcp.clickhouse.cloud/mcp")

ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS", "*")

# Model configuration. Override these in Cloud Run when needed.
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
SUPERVISOR_MODEL = os.getenv("SUPERVISOR_MODEL", DEFAULT_MODEL)
PLANNER_MODEL = os.getenv("PLANNER_MODEL", DEFAULT_MODEL)
TAKE_ANALYZER_MODEL = os.getenv("TAKE_ANALYZER_MODEL", DEFAULT_MODEL)
EDITOR_MODEL = os.getenv("EDITOR_MODEL", DEFAULT_MODEL)

# Runtime
APP_NAME = os.getenv("APP_NAME", "cine-supervisor")
STREAMLIT_PORT = int(os.getenv("PORT", "8080"))
