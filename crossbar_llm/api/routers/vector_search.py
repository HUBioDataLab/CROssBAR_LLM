from fastapi import APIRouter, UploadFile, Request, Response, File, Depends

from crossbar_llm.api.services.agent_service import AgentService
from crossbar_llm.api.core.deps import get_runtime_service
from crossbar_llm.api.core.browser_identity import BrowserIdentity, get_or_create_browser_identity
from crossbar_llm.api.schemas.responses import ChatResponse, PendingResumeResponse
from crossbar_llm.api.schemas.requests import VectorSearchRequest, UploadVectorSearchRequest
from crossbar_llm.api.core.rate_limit import standard_rate_limits


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

    return agent_service.run_vector(session_id=session_id, browser_id=identity.browser_id, payload=payload)


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
