"""LangChain `@tool` wrappers around the PubTator3 client."""
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from crossbar_llm.pubtator3_tools import client as _client_mod
from crossbar_llm.pubtator3_tools.client import (
    EntityCandidate,
    PubTator3Document,
    RelatedEntity,
    SearchHit,
)


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

_RELATION_ALIASES = {
    "negatively_correlate": "negative_correlate",
    "positively_correlate": "positive_correlate",
}


class AutocompleteInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "Free-text biomedical entity name to resolve, e.g. 'JAK1', "
            "'metformin', 'Alzheimer disease'. Do NOT pass an already-resolved "
            "accession (a string starting with '@') — those are the OUTPUT of "
            "this tool, not the input."
        ),
    )
    concept: _CONCEPT_TYPES | None = Field(
        None,
        description=(
            "Optional biotype hint that narrows the candidate set: one of "
            "gene, chemical, disease, species, variant, cellline. Use this "
            "when the user's question makes the type unambiguous (e.g. "
            "'metformin' is clearly a chemical). Omit when uncertain."
        ),
    )
    limit: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum candidates to return (1–20). Default 5 is plenty for picking the top match.",
    )


class AutocompleteOutput(BaseModel):
    candidates: list[EntityCandidate] = []
    error: str | None = None


@tool("pubtator3_autocomplete", args_schema=AutocompleteInput)
async def pubtator3_autocomplete(
    query: str,
    concept: _CONCEPT_TYPES | None = None,
    limit: int = 5,
) -> AutocompleteOutput:
    """Resolve a free-text biomedical entity name to its PubTator3 accession.

    Wraps GET /entity/autocomplete/. Given a query such as "JAK1",
    "metformin", or "Alzheimer disease", returns ranked candidate
    entities — each carrying the PubTator3 accession (`@TYPE_Name`),
    the underlying database identifier and source (e.g. NCBI Gene ID,
    MeSH ID), the human-readable name, and the biotype.

    An empty candidates list means the entity is not in PubTator3's
    vocabulary. The tool never raises — transport / parse errors are
    captured in `output.error`.
    """
    try:
        candidates = await _client_mod.autocomplete(query, concept=concept, limit=limit)
        return AutocompleteOutput(candidates=candidates)
    except Exception as e:
        return AutocompleteOutput(error=f"{type(e).__name__}: {e}")


class FindPartnersInput(BaseModel):
    e1_accession: str = Field(
        ...,
        description=(
            "PubTator3 accession of the known entity, e.g. '@GENE_JAK1', "
            "'@DISEASE_Alzheimer_Disease'. Must start with '@'. Get this "
            "from `pubtator3_autocomplete` first if you only have free text."
        ),
    )
    relation: _RELATION_TYPES = Field(
        ...,
        description=(
            "PubTator3 relation type. Pick the value whose semantics match the user's verb:\n"
            "- treat                : a chemical/drug treats a disease.\n"
            "- cause                : positive correlation; chemical-induced diseases and variant-caused genetic diseases.\n"
            "- associate            : generic association with no specific direction.\n"
            "- prevent              : negative correlation; includes variant-disease.\n"
            "- positive_correlate   : same-direction co-movement; chemical-gene, co-expression.\n"
            "- negative_correlate   : opposite-direction co-movement; chemical-gene, co-expression.\n"
            "- compare              : comparing the effect of two chemicals/drugs.\n"
            "- cotreat              : two or more chemicals/drugs administered together.\n"
            "- inhibit              : negative correlation; disease-gene, chemical-variant.\n"
            "- stimulate            : positive correlation; disease-gene, disease-variant.\n"
            "- interact             : physical interaction (e.g. protein binding); gene-gene, gene-chemical, chemical-variant.\n"
            "- drug_interact        : pharmacodynamic interaction between two chemicals producing side effects."
        ),
    )
    e2_type: _ENTITY_TYPES = Field(
        ...,
        description=(
            "Type of partner to discover. PubTator3 only annotates these six "
            "entity types, each grounded in a specific terminology:\n"
            "- Gene                 : NCBI Gene IDs.\n"
            "- Disease              : MeSH (Medical Subject Headings).\n"
            "- Chemical             : MeSH (Medical Subject Headings).\n"
            "- Variant              : dbSNP IDs when available, otherwise HGVS format.\n"
            "- Species              : NCBI Taxonomy IDs.\n"
            "- CellLine             : Cellosaurus IDs.\n"
            "Note the capital-cased values — they differ from the lowercase "
            "`concept` used by autocomplete."
        ),
    )


class FindPartnersOutput(BaseModel):
    partners: list[RelatedEntity] = []
    error: str | None = None


