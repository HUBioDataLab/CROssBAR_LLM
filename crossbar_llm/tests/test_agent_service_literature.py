import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("BROWSER_COOKIE_SECRET", "test-browser-secret")
os.environ.setdefault("RATE_LIMIT_IP_HASH_SECRET", "test-rate-limit-secret")

from crossbar_llm.agent_tools.callback_handler import UsageMetricsCallback, UsageRecord
from crossbar_llm.agent_tools.cypher_agent import CypherAgent
from crossbar_llm.api.schemas.requests import DbSearchRequest, LiteratureToolsConfig
from crossbar_llm.api.services.agent_service import AgentService


class _Graph:
    def __init__(self, result=None, started=None, release=None):
        self.result = result or {"is_ok": True, "final_answer": "graph answer"}
        self.started = started
        self.release = release

    async def ainvoke(self, state, config):
        if self.started:
            self.started.set()
        if self.release:
            await self.release.wait()
        return {**state, **self.result}


def _payload(*, execution_mode="generate_and_run"):
    return DbSearchRequest(
        provider="openai",
        model="gpt-4o-mini",
        question="What is the role of EGFR in cancer?",
        execution_mode=execution_mode,
        literature_tools=LiteratureToolsConfig(paperclip=True, pubtator3=True),
    )


def _service(literature_run):
    service = AgentService.__new__(AgentService)
    service.literature_service = SimpleNamespace(run=literature_run)
    return service


def test_graph_topology_is_identical_with_and_without_preflight():
    """The preflight must not change the compiled graph.

    A request and its later resume share one checkpointer, so if enabling
    literature tools rewired the entry point, the resume would be replaying a
    checkpoint written by a differently-shaped graph.
    """
    agent = object.__new__(CypherAgent)
    agent.benchmark_mode = False
    agent.debug_mode = False

    edges = {
        (edge.source, edge.target)
        for edge in agent.build_graph(checkpointer=None).get_graph().edges
    }

    assert ("__start__", "biological_relevance_validation") in edges


def test_prevalidated_state_skips_the_second_relevance_call():
    """A seeded verdict must not be re-paid for inside the graph."""
    agent = object.__new__(CypherAgent)
    agent.llm_factory = SimpleNamespace(
        create_biological_relevance_validator_llm=lambda: (_ for _ in ()).throw(
            AssertionError("relevance was re-validated despite a seeded verdict")
        )
    )

    result = agent.biological_relevance_validation_node(
        {"question": "What is EGFR?", "biological_relevance": True}
    )

    assert result == {}


@pytest.mark.asyncio
async def test_irrelevant_question_skips_core_and_literature(monkeypatch):
    async def unexpected_literature(**kwargs):
        raise AssertionError("literature tools should not run")

    service = _service(unexpected_literature)
    graph = _Graph(result={"is_ok": False})
    agent = SimpleNamespace(
        avalidate_biological_relevance=AsyncMock(return_value={
            "biological_relevance": False,
            "final_answer": "outside the biological domain",
        })
    )
    callback = UsageMetricsCallback("session", strict=False)
    monkeypatch.setattr(
        service,
        "_build_agent_graph",
        lambda **kwargs: (graph, agent, callback, {}),
    )

    result, literature, literature_callback = await service._run_initial_request(
        session_id="session",
        browser_id="browser",
        payload=_payload(),
        initial_state={"question": "What is the stock price?", "is_ok": False},
        usage_callback=callback,
    )

    assert result["biological_relevance"] is False
    assert result["final_answer"] == "outside the biological domain"
    assert literature is None
    assert literature_callback is None


@pytest.mark.asyncio
async def test_core_and_literature_start_in_parallel_after_relevance_gate(monkeypatch):
    started = {"core": asyncio.Event(), "literature": asyncio.Event()}
    release = asyncio.Event()

    async def literature_run(**kwargs):
        started["literature"].set()
        await release.wait()
        return {"paperclip": {"status": "completed"}}

    service = _service(literature_run)
    graph = _Graph(started=started["core"], release=release)
    agent = SimpleNamespace(
        avalidate_biological_relevance=AsyncMock(return_value={
            "biological_relevance": True,
            "final_answer": None,
        })
    )
    callback = UsageMetricsCallback("session", strict=False)
    monkeypatch.setattr(
        service,
        "_build_agent_graph",
        lambda **kwargs: (graph, agent, callback, {}),
    )

    task = asyncio.create_task(
        service._run_initial_request(
            session_id="session",
            browser_id="browser",
            payload=_payload(),
            initial_state={"question": "What is EGFR?"},
            usage_callback=callback,
        )
    )
    await asyncio.wait_for(
        asyncio.gather(*(event.wait() for event in started.values())),
        timeout=1,
    )
    release.set()
    result, literature, literature_callback = await task

    assert result["biological_relevance"] is True
    assert literature["paperclip"]["status"] == "completed"
    # Literature gets its own lenient handler so the core agent keeps strict
    # usage accounting.
    assert literature_callback is not None and literature_callback.strict is False


