"""The orchestrator: route a question to specialist agents and merge their answers.

One request runs in three stages:

1. Plan. The biological-relevance gate and the router run concurrently. An
   out-of-domain question stops here, before any agent spends anything.
2. Run. The routed agents work concurrently, each isolated from the others: a
   failing agent is reported as failed, it does not take the request down. In
   "generate" mode the knowledge-graph agent pauses for the user to review its
   Cypher, and the other routed agents wait for that approval (the plan is
   kept in the session) so nothing is billed for a question the user may drop.
3. Synthesize. Two or more answers are merged into one, with duplication
   removed and contradictions resolved and listed. A single answer is passed
   through as is.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from time import monotonic
from typing import Any
from collections.abc import Coroutine

from fastapi import HTTPException, status, UploadFile
from langgraph.types import Command

from crossbar_llm.agent_tools.callback_handler import UsageMetricsCallback
from crossbar_llm.agent_tools.config import LLMConfig, Neo4jConfig, ReasoningConfig
from crossbar_llm.agent_tools.cypher_agent import (
    CypherAgent,
    avalidate_biological_relevance,
)
from crossbar_llm.agent_tools.llm_factory import LLMFactory
from crossbar_llm.agent_tools.logging_config import get_logger

from crossbar_llm.api.schemas.common import ExecutionControl, SearchMode
from crossbar_llm.api.schemas.requests import (
    ModelConfigRequest,
    VectorSearchRequest,
    UploadVectorSearchRequest,
    DbSearchRequest,
    ResumeRequest,
)
from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.schemas.responses import (
    AgentRunResult,
    ChatResponse,
    Contradiction,
    PendingResumeResponse,
    RoutingDecision,
)
from crossbar_llm.api.services import orchestration_events as events
from crossbar_llm.api.services import orchestration_results as results
from crossbar_llm.api.services.agent_catalog import unavailable_reasons
from crossbar_llm.api.services.fileguard import FileGuard
from crossbar_llm.api.services.kg_runner import (
    INTERRUPT_KEY,
    KG_STEP_LABELS,
    kg_agent_result,
    stream_kg_graph,
)
from crossbar_llm.api.services.literature_service import LiteratureService
from crossbar_llm.api.services.orchestration_events import EventSink, discard_events
from crossbar_llm.api.services.orchestration_results import (
    AgentOutcome,
    AgentSelection,
    FinalAnswer,
    RequestRun,
)
from crossbar_llm.api.services.session_store import (
    ChatSessionContext,
    SessionNotFoundError,
    SessionStore,
    session_store,
)
from crossbar_llm.orchestrator.llm import build_chat_model
from crossbar_llm.orchestrator.registry import AgentId
from crossbar_llm.orchestrator.router import (
    ConversationTurn,
    RoutingPlan,
    route_question,
)
from crossbar_llm.orchestrator.synthesizer import (
    AgentReport,
    fallback_answer,
    synthesize_reports,
)

logger = get_logger(__name__)

AgentWork = dict[AgentId, Coroutine[Any, Any, AgentOutcome]]


class AgentService:
    def __init__(
            self,
            settings: Settings = Settings(),
            session_store: SessionStore = session_store
        ):

        self.neo4j_config = Neo4jConfig()
        self.settings = settings
        self.session_store = session_store
        self.literature_service = LiteratureService(settings)

    async def aclose(self) -> None:
        await self.literature_service.aclose()

    # ------------------------------------------------------------------ setup

    def require_session(self, session_id: str, browser_id: str) -> ChatSessionContext:
        try:
            return self.session_store.get_session(
                session_id=session_id, browser_id=browser_id
            )
        except (SessionNotFoundError, ValueError):
            # One answer for "no such session" and "not yours": telling them
            # apart would confirm that someone else's session id exists.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with ID {session_id} not found.",
            ) from None

    @contextmanager
    def _exclusive(self, session_id: str, browser_id: str):
        """Hold the session for one request at a time."""
        self.require_session(session_id, browser_id)
        if not self.session_store.claim(session_id, browser_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This chat is still answering a question. Wait for it to "
                    "finish, or start a new conversation."
                ),
            )
        try:
            yield
        finally:
            self.session_store.release(session_id, browser_id)

    def _select_agents(self, payload: ModelConfigRequest) -> AgentSelection:
        unavailable = unavailable_reasons(self.settings)
        enabled: list[AgentId] = []
        skipped: dict[AgentId, str] = {}
        for agent_id in AgentId:
            if not getattr(payload.agents, agent_id.value):
                skipped[agent_id] = results.DISABLED_REASON
            elif agent_id in unavailable:
                skipped[agent_id] = unavailable[agent_id]
            else:
                enabled.append(agent_id)
        return AgentSelection(enabled=enabled, skipped=skipped)

    def _validated_selection(
        self, payload: ModelConfigRequest, *, vector_search: bool
    ) -> AgentSelection:
        selection = self._select_agents(payload)
        if vector_search and AgentId.KNOWLEDGE_GRAPH not in selection.enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Vector search runs on the Knowledge Graph agent. Enable it "
                    "to use vector search."
                ),
            )
        if not selection.enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "None of the enabled agents can run on this server: "
                    + " ".join(selection.skipped.values())
                ),
            )
        return selection

    def _new_run(
        self,
        *,
        session_id: str,
        browser_id: str,
        payload: ModelConfigRequest,
        emit: EventSink | None,
    ) -> RequestRun:
        core_callback = UsageMetricsCallback(session_id=session_id)
        aux_callback = UsageMetricsCallback(session_id=session_id, strict=False)
        reasoning = ReasoningConfig(
            enabled=payload.reasoning_enabled,
            effort=payload.reasoning_effort,
        )
        return RequestRun(
            session_id=session_id,
            browser_id=browser_id,
            payload=payload,
            emit=emit or discard_events,
            llm_config=LLMConfig(
                model=payload.model,
                provider=payload.provider,
                callbacks=[core_callback],
                reasoning=reasoning,
            ),
            core_callback=core_callback,
            aux_callback=aux_callback,
            orchestrator_model=build_chat_model(
                model=payload.model,
                provider=payload.provider,
                callbacks=[aux_callback],
                reasoning=reasoning,
            ),
        )

    def _build_kg_graph(self, run: RequestRun):
        session = self.require_session(run.session_id, run.browser_id)
        agent = CypherAgent(
            llm_config=run.llm_config,
            neo4j_config=self.neo4j_config,
            top_k=run.payload.top_k,
            debug_mode=self.settings.debug,
        )
        graph = agent.build_graph(checkpointer=session.checkpointer)
        return graph, {"configurable": {"thread_id": run.session_id}}

    # ----------------------------------------------------------------- agents

    @staticmethod
    async def _gather_or_cancel(*coros: Coroutine[Any, Any, Any]) -> list[Any]:
        """Await everything together; if this request stops, stop all of it.

        No task may be left running detached, spending metered calls on a
        response nobody will receive — which a bare `gather` allows when one
        coroutine raises or the client disconnects mid-flight.
        """
        tasks = [asyncio.create_task(coro) for coro in coros]
        try:
            return list(await asyncio.gather(*tasks))
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _run_concurrently(self, work: AgentWork) -> dict[AgentId, AgentOutcome]:
        """Run agents side by side. The agent wrappers turn their own failures
        into results, so what propagates is cancellation or a bug."""
        if not work:
            return {}
        outcomes = await self._gather_or_cancel(*work.values())
        return dict(zip(work, outcomes))

    async def _agent_completed(
        self, run: RequestRun, agent_id: AgentId, result: AgentRunResult
    ) -> None:
        await run.emit(
            events.AGENT_COMPLETED,
            {
                "agent": agent_id.value,
                "status": result.status,
                "duration_seconds": result.duration_seconds,
                "warnings": result.warnings,
            },
        )

    async def _run_kg_agent(self, run: RequestRun, graph_input: Any) -> AgentOutcome:
        agent_id = AgentId.KNOWLEDGE_GRAPH
        await run.emit(events.AGENT_STARTED, {"agent": agent_id.value})
        started = monotonic()

        async def on_step(node: str) -> None:
            if node == results.RELEVANCE_NODE:
                # Only reuses the orchestrator's own verdict: not real progress.
                return
            await run.emit(
                events.AGENT_PROGRESS,
                {
                    "agent": agent_id.value,
                    "step": node,
                    "label": KG_STEP_LABELS.get(node, node),
                },
            )

        try:
            # Building the agent reads the graph schema from Neo4j over a
            # blocking driver; off the event loop, so the literature agents
            # running alongside are not stalled by it.
            graph, config = await asyncio.to_thread(self._build_kg_graph, run)
            state = await stream_kg_graph(graph, graph_input, config, on_step)
        except Exception as error:
            logger.error(
                "Knowledge Graph agent failed",
                event_type="kg_agent_failed",
                component="AgentService._run_kg_agent",
                error_type=type(error).__name__,
                error=str(error),
                exc_info=error,
            )
            result = AgentRunResult(
                status="failed",
                warnings=[
                    (
                        f"The Knowledge Graph agent failed with {type(error).__name__}. "
                        "See the server logs for details."
                    )
                ],
                usage=results.kg_usage(run),
                duration_seconds=round(monotonic() - started, 2),
            )
            await self._agent_completed(run, agent_id, result)
            return AgentOutcome(result=result)

        if interrupts := state.get(INTERRUPT_KEY):
            review = interrupts[0].value
            await run.emit(
                events.REVIEW_REQUIRED,
                {"agent": agent_id.value, "generated_cypher": review.get("current_cypher")},
            )
            return AgentOutcome(
                state=state,
                pending_cypher=review.get("current_cypher"),
                pending_question=review.get("question"),
            )

        result = kg_agent_result(
            state,
            usage=results.kg_usage(run),
            duration_seconds=round(monotonic() - started, 2),
        )
        await self._agent_completed(run, agent_id, result)
        return AgentOutcome(result=result, state=state)

    async def _run_literature_agent(
        self, run: RequestRun, agent_id: AgentId, question: str
    ) -> AgentOutcome:
        await run.emit(events.AGENT_STARTED, {"agent": agent_id.value})
        started = monotonic()
        result = await self.literature_service.run_tool(
            agent_id.value,
            question=question,
            payload=run.payload,
            callback=run.aux_callback,
        )
        result = result.model_copy(
            update={"duration_seconds": round(monotonic() - started, 2)}
        )
        await self._agent_completed(run, agent_id, result)
        return AgentOutcome(result=result)

    def _literature_work(
        self, run: RequestRun, agents: list[AgentId], question: str
    ) -> AgentWork:
        return {
            agent_id: self._run_literature_agent(run, agent_id, question)
            for agent_id in agents
        }

    # ------------------------------------------------- planning and synthesis

    def _history(self, session: ChatSessionContext) -> list[ConversationTurn]:
        turns = self.settings.orchestrator_history_turns
        return list(session.history[-turns:]) if turns > 0 else []

    async def _plan(
        self,
        run: RequestRun,
        *,
        question: str,
        selection: AgentSelection,
        required: list[AgentId],
        history: list[ConversationTurn],
    ) -> tuple[dict[str, Any], RoutingPlan]:
        """Relevance and routing together: neither waits on the other."""
        verdict, plan = await self._gather_or_cancel(
            avalidate_biological_relevance(LLMFactory(run.llm_config), question),
            route_question(
                chat_model=run.orchestrator_model,
                question=question,
                enabled=selection.enabled,
                history=history,
                required=required,
            ),
        )
        return verdict, plan

    async def _synthesize(
        self, run: RequestRun, question: str, reports: list[AgentReport]
    ) -> FinalAnswer:
        if len(reports) < 2:
            return FinalAnswer(text=reports[0].answer if reports else "")

        await run.emit(
            events.SYNTHESIS_STARTED, {"agents": [report.agent.value for report in reports]}
        )
        try:
            synthesis = await synthesize_reports(
                chat_model=run.orchestrator_model,
                question=question,
                reports=reports,
            )
        except Exception as error:
            logger.error(
                "Orchestrator synthesis failed; returning the reports separately",
                event_type="orchestrator_synthesis_failed",
                component="AgentService._synthesize",
                error_type=type(error).__name__,
                error=str(error),
                exc_info=error,
            )
            await run.emit(
                events.SYNTHESIS_COMPLETED, {"synthesized": False, "contradictions": 0}
            )
            return FinalAnswer(
                text=fallback_answer(reports),
                warnings=[results.SYNTHESIS_FAILED_WARNING],
            )

        contradictions = [
            Contradiction(
                topic=item.topic, agents=list(item.agents), resolution=item.resolution
            )
            for item in synthesis.contradictions
        ]
        await run.emit(
            events.SYNTHESIS_COMPLETED,
            {"synthesized": True, "contradictions": len(contradictions)},
        )
        return FinalAnswer(
            text=synthesis.answer, contradictions=contradictions, synthesized=True
        )

    async def _finalize(
        self,
        run: RequestRun,
        *,
        question: str,
        search_mode: SearchMode,
        plan: RoutingPlan,
        routing: RoutingDecision,
        outcomes: dict[AgentId, AgentOutcome],
    ) -> ChatResponse:
        reports = results.answer_reports(plan, outcomes)
        if reports:
            final = await self._synthesize(
                run, plan.standalone_question or question, reports
            )
            self.session_store.record_turn(
                session_id=run.session_id,
                browser_id=run.browser_id,
                turn=ConversationTurn(
                    question=question,
                    answer=final.text[: self.settings.orchestrator_history_answer_chars],
                ),
                max_turns=self.settings.orchestrator_history_turns,
            )
        else:
            final = FinalAnswer(text=results.no_answer_text(outcomes))

        return results.chat_response(
            run,
            question=question,
            search_mode=search_mode,
            plan=plan,
            routing=routing,
            outcomes=outcomes,
            reports=reports,
            final=final,
        )

    def _mark_pending(
        self, run: RequestRun, kg: AgentOutcome | None, plan: RoutingPlan
    ) -> bool:
        """Record whether the session now waits on a Cypher review."""
        pending = kg is not None and kg.pending
        self.session_store.mark_resume_pending(
            session_id=run.session_id,
            browser_id=run.browser_id,
            pending=pending,
            pending_cypher=kg.pending_cypher if pending else None,
            pending_plan=plan if pending else None,
        )
        return pending

    # --------------------------------------------------------------- requests

    async def _answer_question(self, **kwargs: Any) -> ChatResponse | PendingResumeResponse:
        with self._exclusive(kwargs["session_id"], kwargs["browser_id"]):
            return await self._answer_question_exclusively(**kwargs)

    async def _answer_question_exclusively(
        self,
        *,
        session_id: str,
        browser_id: str,
        payload: DbSearchRequest | VectorSearchRequest | UploadVectorSearchRequest,
        search_mode: SearchMode,
        initial_state: dict[str, Any],
        emit: EventSink | None,
    ) -> ChatResponse | PendingResumeResponse:
        session = self.require_session(session_id, browser_id)
        is_vector = search_mode == SearchMode.VECTOR_SEARCH
        selection = self._validated_selection(payload, vector_search=is_vector)
        run = self._new_run(
            session_id=session_id, browser_id=browser_id, payload=payload, emit=emit
        )
        question = payload.question

        await run.emit(
            events.ORCHESTRATION_STARTED,
            {
                "enabled": [agent_id.value for agent_id in selection.enabled],
                "skipped": {key.value: value for key, value in selection.skipped.items()},
            },
        )
        verdict, plan = await self._plan(
            run,
            question=question,
            selection=selection,
            required=[AgentId.KNOWLEDGE_GRAPH] if is_vector else [],
            history=self._history(session),
        )

        if verdict.get("biological_relevance") is False:
            self._mark_pending(run, None, plan)
            await run.emit(
                events.RELEVANCE_REJECTED, {"reason": verdict.get("final_answer")}
            )
            return results.out_of_domain_response(
                run,
                question=question,
                search_mode=search_mode,
                plan=plan,
                selection=selection,
                verdict=verdict,
            )

        routing = results.routing_decision(plan, selection)
        await run.emit(events.ROUTING_COMPLETED, routing.model_dump(mode="json"))

        kg_selected = AgentId.KNOWLEDGE_GRAPH in plan.selected
        literature = [
            agent_id for agent_id in plan.selected if agent_id != AgentId.KNOWLEDGE_GRAPH
        ]
        # Literature waits for the user's Cypher approval in generate mode:
        # paying for evidence before anything is approved would bill work the
        # user may well discard.
        defer_literature = (
            kg_selected and payload.execution_mode == ExecutionControl.GENERATE
        )

        work: AgentWork = {}
        if kg_selected:
            # The relevance verdict is seeded so the graph reuses it instead of
            # paying for the same call twice.
            work[AgentId.KNOWLEDGE_GRAPH] = self._run_kg_agent(
                run, {**initial_state, **verdict}
            )
        if not defer_literature:
            work.update(self._literature_work(run, literature, plan.standalone_question))
        outcomes = await self._run_concurrently(work)

        kg = outcomes.get(AgentId.KNOWLEDGE_GRAPH)
        if self._mark_pending(run, kg, plan):
            return results.pending_response(
                run, search_mode=search_mode, question=question, routing=routing, kg=kg
            )

        if defer_literature and literature:
            # The graph ended without asking for review (no valid query could
            # be built), so there is nothing left to wait for.
            outcomes.update(
                await self._run_concurrently(
                    self._literature_work(run, literature, plan.standalone_question)
                )
            )

        return await self._finalize(
            run,
            question=question,
            search_mode=search_mode,
            plan=plan,
            routing=routing,
            outcomes=outcomes,
        )

    def _base_state(
            self,
            *,
            question: str,
            execution_mode: str,
            cypher_mode: SearchMode,
            vector_index: str | None = None,
            embedding: list[float] | None = None
        ):

        return {
            "question": question,
            # Reset per question. The session checkpointer carries every key
            # forward between questions, and the relevance node skips itself
            # when a verdict is already present — so a stale verdict here would
            # silently apply the PREVIOUS question's relevance to this one.
            "biological_relevance": None,
            "resolved_entities": None,
            "cypher_mode": cypher_mode,
            "vector_index": vector_index,
            "embedding": embedding,
            "current_cypher": "",
            "retry_count": 0,
            "recent_questions": [],
            "is_ok": False,
            "cypher_attempts": [],
            "no_valid_schema_path": False,
            "execution_result": None,
            "final_answer": None,
            "web_search_used": False,
            "web_search_result": None,
            "nodes": [],
            "node_properties": [],
            "edges": [],
            "edge_properties": [],
            "execution_mode": execution_mode,
        }

    async def run_db(
            self,
            session_id: str,
            browser_id: str,
            payload: DbSearchRequest,
            emit: EventSink | None = None,
        ) -> ChatResponse | PendingResumeResponse:

        return await self._answer_question(
            session_id=session_id,
            browser_id=browser_id,
            payload=payload,
            search_mode=SearchMode.DB_SEARCH,
            initial_state=self._base_state(
                question=payload.question,
                execution_mode=payload.execution_mode,
                cypher_mode=SearchMode.DB_SEARCH,
            ),
            emit=emit,
        )

    async def run_vector(
            self,
            session_id: str,
            browser_id: str,
            payload: VectorSearchRequest,
            emit: EventSink | None = None,
        ) -> ChatResponse | PendingResumeResponse:

        return await self._answer_question(
            session_id=session_id,
            browser_id=browser_id,
            payload=payload,
            search_mode=SearchMode.VECTOR_SEARCH,
            initial_state=self._base_state(
                question=payload.question,
                execution_mode=payload.execution_mode,
                cypher_mode=SearchMode.VECTOR_SEARCH,
                vector_index=payload.vector_index,
            ),
            emit=emit,
        )

    async def load_embedding(
            self,
            payload: UploadVectorSearchRequest,
            embedding_file: UploadFile,
        ) -> list[float]:
        """Validate and read an uploaded embedding.

        Separate from running the question so a streaming endpoint can read the
        file before its response starts: the upload may be closed by then, and
        a bad file still gets a real 4xx instead of an error event.
        """
        guard = FileGuard(settings=self.settings, vector_index=payload.vector_index)
        embedding_array = await guard.load_embedding(embedding_file)
        return embedding_array.tolist()

    async def run_vector_embedding(
            self,
            session_id: str,
            browser_id: str,
            payload: UploadVectorSearchRequest,
            embedding: list[float],
            emit: EventSink | None = None,
        ) -> ChatResponse | PendingResumeResponse:

        return await self._answer_question(
            session_id=session_id,
            browser_id=browser_id,
            payload=payload,
            search_mode=SearchMode.VECTOR_SEARCH,
            initial_state=self._base_state(
                question=payload.question,
                execution_mode=payload.execution_mode,
                cypher_mode=SearchMode.VECTOR_SEARCH,
                vector_index=payload.vector_index,
                embedding=embedding,
            ),
            emit=emit,
        )

    async def run_vector_upload(
            self,
            session_id: str,
            browser_id: str,
            payload: UploadVectorSearchRequest,
            embedding_file: UploadFile,
            emit: EventSink | None = None,
        ) -> ChatResponse | PendingResumeResponse:

        embedding = await self.load_embedding(payload, embedding_file)
        return await self.run_vector_embedding(
            session_id, browser_id, payload, embedding, emit
        )

    # ------------------------------------------------------------------ resume

    async def resume(
            self,
            session_id: str,
            browser_id: str,
            payload: ResumeRequest,
            emit: EventSink | None = None,
        ) -> ChatResponse | PendingResumeResponse:

        with self._exclusive(session_id, browser_id):
            return await self._resume_exclusively(session_id, browser_id, payload, emit)

    async def _resume_exclusively(
            self,
            session_id: str,
            browser_id: str,
            payload: ResumeRequest,
            emit: EventSink | None,
        ) -> ChatResponse | PendingResumeResponse:

        session = self.require_session(session_id, browser_id)
        results.validate_resume(session, payload)

        plan, selection = results.resume_plan(
            session.pending_plan, self._select_agents(payload)
        )
        run = self._new_run(
            session_id=session_id, browser_id=browser_id, payload=payload, emit=emit
        )
        routing = results.routing_decision(plan, selection)
        await run.emit(
            events.ORCHESTRATION_STARTED,
            {"enabled": [agent_id.value for agent_id in plan.selected], "skipped": {}},
        )
        await run.emit(events.ROUTING_COMPLETED, routing.model_dump(mode="json"))

        kg = await self._run_kg_agent(
            run, Command(resume=payload.model_dump(include={"action", "edited_cypher"}))
        )

        # An approved query that fails execution is retried, and in generate
        # mode the retry pauses at human review again. The session must stay
        # pending with the new Cypher, or the next resume is turned away — and
        # the other agents keep waiting, since that response carries no answer.
        if self._mark_pending(run, kg, plan):
            return results.pending_response(
                run,
                search_mode=payload.search_mode,
                question=plan.standalone_question,
                routing=routing,
                kg=kg,
            )

        # A resume request carries no question of its own; it lives in the
        # checkpointed graph state.
        question = (kg.state or {}).get("question") or plan.standalone_question
        literature = [
            agent_id for agent_id in plan.selected if agent_id != AgentId.KNOWLEDGE_GRAPH
        ]
        outcomes = {
            AgentId.KNOWLEDGE_GRAPH: kg,
            **await self._run_concurrently(
                self._literature_work(
                    run, literature, plan.standalone_question or question
                )
            ),
        }
        return await self._finalize(
            run,
            question=question,
            search_mode=payload.search_mode,
            plan=plan,
            routing=routing,
            outcomes=outcomes,
        )


__all__ = ["AgentService"]
