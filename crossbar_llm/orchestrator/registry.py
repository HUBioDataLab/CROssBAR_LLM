"""The specialist agents users can select for a question.

One entry per agent. The synthesizer cites each agent by its `tag`, and the
`/agents` endpoint serves `name`/`summary` to the UI, so adding an agent starts
here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class AgentId(StrEnum):
    KNOWLEDGE_GRAPH = "knowledge_graph"
    PAPERCLIP = "paperclip"
    PUBTATOR3 = "pubtator3"


AgentKind = Literal["knowledge_graph", "literature"]


@dataclass(frozen=True)
class AgentSpec:
    id: AgentId
    name: str
    tag: str
    kind: AgentKind
    summary: str
    supports_vector_search: bool = False


AGENT_SPECS: dict[AgentId, AgentSpec] = {
    AgentId.KNOWLEDGE_GRAPH: AgentSpec(
        id=AgentId.KNOWLEDGE_GRAPH,
        name="Knowledge Graph",
        tag="KG",
        kind="knowledge_graph",
        summary="Generates Cypher over the CROssBARv2 biomedical knowledge graph.",
        supports_vector_search=True,
    ),
    AgentId.PAPERCLIP: AgentSpec(
        id=AgentId.PAPERCLIP,
        name="Paperclip",
        tag="Paperclip",
        kind="literature",
        summary="Broad literature search with citable source links.",
    ),
    AgentId.PUBTATOR3: AgentSpec(
        id=AgentId.PUBTATOR3,
        name="PubTator3",
        tag="PubTator3",
        kind="literature",
        summary="NCBI entity- and relation-aware publication evidence.",
    ),
}

LITERATURE_AGENTS: tuple[AgentId, ...] = tuple(
    agent_id for agent_id, spec in AGENT_SPECS.items() if spec.kind == "literature"
)

_TAG_LOOKUP: dict[str, AgentId] = {
    alias.lower(): agent_id
    for agent_id, spec in AGENT_SPECS.items()
    for alias in (agent_id.value, spec.tag, spec.name)
}


def resolve_agent(reference: str) -> AgentId | None:
    """Map an agent id, source tag, or display name to its canonical id."""
    return _TAG_LOOKUP.get(reference.strip().strip("[]").lower())


__all__ = [
    "AGENT_SPECS",
    "LITERATURE_AGENTS",
    "AgentId",
    "AgentKind",
    "AgentSpec",
    "resolve_agent",
]
