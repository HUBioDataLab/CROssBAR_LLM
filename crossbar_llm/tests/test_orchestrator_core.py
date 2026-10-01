"""The orchestrator package on its own: routing, synthesis, and the helpers
the service builds on. LLMs are LangChain fake chat models, so the real prompt
templates are formatted (a stray brace fails here) and the JSON fallback path
runs for real."""
import asyncio
import json
import os

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda
from pydantic import SecretStr

from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.routers.streaming import stream_orchestration
from crossbar_llm.api.schemas.responses import ChatResponse
from crossbar_llm.api.services.agent_catalog import unavailable_reasons
from crossbar_llm.api.services.kg_runner import stream_kg_graph
from crossbar_llm.api.services.session_store import SessionStore
from crossbar_llm.orchestrator.llm import extract_json_object
from crossbar_llm.orchestrator.registry import AgentId, resolve_agent
from crossbar_llm.orchestrator.router import ConversationTurn, route_question
from crossbar_llm.orchestrator.schemas import RoutingOutput, SynthesisOutput
from crossbar_llm.orchestrator.synthesizer import (
    MAX_RECORD_ROWS,
    AgentReport,
    fallback_answer,
    format_report,
    synthesize_reports,
)

KG, PAPERCLIP, PUBTATOR3 = AgentId.KNOWLEDGE_GRAPH, AgentId.PAPERCLIP, AgentId.PUBTATOR3
ALL = [KG, PAPERCLIP, PUBTATOR3]


class _NeverCalled(FakeListChatModel):
    responses: list[str] = []

    def with_structured_output(self, schema, **kwargs):
        raise AssertionError("the router called the LLM when it had nothing to decide")


class _Structured(FakeListChatModel):
    """Answers through provider structured output, recording the prompt."""

    responses: list[str] = []
    output: object = None
    prompts: list = []

    def with_structured_output(self, schema, **kwargs):
        def answer(prompt_value):
            self.prompts.append(prompt_value.to_string())
            if isinstance(self.output, Exception):
                raise self.output
            return self.output

        return RunnableLambda(answer)


def _json_model(payload):
    """No structured output, so the call takes the plain-JSON fallback."""
    return FakeListChatModel(responses=[f"Sure! ```json\n{json.dumps(payload)}\n```"])


# ----------------------------------------------------------------- registry


@pytest.mark.parametrize(
    "reference, expected",
    [("knowledge_graph", KG), ("KG", KG), ("[KG]", KG), ("paperclip", PAPERCLIP),
     ("PubTator3", PUBTATOR3), ("Knowledge Graph", KG), ("wikipedia", None)],
)
def test_resolve_agent_accepts_ids_tags_and_names(reference, expected):
    assert resolve_agent(reference) is expected


# ------------------------------------------------------------------- router


@pytest.mark.asyncio
async def test_single_enabled_agent_needs_no_llm_call():
    plan = await route_question(
        chat_model=_NeverCalled(), question="What is EGFR?", enabled=[PUBTATOR3]
    )

    assert plan.selected == (PUBTATOR3,)
    assert plan.strategy == "single_agent"
    assert plan.standalone_question == "What is EGFR?"


@pytest.mark.asyncio
async def test_lone_knowledge_graph_skips_the_rewrite_even_with_history():
    # The graph agent keeps its own history, so there is nothing to rewrite for.
    plan = await route_question(
        chat_model=_NeverCalled(),
        question="And its side effects?",
        enabled=[KG],
        history=[ConversationTurn("What targets EGFR?", "Gefitinib.")],
    )

    assert plan.strategy == "single_agent"


@pytest.mark.asyncio
async def test_lone_literature_agent_with_history_gets_a_standalone_question():
    model = _json_model(
        {
            "standalone_question": "What are the side effects of gefitinib?",
            "agents": [{"agent": "paperclip", "reason": "literature"}],
            "rationale": "one agent",
        }
    )

    plan = await route_question(
        chat_model=model,
        question="And its side effects?",
        enabled=[PAPERCLIP],
        history=[ConversationTurn("What targets EGFR?", "Gefitinib.")],
    )

    assert plan.strategy == "llm"
    assert plan.standalone_question == "What are the side effects of gefitinib?"


