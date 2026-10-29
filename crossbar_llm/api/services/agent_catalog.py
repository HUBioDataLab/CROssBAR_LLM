"""Which agents this server can run, for the router and for the UI."""
from __future__ import annotations

import os

from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.schemas.requests import ModelConfigRequest
from crossbar_llm.api.schemas.responses import AgentCatalogResponse, AgentInfo
from crossbar_llm.orchestrator.registry import AGENT_SPECS, AgentId
from crossbar_llm.paperclip_tools.adapter import API_KEY_ENV as PAPERCLIP_API_KEY_ENV

PAPERCLIP_USER_KEY_REASON = "Enter your Paperclip API key to use this agent."


def server_paperclip_key(settings: Settings) -> str | None:
    """The server's own Paperclip key, or None when users must bring theirs.

    Production never spends the server's key: every user supplies their own,
    so one account's quota is not shared by everyone who opens the site.
    """
    if settings.env_settings.app_env == "production":
        return None
    configured = settings.env_settings.paperclip_api_key
    if configured is not None and configured.get_secret_value().strip():
        return configured.get_secret_value()
    # The adapter falls back to the process environment, so honour it here too.
    return os.environ.get(PAPERCLIP_API_KEY_ENV, "").strip() or None


def user_paperclip_key(payload: ModelConfigRequest | None) -> str | None:
    key = payload.paperclip_api_key if payload is not None else None
    return key.get_secret_value() if key is not None else None


def unavailable_reasons(
    settings: Settings, payload: ModelConfigRequest | None = None
) -> dict[AgentId, str]:
    """Agents that cannot run on this server, and why. Absent means available.

    With a `payload`, a key the user sent with the request counts too.
    """
    reasons: dict[AgentId, str] = {}
    if server_paperclip_key(settings) is None and user_paperclip_key(payload) is None:
        reasons[AgentId.PAPERCLIP] = PAPERCLIP_USER_KEY_REASON
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
                # Paperclip is the only agent a user's own key can unlock.
                requires_user_key=(
                    spec.id == AgentId.PAPERCLIP and spec.id in reasons
                ),
            )
            for spec in AGENT_SPECS.values()
        ]
    )
