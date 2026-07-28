from functools import lru_cache

from crossbar_llm.api.services.agent_service import AgentService


@lru_cache()
def get_runtime_service() -> AgentService:
    return AgentService()
