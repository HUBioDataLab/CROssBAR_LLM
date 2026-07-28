How to install:
```bash
uv init --bare
uv python pin 3.12.11
uv add --requirements requirements.txt
uv sync
```

Recommended installation for reproducing the locked environment:
```bash
uv sync --locked
```

Environment file:
- Copy `.env.example` and create `.env` at `crossbar_llm/agent_tools/.env`
- Use `.env.example` as the template for required variables

How to run the API with reload:
```bash
uv run uvicorn crossbar_llm.api.main:app --host 127.0.0.1 --port 8002 --reload
```
