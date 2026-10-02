"""Pipeline state carried between nodes.

Build order step 5. Beyond the question and the answer, state records what was lost on the way:
hits dropped for a missing pmid, pmids whose fetch failed, and validation warnings. A degraded
answer is acceptable; a silently degraded one is not (ADR-001, ADR-002).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from crossbar_llm.litsense_tools.models import (
    Answer,
    ArticleContext,
    DepthVerdict,
    RelevanceVerdict,
    SelectionResult,
    SentenceHit,
    SynthesisOutput,
    TokenUsage,
)


class PipelineState(BaseModel):
    """Everything the linear pipeline accumulates on its way to an `Answer`.

    The intermediate fields are optional or empty because each node fills exactly one of
    them; in a linear graph every node can rely on its predecessors' fields being set.
    """

    question: str
    relevance: RelevanceVerdict | None = Field(
        default=None,
        description="The gate's verdict; None when the gate is disabled (ADR-008).",
    )
    hits: list[SentenceHit] = Field(default_factory=list)
    selection: SelectionResult | None = None
    articles: list[ArticleContext] = Field(default_factory=list)
    failed_pmids: list[int] = Field(
        default_factory=list,
        description="Selected pmids whose fetch failed; reported, never silently lost.",
    )
    output: SynthesisOutput | None = None
    depth: DepthVerdict | None = Field(
        default=None,
        description="The depth evaluator's verdict on the latest output; None when the "
        "full-text loop is disabled (ADR-009).",
    )
    refined: bool = Field(
        default=False,
        description="True once the one full-text refinement pass has run (ADR-009).",
    )
    fulltext_failed_pmcids: list[str] = Field(
        default_factory=list,
        description="pmcids whose full-text fetch failed during refinement; reported, "
        "never silently lost.",
    )
    answer: Answer | None = None
    usage: TokenUsage = Field(
        default_factory=TokenUsage,
        description="Token consumption summed over every model call of this run (gate, "
        "synthesis, depth evaluator). Zero when no model reports usage, e.g. dry runs.",
    )
