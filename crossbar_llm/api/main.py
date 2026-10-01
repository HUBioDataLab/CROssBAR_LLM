from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from crossbar_llm.api.core.rate_limit import limiter
from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.routers.session import router as session_router
from crossbar_llm.api.routers.health import router as health_router
from crossbar_llm.api.routers.db_search import router as db_search_router
from crossbar_llm.api.routers.resume import router as resume_router
from crossbar_llm.api.routers.vector_search import router as vector_search_router
from crossbar_llm.api.routers.models import router as models_router
from crossbar_llm.api.core.deps import get_runtime_service

settings = Settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    # Only close a service that was actually built. `get_runtime_service` is
    # lru_cached, so calling it unconditionally here would CONSTRUCT one at
    # shutdown — Neo4j config and all — in any process that never served a
    # request, purely to close nothing, and would fail the shutdown outright
    # where that config is absent.
    if get_runtime_service.cache_info().currsize:
        await get_runtime_service().aclose()
        get_runtime_service.cache_clear()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# In development the React dev server (localhost:3000) talks to the API (localhost:8000)
# cross-origin with credentials, so it needs an explicit CORS allow-list.
if settings.is_dev:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=settings.allowed_credentials,
        allow_methods=settings.allowed_methods,
        allow_headers=settings.allowed_headers,
    )


app.include_router(
    health_router
)

app.include_router(
    session_router
)


app.include_router(
    db_search_router
)

app.include_router(
    resume_router
)

app.include_router(
    vector_search_router
)

app.include_router(
    models_router
)

