"""Pydantic schemas + graph state for the Paperclip LangGraph.

Kept separate from `schemas.py` (which is PubTator3-specific and imports the
PubTator3 client models) so the Paperclip module stays self-contained. The two
tools deliberately have different internals but the SAME external contract —
`question (+ state) in -> {final_answer, citations, warnings, usage} out` — so
the future top-level graph can dispatch to either interchangeably.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Literal, TypedDict

from pydantic import BaseModel, Field

from crossbar_llm.paperclip_tools.adapter import (
    PaperHit,
    PaperMeta,
    PaperclipSectionName,
)


PaperclipQuestionType = Literal[
    "keyword_search",
    "list_breadth",
    "full_text_depth",
    "sql_aggregate",
    "analogical_search",
    "out_of_scope",
]

# Mirror of `PaperclipSource` but spelled out here so the router LLM schema is
# self-documenting. Unlike the MCP text-parsing path (which requires an
# explicit `-s`), the REST path supports a genuine unscoped/broad search —
# so `source=None` is now a valid, in fact the DEFAULT, choice (see
# `PaperclipRouterDecision.source`).
PaperclipSourceChoice = Literal[
    "pmc",
    "biorxiv",
    "medrxiv",
    "arxiv",
    "fda",
    "trials",
    "proteins",
    "pdb",
    "chembl",
]


class PaperclipRouterDecision(BaseModel):
    question_type: PaperclipQuestionType = Field(
        ...,
        description=(
            "keyword_search: general biomedical literature question answered by "
            "retrieving a handful of relevant papers (the default, and Paperclip's "
            "core strength).\n"
            "list_breadth: 'list all / enumerate / which drugs/genes/trials ...' "
            "questions that want broad coverage; the pipeline widens the result "
            "limit.\n"
            "full_text_depth: the user explicitly wants mechanisms, methods, "
            "results, protocols, or paragraph-level detail beyond abstracts; the "
            "pipeline fetches full paper body text.\n"
            "sql_aggregate: the question asks for a COUNT, RANKING, or aggregate "
            "ACROSS MANY PAPERS, over their bibliographic metadata (how many "
            "papers/by year/by journal/by source/by author) — answered with a "
            "direct SQL query instead of retrieval+synthesis. Fill `sql_query`. "
            "Two hard exclusions:\n"
            "  (a) NOT 'how many papers discuss/mention/are about X' — that needs "
            "free-text/semantic matching over abstracts, which this route cannot "
            "safely do (see `sql_query`'s description); use keyword_search/"
            "list_breadth.\n"
            "  (b) NOT a lookup of PROPERTIES OF ONE NAMED RECORD — a protein's "
            "sequence length, a PDB accession, a drug's approval status or label "
            "warnings, a trial's enrollment or phase. Nothing is being aggregated "
            "there, and the ONLY SQL table is `documents` (papers): it holds no "
            "protein, trial, or drug-label data, so such a query cannot run at "
            "all. Those are keyword_search.\n"
            "analogical_search: RARE. ONLY when the user explicitly asks what OTHER "
            "RESEARCH FIELDS (not other diseases) use a similar method/technique for an "
            "analogous problem — crossing fields like biology vs. physics vs. NLP, not "
            "crossing diseases within biomedicine ('pathways shared between diabetes and "
            "lymphoma' is keyword_search, NOT this). A question naming a specific drug/"
            "gene/disease/protein is virtually never this route. Fill `analogical_query`. "
            "WHEN IN DOUBT, do NOT use it — default to keyword_search.\n"
            "out_of_scope: Paperclip cannot help — non-biomedical questions, or "
            "EXPLICIT knowledge-graph traversal (shortest path between X and Y, "
            "k-hop neighbours). A question that merely CHAINS through an unnamed "
            "intermediate ('diseases related to a gene/protein associated with drug "
            "X') is NOT out_of_scope — the literature states such associations "
            "directly, so route it as list_breadth and see `search_query` for how "
            "to phrase it."
        ),
    )
    source: PaperclipSourceChoice | None = Field(
        None,
        description=(
            "Which Paperclip corpus to search — leave null (the DEFAULT) for a "
            "broad, unscoped search across the general literature corpora; only set "
            "it when the question specifically needs a narrow corpus:\n"
            "- null (DEFAULT): general biomedical literature questions — "
            "mechanisms, protein domains/functions/interactions, drug targets, "
            "pathways, findings. Searches broadly rather than guessing one corpus. "
            "A question merely MENTIONING a protein does NOT mean 'proteins'.\n"
            "- pmc / biorxiv / medrxiv / arxiv: set explicitly only when the "
            "question specifically wants ONE of these corpora (e.g. 'preprint "
            "work' -> biorxiv/medrxiv/arxiv); otherwise leave source null.\n"
            "- fda: ONLY for explicitly REGULATORY questions — approval status, "
            "boxed/label warnings, FDA-approved indications, regulatory history. Do "
            "NOT use it for what a drug IS or CONTAINS, its components/composition, "
            "targets, or uses (e.g. 'which drugs are in LONSURF?', 'what is drug X "
            "made of?') — those are literature facts, leave source null.\n"
            "- trials: ONLY for explicit clinical-trial-registry questions (a "
            "specific NCT trial, enrollment, trial phase/status). General 'is drug X "
            "used for disease Y' questions are literature -> leave source null.\n"
            "- proteins / pdb / chembl: RECORD corpora — UniProt/PDB/ChEMBL "
            "entries holding database FIELDS, with no abstracts and no prose. "
            "They can only answer a question whose answer IS one of those fields: "
            "a sequence length, an accession, an organism, a structure id, a "
            "ChEMBL bioactivity value. Everything a PAPER reports rather than a "
            "record lists is literature — which domain binds what, how a complex "
            "assembles, what a protein does, what regulates it, which diseases, "
            "drugs or phenotypes relate to it. The question containing the words "
            "'protein', 'gene', 'domain', 'complex' or a protein name is NOT a "
            "reason to set this. TEST: name the exact record field that answers "
            "the question. If you cannot, leave source null.\n"
            "  These corpora are reached ONLY by looking up a protein you can "
            "already NAME — they match on the name text and cannot filter or "
            "enumerate by organism, annotation, or disease. So a question that "
            "asks WHICH records satisfy a condition ('which proteins in mouse "
            "are annotated with...', 'which orthologs of ALS proteins...') is "
            "NOT answerable here even though organism and annotation are real "
            "record fields — you would have to know the answer to write the "
            "lookup. Those are literature: leave source null. Name matching is "
            "also blind to abbreviations — searching 'ALS' returns acetolactate "
            "synthase, not the ALS disease proteins.\n"
            "WHEN IN DOUBT, leave source null — broad search is the right answer "
            "for the large majority of biomedical questions."
        ),
    )
    search_query: str = Field(
        ...,
        description=(
            "Focused search query, 2-6 keywords, built in two steps.\n"
            "  STEP 1 — identify the ANSWER TYPE: the kind of thing the user wants "
            "back (drugs? genes? side effects? pathways?). It is the noun right "
            "after 'which'/'what'/'name all'.\n"
            "  STEP 2 — write the query that retrieves papers ABOUT that answer "
            "type, as a reader would phrase the topic. Keep the subject the "
            "question is anchored on; drop every intermediate entity the question "
            "only routes THROUGH.\n"
            "  Worked example: 'Which drugs target proteins associated with "
            "Alzheimer disease?' -> answer type is drugs, subject is Alzheimer "
            "disease, 'proteins' is only the link between them -> query 'drugs "
            "approved for Alzheimer disease'. Keeping the intermediate retrieves "
            "papers about protein targets, which name no drugs at all. Longer "
            "chains collapse the same way: 'diseases related to a gene associated "
            "with drug X' -> 'X associated diseases'.\n"
            "  Do NOT paste the whole sentence — that belongs in `map_question` "
            "(a full extraction question, not a retrieval query; see its own "
            "description). Topic queries with no chain stay as they are, e.g. "
            "'BTK inhibitor chronic lymphocytic leukemia', 'metformin mechanism "
            "of action'. "
            "This is filled for ALL in-scope routes — including sql_aggregate, where "
            "it's the fallback keyword search used if the SQL query fails (bad "
            "query, timeout), and analogical_search, where it's the fallback keyword "
            "search used if the analogical search returns zero hits — and is also "
            "the general zero-result fallback query. Leave a short topic phrase even "
            "for out_of_scope."
        ),
    )
    analogical_query: str | None = Field(
        None,
        description=(
            "Filled ONLY when question_type=analogical_search (null otherwise): a "
            "1-2 sentence description of the underlying METHOD/PROBLEM PATTERN, never "
            "keywords (keywords defeat analogical ranking — returns topical matches, "
            "not cross-domain analogies). E.g. 'correcting for systematic "
            "under-reporting when the missingness mechanism is unknown', not 'missing "
            "data bias'."
        ),
    )
    map_question: str = Field(
        ...,
        description=(
            "The question asked to each retrieved paper individually via Paperclip's "
            "`map` (a per-paper full-text reader) — DIFFERENT from search_query "
            "(keywords for retrieval): this is a full, specific question for "
            "extraction. Be concrete and enumerate every field you want pulled out, "
            "e.g. NOT 'summarize this paper' but 'What delivery vector or inhibitor "
            "mechanism was used, what cell type or population was studied, and what "
            "was the reported efficacy or outcome?'. A vague question yields vague "
            "per-paper answers and hurts the found/not-found signal each paper is "
            "judged on. If the user's own question is already this specific, you may "
            "reuse it near-verbatim; if it's broad or terse ('mechanism of X?'), "
            "expand it into the concrete sub-questions that would actually answer "
            "it. Filled for ALL in-scope routes, including sql_aggregate — it's "
            "unused if the SQL query succeeds (nothing to map over), but ready in "
            "case it falls back to a literature search."
        ),
    )
    sql_query: str | None = Field(
        None,
        description=(
            "A single read-only SQL SELECT statement, filled ONLY when "
            "question_type=sql_aggregate (null otherwise). Runs against a "
            "`documents` table: id, title, doi, authors, source ('biorxiv'|"
            "'medrxiv'|'pmc'|'arxiv'), abstract_text, pub_date, journal_title, "
            "article_type, pmid, keywords (JSONB), categories (JSONB), pub_year "
            "(INT), created_at. journal_title/article_type/pmid/keywords/"
            "categories/pub_year are PMC-only (NULL for biorxiv/medrxiv/arxiv) — "
            "filter with `source = 'pmc'` when using them.\n"
            "CRITICAL constraints (server-enforced, confirmed live):\n"
            "- SELECT only. No writes, no other tables.\n"
            "- `documents` is NOT one unified table — it's split by `source`. "
            "Use the `source` field above (e.g. 'pmc') to scope which shard(s) "
            "get queried; a bare `WHERE source = 'x'` clause without also setting "
            "`source` above only filters WITHIN whatever shard(s) were already "
            "selected, and will silently return zero rows if that shard wasn't "
            "reached. `source='trials'`/`'proteins'` are NOT valid here at all — "
            "never write sql_aggregate for trial or protein counts.\n"
            "- Free-text pattern matching (`abstract_text ILIKE '%keyword%'`) over "
            "the full pmc/arxiv tables (millions of rows, unindexed for this) "
            "reliably times out (15s server limit). Only use ILIKE on short "
            "structured fields like `authors` or `title`, never `abstract_text`, "
            "and always pair with a `source`/`pub_year`/other filter to narrow the "
            "scanned rows first."
        ),
    )
    full_text: bool = Field(
        False,
        description=(
            "Whether to fetch full paper body text (True) or abstracts only "
            "(False). DEFAULT FALSE — abstracts answer most questions cheaply. Set "
            "True only for full_text_depth questions (mechanisms, methods, results, "
            "paragraph detail)."
        ),
    )
    sections: list[PaperclipSectionName] | None = Field(
        None,
        description=(
            "OPTIONAL body-section filter, applied ONLY when full_text=True. When "
            "set, only these sections are pulled from each paper instead of the "
            "whole body — cheaper and more focused. Pick the section(s) the "
            "question targets: methods/protocol/assay -> ['methods']; "
            "findings/data/numbers -> ['results']; mechanism/interpretation -> "
            "['discussion']; takeaways -> ['conclusion']. Leave null to pull the "
            "whole body. Has NO effect when full_text=False."
        ),
    )
    year: str | None = Field(
        None,
        description=(
            "Optional publication-year filter passed to search (e.g. '2023' or "
            "'2020-2024') when the user constrains recency. Usually null."
        ),
    )
    rationale: str = Field("", description="One-sentence justification for the classification.")


class PaperclipDepthEvaluation(BaseModel):
    sufficient: bool = Field(
        ...,
        description=(
            "True if the answer is scientifically substantive for the question — "
            "names specific entities, describes mechanisms/findings, cites papers. "
            "False if it reads like a restatement of the question with references "
            "attached but no real biology."
        ),
    )
    missing: str | None = Field(
        None,
        description=(
            "If sufficient=False, a short note on the gap — e.g. 'no mechanism "
            "described', 'no quantitative results'. Null when sufficient=True. The "
            "only escalation lever is fetching full text, so this drives whether we "
            "re-fetch with full_text=True."
        ),
    )
    rationale: str = Field("", description="One-sentence justification for the verdict.")


class Citation(BaseModel):
    """A resolved, citable reference threaded into the final answer. Every field
    that can ground provenance (doi/pmid/url) is carried so the top-level graph /
    API can render a proper reference list."""
    ref_num: int
    doc_id: str
    title: str = ""
    authors: str = ""
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    url: str = ""


class PaperContext(BaseModel):
    """Assembled per-paper context passed to the synthesizer: always the meta
    (title/abstract + citable ids), plus body text when full_text depth is on."""
    doc_id: str
    meta: PaperMeta
    body: str | None = None


class PaperclipState(TypedDict, total=False):
    question: str
    chat_history: list

    # Router decision. `source=None`/absent means "broad/unscoped search" —
    # see `PaperclipRouterDecision.source`.
    question_type: PaperclipQuestionType
    source: str | None
    search_query: str
    analogical_query: str | None
    map_question: str
    full_text: bool
    sections: list[str] | None
    year: str | None
    rationale: str

    # Retrieval.
    hits: list[PaperHit]
    search_id: str | None
    queries_used: list[str]
    documents: list[PaperContext]
    citations: list[Citation]

    # SQL aggregate route (question_type == "sql_aggregate"). sql_error set
    # means the query failed and the graph fell back to search_query instead.
    sql_query: str | None
    sql_columns: list[str]
    sql_rows: list[dict]
    sql_error: str | None

    # Synthesis + depth loop.
    final_answer: str | None
    depth_sufficient: bool
    depth_missing: str | None
    depth_skip_reason: str | None
    refinement_attempted: bool

    warnings: list[str]


PaperclipRouterFn = Callable[[str], Awaitable[PaperclipRouterDecision]]
PaperclipSynthesizerFn = Callable[[PaperclipState], Awaitable[str]]
PaperclipEvaluatorFn = Callable[[PaperclipState], Awaitable[PaperclipDepthEvaluation]]


__all__ = [
    "PaperclipQuestionType",
    "PaperclipSourceChoice",
    "PaperclipRouterDecision",
    "PaperclipDepthEvaluation",
    "Citation",
    "PaperContext",
    "PaperclipState",
    "PaperclipRouterFn",
    "PaperclipSynthesizerFn",
    "PaperclipEvaluatorFn",
]
