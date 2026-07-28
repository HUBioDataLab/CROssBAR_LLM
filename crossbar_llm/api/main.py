from fastapi import FastAPI

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from crossbar_llm.api.core.rate_limit import limiter
from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.routers.session import router as session_router
from crossbar_llm.api.routers.health import router as health_router
from crossbar_llm.api.routers.db_search import router as db_search_router
from crossbar_llm.api.routers.resume import router as resume_router
from crossbar_llm.api.routers.vector_search import router as vector_search_router

from crossbar_llm.agent_tools.logging_config import disable_logging

disable_logging()


settings = Settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


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



