"""End-to-end tests through the FastAPI routes.

These drive the real app with a TestClient: routing, the browser-identity
cookie, request validation, the response model and JSON serialisation all run
for real. Only the two agent boundaries are replaced — the Cypher graph and the
literature agents — because those reach Neo4j and metered third-party services.

The service is swapped in through `app.dependency_overrides`; patching won't do,
since `get_runtime_service` is `lru_cache`d and the routers resolve it via
`Depends`.
"""
import pytest
from fastapi.testclient import TestClient

from crossbar_llm.api.core.deps import get_runtime_service
from crossbar_llm.api.core.rate_limit import limiter
from crossbar_llm.api.main import app
from crossbar_llm.api.schemas.common import SearchMode
from crossbar_llm.api.schemas.requests import (
    DbSearchRequest,
    LiteratureToolsConfig,
    UploadVectorSearchRequest,
)
from crossbar_llm.api.schemas.responses import (
    ChatResponse,
    LiteratureToolResult,
    PendingResumeResponse,
)


class _StubAgentService:
    """Records what the routers hand the service, and returns a fixed response."""

    def __init__(self):
        self.calls = []
        self.response = None

    def _record(self, name, payload):
        self.calls.append((name, payload))
        return self.response or ChatResponse(
            session_id="session-1",
            status="completed",
            question=payload.question,
            mode=SearchMode.DB_SEARCH,
            final_answer="graph answer",
        )

    async def run_db(self, *, session_id, browser_id, payload):
        return self._record("run_db", payload)

    async def run_vector(self, *, session_id, browser_id, payload):
        return self._record("run_vector", payload)

    async def run_vector_upload(self, *, session_id, browser_id, payload, embedding_file):
        return self._record("run_vector_upload", payload)

    async def resume(self, *, session_id, browser_id, payload):
        self.calls.append(("resume", payload))
        return self.response or ChatResponse(
            session_id=session_id,
            status="completed",
            question="What is EGFR?",
            mode=payload.search_mode,
            final_answer="graph answer",
        )


@pytest.fixture
def service():
    stub = _StubAgentService()
    app.dependency_overrides[get_runtime_service] = lambda: stub
    yield stub
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    # These tests share one client IP, and the standard limit is 6 requests a
    # minute — comfortably inside what this module already sends. Pinned off so
    # that adding the next test here fails for its own reasons, not because it
    # tipped the suite over a rate limit.
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


def test_db_search_defaults_both_tools_off(client, service):
    response = client.post("/sessions/session-1/db-search/query", json=_body())

    assert response.status_code == 200
    _, payload = service.calls[0]
    assert payload.literature_tools == LiteratureToolsConfig()
    # Absent rather than null: a request that asked for nothing says nothing.
    assert response.json()["literature"] is None


@pytest.mark.parametrize(
    "tools",
    [
        {"paperclip": True, "pubtator3": False},
        {"paperclip": False, "pubtator3": True},
        {"paperclip": True, "pubtator3": True},
    ],
)
def test_db_search_forwards_each_tool_combination(client, service, tools):
    response = client.post(
        "/sessions/session-1/db-search/query",
        json=_body(literature_tools=tools),
    )

    assert response.status_code == 200
    _, payload = service.calls[0]
    assert payload.literature_tools.paperclip is tools["paperclip"]
    assert payload.literature_tools.pubtator3 is tools["pubtator3"]


def test_literature_results_serialize_per_tool(client, service):
    service.response = ChatResponse(
        session_id="session-1",
        status="completed",
        question="What is EGFR?",
        mode=SearchMode.DB_SEARCH,
        final_answer="graph answer",
        literature={
            "paperclip": LiteratureToolResult(
                status="completed",
                answer="paper answer",
                citations=[{"title": "A paper", "url": "https://example.org/1"}],
            ),
            "pubtator3": LiteratureToolResult(
                status="failed",
                warnings=["pubtator3 timed out after 180 seconds."],
            ),
        },
    )

    body = client.post(
        "/sessions/session-1/db-search/query",
        json=_body(literature_tools={"paperclip": True, "pubtator3": True}),
    ).json()

    # One tool failing leaves the other's answer and the core answer intact.
    assert body["final_answer"] == "graph answer"
    assert body["literature"]["paperclip"]["answer"] == "paper answer"
    assert body["literature"]["paperclip"]["citations"][0]["url"] == "https://example.org/1"
    assert body["literature"]["pubtator3"]["status"] == "failed"
    assert body["literature"]["pubtator3"]["answer"] is None


def test_resume_carries_the_tool_selection(client, service):
    response = client.post(
        "/sessions/session-1/resume",
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "search_mode": "db_search",
            "execution_mode": "resume",
            "action": "approve",
            "edited_cypher": "MATCH (g:Gene) RETURN g",
            "literature_tools": {"paperclip": True, "pubtator3": False},
        },
    )

    assert response.status_code == 200
    name, payload = service.calls[0]
    assert name == "resume"
    assert payload.literature_tools.paperclip is True


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
            "paperclip": "true",
            "pubtator3": "false",
        },
        files={"embedding_file": ("embedding.npy", b"\x00\x01", "application/octet-stream")},
    )

    assert response.status_code == 200
    _, payload = service.calls[0]
    assert payload.literature_tools == LiteratureToolsConfig(
        paperclip=True, pubtator3=False
    )


def test_pending_review_response_reports_its_status(client, service):
    service.response = PendingResumeResponse(
        session_id="session-1",
        question="What is EGFR?",
        mode=SearchMode.DB_SEARCH,
        generated_cypher="MATCH (g:Gene) RETURN g",
    )

    body = client.post("/sessions/session-1/db-search/query", json=_body()).json()

    assert body["status"] == "awaiting_human_review"
    assert body["generated_cypher"] == "MATCH (g:Gene) RETURN g"


def test_literature_tools_reject_non_boolean_values(client, service):
    response = client.post(
        "/sessions/session-1/db-search/query",
        json=_body(literature_tools={"paperclip": "sometimes"}),
    )

    assert response.status_code == 422
    assert service.calls == []


def test_api_contract_round_trips_literature_configuration():
    request = DbSearchRequest.model_validate(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "question": "What is EGFR?",
            "execution_mode": "generate_and_run",
            "literature_tools": {"paperclip": True, "pubtator3": False},
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
        paperclip=True,
        pubtator3=False,
        vector_category="gene",
        embedding_type="anc2vec",
    )

    assert request.literature_tools == LiteratureToolsConfig(
        paperclip=True, pubtator3=False
    )
    assert upload_request.literature_tools == request.literature_tools
