"""Pydantic models at every boundary.

Written from responses actually observed and captured in ``tests/fixtures/`` (build order
step 1), not from guesses. The observations behind the non-obvious choices here are recorded in
ADR-005 (publication endpoint) and ADR-006 (the score sentinel).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

#: Value the search endpoint emits for a sentence the reranker did not score. It is a sentinel,
#: not a perfect match: these hits arrive as a trailing block after the descending scored ones,
#: and under ``rerank=false`` every score is this value. See ADR-006.
UNSCORED_SENTINEL = 1.0

#: `section` values observed on sentence hits, plus ``None``. Recorded for reference only —
#: nothing validates against this set, because the API is free to add more.
OBSERVED_SENTENCE_SECTIONS = frozenset(
    {"title", "abstract", "INTRO", "METHODS", "RESULTS", "DISCUSS", "CONCL"}
)

#: `infons.type` values observed on publication passages. The endpoint has never returned
#: anything else, including for articles whose full text is in PMC (ADR-005).
OBSERVED_PASSAGE_SECTIONS = frozenset({"title", "abstract"})

#: `infons.section_type` values observed on BioC-PMC full-text passages (ADR-009). For
#: reference only — the API is free to add more.
OBSERVED_FULLTEXT_SECTIONS = frozenset(
    {
        "TITLE", "ABSTRACT", "INTRO", "METHODS", "RESULTS", "DISCUSS", "CONCL",
        "FIG", "TABLE", "REF", "SUPPL", "AUTH_CONT", "COMP_INT",
    }
)

#: The full-text sections worth grounding an answer in: the narrative body. References,
#: figure/table scaffolding and author-contribution boilerplate are noise at LLM prices.
NARRATIVE_FULLTEXT_SECTIONS = frozenset(
    {"ABSTRACT", "INTRO", "METHODS", "RESULTS", "DISCUSS", "CONCL"}
)


class Entity(BaseModel):
    """One PubTator entity mention, parsed from a sentence hit's annotation string.

    The search endpoint attaches entities as ``start|length|type|id`` strings; ``text`` is
    the mention sliced out of the sentence. Distinct entities (by type+id) surface on the
    final `Answer` — the Trello "return entity ids" task (2026-08-18).
    """

    text: str
    type: str
    id: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.type, self.id)


class SentenceHit(BaseModel):
    """One sentence returned by ``/api/sentences/``.

    The endpoint returns a flat array of these — not articles. The same ``pmid`` appears in
    several entries; grouping them is `select`'s job (ADR-001).
    """

    model_config = ConfigDict(extra="ignore")

    pmid: int | None = None
    pmcid: str | None = None
    text: str
    score: float
    section: str | None = None
    annotations: list[str] | None = Field(
        default=None,
        description="PubTator entities as 'start|length|type|id' strings.",
    )

    @property
    def entities(self) -> list[Entity]:
        """The hit's annotations as parsed entities, skipping anything malformed.

        The format is ``start|length|type|id`` with the id allowed to contain ``|`` itself
        (split at most three times). Out-of-range offsets yield an empty mention text but
        keep the id — the id is the useful part.
        """
        parsed: list[Entity] = []
        for annotation in self.annotations or []:
            parts = annotation.split("|", 3)
            if len(parts) != 4:
                continue
            try:
                start, length = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            if start < 0 or length <= 0 or not parts[3]:
                continue
            parsed.append(
                Entity(text=self.text[start : start + length], type=parts[2], id=parts[3])
            )
        return parsed

    @property
    def is_unscored(self) -> bool:
        """True when the reranker did not score this hit.

        Only meaningful when the request was made with ``rerank=true``; with ``rerank=false``
        every hit is unscored and ordering is the API's own.
        """
        return self.score == UNSCORED_SENTINEL


class PassageInfons(BaseModel):
    """Metadata block on a passage. Contents vary by passage type and by source.

    `type` is what the LitSense publication endpoint uses (`title`/`abstract`, ADR-005);
    `section_type` is what BioC-PMC full-text passages carry (`INTRO`/`METHODS`/...,
    ADR-009).
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str | None = None
    section_type: str | None = None
    journal: str | None = None
    year: str | None = None
    authors: str | None = None
    pmc_id: str | None = Field(default=None, alias="article-id_pmc")


