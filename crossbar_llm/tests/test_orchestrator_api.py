"""End-to-end tests through the FastAPI routes.

These drive the real app with a TestClient: routing, the browser-identity
cookie, request validation, the response model, JSON serialisation and the
server-sent-event framing all run for real. Only the orchestrator itself is
replaced, because it reaches Neo4j and metered third-party services.

The service is swapped in through `app.dependency_overrides`; patching won't do,
since `get_runtime_service` is `lru_cache`d and the routers resolve it via
`Depends`.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from crossbar_llm.api.core.deps import get_runtime_service
from crossbar_llm.api.core.rate_limit import limiter
from crossbar_llm.api.main import app
from crossbar_llm.api.schemas.common import SearchMode
from crossbar_llm.api.schemas.requests import (
    AgentsConfig,
    DbSearchRequest,
    UploadVectorSearchRequest,
)
from crossbar_llm.api.schemas.responses import (
    AgentRunResult,
    ChatResponse,
    Contradiction,
    OrchestrationResult,
    PendingResumeResponse,
    RoutingDecision,
)
from crossbar_llm.orchestrator.registry import AgentId


class _StubAgentService:
    """Records what the routers hand the service, and returns a fixed response."""

    def __init__(self):
        self.calls = []
        self.response = None
        self.error = None
        self.settings = SimpleNamespace(sse_keepalive_seconds=15.0)
        self.known_sessions = {"session-1"}

    def require_session(self, session_id, browser_id):
        if session_id not in self.known_sessions:
            raise HTTPException(status_code=404, detail="Session not found.")

    async def _record(self, name, payload, emit):
        self.calls.append((name, payload))
        if emit is not None:
            await emit("orchestration.started", {"enabled": ["knowledge_graph"]})
            await emit("agent.started", {"agent": "knowledge_graph"})
        if self.error is not None:
            raise self.error
        return self.response or ChatResponse(
            session_id="session-1",
            status="completed",
            question=getattr(payload, "question", "What is EGFR?"),
            mode=SearchMode.DB_SEARCH,
            final_answer="graph answer",
        )

    async def run_db(self, *, session_id, browser_id, payload, emit=None):
        return await self._record("run_db", payload, emit)

    async def run_vector(self, *, session_id, browser_id, payload, emit=None):
        return await self._record("run_vector", payload, emit)

    async def run_vector_upload(self, *, session_id, browser_id, payload, embedding_file, emit=None):
        return await self._record("run_vector_upload", payload, emit)

    async def load_embedding(self, payload, embedding_file):
        return [0.0, 1.0]

    async def run_vector_embedding(self, session_id, browser_id, payload, embedding, emit=None):
        return await self._record("run_vector_embedding", payload, emit)

    async def resume(self, *, session_id, browser_id, payload, emit=None):
        return await self._record("resume", payload, emit)


@pytest.fixture
def service():
    stub = _StubAgentService()
    app.dependency_overrides[get_runtime_service] = lambda: stub
    yield stub
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    # These tests share one client IP, and the standard limit is 6 requests a
    # minute. Pinned off so that adding the next test here fails for its own
    # reasons, not because it tipped the suite over a rate limit.
    was_enabled = limiter.enabled
    limiter.enabled = False
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        limiter.enabled = was_enabled


def _body(**overrides):
    body = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "question": "What is the role of EGFR in cancer?",
        "execution_mode": "generate_and_run",
    }
    body.update(overrides)
    return body


def _events(response):
    """Parse an SSE body into (event, data) pairs, skipping comments."""
    parsed = []
    for block in response.text.strip().split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        if not lines:
            continue
        event = next(line[len("event: "):] for line in lines if line.startswith("event: "))
        data = next(line[len("data: "):] for line in lines if line.startswith("data: "))
        parsed.append((event, json.loads(data)))
    return parsed


def test_db_search_enables_every_agent_by_default(client, service):
    response = client.post("/sessions/session-1/db-search/query", json=_body())

    assert response.status_code == 200
    _, payload = service.calls[0]
    assert payload.agents == AgentsConfig()
    assert payload.agents.enabled() == list(AgentId)


@pytest.mark.parametrize(
    "agents",
    [
        {"knowledge_graph": True, "paperclip": False, "pubtator3": False},
        {"knowledge_graph": False, "paperclip": True, "pubtator3": False},
        {"knowledge_graph": False, "paperclip": False, "pubtator3": True},
        {"knowledge_graph": True, "paperclip": True, "pubtator3": True},
    ],
)
def test_db_search_forwards_each_agent_combination(client, service, agents):
    response = client.post(
        "/sessions/session-1/db-search/query", json=_body(agents=agents)
    )

    assert response.status_code == 200
    _, payload = service.calls[0]
    for agent_id, enabled in agents.items():
        assert getattr(payload.agents, agent_id) is enabled


def test_disabling_every_agent_is_rejected(client, service):
    response = client.post(
        "/sessions/session-1/db-search/query",
        json=_body(
            agents={"knowledge_graph": False, "paperclip": False, "pubtator3": False}
        ),
    )

    assert response.status_code == 422
    assert service.calls == []


def test_agent_switches_reject_non_boolean_values(client, service):
    response = client.post(
        "/sessions/session-1/db-search/query",
        json=_body(agents={"paperclip": "sometimes"}),
    )

    assert response.status_code == 422
    assert service.calls == []


def test_orchestration_serializes_per_agent(client, service):
    service.response = ChatResponse(
        session_id="session-1",
        status="completed",
        question="What is EGFR?",
        mode=SearchMode.DB_SEARCH,
        final_answer="merged answer [KG] [Paperclip]",
        orchestration=OrchestrationResult(
            routing=RoutingDecision(
                selected=[AgentId.KNOWLEDGE_GRAPH, AgentId.PAPERCLIP],
                skipped={AgentId.PUBTATOR3: "Disabled in your agent settings."},
                strategy="llm",
            ),
            agents={
                AgentId.KNOWLEDGE_GRAPH: AgentRunResult(status="completed", answer="kg"),
                AgentId.PAPERCLIP: AgentRunResult(
                    status="completed",
                    answer="paper answer",
                    citations=[{"title": "A paper", "url": "https://example.org/1"}],
                ),
            },
            contradictions=[
                Contradiction(
                    topic="EGFR expression",
                    agents=[AgentId.KNOWLEDGE_GRAPH, AgentId.PAPERCLIP],
                    resolution="The graph lacks the record; the paper reports it.",
                )
            ],
            synthesized=True,
            answer_sources=[AgentId.KNOWLEDGE_GRAPH, AgentId.PAPERCLIP],
        ),
    )

    body = client.post("/sessions/session-1/db-search/query", json=_body()).json()

    orchestration = body["orchestration"]
    assert body["final_answer"] == "merged answer [KG] [Paperclip]"
    assert orchestration["routing"]["selected"] == ["knowledge_graph", "paperclip"]
    assert orchestration["routing"]["skipped"]["pubtator3"].startswith("Disabled")
    assert orchestration["agents"]["paperclip"]["citations"][0]["url"] == "https://example.org/1"
    assert orchestration["contradictions"][0]["agents"] == ["knowledge_graph", "paperclip"]
    assert orchestration["synthesized"] is True


def test_resume_carries_the_agent_selection(client, service):
    response = client.post(
        "/sessions/session-1/resume",
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "search_mode": "db_search",
            "execution_mode": "resume",
            "action": "approve",
            "edited_cypher": "MATCH (g:Gene) RETURN g",
            "agents": {"paperclip": True, "pubtator3": False},
        },
    )

    assert response.status_code == 200
    name, payload = service.calls[0]
    assert name == "resume"
    assert payload.agents.paperclip is True
    assert payload.agents.pubtator3 is False


def test_resume_can_pause_for_review_again(client, service):
    service.response = PendingResumeResponse(
        session_id="session-1",
        question="What is EGFR?",
        mode=SearchMode.DB_SEARCH,
        generated_cypher="MATCH (m) RETURN m",
    )

    body = client.post(
        "/sessions/session-1/resume",
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "search_mode": "db_search",
            "execution_mode": "resume",
            "action": "approve",
            "edited_cypher": "MATCH (g:Gene) RETURN g",
        },
    ).json()

    assert body["status"] == "awaiting_human_review"
    assert body["generated_cypher"] == "MATCH (m) RETURN m"


def test_vector_upload_maps_flat_form_switches(client, service):
    response = client.post(
        "/sessions/session-1/vector-search/upload-query",
        data={
            "question": "What is the role of EGFR in cancer?",
            "execution_mode": "generate_and_run",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "vector_category": "gene",
            "embedding_type": "anc2vec",
            # Multipart cannot carry a nested object, so the switches travel
            # flat and are reassembled server-side.
            "knowledge_graph": "true",
            "paperclip": "true",
            "pubtator3": "false",
        },
        files={"embedding_file": ("embedding.npy", b"\x00\x01", "application/octet-stream")},
    )

    assert response.status_code == 200
    _, payload = service.calls[0]
    assert payload.agents == AgentsConfig(
        knowledge_graph=True, paperclip=True, pubtator3=False
    )


def test_pending_review_response_reports_its_status(client, service):
    service.response = PendingResumeResponse(
        session_id="session-1",
        question="What is EGFR?",
        mode=SearchMode.DB_SEARCH,
        generated_cypher="MATCH (g:Gene) RETURN g",
        orchestration=OrchestrationResult(
            routing=RoutingDecision(
                selected=[AgentId.KNOWLEDGE_GRAPH, AgentId.PUBTATOR3], strategy="llm"
            )
        ),
    )

    body = client.post("/sessions/session-1/db-search/query", json=_body()).json()

    assert body["status"] == "awaiting_human_review"
    assert body["generated_cypher"] == "MATCH (g:Gene) RETURN g"
    # The plan the approval will carry out, so the UI can say who runs next.
    assert body["orchestration"]["routing"]["selected"] == ["knowledge_graph", "pubtator3"]


def test_stream_sends_progress_then_the_result(client, service):
    response = client.post(
        "/sessions/session-1/db-search/query/stream", json=_body()
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    assert [name for name, _ in events] == [
        "orchestration.started",
        "agent.started",
        "result",
    ]
    assert events[-1][1]["final_answer"] == "graph answer"


@pytest.mark.parametrize(
    "path, kwargs",
    [
        ("/sessions/session-1/vector-search/query/stream", {"json": _body(vector_category="Protein", embedding_type="Esm2")}),
        (
            "/sessions/session-1/resume/stream",
            {
                "json": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "search_mode": "db_search",
                    "execution_mode": "resume",
                    "action": "approve",
                    "edited_cypher": "MATCH (g:Gene) RETURN g",
                }
            },
        ),
        (
            "/sessions/session-1/vector-search/upload-query/stream",
            {
                "data": {
                    "question": "What is the role of EGFR in cancer?",
                    "execution_mode": "generate_and_run",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "vector_category": "Protein",
                    "embedding_type": "Esm2",
                },
                "files": {"embedding_file": ("e.npy", b"\x00", "application/octet-stream")},
            },
        ),
    ],
)
def test_every_streaming_route_ends_with_a_result(client, service, path, kwargs):
    response = client.post(path, **kwargs)

    assert response.status_code == 200
    assert _events(response)[-1][0] == "result"


def test_stream_reports_service_errors_as_an_error_event(client, service):
    service.error = HTTPException(status_code=400, detail="Vector search runs on the Knowledge Graph agent.")

    events = _events(
        client.post("/sessions/session-1/db-search/query/stream", json=_body())
    )

    assert events[-1] == (
        "error",
        {"status_code": 400, "detail": "Vector search runs on the Knowledge Graph agent."},
    )


def test_stream_hides_unexpected_error_detail(client, service):
    service.error = RuntimeError("bolt://user:secret@neo4j failed")

    name, data = _events(
        client.post("/sessions/session-1/db-search/query/stream", json=_body())
    )[-1]

    assert name == "error"
    assert data["status_code"] == 500
    assert "secret" not in data["detail"]


def test_stream_for_an_unknown_session_is_a_real_404(client, service):
    response = client.post("/sessions/nope/db-search/query/stream", json=_body())

    assert response.status_code == 404
    assert service.calls == []


def test_agents_catalog_lists_every_agent(client, monkeypatch):
    monkeypatch.delenv("PAPERCLIP_API_KEY", raising=False)
    from crossbar_llm.api.routers import agents as agents_router

    monkeypatch.setattr(
        agents_router.settings.env_settings, "paperclip_api_key", None
    )

    body = client.get("/agents").json()

    by_id = {agent["id"]: agent for agent in body["agents"]}
    assert set(by_id) == {"knowledge_graph", "paperclip", "pubtator3"}
    assert by_id["knowledge_graph"]["supports_vector_search"] is True
    assert by_id["pubtator3"]["available"] is True
    # An unconfigured Paperclip is listed, so the UI can say why it is off.
    assert by_id["paperclip"]["available"] is False
    assert "API key" in by_id["paperclip"]["unavailable_reason"]


def test_api_contract_round_trips_agent_configuration():
    request = DbSearchRequest.model_validate(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "question": "What is EGFR?",
            "execution_mode": "generate_and_run",
            "agents": {"knowledge_graph": False, "paperclip": True, "pubtator3": False},
        }
    )
    upload_request = UploadVectorSearchRequest.as_form(
        question="What is EGFR?",
        execution_mode="generate_and_run",
        provider="openai",
        model="gpt-4o-mini",
        top_k=10,
        reasoning_enabled=False,
        reasoning_effort=None,
        knowledge_graph=False,
        paperclip=True,
        pubtator3=False,
        vector_category="gene",
        embedding_type="anc2vec",
    )

    assert request.agents.enabled() == [AgentId.PAPERCLIP]
    assert upload_request.agents == request.agents
