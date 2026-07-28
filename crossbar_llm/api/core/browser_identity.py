from secrets import token_urlsafe
from pydantic import BaseModel, ConfigDict
from itsdangerous import URLSafeSerializer, BadSignature

from fastapi import Request, Response, HTTPException, status

from crossbar_llm.api.core.settings import Settings


class BrowserIdentity(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )
    browser_id: str
    is_new: bool


def _get_serializer() -> URLSafeSerializer:
    settings = Settings()
    return URLSafeSerializer(
        settings.env_settings.browser_cookie_secret.get_secret_value().encode("utf-8"),
        salt="browser-id"
    )

def _sign_browser_id(browser_id: str) -> str:
    serializer = _get_serializer()
    return serializer.dumps({"browser_id": browser_id})

def _load_browser_id(signed_value: str) -> str:
    serializer = _get_serializer()
    try:
        data = serializer.loads(signed_value)
    except BadSignature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid browser identity cookie."
        )
    
    browser_id = data.get("browser_id")
    if not isinstance(browser_id, str) or not browser_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid browser identity cookie payload."
        )
    
    return browser_id


def get_or_create_browser_identity(
        request: Request,
    ) -> BrowserIdentity:
    
    settings = Settings()
    cookie_name = settings.browser_cookie_name

    signed_cookie = request.cookies.get(cookie_name)
    if signed_cookie:
        existing_browser_id = _load_browser_id(signed_cookie)
        return BrowserIdentity(browser_id=existing_browser_id, is_new=False)
    
    return BrowserIdentity(browser_id=token_urlsafe(32), is_new=True)


def set_browser_cookie(response: Response, browser_id: str) -> None:
    settings = Settings()
    signed_value = _sign_browser_id(browser_id)

    response.set_cookie(
        key=settings.browser_cookie_name,
        value=signed_value,
        max_age=settings.browser_cookie_max_age_seconds,
        secure=settings.browser_cookie_secure,
        samesite=settings.browser_cookie_samesite,
        httponly=True,
        path="/"
    )
