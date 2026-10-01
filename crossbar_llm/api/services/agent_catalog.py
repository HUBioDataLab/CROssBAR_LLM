"""Which agents this server can run, for the router and for the UI."""
from __future__ import annotations

import os

from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.schemas.responses import AgentCatalogResponse, AgentInfo
from crossbar_llm.orchestrator.registry import AGENT_SPECS, AgentId
from crossbar_llm.paperclip_tools.adapter import API_KEY_ENV as PAPERCLIP_API_KEY_ENV


def _paperclip_configured(settings: Settings) -> bool:
    configured = settings.env_settings.paperclip_api_key
    if configured is not None and configured.get_secret_value().strip():
        return True
    # The adapter falls back to the process environment, so honour it here too.
    return bool(os.environ.get(PAPERCLIP_API_KEY_ENV, "").strip())


def unavailable_reasons(settings: Settings) -> dict[AgentId, str]:
    """Agents that cannot run on this server, and why. Absent means available."""
    reasons: dict[AgentId, str] = {}
    if not _paperclip_configured(settings):
        reasons[AgentId.PAPERCLIP] = (
            "Paperclip is not configured on this server (no API key)."
        )
    return reasons


def agent_catalog(settings: Settings) -> AgentCatalogResponse:
    reasons = unavailable_reasons(settings)
    return AgentCatalogResponse(
        agents=[
            AgentInfo(
                id=spec.id,
                name=spec.name,
                kind=spec.kind,
                summary=spec.summary,
                available=spec.id not in reasons,
                unavailable_reason=reasons.get(spec.id),
                supports_vector_search=spec.supports_vector_search,
            )
            for spec in AGENT_SPECS.values()
        ]
    )
