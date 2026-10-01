"""The orchestrator's request flow, with every agent faked.

The knowledge-graph agent is a fake LangGraph that streams the same
(mode, payload) chunks the real one does; the literature agents, relevance
gate, router and synthesizer are fakes recording what they were asked. What
runs for real is the orchestration itself: selection, concurrency, isolation,
review deferral, resume and the response it builds.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from crossbar_llm.agent_tools.callback_handler import UsageMetricsCallback, UsageRecord
from crossbar_llm.agent_tools.cypher_agent import CypherAgent
from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.schemas.common import SearchMode
from crossbar_llm.api.schemas.requests import (
    AgentsConfig,
    DbSearchRequest,
    ResumeRequest,
    VectorSearchRequest,
)
from crossbar_llm.api.schemas.responses import AgentRunResult, PendingResumeResponse
from crossbar_llm.api.services import agent_service as agent_service_module
from crossbar_llm.api.services import orchestration_results as results
from crossbar_llm.api.services.agent_service import AgentService
from crossbar_llm.api.services.session_store import SessionStore
from crossbar_llm.orchestrator.registry import AgentId
from crossbar_llm.orchestrator.router import RoutingPlan
from crossbar_llm.orchestrator.synthesizer import Contradiction, Synthesis

BROWSER = "browser"
KG, PAPERCLIP, PUBTATOR3 = AgentId.KNOWLEDGE_GRAPH, AgentId.PAPERCLIP, AgentId.PUBTATOR3

KG_DONE = {
    "question": "What is the role of EGFR in cancer?",
    "is_ok": True,
    "final_answer": "graph answer",
    "current_cypher": "MATCH (g:Gene) RETURN g",
    "execution_result": [{"g.id": "EGFR"}],
    "follow_up_questions": ["q1", "q2", "q3"],
}


class _FakeGraph:
    """Streams what LangGraph streams for `stream_mode=["updates", "values"]`."""

    def __init__(self, final=KG_DONE, *, interrupt=None, started=None, release=None):
        self.final = final
        self.interrupt = interrupt
        self.started = started
        self.release = release
        self.inputs = []
        self.cancelled = False

    async def astream(self, graph_input, config, stream_mode):
        assert stream_mode == ["updates", "values"]
        self.inputs.append(graph_input)
        if self.started:
            self.started.set()
        try:
            if self.release:
                await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        for node in ("biological_relevance_validation", "generate_cypher", "execute_cypher"):
            yield "updates", {node: {}}
        if self.interrupt is not None:
            yield "updates", {"__interrupt__": (SimpleNamespace(value=self.interrupt),)}
        yield "values", self.final


class _Literature:
    def __init__(self, *, started=None, release=None, failing=()):
        self.calls = []
        self.started = started or {}
        self.release = release
        self.failing = set(failing)
        self.cancelled = []

    async def run_tool(self, name, *, question, payload, callback):
        self.calls.append((name, question))
        if name in self.started:
            self.started[name].set()
        try:
            if self.release:
                await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.append(name)
            raise
        if name in self.failing:
            return AgentRunResult(status="failed", warnings=[f"{name} timed out."])
        return AgentRunResult(
            status="completed",
            answer=f"{name} answer",
            citations=[{"title": f"{name} paper", "url": "https://example.org"}],
        )


class _Harness:
    """An AgentService with fake agents, plus a record of what each was asked."""

    def __init__(self, monkeypatch, *, graph=None, literature=None, plan=None,
                 relevant=True, synthesis=None, unavailable=None):
        self.store = SessionStore(ttl_minutes=45, max_sessions_per_user=5)
        self.session_id = self.store.create_session(browser_id=BROWSER).session_id
        self.graph = graph or _FakeGraph()
        self.literature = literature or _Literature()
        self.plan = plan
        self.route_calls = []
        self.synthesis_calls = []
        self.kg_builds = 0
        self.events = []

        service = AgentService.__new__(AgentService)
        service.settings = Settings()
        service.session_store = self.store
        service.literature_service = self.literature
        service.neo4j_config = None
        self.service = service

        def build_kg_graph(run):
            self.kg_builds += 1
            if isinstance(self.graph, Exception):
                raise self.graph
            return self.graph, {}

        monkeypatch.setattr(service, "_build_kg_graph", build_kg_graph)

        async def relevance(llm_factory, question):
            if relevant:
                return {"biological_relevance": True, "final_answer": None}
            return {"biological_relevance": False, "final_answer": "outside the domain"}

        async def route(*, chat_model, question, enabled, history, required):
            self.route_calls.append(
                {"enabled": list(enabled), "history": list(history), "required": list(required)}
            )
            if self.plan is not None:
                return self.plan
            return RoutingPlan(
                selected=tuple(enabled),
                reasons={},
                rationale="all of them",
                standalone_question=f"standalone: {question}",
                strategy="llm",
            )

        async def synthesize(*, chat_model, question, reports):
            self.synthesis_calls.append((question, [report.agent for report in reports]))
            if isinstance(synthesis, Exception):
                raise synthesis
            return synthesis or Synthesis(
                answer="merged answer",
                contradictions=(
                    Contradiction(
                        topic="EGFR role",
                        agents=(KG, PAPERCLIP),
                        resolution="Both are right in different tissues.",
                    ),
                ),
            )

        monkeypatch.setattr(agent_service_module, "avalidate_biological_relevance", relevance)
        monkeypatch.setattr(agent_service_module, "route_question", route)
        monkeypatch.setattr(agent_service_module, "synthesize_reports", synthesize)
        monkeypatch.setattr(agent_service_module, "build_chat_model", lambda **kwargs: object())
        monkeypatch.setattr(
            agent_service_module, "unavailable_reasons", lambda settings: dict(unavailable or {})
        )
        monkeypatch.setattr(agent_service_module, "LLMFactory", lambda config: object())

    async def emit(self, event, data):
        self.events.append((event, data))

    async def ask(self, *, execution_mode="generate_and_run", agents=None, question=None):
        payload = DbSearchRequest(
            provider="openai",
            model="gpt-4o-mini",
            question=question or "What is the role of EGFR in cancer?",
            execution_mode=execution_mode,
            agents=agents or AgentsConfig(),
        )
        return await self.service.run_db(
            self.session_id, BROWSER, payload, emit=self.emit
        )

    async def resume(self, *, agents=None, cypher="MATCH (g:Gene) RETURN g"):
        payload = ResumeRequest(
            provider="openai",
            model="gpt-4o-mini",
            search_mode="db_search",
            action="approve",
            edited_cypher=cypher,
            agents=agents or AgentsConfig(),
        )
        return await self.service.resume(self.session_id, BROWSER, payload, emit=self.emit)

    @property
    def session(self):
        return self.store.get_session(self.session_id, BROWSER)

    def event_names(self):
        return [name for name, _ in self.events]


def _plan(*selected, standalone="standalone question"):
    return RoutingPlan(
        selected=tuple(selected),
        reasons={agent: "useful" for agent in selected},
        rationale="planned",
        standalone_question=standalone,
        strategy="llm",
    )


# ----------------------------------------------------------- the KG graph


def test_graph_topology_is_identical_with_and_without_preflight():
    """The preflight must not change the compiled graph.

    A request and its later resume share one checkpointer, so if the
    orchestrator rewired the entry point, the resume would be replaying a
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


