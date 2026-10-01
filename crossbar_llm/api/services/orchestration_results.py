"""Per-request state and response building for the orchestrator.

`AgentService` decides what runs; this module holds what one run carries
around and turns its outcomes into API responses.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

from crossbar_llm.agent_tools.callback_handler import (
    UsageMetricsCallback,
    merge_usage_summaries,
    usage_slice,
)
from crossbar_llm.agent_tools.config import LLMConfig
from crossbar_llm.api.schemas.common import SearchMode
from fastapi import HTTPException, status

from crossbar_llm.api.schemas.requests import ModelConfigRequest, ResumeRequest
from crossbar_llm.api.schemas.responses import (
    AgentRunResult,
    ChatResponse,
    Contradiction,
    OrchestrationResult,
    PendingResumeResponse,
    RoutingDecision,
)
from crossbar_llm.api.services.orchestration_events import EventSink
from crossbar_llm.api.services.session_store import ChatSessionContext
from crossbar_llm.orchestrator.registry import AgentId
from crossbar_llm.orchestrator.router import RoutingPlan
from crossbar_llm.orchestrator.synthesizer import AgentReport

RELEVANCE_NODE = "biological_relevance_validation"
ORCHESTRATOR_NODE_PREFIX = "orchestrator."

DISABLED_REASON = "Disabled in your agent settings."
NOT_ROUTED_REASON = "Not needed for this question."
OUT_OF_DOMAIN_REASON = "The question is outside the biomedical domain."
NO_ANSWER = (
    "None of the selected agents could answer this question. Try rephrasing "
    "it, or enable more agents."
)
SYNTHESIS_FAILED_WARNING = (
    "The orchestrator could not merge the agents' answers, so each is shown "
    "separately."
)


@dataclass
class RequestRun:
    """Everything one request's agents share."""

    session_id: str
    browser_id: str
    payload: ModelConfigRequest
    emit: EventSink
    llm_config: LLMConfig
    # Strict for the knowledge-graph agent: a provider that hides usage
    # metadata should fail loudly there rather than bill silently. Lenient for
    # the orchestrator and literature agents, whose JSON-fallback path
    # legitimately returns responses without it.
    core_callback: UsageMetricsCallback
    aux_callback: UsageMetricsCallback
    orchestrator_model: Any


@dataclass
class AgentOutcome:
    """One agent's run. No `result` but a `state` means it paused for review."""

    result: AgentRunResult | None = None
    state: dict[str, Any] | None = None
    pending_cypher: str | None = None
    pending_question: str | None = None

    @property
    def pending(self) -> bool:
        return self.result is None and self.state is not None