@pytest.mark.asyncio
async def test_generate_only_does_not_start_literature(monkeypatch):
    async def unexpected_literature(**kwargs):
        raise AssertionError("literature tools should wait for resume")

    service = _service(unexpected_literature)
    graph = _Graph()
    agent = SimpleNamespace()
    callback = UsageMetricsCallback("session", strict=False)

    monkeypatch.setattr(
        service,
        "_build_agent_graph",
        lambda **kwargs: (graph, agent, callback, {}),
    )

    result, literature, literature_callback = await service._run_initial_request(
        session_id="session",
        browser_id="browser",
        payload=_payload(execution_mode="generate"),
        initial_state={"question": "What is EGFR?"},
        usage_callback=callback,
    )

    assert result["final_answer"] == "graph answer"
    assert literature is None
    assert literature_callback is None


@pytest.mark.asyncio
async def test_core_failure_cancels_literature_instead_of_orphaning_it():
    """A failing Cypher graph must not leave literature agents running.

    `asyncio.gather` without `return_exceptions` propagates the first error but
    leaves siblings running, so a bare gather here let the literature agents
    carry on spending metered Paperclip calls and LLM tokens long after the
    request had already failed.
    """
    literature_finished = False
    literature_cancelled = False

    async def literature_run(**kwargs):
        nonlocal literature_finished, literature_cancelled
        try:
            await asyncio.sleep(0.5)
            literature_finished = True
            return {"paperclip": {"status": "completed"}}
        except asyncio.CancelledError:
            literature_cancelled = True
            raise

    class _FailingGraph:
        async def ainvoke(self, state, config):
            await asyncio.sleep(0.01)
            raise RuntimeError("neo4j exploded")

    service = _service(literature_run)

    with pytest.raises(RuntimeError, match="neo4j exploded"):
        await service._gather_core_and_literature(
            graph=_FailingGraph(),
            initial_state={},
            config={},
            question="What is EGFR?",
            payload=_payload(),
            literature_callback=UsageMetricsCallback("session", strict=False),
        )

    # Give an orphaned task the time it would have needed to finish.
    await asyncio.sleep(0.6)
    assert literature_cancelled is True
    assert literature_finished is False


@pytest.mark.asyncio
async def test_literature_failure_cancels_the_core_graph():
    """And the same in the other direction, so no Neo4j work is left dangling."""
    core_cancelled = False

    class _SlowGraph:
        async def ainvoke(self, state, config):
            nonlocal core_cancelled
            try:
                await asyncio.sleep(0.5)
                return {"is_ok": True}
            except asyncio.CancelledError:
                core_cancelled = True
                raise

    async def literature_run(**kwargs):
        await asyncio.sleep(0.01)
        raise RuntimeError("literature orchestration bug")

    service = _service(literature_run)

    with pytest.raises(RuntimeError, match="literature orchestration bug"):
        await service._gather_core_and_literature(
            graph=_SlowGraph(),
            initial_state={},
            config={},
            question="What is EGFR?",
            payload=_payload(),
            literature_callback=UsageMetricsCallback("session", strict=False),
        )

    await asyncio.sleep(0.6)
    assert core_cancelled is True


