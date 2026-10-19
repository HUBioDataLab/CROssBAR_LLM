"""Running the knowledge-graph (Cypher) agent as one agent among several."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from langgraph.graph.state import CompiledStateGraph

from crossbar_llm.api.schemas.responses import AgentRunResult

INTERRUPT_KEY = "__interrupt__"

# Past tense: LangGraph reports a node once it has finished.
KG_STEP_LABELS: dict[str, str] = {
    "biological_relevance_validation": "Checked domain relevance",
    "entity_resolution": "Resolved entities in the graph",
    "generate_cypher": "Generated a Cypher query",
    "validate_cypher": "Validated the query against the schema",
    "error_correction": "Corrected the query",
    "web_search": "Searched the web for query hints",
    "human_review": "Applied your review",
    "execute_cypher": "Ran the query on CROssBARv2",
    "answer": "Interpreted the graph results",
    "follow_up_questions": "Suggested follow-up questions",
    "fail": "Could not build a working query",
}

KG_FALLBACK_FAILURE = "The Knowledge Graph agent could not answer this question."


async def stream_kg_graph(
    graph: CompiledStateGraph,
    graph_input: Any,
    config: dict[str, Any],
    on_step: Callable[[str], Awaitable[None]],
) -> dict[str, Any]:
    """`graph.ainvoke`, but calling `on_step` as each node finishes.

    Mirrors how `ainvoke` builds its result from the same two stream modes —
    the latest `values` snapshot, plus `__interrupt__` when the graph paused —
    so callers see exactly the state they would have got from `ainvoke`.
    """
    latest: dict[str, Any] = {}
    interrupts: list[Any] = []
    async for mode, payload in graph.astream(
        graph_input, config=config, stream_mode=["updates", "values"]
    ):
        if mode == "values":
            latest = payload
        elif mode == "updates" and isinstance(payload, dict):
            if (pending := payload.get(INTERRUPT_KEY)) is not None:
                interrupts.extend(pending)
                continue
            for node in payload:
                await on_step(node)
    if interrupts:
        return {**latest, INTERRUPT_KEY: interrupts}
    return latest


def kg_agent_result(
    state: dict[str, Any],
    *,
    usage: dict[str, Any],
    duration_seconds: float,
) -> AgentRunResult:
    answer = state.get("final_answer")
    if state.get("is_ok") is True and answer:
        return AgentRunResult(
            status="completed",
            answer=answer,
            usage=usage,
            duration_seconds=duration_seconds,
        )
    return AgentRunResult(
        status="failed",
        warnings=[answer or KG_FALLBACK_FAILURE],
        usage=usage,
        duration_seconds=duration_seconds,
    )
