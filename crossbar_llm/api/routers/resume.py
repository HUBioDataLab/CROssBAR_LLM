from fastapi import APIRouter, Request, Response, Depends

from crossbar_llm.api.services.agent_service import AgentService
from crossbar_llm.api.core.deps import get_runtime_service
from crossbar_llm.api.core.browser_identity import BrowserIdentity, get_or_create_browser_identity
from crossbar_llm.api.schemas.requests import ResumeRequest
from crossbar_llm.api.schemas.responses import ChatResponse
from crossbar_llm.api.core.rate_limit import standard_rate_limits

router = APIRouter(
    prefix="/sessions/{session_id}/resume",
    tags=["resume"],
)

@router.post("", response_model=ChatResponse)
@standard_rate_limits
async def resume_session(
    request: Request,
    response: Response,
    session_id: str,
    payload: ResumeRequest,
    identity: BrowserIdentity = Depends(get_or_create_browser_identity),
    agent_service: AgentService = Depends(get_runtime_service)
    ):

    return agent_service.resume(session_id=session_id, browser_id=identity.browser_id, payload=payload)
