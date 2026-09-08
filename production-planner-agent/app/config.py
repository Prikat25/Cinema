"""Central application configuration.

Keep environment variables, API credentials, and model names in one place.
Never hard-code secrets in application code.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Credentials / external services
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST")
CLICKHOUSE_PORT = os.getenv("CLICKHOUSE_PORT")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD")
ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS", "*")

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
SUPERVISOR_MODEL = os.getenv("SUPERVISOR_MODEL", "gemini-3.5-flash-lite")
PLANNER_MODEL = os.getenv("PLANNER_MODEL", SUPERVISOR_MODEL)
TAKE_ANALYZER_MODEL = os.getenv("TAKE_ANALYZER_MODEL", SUPERVISOR_MODEL)
EDITOR_MODEL = os.getenv("EDITOR_MODEL", SUPERVISOR_MODEL)

# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------
APP_NAME = os.getenv("APP_NAME", "app")
STREAMLIT_PORT = int(os.getenv("PORT", "8080"))