class Passage(BaseModel):
    """One BioC passage of a publication document.

    The rich PubTator ``annotations`` and ``relations`` the API attaches are deliberately not
    modelled: v1 does not use them, and admitting them into the type would invite it to.
    """

    model_config = ConfigDict(extra="ignore")

    infons: PassageInfons = Field(default_factory=PassageInfons)
    offset: int = 0
    text: str = ""

    @property
    def section(self) -> str | None:
        return self.infons.type


class Publication(BaseModel):
    """A document from ``/publication/{pmid}``.

    In practice this is always title + abstract; see :func:`section_text` and ADR-005.
    """

    model_config = ConfigDict(extra="ignore")

    pmid: int
    pmcid: str | None = None
    journal: str | None = None
    date: datetime | None = None
    authors: list[str] = Field(default_factory=list)
    passages: list[Passage] = Field(default_factory=list)

    def section_text(self, section: str) -> str | None:
        """Text of the named section, or ``None`` when it is absent *or* empty.

        A publication with no abstract still comes back with an ``abstract`` passage whose
        ``text`` is the empty string. Absent and empty are collapsed on purpose: both mean
        "there is nothing here to ground an answer in", and the caller should not have to know
        which flavour of nothing it got.
        """
        wanted = section.casefold()
        parts = [
            p.text.strip()
            for p in self.passages
            if (p.section or "").casefold() == wanted and p.text.strip()
        ]
        return "\n\n".join(parts) if parts else None

    @property
    def title(self) -> str | None:
        return self.section_text("title")

    @property
    def abstract(self) -> str | None:
        return self.section_text("abstract")


class FullText(BaseModel):
    """One article's full text from the BioC-PMC service (ADR-009).

    Parsed out of the observed wrapper — a list of BioC collections, article at
    ``[0]["documents"][0]`` — by `client.fetch_full_text`. Reuses `Passage`; the section
    lives in ``infons.section_type`` here, not ``infons.type``.
    """

    model_config = ConfigDict(extra="ignore")

    pmcid: str
    passages: list[Passage] = Field(default_factory=list)

    def body(self, *, max_chars: int) -> str | None:
        """The narrative body — `NARRATIVE_FULLTEXT_SECTIONS` in document order, capped.

        The cap cuts at a passage boundary; one oversized passage is truncated rather than
        dropped. Returns None when no narrative passage has text.
        """
        parts: list[str] = []
        used = 0
        for passage in self.passages:
            section = (passage.infons.section_type or "").upper()
            text = passage.text.strip()
            if section not in NARRATIVE_FULLTEXT_SECTIONS or not text:
                continue
            remaining = max_chars - used
            if remaining <= 0:
                break
            if len(text) > remaining:
                text = text[:remaining]
            parts.append(text)
            used += len(text) + 2
        return "\n\n".join(parts) if parts else None


class ArticleContext(BaseModel):
    """One publication as it is presented to the model.

    The sentences that caused the article to be retrieved travel with it: they are the reason
    it is here and they cost almost nothing to include (ADR-001).
    """

    pmid: int
    pmcid: str | None = Field(
        default=None,
        description=(
            "PMC id from the retrieval-side hits (the publication document's own is always "
            "null, ADR-005). The handle for the full-text fetch (ADR-009)."
        ),
    )
    title: str | None = None
    journal: str | None = None
    date: datetime | None = None
    section: str
    text: str | None = None
    matched_sentences: list[str] = Field(default_factory=list)
    entities: list[Entity] = Field(
        default_factory=list,
        description="Distinct PubTator entities from the article's matched sentences.",
    )

    @property
    def has_text(self) -> bool:
        return bool(self.text)


class SelectedArticle(BaseModel):
    """One publication chosen by `select`, with the hits that earned its place.

    The hits travel whole rather than as bare sentence strings: `fetch` wants the
    retrieval-side ``pmcid`` (the document's own is always null, ADR-005) and `synthesize`
    wants the sentence texts.
    """

    pmid: int
    hits: list[SentenceHit]

    @property
    def matched_sentences(self) -> list[str]:
        return [hit.text for hit in self.hits]

    @property
    def entities(self) -> list[Entity]:
        """Distinct entities across the group's hits, first occurrence wins."""
        seen: dict[tuple[str, str], Entity] = {}
        for hit in self.hits:
            for entity in hit.entities:
                seen.setdefault(entity.key, entity)
        return list(seen.values())


