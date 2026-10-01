"""The specialist agents the orchestrator can route a question to.

One entry per agent. The router reads `routing_profile` to decide who is worth
asking, the synthesizer cites each agent by its `tag`, and the `/agents`
endpoint serves `name`/`summary` to the UI — so adding an agent starts here.
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
    routing_profile: str
    supports_vector_search: bool = False


AGENT_SPECS: dict[AgentId, AgentSpec] = {
    AgentId.KNOWLEDGE_GRAPH: AgentSpec(
        id=AgentId.KNOWLEDGE_GRAPH,
        name="Knowledge Graph",
        tag="KG",
        kind="knowledge_graph",
        summary="Generates Cypher over the CROssBARv2 biomedical knowledge graph.",
        routing_profile=(
            "Queries the curated CROssBARv2 knowledge graph (Neo4j) by writing "
            "Cypher. Strong for structured facts recorded as relationships "
            "between genes, proteins, drugs, compounds, diseases, pathways, "
            "phenotypes, GO terms, protein domains, EC numbers and organisms: "
            "listing or counting associated entities, multi-hop paths, shortest "
            "paths, and embedding-based similarity search. Weak for mechanisms "
            "explained in prose, recent findings, clinical outcomes, or anything "
            "not stored as a graph edge."
        ),
        supports_vector_search=True,
    ),
    AgentId.PAPERCLIP: AgentSpec(
        id=AgentId.PAPERCLIP,
        name="Paperclip",
        tag="Paperclip",
        kind="literature",
        summary="Broad literature search with citable source links.",
        routing_profile=(
            "Searches a broad corpus of biomedical publications and answers from "
            "the retrieved papers, with citations. Strong for mechanisms, "
            "experimental evidence, recent research, clinical context and "
            "open-ended 'how' or 'why' questions. Weak for exhaustive "
            "enumeration or graph-style traversals."
        ),
    ),
    AgentId.PUBTATOR3: AgentSpec(
        id=AgentId.PUBTATOR3,
        name="PubTator3",
        tag="PubTator3",
        kind="literature",
        summary="NCBI entity- and relation-aware publication evidence.",
        routing_profile=(
            "Searches PubMed through NCBI PubTator3, which annotates genes, "
            "diseases, chemicals, variants and species, and the relations "
            "between them (treats, causes, interacts with, ...). Strong for "
            "literature-backed relationships between specific named entities, "
            "with PMIDs. Weak for questions that name no concrete entity."
        ),
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
    """Map an id, tag or display name the LLM wrote back to an agent id."""
    return _TAG_LOOKUP.get(reference.strip().strip("[]").lower())


__all__ = [
    "AGENT_SPECS",
    "LITERATURE_AGENTS",
    "AgentId",
    "AgentKind",
    "AgentSpec",
    "resolve_agent",
]
