"""Decide which of the user's enabled agents should answer a question."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)

from crossbar_llm.agent_tools.logging_config import get_logger
from crossbar_llm.orchestrator.llm import ainvoke_structured
from crossbar_llm.orchestrator.prompts import (
    ROUTER_HUMAN_TEMPLATE,
    ROUTER_JSON_INSTRUCTION,
    ROUTER_SYSTEM_TEMPLATE,
    VECTOR_MODE_RULE,
)
from crossbar_llm.orchestrator.registry import AGENT_SPECS, AgentId, resolve_agent
from crossbar_llm.orchestrator.schemas import RoutingOutput

logger = get_logger(__name__)

ROUTER_NODE_NAME = "orchestrator.router"

RoutingStrategy = Literal["llm", "single_agent", "fallback"]


@dataclass(frozen=True)
class ConversationTurn:
    question: str
    answer: str


@dataclass(frozen=True)
class RoutingPlan:
    selected: tuple[AgentId, ...]
    reasons: dict[AgentId, str]
    rationale: str
    standalone_question: str
    strategy: RoutingStrategy
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _format_profiles(enabled: Sequence[AgentId]) -> str:
    return "\n".join(
        f"- {agent_id.value} ({AGENT_SPECS[agent_id].name}): "
        f"{AGENT_SPECS[agent_id].routing_profile}"
        for agent_id in enabled
    )


def _format_history(history: Sequence[ConversationTurn]) -> str:
    if not history:
        return "(none: this is the first question)"
    return "\n".join(
        f"User: {turn.question}\nAssistant: {turn.answer}" for turn in history
    )


def _prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(ROUTER_SYSTEM_TEMPLATE),
            HumanMessagePromptTemplate.from_template(ROUTER_HUMAN_TEMPLATE),
        ]
    )


def _with_required(
    selected: list[AgentId], required: Sequence[AgentId]
) -> list[AgentId]:
    return [*required, *(agent for agent in selected if agent not in required)]


def _plan_from_output(
    output: RoutingOutput,
    *,
    question: str,
    enabled: Sequence[AgentId],
    required: Sequence[AgentId],
) -> RoutingPlan:
    reasons: dict[AgentId, str] = {}
    for route in output.agents:
        agent_id = resolve_agent(route.agent)
        # The model only sees the enabled agents, but nothing stops it naming
        # another — a disabled agent must never run because an LLM said so.
        if agent_id in enabled and agent_id not in reasons:
            reasons[agent_id] = route.reason.strip()

    selected = _with_required(list(reasons), required)
    if not selected:
        return _fallback(
            question,
            enabled,
            "The orchestrator selected no usable agent, so every enabled agent was asked.",
        )
    return RoutingPlan(
        selected=tuple(selected),
        reasons=reasons,
        rationale=output.rationale.strip(),
        standalone_question=output.standalone_question.strip() or question,
        strategy="llm",
    )


def _fallback(question: str, enabled: Sequence[AgentId], warning: str) -> RoutingPlan:
    return RoutingPlan(
        selected=tuple(enabled),
        reasons={},
        rationale="All enabled agents were consulted.",
        standalone_question=question,
        strategy="fallback",
        warnings=(warning,),
    )


async def route_question(
    *,
    chat_model: BaseChatModel,
    question: str,
    enabled: Sequence[AgentId],
    history: Sequence[ConversationTurn] = (),
    required: Sequence[AgentId] = (),
) -> RoutingPlan:
    """Pick agents from `enabled`. Never selects an agent outside it.

    `required` agents are always selected (vector search can only run on the
    knowledge graph). A routing failure degrades to asking every enabled agent
    rather than failing the request: a slower answer beats no answer.
    """
    if not enabled:
        raise ValueError("route_question needs at least one enabled agent")
    required = [agent for agent in required if agent in enabled]

    # The knowledge-graph agent keeps its own conversation history, so a
    # standalone rewrite only matters when a literature agent will read it.
    needs_rewrite = bool(history) and enabled[0] != AgentId.KNOWLEDGE_GRAPH
    if len(enabled) == 1 and not needs_rewrite:
        # Nothing to choose and nothing to rewrite, so an LLM call buys nothing.
        return RoutingPlan(
            selected=tuple(enabled),
            reasons={},
            rationale=f"Only the {AGENT_SPECS[enabled[0]].name} agent is enabled.",
            standalone_question=question,
            strategy="single_agent",
        )

    try:
        output = await ainvoke_structured(
            chat_model=chat_model,
            prompt=_prompt(),
            schema=RoutingOutput,
            values={
                "agent_profiles": _format_profiles(enabled),
                "mode_rules": VECTOR_MODE_RULE
                if AgentId.KNOWLEDGE_GRAPH in required
                else "",
                "history": _format_history(history),
                "question": question,
            },
            json_instruction=ROUTER_JSON_INSTRUCTION,
            node_name=ROUTER_NODE_NAME,
        )
    except Exception as error:
        logger.error(
            "Orchestrator routing failed; consulting every enabled agent",
            event_type="orchestrator_routing_failed",
            component="orchestrator.route_question",
            error_type=type(error).__name__,
            error=str(error),
            exc_info=error,
        )
        return _fallback(
            question,
            enabled,
            "Routing failed, so every enabled agent was consulted.",
        )

    plan = _plan_from_output(
        output, question=question, enabled=enabled, required=required
    )
    logger.info(
        "Orchestrator routed question",
        event_type="orchestrator_routed",
        component="orchestrator.route_question",
        selected=[agent.value for agent in plan.selected],
        strategy=plan.strategy,
    )
    return plan


__all__ = [
    "ROUTER_NODE_NAME",
    "ConversationTurn",
    "RoutingPlan",
    "route_question",
]
