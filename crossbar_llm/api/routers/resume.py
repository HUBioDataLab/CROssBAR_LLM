from fastapi import APIRouter, Request, Response, Depends
from fastapi.responses import StreamingResponse

from crossbar_llm.api.services.agent_service import AgentService
from crossbar_llm.api.core.deps import get_runtime_service
from crossbar_llm.api.core.browser_identity import BrowserIdentity, get_or_create_browser_identity
from crossbar_llm.api.schemas.requests import ResumeRequest
from crossbar_llm.api.schemas.responses import ChatResponse, PendingResumeResponse
from crossbar_llm.api.core.rate_limit import standard_rate_limits
from crossbar_llm.api.routers.streaming import stream_orchestration

router = APIRouter(
    prefix="/sessions/{session_id}/resume",
    tags=["resume"],
)

# A resume can pause for review again (an approved query that fails is retried
# and re-reviewed), so it returns either shape.
@router.post("", response_model=ChatResponse | PendingResumeResponse)
@standard_rate_limits
async def resume_session(
    request: Request,
    response: Response,
    session_id: str,
    payload: ResumeRequest,
    identity: BrowserIdentity = Depends(get_or_create_browser_identity),
    agent_service: AgentService = Depends(get_runtime_service)
    ):

    return await agent_service.resume(session_id=session_id, browser_id=identity.browser_id, payload=payload)


@router.post("/stream", response_class=StreamingResponse)
@standard_rate_limits
async def resume_session_stream(
    request: Request,
    response: Response,
    session_id: str,
    payload: ResumeRequest,
    identity: BrowserIdentity = Depends(get_or_create_browser_identity),
    agent_service: AgentService = Depends(get_runtime_service)
    ):
    """The resume as server-sent events: orchestration progress, then the result."""
    agent_service.require_session(session_id, identity.browser_id)
    return stream_orchestration(
        lambda emit: agent_service.resume(
            session_id=session_id, browser_id=identity.browser_id, payload=payload, emit=emit
        ),
        keepalive_seconds=agent_service.settings.sse_keepalive_seconds,
    )
