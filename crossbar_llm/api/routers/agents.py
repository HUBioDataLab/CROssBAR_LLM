from fastapi import APIRouter

from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.schemas.responses import AgentCatalogResponse
from crossbar_llm.api.services.agent_catalog import agent_catalog

router = APIRouter(
    prefix="/agents",
    tags=["agents"],
)

settings = Settings()


@router.get("", response_model=AgentCatalogResponse)
async def list_agents() -> AgentCatalogResponse:
    """The agents the orchestrator can route to, and whether each can run here.

    Deliberately independent of the runtime service: the UI needs this list
    to render its agent switches even while the knowledge graph is unreachable.
    """
    return agent_catalog(settings)
