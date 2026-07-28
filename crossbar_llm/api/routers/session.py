from fastapi import APIRouter, status, Request, Response, HTTPException, Depends

from crossbar_llm.api.services.session_store import SessionStore
from crossbar_llm.api.schemas.responses import SessionCreateResponse
from crossbar_llm.api.services.session_store import session_store, SessionLimitExceededError, SessionNotFoundError
from crossbar_llm.api.core.browser_identity import (
    BrowserIdentity,
    get_or_create_browser_identity,
    set_browser_cookie
)

from crossbar_llm.api.core.rate_limit import limiter

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
)

@router.post("", response_model=SessionCreateResponse)
@limiter.limit("7/hour")
async def create_session(
    request: Request,
    response: Response,
    identity: BrowserIdentity = Depends(get_or_create_browser_identity),
    store: SessionStore = Depends(session_store)
    ) -> SessionCreateResponse:

    try:
        session = store.create_session(browser_id=identity.browser_id)
    except SessionLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session limit exceeded. Maximum allowed sessions per user is {exc.limit}.",
        )
    
    if identity.is_new:
        set_browser_cookie(response, identity.browser_id)
    
    return SessionCreateResponse(session_id=session.session_id)

@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("15/hour")
async def delete_session(
    request: Request,
    response: Response,
    session_id: str,
    identity: BrowserIdentity = Depends(get_or_create_browser_identity),
    store: SessionStore = Depends(session_store)
    ) -> None:

    try:
        store.delete_session(session_id=session_id, browser_id=identity.browser_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