@pytest.mark.asyncio
async def test_router_never_selects_an_agent_outside_the_enabled_set():
    model = _Structured(
        output=RoutingOutput(
            standalone_question="What is EGFR?",
            agents=[
                {"agent": "paperclip", "reason": "disabled, must be dropped"},
                {"agent": "PubTator3", "reason": "tag instead of id"},
                {"agent": "wikipedia", "reason": "not an agent at all"},
            ],
            rationale="mixed",
        ),
        prompts=[],
    )

    plan = await route_question(
        chat_model=model, question="What is EGFR?", enabled=[KG, PUBTATOR3]
    )

    assert plan.selected == (PUBTATOR3,)
    assert plan.reasons == {PUBTATOR3: "tag instead of id"}
    # Only the enabled agents' profiles reach the prompt.
    assert "pubtator3 (PubTator3)" in model.prompts[0]
    assert "paperclip (Paperclip)" not in model.prompts[0]


@pytest.mark.asyncio
async def test_required_agents_are_always_selected_first():
    model = _Structured(
        output=RoutingOutput(
            standalone_question="q",
            agents=[{"agent": "paperclip", "reason": "context"}],
            rationale="r",
        ),
        prompts=[],
    )

    plan = await route_question(
        chat_model=model, question="q", enabled=ALL, required=[KG]
    )

    assert plan.selected == (KG, PAPERCLIP)
    assert "embedding similarity search" in model.prompts[0]


@pytest.mark.asyncio
async def test_routing_with_no_usable_agent_falls_back_to_every_enabled_one():
    model = _Structured(
        output=RoutingOutput(standalone_question="q", agents=[], rationale="none"),
        prompts=[],
    )

    plan = await route_question(chat_model=model, question="q", enabled=ALL)

    assert plan.selected == tuple(ALL)
    assert plan.strategy == "fallback"
    assert plan.warnings


@pytest.mark.asyncio
async def test_routing_failure_falls_back_instead_of_failing_the_request():
    model = FakeListChatModel(responses=["I would rather not answer in JSON."])

    plan = await route_question(chat_model=model, question="q", enabled=[KG, PAPERCLIP])

    assert plan.selected == (KG, PAPERCLIP)
    assert plan.strategy == "fallback"


@pytest.mark.asyncio
async def test_router_includes_history_in_the_prompt():
    model = _Structured(
        output=RoutingOutput(
            standalone_question="q", agents=[{"agent": "kg", "reason": "r"}], rationale="r"
        ),
        prompts=[],
    )

    await route_question(
        chat_model=model,
        question="And its side effects?",
        enabled=ALL,
        history=[ConversationTurn("What targets EGFR?", "Gefitinib.")],
    )

    assert "User: What targets EGFR?\nAssistant: Gefitinib." in model.prompts[0]


# -------------------------------------------------------------- synthesizer


def test_report_carries_tag_answer_records_and_sources():
    report = AgentReport(
        agent=KG,
        status="completed",
        answer="EGFR is targeted by gefitinib.",
        records=[{"row": index} for index in range(MAX_RECORD_ROWS + 10)],
    )
    literature = AgentReport(
        agent=PUBTATOR3,
        status="completed",
        answer="Gefitinib inhibits EGFR [1].",
        citations=[{"title": "Gefitinib trial", "pmid": "123", "url": "https://p/123"}],
    )

    kg_text, literature_text = format_report(report), format_report(literature)

    assert kg_text.startswith("### [KG] Knowledge Graph (status: completed)")
    assert f"first {MAX_RECORD_ROWS} of {MAX_RECORD_ROWS + 10}" in kg_text
    assert f'"row": {MAX_RECORD_ROWS}' not in kg_text
    assert "[1] Gefitinib trial (PMID 123) https://p/123" in literature_text


@pytest.mark.asyncio
async def test_synthesis_maps_contradiction_sources_to_agent_ids():
    model = _json_model(
        {
            "answer": "Merged [KG] [PubTator3].",
            "contradictions": [
                {
                    "topic": "EGFR in glioma",
                    "agents": ["KG", "PubTator3", "a blog"],
                    "resolution": "The graph has no record; the literature reports one.",
                }
            ],
        }
    )

    synthesis = await synthesize_reports(
        chat_model=model,
        question="q",
        reports=[
            AgentReport(agent=KG, status="completed", answer="a"),
            AgentReport(agent=PUBTATOR3, status="completed", answer="b"),
        ],
    )

    assert synthesis.answer == "Merged [KG] [PubTator3]."
    assert synthesis.contradictions[0].agents == (KG, PUBTATOR3)


@pytest.mark.asyncio
async def test_empty_synthesis_is_an_error_not_a_blank_answer():
    model = _Structured(output=SynthesisOutput(answer="  "), prompts=[])

    with pytest.raises(ValueError):
        await synthesize_reports(
            chat_model=model,
            question="q",
            reports=[AgentReport(agent=KG, status="completed", answer="a")] * 2,
        )


