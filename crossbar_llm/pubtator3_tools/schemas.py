"""Pydantic schemas and shared type aliases for the PubTator3 LangGraph.

Kept separate from the orchestration in `pubtator3_graph.py` so other
modules (benchmark runner, tools, future API layer) can import the
schemas without dragging the graph builder + its LangChain deps along.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Literal, TypeVar, TypedDict

from pydantic import BaseModel, Field

from crossbar_llm.pubtator3_tools.client import (
    DocumentRelation,
    EntityCandidate,
    Passage,
    PubTator3Document,
    RelatedEntity,
)


QuestionType = Literal[
    "single_node",
    "relation_known_pair",
    "relation_partner_discovery",
    "keyword_search",
    "out_of_scope",
]

_RELATION_TYPES = Literal[
    "treat",
    "cause",
    "associate",
    "prevent",
    "positive_correlate",
    "negative_correlate",
    "compare",
    "cotreat",
    "inhibit",
    "stimulate",
    "interact",
    "drug_interact",
]

_ENTITY_TYPES = Literal[
    "Gene",
    "Chemical",
    "Disease",
    "Species",
    "Variant",
    "CellLine",
]

_CONCEPT_TYPES = Literal[
    "gene",
    "chemical",
    "disease",
    "species",
    "variant",
    "cellline",
]

# PubTator3 BioC `section_type` values for full-text body sections.
# Title + abstract are kept implicitly and are not selectable here.
_SECTION_TYPES = Literal[
    "INTRO",
    "METHODS",
    "RESULTS",
    "DISCUSS",
    "CONCL",
    "FIG",
    "TABLE",
    "CASE",
]

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class EntityMention(BaseModel):
    text: str = Field(
        ...,
        description=(
            "Entity query text to send to PubTator3 autocomplete, e.g. 'JAK1'. "
            "Prefer the surface form from the user's question, but canonical "
            "normalization is allowed when it refers to the same explicitly "
            "mentioned entity (for example, use 'BTK' for \"Bruton's tyrosine "
            "kinase\"). Do NOT invent new entity names from training knowledge."
        ),
    )
    suggested_type: _CONCEPT_TYPES | None = Field(
        None,
        description=(
            "Biotype hint to narrow PubTator3 autocomplete (lowercase: gene, "
            "chemical, disease, species, variant, cellline). SET THIS whenever "
            "the type is clear from context — gene symbols / kinases / "
            "receptors -> 'gene'; drug or compound names -> 'chemical'; "
            "disease or syndrome names -> 'disease'. Leaving this null lets "
            "autocomplete pick the wrong entity type (e.g. resolving a kinase "
            "name to a disease that shares the surface form)."
        ),
    )
    role: Literal["e1", "e2"] | None = Field(
        None,
        description=(
            "For relation_known_pair, marks which side of the relation. "
            "e1 is the actor / subject (e.g. 'metformin' in 'metformin treats T2D'); "
            "e2 is the object / partner. Leave None for single_node and partner_discovery."
        ),
    )


class RouterDecision(BaseModel):
    question_type: QuestionType = Field(
        ...,
        description=(
            "single_node: question is about ONE biomedical entity, no relation.\n"
            "relation_known_pair: user asks about a SPECIFIC pair plus a relation.\n"
            "relation_partner_discovery: user asks for partners of one entity by relation.\n"
            "keyword_search: biomedical question whose answer likely exists in the "
            "literature but does not fit the structured forms above — e.g. side "
            "effects, adverse events, mechanism of action, pharmacokinetics, "
            "off-label use, pathway / ortholog / GO questions. PubTator3 has no "
            "dedicated entity types for these but PubMed/PMC do contain the text. "
            "Free-text /search/ will surface relevant papers. Set `keyword_query`.\n"
            "out_of_scope: PubTator3 cannot help at all — non-biomedical questions, "
            "pure graph-traversal output requests (shortest path, etc.), math, "
            "opinion, news, weather."
        ),
    )
    mentions: list[EntityMention] = Field(
        default_factory=list,
        description=(
            "Biomedical entity mentions. Order matters for relation_known_pair: "
            "[e1 first, e2 second]. For partner discovery: [anchor only]. "
            "For single_node: [the one entity]. For keyword_search and "
            "out_of_scope: may be empty."
        ),
    )
    relation: _RELATION_TYPES | None = Field(
        None,
        description="Relation type (PubTator3 vocabulary). Required for relation_* types.",
    )
    e2_type: _ENTITY_TYPES | None = Field(
        None,
        description=(
            "Required ONLY for relation_partner_discovery — the type of partner to find. "
            "Capitalized: Gene/Chemical/Disease/Species/Variant/CellLine."
        ),
    )
    keyword_query: str | None = Field(
        None,
        description=(
            "Focused free-text PubMed query distilled from the user's "
            "question, e.g. 'imatinib side effects', 'BTK inhibitor CLL', "
            "'Denosumab RANKL', 'metformin pharmacokinetics'. Prefer 2–6 "
            "keywords that maximise recall on the topic; do not paste the "
            "whole sentence.\n\n"
            "Fill this for ALL in-scope routes:\n"
            "- keyword_search: it is the primary query the pipeline runs.\n"
            "- single_node, relation_known_pair, relation_partner_discovery:"
            " it is the FALLBACK query the pipeline runs ONLY when the "
            "structured PubTator3 search returns 0 PMIDs (which happens "
            "often because BioREx didn't tag the exact relation, or the "
            "entity pair isn't co-mentioned in PubTator3's graph even when "
            "PubMed/PMC clearly discusses it).\n\n"
            "Leave null only for out_of_scope."
        ),
    )
    full_text: bool = Field(
        False,
        description=(
            "Whether the downstream pipeline should fetch full paper body "
            "text (True) or only titles + abstracts (False). DEFAULT IS "
            "FALSE — abstracts are sufficient for almost every question. "
            "Set True ONLY when the user explicitly asks for the full "
            "paper, body text, methods / results sections, or detailed "
            "paragraph-level content beyond the abstract."
        ),
    )
    sections: list[_SECTION_TYPES] | None = Field(
        None,
        description=(
            "OPTIONAL body-section filter applied ONLY when full_text=True. "
            "When non-empty, the downstream pipeline keeps title + abstract "
            "(always) plus body passages whose section_type is in this list "
            "— everything else is dropped before synthesis to save tokens. "
            "Pick this when the user's question targets one part of the "
            "paper: methods/protocol/assay questions -> ['METHODS']; "
            "results/findings/data questions -> ['RESULTS']; "
            "mechanism/interpretation questions -> ['DISCUSS']; "
            "case-report questions -> ['CASE']. Leave None when the user "
            "wants the whole body or full_text=False. This field has NO "
            "effect when full_text=False — never set it as a substitute "
            "for asking for full text."
        ),
    )
    rationale: str = Field("", description="One-sentence justification for the classification.")


class DepthEvaluation(BaseModel):
    sufficient: bool = Field(
        ...,
        description=(
            "True if the answer is scientifically substantive given the "
            "user's question — names specific entities, describes mechanisms "
            "or modes of action, references concrete findings rather than "
            "vague associations. False if the answer reads like a question "
            "restatement with PMIDs attached but no real biology."
        ),
    )
    missing: str | None = Field(
        None,
        description=(
            "If sufficient=False, a single short note on what's missing — "
            "e.g. 'no mechanism described', 'no quantitative results', "
            "'lists entities without specifying their roles'. Null when "
            "sufficient=True."
        ),
    )
    suggested_sections: list[_SECTION_TYPES] | None = Field(
        None,
        description=(
            "When sufficient=False AND full_text is already True, OPTIONALLY "
            "name body sections that should be added on the refinement pass "
            "to fill the gap. Examples: gap='no mechanism described' "
            "-> ['DISCUSS', 'RESULTS']; gap='no protocol detail' "
            "-> ['METHODS']; gap='no quantitative numbers' "
            "-> ['RESULTS', 'TABLE']. The pipeline UNIONS these with the "
            "sections already pulled — do not re-list ones that are "
            "already in `current_sections`. Leave None to fall back to "
            "'pull every body section' (the safe default escalation). "
            "Has no effect when sufficient=True or when full_text=False."
        ),
    )
    rationale: str = Field("", description="One-sentence justification for the verdict.")


class PubTator3State(TypedDict, total=False):
    question: str

    question_type: QuestionType
    mentions: list[EntityMention]
    relation: str | None
    e2_type: str | None
    keyword_query: str | None
    full_text: bool
    sections: list[str] | None
    rationale: str

    resolved: dict[str, EntityCandidate]
    unresolved: list[str]

    partners: list[RelatedEntity]
    queries_used: list[str]
    pmids: list[int]
    total_articles: int

    documents: list[PubTator3Document]
    passages: list[Passage]
    document_relations: list[DocumentRelation]
    final_answer: str | None

    depth_sufficient: bool
    depth_missing: str | None
    depth_skip_reason: str | None
    refinement_attempted: bool

    warnings: list[str]


RouterFn = Callable[[str], Awaitable[RouterDecision]]
SynthesizerFn = Callable[[PubTator3State], Awaitable[str]]
EvaluatorFn = Callable[[PubTator3State], Awaitable[DepthEvaluation]]


__all__ = [
    "QuestionType",
    "StructuredModel",
    "EntityMention",
    "RouterDecision",
    "DepthEvaluation",
    "PubTator3State",
    "RouterFn",
    "SynthesizerFn",
    "EvaluatorFn",
]