def test_usage_summary_merges_core_and_literature_totals():
    """The response's `usage` must cover both handlers, not just the core one."""
    service = AgentService.__new__(AgentService)

    core = UsageMetricsCallback("session")
    core.per_node_usage["generate_cypher"] = UsageRecord(
        input_tokens=100, output_tokens=10, total_tokens=110, call_count=1
    )
    core.aggregated_usage.totals.add_usage(
        {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
    )
    core.aggregated_usage.register_model("generate_cypher", "gpt-4o-mini")

    literature = UsageMetricsCallback("session", strict=False)
    literature.per_node_usage["paperclip.router"] = UsageRecord(
        input_tokens=5, output_tokens=1, total_tokens=6, call_count=1
    )
    literature.aggregated_usage.totals.add_usage(
        {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6}
    )
    literature.aggregated_usage.register_model("paperclip.router", "gpt-4o-mini")

    merged = service._usage_summary(core, literature)

    assert merged["aggregated_usage"]["totals"]["total_tokens"] == 116
    assert set(merged["per_node_usage"]) == {"generate_cypher", "paperclip.router"}
    # With no literature handler the shape is unchanged from before.
    assert service._usage_summary(core, None) == core.get_summary()


def test_relevance_is_revalidated_for_each_question_in_a_session():
    """A session's checkpointer carries state between questions, and the
    relevance node skips itself when a verdict is present. Unless each
    question's initial state clears the verdict, question 2 silently inherits
    question 1's — letting an off-topic question through, or turning a valid
    one away."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    from crossbar_llm.agent_tools.cypher_agent import CypherAgentState
    from crossbar_llm.api.schemas.common import SearchMode

    judged = []

    class _FakeValidator:
        def invoke(self, messages, config=None):
            question = messages[-1].content
            judged.append(question)
            return {
                "parsed": SimpleNamespace(
                    relevant="stock" not in question, reason="test verdict"
                )
            }

    agent = object.__new__(CypherAgent)
    agent.llm_factory = SimpleNamespace(
        create_biological_relevance_validator_llm=lambda: _FakeValidator()
    )
    builder = StateGraph(CypherAgentState)
    builder.add_node("relevance", agent.biological_relevance_validation_node)
    builder.add_edge(START, "relevance")
    builder.add_edge("relevance", END)
    graph = builder.compile(checkpointer=MemorySaver())

    service = AgentService.__new__(AgentService)
    config = {"configurable": {"thread_id": "one-session"}}

    def ask(question):
        return graph.invoke(
            service._base_state(
                question=question,
                execution_mode="generate_and_run",
                cypher_mode=SearchMode.DB_SEARCH,
            ),
            config,
        )

    first = ask("What is the role of EGFR in cancer?")
    second = ask("What is Apple's stock price today?")

    assert first["biological_relevance"] is True
    assert len(judged) == 2, "second question reused the first question's verdict"
    assert second["biological_relevance"] is False


class _SessionStore:
    def __init__(self, pending_cypher="MATCH (n) RETURN n"):
        self.session = SimpleNamespace(
            pending_resume=True, pending_cypher=pending_cypher
        )
        self.marks = []

    def get_session(self, session_id, browser_id):
        return self.session

    def mark_resume_pending(self, session_id, browser_id, pending, pending_cypher=None):
        self.marks.append((pending, pending_cypher))


def _resume_payload():
    from crossbar_llm.api.schemas.requests import ResumeRequest

    return ResumeRequest(
        provider="openai",
        model="gpt-4o-mini",
        search_mode="db_search",
        action="approve",
        edited_cypher="MATCH (n) RETURN n",
        literature_tools=LiteratureToolsConfig(paperclip=True, pubtator3=True),
    )


def _resume_service(monkeypatch, graph_result, literature_run):
    service = _service(literature_run)
    service.session_store = _SessionStore()
    class _ResumeGraph:
        async def ainvoke(self, command, config):
            return graph_result

    graph = _ResumeGraph()
    callback = UsageMetricsCallback("session")
    monkeypatch.setattr(
        service,
        "_build_agent_graph",
        lambda **kwargs: (graph, None, callback, {}),
    )
    return service


@pytest.mark.asyncio
async def test_resume_that_pauses_for_review_again_skips_literature(monkeypatch):
    """A failed approved query retries and pauses at human review again.

    That response is a `PendingResumeResponse`, which carries no literature, so
    running the tools here would pay for evidence the user never sees — and
    again on every later resume. The session must also stay pending, with the
    NEW Cypher, or the next resume is rejected as "not pending".
    """
    from crossbar_llm.api.schemas.responses import PendingResumeResponse

    async def unexpected_literature(**kwargs):
        raise AssertionError("literature ran for a response that discards it")

    interrupt = SimpleNamespace(
        value={"question": "What is EGFR?", "current_cypher": "MATCH (m) RETURN m"}
    )
    service = _resume_service(
        monkeypatch,
        {"__interrupt__": [interrupt], "question": "What is EGFR?"},
        unexpected_literature,
    )

    response = await service.resume(
        session_id="session", browser_id="browser", payload=_resume_payload()
    )

    assert isinstance(response, PendingResumeResponse)
    assert response.generated_cypher == "MATCH (m) RETURN m"
    assert service.session_store.marks == [(True, "MATCH (m) RETURN m")]


@pytest.mark.asyncio
async def test_completed_resume_runs_literature(monkeypatch):
    calls = []

    async def literature_run(**kwargs):
        calls.append(kwargs["question"])
        return {}

    service = _resume_service(
        monkeypatch,
        {"is_ok": True, "final_answer": "graph answer", "question": "What is EGFR?"},
        literature_run,
    )

    await service.resume(
        session_id="session", browser_id="browser", payload=_resume_payload()
    )

    assert calls == ["What is EGFR?"]
    assert service.session_store.marks == [(False, None)]
