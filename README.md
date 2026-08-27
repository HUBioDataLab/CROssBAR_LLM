# CROSSBAR LLM

## Project Layout

```text
crossbar_llm_github/
├── crossbar_llm/
│   ├── agent_tools/       # Agent, LLM, prompt, logging, and Neo4j logic
│   ├── api/               # FastAPI backend
│   ├── frontend/          # React chat application
│   └── tests/             # Python tests
├── benchmarks/            # Separate uv project for benchmark and analysis code
├── pyproject.toml         
├── uv.lock                
├── requirements.txt       # Dependency list used to initialize/update the uv project
└── .env.example           # Template for required environment variables
```

The main Python application is managed with `uv`. The frontend is a separate React app under `crossbar_llm/frontend`.

## Install the Backend

From the repository root:

```bash
uv sync
```

For exact reproducibility from the committed lockfile:

```bash
uv sync --locked
```

If you need to recreate the project from `requirements.txt`:

```bash
uv init --bare
uv python pin 3.12.11
uv add --requirements requirements.txt
uv sync
```

## Environment File

Copy `.env.example` and create the runtime `.env` file at:

```text
crossbar_llm/agent_tools/.env
```

Use `.env.example` as the template for required variables:

```text
OPENAI_API_KEY=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=

NEO4J_USER=
NEO4J_PASSWORD=
NEO4J_DB_NAME=
NEO4J_URI=

APP_ENV=
BROWSER_COOKIE_SECRET=
RATE_LIMIT_IP_HASH_SECRET=
```

## Run the Backend API

Start the FastAPI backend from the repository root:

```bash
uv run uvicorn crossbar_llm.api.main:app --host 127.0.0.1 --port 8001 --reload
```

Keep this terminal running while using the frontend.

## Install the Frontend

Open a second terminal and install frontend dependencies:

```bash
cd crossbar_llm/frontend
npm install
```

## Run the Frontend

First, make sure the backend API is already running:

```bash
uv run uvicorn crossbar_llm.api.main:app --host 127.0.0.1 --port 8001 --reload
```

Then, in a second terminal:

```bash
cd crossbar_llm/frontend
npm start
```

The React development server will open the chat app in the browser, usually at:

```text
http://localhost:3000
```

During frontend development, changes to JavaScript and CSS files should reload automatically while `npm start` is running.

## Benchmarks

Benchmark and analysis code has its own `uv` project under `benchmarks/`. See:

```text
benchmarks/README.md
```