def test_fallback_answer_keeps_each_report_under_its_agent():
    text = fallback_answer(
        [
            AgentReport(agent=KG, status="completed", answer="graph says"),
            AgentReport(agent=PAPERCLIP, status="completed", answer="papers say"),
        ]
    )

    assert text == "**Knowledge Graph**\n\ngraph says\n\n**Paperclip**\n\npapers say"


def test_json_extraction_tolerates_fences_and_preamble():
    assert extract_json_object('Here:\n```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}
    with pytest.raises(ValueError):
        extract_json_object("no json here")


# ---------------------------------------------------------------- kg runner


@pytest.mark.asyncio
async def test_stream_kg_graph_matches_ainvoke_including_interrupts():
    """The streamed run must hand back exactly what `ainvoke` would have, or a
    paused graph would silently look finished."""
    from typing import TypedDict

    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    class State(TypedDict, total=False):
        question: str
        cypher: str
        answer: str

    def generate(state):
        return {"cypher": "MATCH (n) RETURN n"}

    def review(state):
        decision = interrupt({"current_cypher": state["cypher"]})
        return {"cypher": decision}

    def answer(state):
        return {"answer": f"ran {state['cypher']}"}

    builder = StateGraph(State)
    builder.add_node("generate", generate)
    builder.add_node("review", review)
    builder.add_node("answer", answer)
    builder.add_edge(START, "generate")
    builder.add_edge("generate", "review")
    builder.add_edge("review", "answer")
    builder.add_edge("answer", END)

    def graph_and_config(thread):
        return builder.compile(checkpointer=MemorySaver()), {"configurable": {"thread_id": thread}}

    steps = []

    async def on_step(node):
        steps.append(node)

    streamed_graph, streamed_config = graph_and_config("a")
    invoked_graph, invoked_config = graph_and_config("b")

    paused = await stream_kg_graph(streamed_graph, {"question": "q"}, streamed_config, on_step)
    expected = await invoked_graph.ainvoke({"question": "q"}, invoked_config)

    assert paused["__interrupt__"][0].value == expected["__interrupt__"][0].value
    assert {k: v for k, v in paused.items() if k != "__interrupt__"} == {
        k: v for k, v in expected.items() if k != "__interrupt__"
    }
    assert steps == ["generate"]

    resumed = await stream_kg_graph(
        streamed_graph, Command(resume="MATCH (m) RETURN m"), streamed_config, on_step
    )

    assert resumed["answer"] == "ran MATCH (m) RETURN m"
    assert "__interrupt__" not in resumed
    assert steps == ["generate", "review", "answer"]


# ---------------------------------------------------------------- streaming


@pytest.mark.asyncio
async def test_stream_sends_keepalives_while_an_agent_is_slow():
    async def slow(emit):
        await emit("agent.started", {"agent": "paperclip"})
        await asyncio.sleep(0.05)
        return ChatResponse(
            session_id="s", status="completed", question="q", mode="db_search", final_answer="a"
        )

    response = stream_orchestration(slow, keepalive_seconds=0.01)
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks[0].startswith("event: agent.started\n")
    assert ": keep-alive\n\n" in chunks
    assert chunks[-1].startswith("event: result\n")


@pytest.mark.asyncio
async def test_closing_the_stream_cancels_the_run():
    cancelled = asyncio.Event()

    async def endless(emit):
        await emit("agent.started", {"agent": "paperclip"})
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    body = stream_orchestration(endless, keepalive_seconds=5).body_iterator
    first = await body.__anext__()
    await body.aclose()

    assert first.startswith("event: agent.started")
    assert cancelled.is_set()


# ------------------------------------------------------- sessions, catalog


def test_session_history_keeps_only_the_latest_turns():
    store = SessionStore(ttl_minutes=45, max_sessions_per_user=5)
    session_id = store.create_session(browser_id="b").session_id

    for index in range(5):
        store.record_turn(session_id, "b", ConversationTurn(f"q{index}", "a"), max_turns=3)

    history = store.get_session(session_id, "b").history
    assert [turn.question for turn in history] == ["q2", "q3", "q4"]


def test_paperclip_is_available_when_a_key_is_configured_either_way(monkeypatch):
    settings = Settings()
    monkeypatch.delenv("PAPERCLIP_API_KEY", raising=False)
    monkeypatch.setattr(settings.env_settings, "paperclip_api_key", None)
    assert PAPERCLIP in unavailable_reasons(settings)

    monkeypatch.setattr(settings.env_settings, "paperclip_api_key", SecretStr("key"))
    assert PAPERCLIP not in unavailable_reasons(settings)

    monkeypatch.setattr(settings.env_settings, "paperclip_api_key", None)
    monkeypatch.setitem(os.environ, "PAPERCLIP_API_KEY", "key")
    assert PAPERCLIP not in unavailable_reasons(settings)