class SelectionResult(BaseModel):
    """`select`'s output: the chosen articles, plus what was dropped on the way.

    The drop counts exist because a degraded selection is acceptable and a silently degraded
    one is not (ADR-001).
    """

    articles: list[SelectedArticle] = Field(default_factory=list)
    dropped_no_pmid: int = 0
    dropped_below_min_score: int = 0

    @property
    def pmids(self) -> list[int]:
        return [article.pmid for article in self.articles]


class Citation(BaseModel):
    """A validated reference, resolved for display.

    Produced by joining the pmids the model returned against the publications actually fetched.
    Never parsed out of prose (ADR-003).
    """

    pmid: int
    title: str | None = None
    journal: str | None = None

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"


class RelevanceVerdict(BaseModel):
    """The relevance gate's structured output (ADR-008).

    Judges the *question*, not the retrieval: is this a coherent biomedical question the
    literature could in principle address? Produced by an LLM before any search happens;
    a negative verdict routes the pipeline straight to END.
    """

    relevant: bool = Field(
        description="True when this is a coherent biomedical question the literature "
        "could in principle address."
    )
    reason: str = Field(
        default="",
        description="One sentence explaining the verdict, shown to the user when negative.",
    )


class DepthVerdict(BaseModel):
    """The depth evaluator's structured output (ADR-009).

    Judges the synthesized answer, not the question: does it have the scientific depth the
    question deserves, given that only abstracts were read? Insufficient triggers the one
    full-text refinement pass.
    """

    sufficient: bool = Field(
        description="True when the answer's scientific depth matches the question."
    )
    missing: str = Field(
        default="",
        description="One sentence naming what is missing, when insufficient.",
    )


class SynthesisOutput(BaseModel):
    """What the LLM is asked to return — and nothing more.

    Deliberately narrower than :class:`Answer`: ``warnings`` belong to the pipeline, so the
    model never gets to write them. `validate` turns this into an `Answer` after checking the
    citations against the fetched set (ADR-003).
    """

    text: str = Field(description="The answer, grounded strictly in the provided articles.")
    citations: list[int] = Field(
        default_factory=list,
        description="PubMed IDs of the provided articles the answer actually draws on.",
    )
    insufficient_context: bool = Field(
        default=False,
        description="True when the provided articles do not contain enough to answer.",
    )


class TokenUsage(BaseModel):
    """Model token consumption, summed over every LLM call a pipeline run made.

    Field names follow Ahmet Oğuzhan's harness (``tokens`` per question) so the benchmark
    records compare directly. Populated from LangChain's provider-normalized
    ``usage_metadata``; a provider that reports nothing leaves every field at zero.
    """

    input: int = 0
    output: int = 0
    reasoning: int = Field(default=0, description="Reasoning/thinking tokens, when reported.")
    cache_read: int = Field(default=0, description="Prompt-cache hits, when reported.")
    total: int = 0
    calls: int = Field(default=0, description="Number of model calls summed here.")

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input=self.input + other.input,
            output=self.output + other.output,
            reasoning=self.reasoning + other.reasoning,
            cache_read=self.cache_read + other.cache_read,
            total=self.total + other.total,
            calls=self.calls + other.calls,
        )

    @classmethod
    def from_usage_metadata(cls, usage: Mapping[str, Any] | None) -> TokenUsage:
        """Lift LangChain's ``UsageMetadata`` dict (any provider) into this model."""
        if not usage:
            return cls()
        out_details = usage.get("output_token_details") or {}
        in_details = usage.get("input_token_details") or {}
        return cls(
            input=int(usage.get("input_tokens", 0)),
            output=int(usage.get("output_tokens", 0)),
            reasoning=int(out_details.get("reasoning", 0)),
            cache_read=int(in_details.get("cache_read", 0)),
            total=int(usage.get("total_tokens", 0)),
        )


class Answer(BaseModel):
    """The synthesis node's structured output, and the library's return type.

    ``citations`` are PubMed IDs and nothing else — the model is asked for structured data, so
    there is never a parsing step between the model and this object (ADR-003).
    """

    text: str
    citations: list[int] = Field(default_factory=list)
    insufficient_context: bool = False
    warnings: list[str] = Field(default_factory=list)
    entities: list[Entity] = Field(
        default_factory=list,
        description=(
            "Distinct PubTator entities from the evidence behind the answer: the cited "
            "articles' matched sentences, or every fetched article's when nothing is cited."
        ),
    )