@dataclass(frozen=True)
class AgentSelection:
    enabled: list[AgentId]
    skipped: dict[AgentId, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FinalAnswer:
    text: str
    contradictions: list[Contradiction] = field(default_factory=list)
    synthesized: bool = False
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ usage


def kg_usage(run: RequestRun) -> dict[str, Any]:
    return usage_slice(
        run.core_callback.get_summary(), lambda node: node != RELEVANCE_NODE
    )


def total_usage(run: RequestRun) -> dict[str, Any]:
    # One request-level total covering every agent. Each agent's `usage` in
    # `orchestration.agents` is a slice of this number, not an addition to it.
    return merge_usage_summaries(
        run.core_callback.get_summary(), run.aux_callback.get_summary()
    )


def orchestrator_usage(run: RequestRun) -> dict[str, Any]:
    return merge_usage_summaries(
        usage_slice(
            run.core_callback.get_summary(), lambda node: node == RELEVANCE_NODE
        ),
        usage_slice(
            run.aux_callback.get_summary(),
            lambda node: node.startswith(ORCHESTRATOR_NODE_PREFIX),
        ),
    )


# ---------------------------------------------------------------- routing


def routing_decision(plan: RoutingPlan, selection: AgentSelection) -> RoutingDecision:
    skipped = dict(selection.skipped)
    for agent_id in selection.enabled:
        if agent_id not in plan.selected:
            skipped[agent_id] = NOT_ROUTED_REASON
    return RoutingDecision(
        selected=list(plan.selected),
        reasons=plan.reasons,
        skipped=skipped,
        rationale=plan.rationale,
        standalone_question=plan.standalone_question,
        strategy=plan.strategy,
    )


# ---------------------------------------------------------------- reports


def agent_results(outcomes: dict[AgentId, AgentOutcome]) -> dict[AgentId, AgentRunResult]:
    return {
        agent_id: outcome.result
        for agent_id, outcome in outcomes.items()
        if outcome.result is not None
    }


def kg_state(outcomes: dict[AgentId, AgentOutcome]) -> dict[str, Any]:
    outcome = outcomes.get(AgentId.KNOWLEDGE_GRAPH)
    return (outcome.state if outcome else None) or {}


def answer_reports(
    plan: RoutingPlan, outcomes: dict[AgentId, AgentOutcome]
) -> list[AgentReport]:
    """The usable answers, in the order the router chose the agents."""
    results = agent_results(outcomes)
    records = kg_state(outcomes).get("execution_result")
    return [
        AgentReport(
            agent=agent_id,
            status=results[agent_id].status,
            answer=results[agent_id].answer,
            citations=results[agent_id].citations,
            records=records if agent_id == AgentId.KNOWLEDGE_GRAPH else None,
            warnings=results[agent_id].warnings,
        )
        for agent_id in plan.selected
        if agent_id in results
        and results[agent_id].status == "completed"
        and results[agent_id].answer
    ]


def no_answer_text(outcomes: dict[AgentId, AgentOutcome]) -> str:
    # A lone knowledge-graph failure keeps its own explanation, as it always
    # has; otherwise say plainly that no agent had an answer.
    if len(agent_results(outcomes)) == 1:
        return kg_state(outcomes).get("final_answer") or NO_ANSWER
    return NO_ANSWER


# -------------------------------------------------------------- responses


def chat_response(
    run: RequestRun,
    *,
    question: str,
    search_mode: SearchMode,
    plan: RoutingPlan,
    routing: RoutingDecision,
    outcomes: dict[AgentId, AgentOutcome],
    reports: list[AgentReport],
    final: FinalAnswer,
) -> ChatResponse:
    state = kg_state(outcomes)
    return ChatResponse(
        session_id=run.session_id,
        status="completed" if reports else "failed",
        mode=search_mode,
        question=question,
        generated_cypher=state.get("current_cypher") or None,
        execution_result=state.get("execution_result"),
        final_answer=final.text,
        follow_up_questions=state.get("follow_up_questions") or [],
        usage=total_usage(run),
        orchestration=OrchestrationResult(
            routing=routing,
            agents=agent_results(outcomes),
            contradictions=final.contradictions,
            synthesized=final.synthesized,
            answer_sources=[report.agent for report in reports],
            warnings=[*plan.warnings, *final.warnings],
            usage=orchestrator_usage(run),
        ),
    )


def out_of_domain_response(
    run: RequestRun,
    *,
    question: str,
    search_mode: SearchMode,
    plan: RoutingPlan,
    selection: AgentSelection,
    verdict: dict[str, Any],
) -> ChatResponse:
    skipped = dict(selection.skipped)
    skipped.update({agent_id: OUT_OF_DOMAIN_REASON for agent_id in selection.enabled})
    return ChatResponse(
        session_id=run.session_id,
        status="failed",
        mode=search_mode,
        question=question,
        final_answer=verdict.get("final_answer"),
        usage=total_usage(run),
        orchestration=OrchestrationResult(
            routing=RoutingDecision(
                selected=[],
                skipped=skipped,
                rationale=OUT_OF_DOMAIN_REASON,
                standalone_question=plan.standalone_question,
                strategy=plan.strategy,
            ),
            usage=orchestrator_usage(run),
        ),
    )


def pending_response(
    run: RequestRun,
    *,
    search_mode: SearchMode,
    question: str,
    routing: RoutingDecision,
    kg: AgentOutcome,
) -> PendingResumeResponse:
    return PendingResumeResponse(
        session_id=run.session_id,
        question=kg.pending_question or question,
        mode=search_mode,
        generated_cypher=kg.pending_cypher,
        orchestration=OrchestrationResult(
            routing=routing, usage=orchestrator_usage(run)
        ),
    )


# ------------------------------------------------------------------ resume


def validate_resume(session: ChatSessionContext, payload: ResumeRequest) -> None:
    if not session.pending_resume:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session with ID {session.session_id} is not pending resume.",
        )

    if payload.action == "approve":
        if session.pending_cypher is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No pending cypher found for approval.",
            )

        if payload.edited_cypher.strip() != session.pending_cypher.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approved cypher must exactly match the last generated cypher.",
            )

def resume_plan(
    stored: RoutingPlan | None, selection: AgentSelection
) -> tuple[RoutingPlan, AgentSelection]:
    """The paused question's plan, minus agents switched off since.

    The knowledge-graph agent always stays: resuming it is the request.
    """
    if stored is None:
        stored = RoutingPlan(
            selected=(AgentId.KNOWLEDGE_GRAPH,),
            reasons={},
            rationale="",
            standalone_question="",
            strategy="single_agent",
        )
    plan = dataclasses.replace(
        stored,
        selected=tuple(
            agent_id
            for agent_id in stored.selected
            if agent_id == AgentId.KNOWLEDGE_GRAPH or agent_id in selection.enabled
        ),
    )
    skipped = {
        agent_id: reason
        for agent_id, reason in selection.skipped.items()
        if agent_id != AgentId.KNOWLEDGE_GRAPH
    }
    return plan, AgentSelection(enabled=list(plan.selected), skipped=skipped)
