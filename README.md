 ## CineSupervisor

CineSupervisor is a Streamlit production-control interface backed by a multi-agent
film-production supervisor. 

Use it to:

- Turn a screenplay into a scene breakdown
- Inspect media metadata
- Generate editorial decision lists (EDLs)
- Analyze takes
- Ask operational questions of the production supervisor
- Query production data directly from ClickHouse using `clickhouse_connect`

## Project Structure

```
production-supervisor-agent/
├── app/         # Core agent code
│   ├── agent.py               # Main agent logic
│   ├── production_planner.py  # Production planner agent logic
│   ├── take_analyzer.py       # Take analyzer agent logic
│   └── app_utils/             # App utilities and helpers
├── tests/                     # Unit, integration, and load tests
├── .env.example                # Environment variable template
├── GEMINI.md                  # AI-assisted development guide
└── pyproject.toml             # Project dependencies
```

> 💡 **Tip:** Use [Antigravity CLI](https://antigravity.google/) for AI-assisted development - project context is pre-configured in `GEMINI.md`.

## Requirements

Before you begin, ensure you have:
- **uv**: Python package manager (used for all dependency management in this project) - [Install](https://docs.astral.sh/uv/getting-started/installation/) ([add packages](https://docs.astral.sh/uv/concepts/dependencies/) with `uv add <package>`)
- **agents-cli**: Agents CLI - Install with `uv tool install google-agents-cli`
- **Google Cloud SDK**: For GCP services - [Install](https://cloud.google.com/sdk/docs/install)

# Environment Variables

Before running or testing the application, create a local .env file from the
provided example:

```bash
cp .env.example .env
```

Then update .env with the required values for your environment(ClickHouse, Gemini API, Google Cloud). Never commit .env or credentials/secrets to source control.

## Quick Start

Install `agents-cli` and its skills if not already installed:

```bash
uvx google-agents-cli setup
```

Install required packages:

```bash
agents-cli install
```
If the project uses the application requirements file:

```bash
pip install -r app/requirements.txt
```

Test the agent with a local web server:

```bash
agents-cli playground (for Agents)
```
Or run the Streamlit UI:

```bash
streamlit run app/streamlit_app.py (for UI with Agent Runner)
```

You can also use features from the [ADK](https://adk.dev/) CLI with `uv run adk`.

## Commands

| Command              | Description                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `agents-cli install` | Install dependencies using uv                                                         |
| `agents-cli playground` | Launch local development environment                                                  |
| `agents-cli lint`    | Run code quality checks                                                               |
| `agents-cli eval`    | Evaluate agent behavior (generate, grade, analyze, and more — see `agents-cli eval --help`) |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests                                                        || [A2A Inspector](https://github.com/a2aproject/a2a-inspector) | Launch A2A Protocol Inspector                                                        |

---

## Development

Edit your agent logic in `app/agent.py` and test with `agents-cli playground` - it auto-reloads on save.

## Run unit and integration tests:

```bash
uv run pytest tests/unit tests/integration
```

## Deployment

```bash
gcloud config set project <your-project-id>
agents-cli deploy
```