def test_relevance_is_revalidated_for_each_question_in_a_session():
    """A session's checkpointer carries state between questions, and the
    relevance node skips itself when a verdict is present. Unless each
    question's initial state clears the verdict, question 2 silently inherits
    question 1's."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    from crossbar_llm.agent_tools.cypher_agent import CypherAgentState

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


# --------------------------------------------------------------- planning


@pytest.mark.asyncio
async def test_out_of_domain_question_runs_no_agent(monkeypatch):
    harness = _Harness(monkeypatch, relevant=False)

    response = await harness.ask()

    assert response.status == "failed"
    assert response.final_answer == "outside the domain"
    assert harness.kg_builds == 0
    assert harness.literature.calls == []
    assert response.orchestration.routing.selected == []
    assert set(response.orchestration.routing.skipped) == set(AgentId)
    assert "relevance.rejected" in harness.event_names()


@pytest.mark.asyncio
async def test_disabled_agents_are_never_offered_to_the_router(monkeypatch):
    harness = _Harness(monkeypatch)

    response = await harness.ask(
        agents=AgentsConfig(knowledge_graph=True, paperclip=False, pubtator3=True)
    )

    assert harness.route_calls[0]["enabled"] == [KG, PUBTATOR3]
    assert [name for name, _ in harness.literature.calls] == ["pubtator3"]
    assert response.orchestration.routing.skipped[PAPERCLIP] == results.DISABLED_REASON
    assert PAPERCLIP not in response.orchestration.agents


@pytest.mark.asyncio
async def test_unavailable_agent_is_skipped_with_its_reason(monkeypatch):
    harness = _Harness(monkeypatch, unavailable={PAPERCLIP: "no API key"})

    response = await harness.ask()

    assert PAPERCLIP not in harness.route_calls[0]["enabled"]
    assert response.orchestration.routing.skipped[PAPERCLIP] == "no API key"


@pytest.mark.asyncio
async def test_agents_the_router_left_out_are_reported_as_not_routed(monkeypatch):
    harness = _Harness(monkeypatch, plan=_plan(PUBTATOR3))

    response = await harness.ask()

    assert harness.kg_builds == 0
    assert [name for name, _ in harness.literature.calls] == ["pubtator3"]
    routing = response.orchestration.routing
    assert routing.skipped[KG] == results.NOT_ROUTED_REASON
    assert routing.skipped[PAPERCLIP] == results.NOT_ROUTED_REASON


@pytest.mark.asyncio
async def test_vector_search_requires_the_knowledge_graph_agent(monkeypatch):
    harness = _Harness(monkeypatch)
    payload = VectorSearchRequest(
        provider="openai",
        model="gpt-4o-mini",
        question="Find proteins similar to EGFR",
        vector_category="Protein",
        embedding_type="Esm2",
        agents=AgentsConfig(knowledge_graph=False),
    )
    monkeypatch.setattr(VectorSearchRequest, "vector_index", property(lambda self: "Esm2Embeddings"))

    with pytest.raises(HTTPException) as raised:
        await harness.service.run_vector(harness.session_id, BROWSER, payload)

    assert raised.value.status_code == 400
    assert harness.route_calls == []


@pytest.mark.asyncio
async def test_vector_search_forces_the_knowledge_graph_into_the_plan(monkeypatch):
    harness = _Harness(monkeypatch)
    payload = VectorSearchRequest(
        provider="openai",
        model="gpt-4o-mini",
        question="Find proteins similar to EGFR",
        vector_category="Protein",
        embedding_type="Esm2",
    )
    monkeypatch.setattr(VectorSearchRequest, "vector_index", property(lambda self: "Esm2Embeddings"))

    await harness.service.run_vector(harness.session_id, BROWSER, payload)

    assert harness.route_calls[0]["required"] == [KG]


@pytest.mark.asyncio
async def test_unknown_session_is_a_404(monkeypatch):
    harness = _Harness(monkeypatch)
    harness.session_id = "missing"

    with pytest.raises(HTTPException) as raised:
        await harness.ask()

    assert raised.value.status_code == 404


# ------------------------------------------------------------ running


@pytest.mark.asyncio
async def test_routed_agents_run_concurrently(monkeypatch):
    release = asyncio.Event()
    kg_started = asyncio.Event()
    literature_started = {"paperclip": asyncio.Event(), "pubtator3": asyncio.Event()}
    harness = _Harness(
        monkeypatch,
        graph=_FakeGraph(started=kg_started, release=release),
        literature=_Literature(started=literature_started, release=release),
    )

    task = asyncio.create_task(harness.ask())
    await asyncio.wait_for(
        asyncio.gather(kg_started.wait(), *(event.wait() for event in literature_started.values())),
        timeout=1,
    )
    release.set()
    response = await task

    assert response.status == "completed"
    assert set(response.orchestration.agents) == set(AgentId)


@pytest.mark.asyncio
async def test_literature_agents_get_the_standalone_question(monkeypatch):
    harness = _Harness(monkeypatch)

    await harness.ask(question="And what about its side effects?")

    assert {question for _, question in harness.literature.calls} == {
        "standalone: And what about its side effects?"
    }
    # The graph keeps its own conversation history, so it gets the original.
    assert harness.graph.inputs[0]["question"] == "And what about its side effects?"
    assert harness.graph.inputs[0]["biological_relevance"] is True


@pytest.mark.asyncio
async def test_multiple_answers_are_synthesized_with_contradictions(monkeypatch):
    harness = _Harness(monkeypatch)

    response = await harness.ask()

    assert response.final_answer == "merged answer"
    orchestration = response.orchestration
    assert orchestration.synthesized is True
    assert orchestration.answer_sources == [KG, PAPERCLIP, PUBTATOR3]
    assert orchestration.contradictions[0].agents == [KG, PAPERCLIP]
    assert harness.synthesis_calls == [
        ("standalone: What is the role of EGFR in cancer?", [KG, PAPERCLIP, PUBTATOR3])
    ]
    # The graph's own outputs still drive the query panel and follow-ups.
    assert response.generated_cypher == "MATCH (g:Gene) RETURN g"
    assert response.follow_up_questions == ["q1", "q2", "q3"]


@pytest.mark.asyncio
async def test_a_single_answer_passes_through_without_synthesis(monkeypatch):
    harness = _Harness(monkeypatch, plan=_plan(KG))

    response = await harness.ask()

    assert response.final_answer == "graph answer"
    assert response.orchestration.synthesized is False
    assert harness.synthesis_calls == []
    assert "synthesis.started" not in harness.event_names()


@pytest.mark.asyncio
async def test_failed_agents_are_left_out_of_the_synthesis(monkeypatch):
    harness = _Harness(monkeypatch, literature=_Literature(failing={"pubtator3"}))

    response = await harness.ask()

    assert harness.synthesis_calls[0][1] == [KG, PAPERCLIP]
    assert response.orchestration.agents[PUBTATOR3].status == "failed"


@pytest.mark.asyncio
async def test_knowledge_graph_failure_is_isolated(monkeypatch):
    harness = _Harness(
        monkeypatch,
        graph=RuntimeError("neo4j exploded"),
        plan=_plan(KG, PAPERCLIP),
    )

    response = await harness.ask()

    assert response.status == "completed"
    assert response.final_answer == "paperclip answer"
    kg = response.orchestration.agents[KG]
    assert kg.status == "failed"
    # Reported by type only: upstream messages can carry credentials.
    assert "RuntimeError" in kg.warnings[0]
    assert "exploded" not in kg.warnings[0]


@pytest.mark.asyncio
async def test_a_lone_knowledge_graph_failure_keeps_its_explanation(monkeypatch):
    failed = {**KG_DONE, "is_ok": False, "final_answer": "I couldn't build a query."}
    harness = _Harness(monkeypatch, graph=_FakeGraph(failed), plan=_plan(KG))

    response = await harness.ask()

    assert response.status == "failed"
    assert response.final_answer == "I couldn't build a query."


@pytest.mark.asyncio
async def test_no_answer_from_any_agent_says_so(monkeypatch):
    harness = _Harness(
        monkeypatch,
        literature=_Literature(failing={"paperclip", "pubtator3"}),
        plan=_plan(PAPERCLIP, PUBTATOR3),
    )

    response = await harness.ask()

    assert response.status == "failed"
    assert response.final_answer == results.NO_ANSWER


@pytest.mark.asyncio
async def test_synthesis_failure_falls_back_to_separate_answers(monkeypatch):
    harness = _Harness(monkeypatch, synthesis=RuntimeError("model down"))

    response = await harness.ask()

    assert response.status == "completed"
    assert "graph answer" in response.final_answer
    assert "paperclip answer" in response.final_answer
    assert response.orchestration.synthesized is False
    assert results.SYNTHESIS_FAILED_WARNING in response.orchestration.warnings


@pytest.mark.asyncio
async def test_cancelling_the_request_stops_every_agent(monkeypatch):
    """A client disconnect cancels the handler; no agent may keep running and
    spending metered calls on a response nobody will receive."""
    release = asyncio.Event()
    kg_started = asyncio.Event()
    started = {"paperclip": asyncio.Event(), "pubtator3": asyncio.Event()}
    literature = _Literature(started=started, release=release)
    graph = _FakeGraph(started=kg_started, release=release)
    harness = _Harness(monkeypatch, graph=graph, literature=literature)

    task = asyncio.create_task(harness.ask())
    await asyncio.wait_for(
        asyncio.gather(kg_started.wait(), *(event.wait() for event in started.values())),
        timeout=1,
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert graph.cancelled is True
    assert sorted(literature.cancelled) == ["paperclip", "pubtator3"]


@pytest.mark.asyncio
async def test_progress_events_tell_the_story_in_order(monkeypatch):
    harness = _Harness(monkeypatch, plan=_plan(KG, PAPERCLIP))

    await harness.ask()

    names = harness.event_names()
    assert names[:2] == ["orchestration.started", "routing.completed"]
    assert names[-2:] == ["synthesis.started", "synthesis.completed"]
    progress = [data for name, data in harness.events if name == "agent.progress"]
    # The graph's relevance node only reuses the orchestrator's verdict, so it
    # is not reported as progress.
    assert [step["step"] for step in progress] == ["generate_cypher", "execute_cypher"]
    assert progress[0]["label"] == "Generated a Cypher query"
    completed = {data["agent"] for name, data in harness.events if name == "agent.completed"}
    assert completed == {"knowledge_graph", "paperclip"}


@pytest.mark.asyncio
async def test_answered_turns_become_router_history(monkeypatch):
    harness = _Harness(monkeypatch)

    await harness.ask(question="What is the role of EGFR in cancer?")
    await harness.ask(question="And its side effects?")

    history = harness.route_calls[1]["history"]
    assert [turn.question for turn in history] == ["What is the role of EGFR in cancer?"]
    assert history[0].answer == "merged answer"


# ------------------------------------------------------- review and resume


@pytest.mark.asyncio
async def test_generate_mode_defers_literature_until_approval(monkeypatch):
    review = {"question": "What is the role of EGFR in cancer?", "current_cypher": "MATCH (g:Gene) RETURN g"}
    harness = _Harness(monkeypatch, graph=_FakeGraph(interrupt=review))

    response = await harness.ask(execution_mode="generate")

    assert isinstance(response, PendingResumeResponse)
    assert response.generated_cypher == "MATCH (g:Gene) RETURN g"
    assert harness.literature.calls == []
    # The plan the approval will carry out is kept, and shown to the user.
    assert response.orchestration.routing.selected == [KG, PAPERCLIP, PUBTATOR3]
    session = harness.session
    assert session.pending_resume is True
    assert session.pending_plan.selected == (KG, PAPERCLIP, PUBTATOR3)

    harness.graph.interrupt = None
    resumed = await harness.resume()

    assert resumed.status == "completed"
    assert resumed.final_answer == "merged answer"
    assert sorted(harness.literature.calls) == [
        ("paperclip", "standalone: What is the role of EGFR in cancer?"),
        ("pubtator3", "standalone: What is the role of EGFR in cancer?"),
    ]
    assert harness.session.pending_resume is False
    assert harness.session.pending_plan is None


@pytest.mark.asyncio
async def test_generate_mode_without_the_graph_answers_immediately(monkeypatch):
    harness = _Harness(monkeypatch, plan=_plan(PAPERCLIP))

    response = await harness.ask(execution_mode="generate")

    assert response.status == "completed"
    assert response.final_answer == "paperclip answer"
    assert harness.session.pending_resume is False


@pytest.mark.asyncio
async def test_generate_mode_graph_failure_still_runs_the_deferred_agents(monkeypatch):
    failed = {**KG_DONE, "is_ok": False, "final_answer": "no valid query"}
    harness = _Harness(monkeypatch, graph=_FakeGraph(failed), plan=_plan(KG, PAPERCLIP))

    response = await harness.ask(execution_mode="generate")

    assert response.status == "completed"
    assert harness.literature.calls == [("paperclip", "standalone question")]


@pytest.mark.asyncio
async def test_resume_drops_agents_switched_off_since_the_plan(monkeypatch):
    review = {"question": "Q", "current_cypher": "MATCH (g:Gene) RETURN g"}
    harness = _Harness(monkeypatch, graph=_FakeGraph(interrupt=review))
    await harness.ask(execution_mode="generate")

    harness.graph.interrupt = None
    resumed = await harness.resume(agents=AgentsConfig(paperclip=False))

    assert [name for name, _ in harness.literature.calls] == ["pubtator3"]
    assert resumed.orchestration.routing.skipped[PAPERCLIP] == results.DISABLED_REASON


@pytest.mark.asyncio
async def test_resume_that_pauses_again_keeps_the_plan_and_waits(monkeypatch):
    """A failed approved query retries and pauses at review again. That response
    carries no answer, so the other agents must keep waiting — and the session
    must stay pending with the NEW Cypher, or the next resume is turned away."""
    review = {"question": "Q", "current_cypher": "MATCH (g:Gene) RETURN g"}
    harness = _Harness(monkeypatch, graph=_FakeGraph(interrupt=review))
    await harness.ask(execution_mode="generate")

    harness.graph.interrupt = {"question": "Q", "current_cypher": "MATCH (m) RETURN m"}
    response = await harness.resume()

    assert isinstance(response, PendingResumeResponse)
    assert response.generated_cypher == "MATCH (m) RETURN m"
    assert harness.literature.calls == []
    session = harness.session
    assert session.pending_cypher == "MATCH (m) RETURN m"
    assert session.pending_plan.selected == (KG, PAPERCLIP, PUBTATOR3)


@pytest.mark.asyncio
async def test_resume_rejects_an_approval_that_does_not_match(monkeypatch):
    review = {"question": "Q", "current_cypher": "MATCH (g:Gene) RETURN g"}
    harness = _Harness(monkeypatch, graph=_FakeGraph(interrupt=review))
    await harness.ask(execution_mode="generate")

    with pytest.raises(HTTPException) as raised:
        await harness.resume(cypher="MATCH (x) RETURN x")

    assert raised.value.status_code == 400


# ------------------------------------------------------------------ usage


def _callback(strict, records):
    callback = UsageMetricsCallback("session", strict=strict)
    for node, tokens in records.items():
        callback.per_node_usage[node] = UsageRecord(
            input_tokens=tokens, output_tokens=0, total_tokens=tokens, call_count=1
        )
        callback.aggregated_usage.totals.add_usage(
            {"input_tokens": tokens, "total_tokens": tokens}
        )
        callback.aggregated_usage.register_model(node, "gpt-4o-mini")
    return callback


def test_usage_is_broken_down_by_agent_and_orchestrator():
    run = SimpleNamespace(
        core_callback=_callback(True, {"biological_relevance_validation": 5, "generate_cypher": 100}),
        aux_callback=_callback(False, {"orchestrator.router": 7, "paperclip.router": 11}),
    )

    total = results.total_usage(run)["aggregated_usage"]["totals"]["total_tokens"]
    kg = results.kg_usage(run)
    orchestrator = results.orchestrator_usage(run)

    assert total == 123
    # Relevance is the orchestrator's gate, not part of the graph agent's bill.
    assert set(kg["per_node_usage"]) == {"generate_cypher"}
    assert set(orchestrator["per_node_usage"]) == {
        "biological_relevance_validation",
        "orchestrator.router",
    }
    assert orchestrator["aggregated_usage"]["totals"]["total_tokens"] == 12


@pytest.mark.asyncio
async def test_an_unexpected_error_in_one_agent_cancels_its_siblings():
    """Agent wrappers turn failures into results, so a raise here is a bug —
    but a bare `gather` would still leave the sibling running detached."""
    sibling_cancelled = asyncio.Event()

    async def sibling():
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            sibling_cancelled.set()
            raise

    async def buggy():
        await asyncio.sleep(0.01)
        raise RuntimeError("orchestration bug")

    with pytest.raises(RuntimeError, match="orchestration bug"):
        await AgentService._gather_or_cancel(sibling(), buggy())

    assert sibling_cancelled.is_set()


@pytest.mark.asyncio
async def test_a_second_request_on_a_busy_session_is_turned_away(monkeypatch):
    """Two requests on one session would share its LangGraph thread and pay
    for every agent twice."""
    release = asyncio.Event()
    started = asyncio.Event()
    harness = _Harness(monkeypatch, graph=_FakeGraph(started=started, release=release))

    first = asyncio.create_task(harness.ask())
    await asyncio.wait_for(started.wait(), timeout=1)
    with pytest.raises(HTTPException) as raised:
        await harness.ask(question="A second question meanwhile")
    release.set()
    await first

    assert raised.value.status_code == 409
    # Released once the first finished: the next question goes through.
    assert (await harness.ask()).status == "completed"


@pytest.mark.asyncio
async def test_a_cancelled_request_releases_the_session(monkeypatch):
    started = asyncio.Event()
    harness = _Harness(
        monkeypatch, graph=_FakeGraph(started=started, release=asyncio.Event())
    )

    task = asyncio.create_task(harness.ask())
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert harness.session.busy is False
