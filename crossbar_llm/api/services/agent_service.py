
import asyncio
from typing import Any

from fastapi import HTTPException, status, UploadFile
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from crossbar_llm.agent_tools.callback_handler import (
    UsageMetricsCallback,
    merge_usage_summaries,
)
from crossbar_llm.agent_tools.config import LLMConfig, Neo4jConfig, ReasoningConfig
from crossbar_llm.agent_tools.cypher_agent import CypherAgent, CypherAgentState

from crossbar_llm.api.schemas.common import ExecutionControl, SearchMode
from crossbar_llm.api.schemas.requests import VectorSearchRequest, UploadVectorSearchRequest, DbSearchRequest, ResumeRequest
from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.services.session_store import session_store, SessionStore
from crossbar_llm.api.schemas.responses import ChatResponse, PendingResumeResponse
from crossbar_llm.api.services.fileguard import FileGuard
from crossbar_llm.api.services.literature_service import LiteratureService


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

    def _build_agent_graph(
            self,
            *,
            session_id: str,
            browser_id: str,
            chat_request: DbSearchRequest | VectorSearchRequest | ResumeRequest,
            usage_callback: UsageMetricsCallback | None = None,
        ) -> tuple[
            CompiledStateGraph,
            CypherAgent,
            UsageMetricsCallback,
            dict[str, dict[str, str]],
        ]:
        
        session = self.session_store.get_session(session_id=session_id, browser_id=browser_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with ID {session_id} not found for browser ID {browser_id}.",
            )
              
        if usage_callback is None:
            usage_callback = UsageMetricsCallback(session_id=session_id)

        llm_config = LLMConfig(
            model=chat_request.model,
            provider=chat_request.provider,
            callbacks=[usage_callback],
            reasoning=ReasoningConfig(
                enabled=chat_request.reasoning_enabled,
                effort=chat_request.reasoning_effort,
            )
        )

        agent = CypherAgent(
            llm_config=llm_config,
            neo4j_config=self.neo4j_config,
            top_k=chat_request.top_k,
            debug_mode=self.settings.debug,
        )

        graph = agent.build_graph(checkpointer=session.checkpointer)
        config = {"configurable": {"thread_id": session_id}}

        return graph, agent, usage_callback, config

    @staticmethod
    def _literature_enabled(payload) -> bool:
        tools = payload.literature_tools
        return tools.paperclip or tools.pubtator3

    @staticmethod
    def _new_literature_callback(session_id: str) -> UsageMetricsCallback:
        """A separate, lenient usage handler for the literature agents.

        Their structured-output path falls back to plain JSON on providers that
        don't support function calling, and those responses legitimately arrive
        without usage metadata — which the strict handler turns into a raised
        error that kills the call. Keeping this on its own handler means that
        leniency applies where it is warranted and does NOT quietly disable the
        core agent's strict accounting, which is what guards the token bill.
        `merge_usage_summaries` recombines the two for the response.
        """
        return UsageMetricsCallback(session_id=session_id, strict=False)

    def _usage_summary(
        self,
        usage_callback: UsageMetricsCallback,
        literature_callback: UsageMetricsCallback | None,
    ) -> dict[str, Any]:
        if literature_callback is None:
            return usage_callback.get_summary()
        return merge_usage_summaries(
            usage_callback.get_summary(), literature_callback.get_summary()
        )

    async def _gather_core_and_literature(
        self,
        *,
        graph: CompiledStateGraph,
        initial_state: dict[str, Any],
        config: dict[str, Any],
        question: str,
        payload,
        literature_callback: UsageMetricsCallback,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Run the Cypher graph and the literature agents concurrently.

        Both sides are real tasks so that a failure on either one cancels the
        other. A plain `gather()` would leave the survivor running detached
        after the request had already failed — the literature agents would keep
        spending metered Paperclip calls and LLM tokens on a response nobody
        will ever receive, and their eventual exception would surface as a bare
        "Task exception was never retrieved".
        """
        core_task = asyncio.create_task(graph.ainvoke(initial_state, config=config))
        literature_task = asyncio.create_task(
            self.literature_service.run(
                question=question,
                payload=payload,
                callback=literature_callback,
            )
        )
        tasks = (core_task, literature_task)
        try:
            result, literature = await asyncio.gather(*tasks)
        except BaseException:
            # Also covers the client disconnecting: Starlette cancels the
            # handler, which cancels this gather, and we stop the work.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return result, literature

    async def _run_initial_request(
        self,
        *,
        session_id: str,
        browser_id: str,
        payload: DbSearchRequest | VectorSearchRequest | UploadVectorSearchRequest,
        initial_state: dict[str, Any],
        usage_callback: UsageMetricsCallback,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, UsageMetricsCallback | None]:
        run_literature = (
            self._literature_enabled(payload)
            and payload.execution_mode == ExecutionControl.GENERATE_AND_RUN
        )
        graph, agent, usage_callback, config = self._build_agent_graph(
            session_id=session_id,
            browser_id=browser_id,
            chat_request=payload,
            usage_callback=usage_callback,
        )

        if not run_literature:
            return await graph.ainvoke(initial_state, config=config), None, None

        # Decide relevance up front so an out-of-domain question never reaches
        # the literature tools, which would spend metered external quota on a
        # question the graph is about to reject anyway. The verdict is seeded
        # into the state, and the relevance node reuses it rather than paying
        # for the same call twice — so the graph still runs end to end and
        # writes its checkpoint exactly as it does without literature enabled.
        relevance = await agent.avalidate_biological_relevance(payload.question)
        initial_state.update(relevance)
        if relevance["biological_relevance"] is False:
            return await graph.ainvoke(initial_state, config=config), None, None

        literature_callback = self._new_literature_callback(session_id)
        result, literature = await self._gather_core_and_literature(
            graph=graph,
            initial_state=initial_state,
            config=config,
            question=payload.question,
            payload=payload,
            literature_callback=literature_callback,
        )
        return result, literature, literature_callback

    
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

    def _to_response(
        self,
        session_id: str,
        cypher_mode: SearchMode,
        result: CypherAgentState,
        usage_callback: UsageMetricsCallback,
        literature: dict[str, Any] | None = None,
        literature_callback: UsageMetricsCallback | None = None,
    ) -> ChatResponse | PendingResumeResponse:


        if result.get("__interrupt__"):
            interrupts = result["__interrupt__"][0].value
            return PendingResumeResponse(
                session_id=session_id,
                question=interrupts.get("question"),
                mode=cypher_mode,
                generated_cypher=interrupts.get("current_cypher"),
            )

        elif result.get("is_ok", False) is False:
            status = "failed"
        else:
            status = "completed"

        return ChatResponse(
            session_id=session_id,
            status=status,
            mode=cypher_mode,
            question=result.get("question"),
            generated_cypher=result.get("current_cypher"),
            execution_result=result.get("execution_result"),
            final_answer=result.get("final_answer"),
            follow_up_questions=result.get("follow_up_questions", []),
            # One request-level total covering both the core agent and any
            # literature agents. `literature[<tool>].usage` breaks this down
            # per tool — it is a slice of this number, not an addition to it.
            usage=self._usage_summary(usage_callback, literature_callback),
            literature=literature or None,
        )

    async def run_db(
            self,
            session_id: str,
            browser_id: str,
            payload: DbSearchRequest
        ) -> ChatResponse | PendingResumeResponse:

        usage_callback = UsageMetricsCallback(session_id=session_id)
        result, literature, literature_callback = await self._run_initial_request(
            session_id=session_id,
            browser_id=browser_id,
            payload=payload,
            usage_callback=usage_callback,
            initial_state=self._base_state(
                question=payload.question,
                execution_mode=payload.execution_mode,
                cypher_mode=SearchMode.DB_SEARCH,
            ),
        )

        interrupts = result.get("__interrupt__")
        pending = bool(interrupts)
        if pending:
            pending_cypher = interrupts[0].value.get("current_cypher")
        else:
            pending_cypher = None

        self.session_store.mark_resume_pending(
            session_id=session_id,
            browser_id=browser_id,
            pending=pending,
            pending_cypher=pending_cypher
        )
        return self._to_response(
            session_id,
            SearchMode.DB_SEARCH,
            result,
            usage_callback,
            literature,
            literature_callback,
        )
    
    async def resume(
            self,
            session_id: str,
            browser_id: str,
            payload: ResumeRequest
        ) -> ChatResponse | PendingResumeResponse:      
       

        session = self.session_store.get_session(session_id=session_id, browser_id=browser_id)
        if not session.pending_resume:
            raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session with ID {session_id} is not pending resume.",
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


        usage_callback = UsageMetricsCallback(session_id=session_id)
        graph, _, usage_callback, config = self._build_agent_graph(
            session_id=session_id,
            browser_id=browser_id,
            chat_request=payload,
            usage_callback=usage_callback,
        )

        result = await graph.ainvoke(
            Command(resume=payload.model_dump(include={"action", "edited_cypher"})),
            config=config
        )

        # An approved query that fails execution is retried, and in generate
        # mode the retry pauses at human review again. The session must stay
        # pending with the new Cypher, or the next resume is turned away.
        interrupts = result.get("__interrupt__")
        pending = bool(interrupts)
        self.session_store.mark_resume_pending(
            session_id=session_id,
            browser_id=browser_id,
            pending=pending,
            pending_cypher=interrupts[0].value.get("current_cypher") if pending else None,
        )

        # Literature runs after the Cypher approval rather than alongside it:
        # in generate mode the question sits idle awaiting review, and paying
        # for literature evidence before the user has approved anything would
        # bill work the user may well discard. The same holds when the resume
        # pauses for review again: that response carries no literature, so the
        # tools wait for the resume that actually completes.
        literature = None
        literature_callback = None
        if self._literature_enabled(payload) and not pending:
            literature_callback = self._new_literature_callback(session_id)
            # `question` comes from the checkpointed state; a resume request has
            # no question of its own. An empty one still reaches the service so
            # it can report "skipped" per tool instead of silently returning
            # nothing to a user who explicitly asked for these tools.
            literature = await self.literature_service.run(
                question=result.get("question") or "",
                payload=payload,
                callback=literature_callback,
            )

        return self._to_response(
            session_id,
            payload.search_mode,
            result,
            usage_callback,
            literature,
            literature_callback,
        )
    
    async def run_vector(
            self,
            session_id: str,
            browser_id: str,
            payload: VectorSearchRequest
        ) -> ChatResponse | PendingResumeResponse:

        usage_callback = UsageMetricsCallback(session_id=session_id)
        result, literature, literature_callback = await self._run_initial_request(
            session_id=session_id,
            browser_id=browser_id,
            payload=payload,
            usage_callback=usage_callback,
            initial_state=self._base_state(
                question=payload.question,
                execution_mode=payload.execution_mode,
                cypher_mode=SearchMode.VECTOR_SEARCH,
                vector_index=payload.vector_index,
            ),
        )

        interrupts = result.get("__interrupt__")
        pending = bool(interrupts)
        if pending:
            pending_cypher = interrupts[0].value.get("current_cypher")
        else:
            pending_cypher = None
        
        self.session_store.mark_resume_pending(
            session_id=session_id, 
            browser_id=browser_id, 
            pending=pending, 
            pending_cypher=pending_cypher
        )
        return self._to_response(
            session_id,
            SearchMode.VECTOR_SEARCH,
            result,
            usage_callback,
            literature,
            literature_callback,
        )
    
    async def run_vector_upload(
            self, 
            session_id: str, 
            browser_id: str, 
            payload: UploadVectorSearchRequest, 
            embedding_file: UploadFile
        ) -> ChatResponse | PendingResumeResponse:

        guard = FileGuard(settings=self.settings, vector_index=payload.vector_index)
        embedding_array = await guard.load_embedding(embedding_file)

        usage_callback = UsageMetricsCallback(session_id=session_id)
        result, literature, literature_callback = await self._run_initial_request(
            session_id=session_id,
            browser_id=browser_id,
            payload=payload,
            usage_callback=usage_callback,
            initial_state=self._base_state(
                question=payload.question,
                execution_mode=payload.execution_mode,
                cypher_mode=SearchMode.VECTOR_SEARCH,
                vector_index=payload.vector_index,
                embedding=embedding_array.tolist(),
            ),
        )

        interrupts = result.get("__interrupt__")
        pending = bool(interrupts)
        if pending:
            pending_cypher = interrupts[0].value.get("current_cypher")
        else:
            pending_cypher = None
        
        self.session_store.mark_resume_pending(
            session_id=session_id, 
            browser_id=browser_id, 
            pending=pending, 
            pending_cypher=pending_cypher
        )
        return self._to_response(
            session_id,
            SearchMode.VECTOR_SEARCH,
            result,
            usage_callback,
            literature,
            literature_callback,
        )
        
        



        
