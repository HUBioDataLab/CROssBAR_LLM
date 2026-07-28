
from fastapi import HTTPException, status, UploadFile
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from crossbar_llm.agent_tools.callback_handler import UsageMetricsCallback
from crossbar_llm.agent_tools.config import LLMConfig, Neo4jConfig, ReasoningConfig
from crossbar_llm.agent_tools.cypher_agent import CypherAgent, CypherAgentState

from crossbar_llm.api.schemas.common import SearchMode
from crossbar_llm.api.schemas.requests import VectorSearchRequest, UploadVectorSearchRequest, DbSearchRequest, ResumeRequest
from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.services.session_store import session_store, SessionStore
from crossbar_llm.api.schemas.responses import ChatResponse, PendingResumeResponse
from crossbar_llm.api.services.fileguard import FileGuard


class AgentService:
    def __init__(
            self,
            settings: Settings = Settings(),
            session_store: SessionStore = session_store
        ):

        self.neo4j_config = Neo4jConfig()
        self.settings = settings
        self.session_store = session_store

    def _build_agent_graph(
            self,
            *,
            session_id: str,
            browser_id: str,
            chat_request: DbSearchRequest | VectorSearchRequest | ResumeRequest,
            resume: bool = False
        ) -> tuple[CompiledStateGraph, UsageMetricsCallback, dict[str, dict[str, str]]]:
        
        session = self.session_store.get_session(session_id=session_id, browser_id=browser_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with ID {session_id} not found for browser ID {browser_id}.",
            )
              
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

        return graph, usage_callback, config

    
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

    def _to_response(self, session_id: str, cypher_mode: SearchMode, result: CypherAgentState, usage_callback: UsageMetricsCallback) -> ChatResponse | PendingResumeResponse:
        
       
        if result.get("__interrupt__"):
            status = "awaiting_human_review"
            interrupts = result["__interrupt__"][0].value
            return PendingResumeResponse(
                session_id=session_id,
                status=status,
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
            usage=usage_callback.get_summary()
        )

    def run_db(
            self,
            session_id: str,
            browser_id: str,
            payload: DbSearchRequest
        ) -> ChatResponse | PendingResumeResponse:

        graph, usage_callback, config = self._build_agent_graph(session_id=session_id, browser_id=browser_id, chat_request=payload)

        result = graph.invoke(
            self._base_state(
                question=payload.question,
                execution_mode=payload.execution_mode,
                cypher_mode=SearchMode.DB_SEARCH,
            ),
            config=config
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
        return self._to_response(session_id, SearchMode.DB_SEARCH, result, usage_callback)
    
    def resume(
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


        graph, usage_callback, config = self._build_agent_graph(session_id=session_id, browser_id=browser_id, chat_request=payload, resume=True)

        result = graph.invoke(
            Command(resume=payload.model_dump(include={"action", "edited_cypher"})),
            config=config
        )

        self.session_store.mark_resume_pending(session_id=session_id, browser_id=browser_id, pending=False)

        return self._to_response(session_id, payload.search_mode, result, usage_callback)
    
    def run_vector(
            self,
            session_id: str,
            browser_id: str,
            payload: VectorSearchRequest
        ) -> ChatResponse | PendingResumeResponse:

        graph, usage_callback, config = self._build_agent_graph(session_id=session_id, browser_id=browser_id, chat_request=payload)

        result = graph.invoke(
            self._base_state(
                question=payload.question,
                execution_mode=payload.execution_mode,
                cypher_mode=SearchMode.VECTOR_SEARCH,
                vector_index=payload.vector_index,
            ),
            config=config
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
        return self._to_response(session_id, SearchMode.VECTOR_SEARCH, result, usage_callback)
    
    async def run_vector_upload(
            self, 
            session_id: str, 
            browser_id: str, 
            payload: UploadVectorSearchRequest, 
            embedding_file: UploadFile
        ) -> ChatResponse | PendingResumeResponse:

        guard = FileGuard(settings=self.settings, vector_index=payload.vector_index)
        embedding_array = await guard.load_embedding(embedding_file)

        graph, usage_callback, config = self._build_agent_graph(session_id=session_id, browser_id=browser_id, chat_request=payload)
        result = graph.invoke(
            self._base_state(
                question=payload.question,
                execution_mode=payload.execution_mode,
                cypher_mode=SearchMode.VECTOR_SEARCH,
                vector_index=payload.vector_index,
                embedding=embedding_array.tolist(),
            ),
            config=config
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
        return self._to_response(session_id, SearchMode.VECTOR_SEARCH, result, usage_callback)
        
        



        