@tool("pubtator3_find_partners", args_schema=FindPartnersInput)
async def pubtator3_find_partners(
    e1_accession: str,
    relation: _RELATION_TYPES,
    e2_type: _ENTITY_TYPES,
) -> FindPartnersOutput:
    """Discover partner entities related to a known entity by a specific relation.

    Wraps GET /relations. Given a known entity accession (e.g.
    `@GENE_JAK1`), a relation type from the PubTator3 vocabulary, and
    a target partner type, returns ranked `RelatedEntity` rows — each
    with source, target, relation type, and the number of supporting
    publications — sorted descending by publication count.

    This endpoint reveals WHICH partners exist; article PMIDs come
    from `pubtator3_search_articles` with a
    `relations:<rel>|<source>|<target>` expression. The tool never
    raises — errors are captured in `output.error`.
    """
    if relation in _RELATION_ALIASES:
        relation = _RELATION_ALIASES[relation]
    try:
        partners = await _client_mod.find_related(
            e1_accession, relation=relation, e2_type=e2_type
        )
        return FindPartnersOutput(partners=partners)
    except Exception as e:
        return FindPartnersOutput(error=f"{type(e).__name__}: {e}")


class SearchArticlesInput(BaseModel):
    text_query: str = Field(
        ...,
        description=(
            "PubTator3 search expression. Three valid forms:\n"
            "  1. Relation: 'relations:<rel>|<source>|<target>' — e.g.\n"
            "     'relations:treat|@CHEMICAL_Metformin|@DISEASE_Diabetes_Mellitus_Type_2'.\n"
            "  2. Boolean entity: '@GENE_JAK1 AND @CHEMICAL_ruxolitinib' — uses\n"
            "     resolved accessions joined by AND/OR.\n"
            "  3. Keyword: 'metformin liver toxicity' — free text fallback.\n"
            "Prefer forms 1 and 2 when possible; they're more precise."
        ),
    )
    page: int = Field(
        1,
        ge=1,
        description="1-indexed page number for paginated results.",
    )


class SearchArticlesOutput(BaseModel):
    hits: list[SearchHit] = []
    total: int = 0
    error: str | None = None


@tool("pubtator3_search_articles", args_schema=SearchArticlesInput)
async def pubtator3_search_articles(
    text_query: str,
    page: int = 1,
) -> SearchArticlesOutput:
    """Search PubTator3 for articles matching a query expression.

    Wraps GET /search/. Accepts three query forms:
      1. Relation expression `relations:<rel>|<source_accession>|<target_accession>`
         — restricts results to PMIDs in which BioREx extracted the relation.
      2. Boolean accession query `@GENE_JAK1 AND @CHEMICAL_ruxolitinib`
         — restricts results to PMIDs co-mentioning the entities.
      3. Free-text keyword query `metformin liver toxicity` — fallback
         when forms 1 and 2 do not apply.

    Returns ranked hits (PMID, title, journal, date, score, snippet)
    plus the total match count. The tool never raises — errors are
    captured in `output.error`.
    """
    try:
        hits, total = await _client_mod.search(text_query, page=page)
        return SearchArticlesOutput(hits=hits, total=total)
    except Exception as e:
        return SearchArticlesOutput(error=f"{type(e).__name__}: {e}")


class ExportPassagesInput(BaseModel):
    pmids: list[int] = Field(
        ...,
        min_length=1,
        max_length=500,
        description=(
            "PubMed IDs to fetch. Get these from `pubtator3_search_articles`. "
            "More than 100 PMIDs are auto-batched into multiple requests by "
            "the client (each request hits the API rate limit individually). "
            "Keep this list focused — passing 500 random PMIDs is wasteful."
        ),
    )
    full_text: bool = Field(
        True,
        description=(
            "When True, fetch full body text for PMC Open Access articles. "
            "When False, only title + abstract. Closed-access articles "
            "always return title + abstract regardless of this flag."
        ),
    )


class ExportPassagesOutput(BaseModel):
    documents: list[PubTator3Document] = []
    error: str | None = None


@tool("pubtator3_export_passages", args_schema=ExportPassagesInput)
async def pubtator3_export_passages(
    pmids: list[int],
    full_text: bool = True,
) -> ExportPassagesOutput:
    """Fetch BioC JSON passages and BioREx relations for a set of PMIDs.

    Wraps GET /publications/export/biocjson. Returns a list of
    `PubTator3Document` — each containing passages (title, abstract,
    full body sections when the article is PMC Open Access) with
    offset-anchored entity annotations, plus document-level BioREx
    relations carrying role accessions, database identifiers, and
    confidence scores.

    PMIDs are auto-batched in groups of 100 (the upstream cap); each
    batch counts against the 3 req/s rate limit. Up to 500 PMIDs per
    call. The tool never raises — errors are captured in `output.error`.
    """
    try:
        docs = await _client_mod.export_biocjson(pmids, full=full_text)
        return ExportPassagesOutput(documents=docs)
    except Exception as e:
        return ExportPassagesOutput(error=f"{type(e).__name__}: {e}")

