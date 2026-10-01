from fastapi import APIRouter, UploadFile, Request, Response, File, Depends
from fastapi.responses import StreamingResponse

from crossbar_llm.api.services.agent_service import AgentService
from crossbar_llm.api.core.deps import get_runtime_service
from crossbar_llm.api.core.browser_identity import BrowserIdentity, get_or_create_browser_identity
from crossbar_llm.api.schemas.responses import ChatResponse, PendingResumeResponse
from crossbar_llm.api.schemas.requests import VectorSearchRequest, UploadVectorSearchRequest
from crossbar_llm.api.core.rate_limit import standard_rate_limits
from crossbar_llm.api.routers.streaming import stream_orchestration


router = APIRouter(
    prefix="/sessions/{session_id}/vector-search",
    tags=["vector-search"],
)


@router.post("/query", response_model=ChatResponse | PendingResumeResponse)
@standard_rate_limits
async def vector_query(
    request: Request,
    response: Response,
    session_id: str,
    payload: VectorSearchRequest,
    identity: BrowserIdentity = Depends(get_or_create_browser_identity),
    agent_service: AgentService = Depends(get_runtime_service)
    ):

    return await agent_service.run_vector(session_id=session_id, browser_id=identity.browser_id, payload=payload)


@router.post("/query/stream", response_class=StreamingResponse)
@standard_rate_limits
async def vector_query_stream(
    request: Request,
    response: Response,
    session_id: str,
    payload: VectorSearchRequest,
    identity: BrowserIdentity = Depends(get_or_create_browser_identity),
    agent_service: AgentService = Depends(get_runtime_service)
    ):
    """`/query` as server-sent events: orchestration progress, then the result."""
    agent_service.require_session(session_id, identity.browser_id)
    return stream_orchestration(
        lambda emit: agent_service.run_vector(
            session_id=session_id, browser_id=identity.browser_id, payload=payload, emit=emit
        ),
        keepalive_seconds=agent_service.settings.sse_keepalive_seconds,
    )


@router.post("/upload-query", response_model=ChatResponse | PendingResumeResponse)
@standard_rate_limits
async def vector_upload_query(
    request: Request,
    response: Response,
    session_id: str,
    payload: UploadVectorSearchRequest = Depends(UploadVectorSearchRequest.as_form),
    embedding_file: UploadFile = File(...),
    identity: BrowserIdentity = Depends(get_or_create_browser_identity),
    agent_service: AgentService = Depends(get_runtime_service)
    ):

    return await agent_service.run_vector_upload(session_id=session_id, browser_id=identity.browser_id, payload=payload, embedding_file=embedding_file)


@router.post("/upload-query/stream", response_class=StreamingResponse)
@standard_rate_limits
async def vector_upload_query_stream(
    request: Request,
    response: Response,
    session_id: str,
    payload: UploadVectorSearchRequest = Depends(UploadVectorSearchRequest.as_form),
    embedding_file: UploadFile = File(...),
    identity: BrowserIdentity = Depends(get_or_create_browser_identity),
    agent_service: AgentService = Depends(get_runtime_service)
    ):
    """`/upload-query` as server-sent events: orchestration progress, then the result."""
    agent_service.require_session(session_id, identity.browser_id)
    # Read before the stream opens: the upload may be closed once it has.
    embedding = await agent_service.load_embedding(payload, embedding_file)
    return stream_orchestration(
        lambda emit: agent_service.run_vector_embedding(
            session_id, identity.browser_id, payload, embedding, emit
        ),
        keepalive_seconds=agent_service.settings.sse_keepalive_seconds,
    )
