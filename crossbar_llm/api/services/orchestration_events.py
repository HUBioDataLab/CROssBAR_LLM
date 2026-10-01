"""Progress events the orchestrator emits while it answers a question.

The streaming endpoints forward these to the browser as server-sent events so
the UI can show which agents are working; the plain JSON endpoints discard
them. Payloads are JSON-serialisable dicts.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]

ORCHESTRATION_STARTED = "orchestration.started"
RELEVANCE_REJECTED = "relevance.rejected"
ROUTING_COMPLETED = "routing.completed"
AGENT_STARTED = "agent.started"
AGENT_PROGRESS = "agent.progress"
AGENT_COMPLETED = "agent.completed"
REVIEW_REQUIRED = "review.required"
SYNTHESIS_STARTED = "synthesis.started"
SYNTHESIS_COMPLETED = "synthesis.completed"


async def discard_events(event: str, data: dict[str, Any]) -> None:
    return None
