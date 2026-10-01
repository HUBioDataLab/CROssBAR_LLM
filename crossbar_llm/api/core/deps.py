from functools import lru_cache

from fastapi import HTTPException, status
from pydantic import ValidationError

from crossbar_llm.agent_tools.logging_config import get_logger
from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.services.agent_service import AgentService

logger = get_logger(__name__)


@lru_cache()
def get_runtime_service() -> AgentService:
    try:
        return AgentService()
    except ValidationError as exc:
        missing_fields = sorted({
            str(error["loc"][-1])
            for error in exc.errors()
            if error.get("type") == "missing" and error.get("loc")
        })

        # Always logged in full — the operator fixing this needs the list.
        logger.error(
            "Runtime service could not be configured",
            event_type="runtime_service_misconfigured",
            component="deps.get_runtime_service",
            missing_fields=missing_fields,
            exc_info=exc,
        )

        # Only echoed to the client in development. The names alone leak no
        # secrets, but on a public deployment they confirm the backend stack to
        # anyone who happens to hit the API while it is misconfigured, and the
        # sentence below already tells a user everything they can act on.
        settings = Settings()
        missing_hint = (
            f" Missing environment variables: {', '.join(missing_fields)}."
            if missing_fields and settings.is_dev
            else ""
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The knowledge-graph backend is not configured, so chat and "
                f"vector queries cannot run.{missing_hint}"
            ),
        ) from exc
