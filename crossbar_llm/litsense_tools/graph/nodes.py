"""Pipeline nodes.

`select` (step 3) and `validate` (step 4) are pure functions over state — no network, no LLM.
They are where correctness actually lives and they are unit-tested against fixtures.
`search` and `fetch` delegate all HTTP to the shared client; `synthesize` delegates all model
access to `llm.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Sequence

from crossbar_llm.litsense_tools.client import (
    FullTextNotFound,
    LitSenseClient,
    LitSenseUnavailable,
    PublicationNotFound,
)
from crossbar_llm.litsense_tools.llm import Synthesizer
from crossbar_llm.litsense_tools.models import (
    Answer,
    ArticleContext,
    Entity,
    RelevanceVerdict,
    SelectedArticle,
    SelectionResult,
    SentenceHit,
    SynthesisOutput,
)
from crossbar_llm.litsense_tools.prompts import synthesis_messages

#: Warning carried by an answer the relevance gate produced instead of the pipeline.
GATE_WARNING = "the relevance gate stopped this question before any retrieval (ADR-008)"


def gate_answer(verdict: RelevanceVerdict) -> Answer:
    """The answer for a question the gate rejected. Pure — no network, no LLM.

    Nothing was searched, fetched, or synthesized, so this is composed here rather than by
    the model: an empty answer with the verdict's reason, flagged `insufficient_context` for
    parity with the zero-article short-circuit (ADR-008).
    """
    text = (
        "This question was judged not to be a biomedical question the literature could "
        "address, so no search was run."
    )
    if verdict.reason:
        text += f" {verdict.reason}"
    return Answer(text=text, insufficient_context=True, warnings=[GATE_WARNING])


def _group_rank(first_seen: int, group: list[SentenceHit]) -> tuple[int, float, int, int]:
    """Ranking key for one pmid group, per ADR-001 as amended by ADR-006.

    Groups with at least one scored hit come first, ordered by their best *scored* hit —
    never by the ``1.0`` sentinel, which marks a hit the reranker declined to score. Ties
    break by group size, then by first appearance in the response.
    """
    scored = [hit.score for hit in group if not hit.is_unscored]
    return (0 if scored else 1, -max(scored, default=0.0), -len(group), first_seen)


def select(
    hits: Sequence[SentenceHit],
    *,
    max_articles: int,
    min_score: float | None = None,
) -> SelectionResult:
    """Reduce a flat sentence-hit list to the publications worth fetching.

    Pure — no I/O. Hits without a ``pmid`` are dropped (they can be neither fetched nor
    cited, ADR-001); ``min_score`` applies to scored hits only, since the sentinel would
    clear any floor (ADR-006). Unscored hits are never dropped outright: they still travel
    as matched sentences for a group that earned its place on other evidence.
    """
    groups: dict[int, list[SentenceHit]] = {}
    dropped_no_pmid = 0
    dropped_below_min_score = 0
    for hit in hits:
        if hit.pmid is None:
            dropped_no_pmid += 1
            continue
        if min_score is not None and not hit.is_unscored and hit.score < min_score:
            dropped_below_min_score += 1
            continue
        groups.setdefault(hit.pmid, []).append(hit)

    ranked = sorted(
        ((index, pmid, group) for index, (pmid, group) in enumerate(groups.items())),
        key=lambda entry: _group_rank(entry[0], entry[2]),
    )
    return SelectionResult(
        articles=[
            SelectedArticle(pmid=pmid, hits=group)
            for _index, pmid, group in ranked[:max_articles]
        ],
        dropped_no_pmid=dropped_no_pmid,
        dropped_below_min_score=dropped_below_min_score,
    )


async def fetch_articles(
    selection: Sequence[SelectedArticle],
    client: LitSenseClient,
    *,
    section: str,
) -> tuple[list[ArticleContext], list[int]]:
    """Fetch the configured section for every selected article, tolerating partial failure.

    Concurrency is bounded by the client itself (its limiter and semaphore), so this can
    gather freely. A pmid that does not resolve or a fetch the service kept failing drops
    that one article and records the pmid; neither fails the pipeline (ADR-005). Results come
    back in selection (rank) order regardless of completion order.
    """
    articles: list[ArticleContext] = []
    failed: list[int] = []

    async def fetch_one(selected: SelectedArticle) -> None:
        try:
            publication = await client.fetch_publication(selected.pmid)
        except (PublicationNotFound, LitSenseUnavailable):
            failed.append(selected.pmid)
            return
        articles.append(
            ArticleContext(
                pmid=selected.pmid,
                # Retrieval-side pmcid: the publication document's own is always null
                # (ADR-005), and this is the handle full-text refinement needs (ADR-009).
                pmcid=next((h.pmcid for h in selected.hits if h.pmcid), None),
                title=publication.title,
                journal=publication.journal,
                date=publication.date,
                section=section,
                text=publication.section_text(section),
                matched_sentences=selected.matched_sentences,
                entities=selected.entities,
            )
        )

    await asyncio.gather(*(fetch_one(selected) for selected in selection))

    rank = {selected.pmid: index for index, selected in enumerate(selection)}
    articles.sort(key=lambda article: rank[article.pmid])
    failed.sort(key=lambda pmid: rank[pmid])
    return articles, failed


#: `ArticleContext.section` value after full-text refinement replaced the abstract.
FULL_TEXT_SECTION = "full_text"


async def refine_articles(
    articles: Sequence[ArticleContext],
    cited: Collection[int],
    client: LitSenseClient,
    *,
    max_chars: int,
) -> tuple[list[ArticleContext], list[str]]:
    """Swap abstracts for narrative full text where PMC has it (ADR-009).

    Candidates are the cited articles when `cited` is non-empty (the evidence the first
    answer actually used), otherwise every article. An article without a pmcid, without
    full text, or whose fetch fails keeps its abstract — the pipeline degrades, never
    breaks; failed pmcids are recorded. Sequential on purpose: the shared limiter paces
    NCBI anyway, and order is preserved.
    """
    refined: list[ArticleContext] = []
    failed: list[str] = []
    for article in articles:
        if article.pmcid is None or (cited and article.pmid not in cited):
            refined.append(article)
            continue
        try:
            full_text = await client.fetch_full_text(article.pmcid)
        except (FullTextNotFound, LitSenseUnavailable):
            failed.append(article.pmcid)
            refined.append(article)
            continue
        body = full_text.body(max_chars=max_chars)
        if body is None:
            refined.append(article)
            continue
        refined.append(
            article.model_copy(update={"text": body, "section": FULL_TEXT_SECTION})
        )
    return refined, failed


def relevance_warning(
    hits: Sequence[SentenceHit], *, threshold: float | None
) -> str | None:
    """Advisory tripwire for questions the literature likely does not address. Pure.

    LitSense never returns an empty result: a nonsense query still gets a full page of hits,
    just uniformly weak ones (best ~0.55 observed, vs ~0.74+ for real questions). Absolute
    score comparison across queries is otherwise off-limits (ADR-001/ADR-006); this is the
    one sanctioned exception, and it only ever *warns* — nothing is filtered, nothing is
    refused (ADR-007). Returns None when disabled, when there are no hits at all (that has
    its own signal), or when nothing is scored (rerank=false).
    """
    if threshold is None or not hits:
        return None
    scored = [hit.score for hit in hits if not hit.is_unscored]
    if not scored:
        return None
    best = max(scored)
    if best >= threshold:
        return None
    return (
        f"retrieval relevance is low: the best reranker score is {best:.3f} "
        f"(threshold {threshold}) — the literature may not address this question"
    )


def pipeline_warnings(selection: SelectionResult, failed_pmids: Sequence[int]) -> list[str]:
    """What the pipeline lost on the way, phrased for the final answer's `warnings`."""
    warnings: list[str] = []
    if selection.dropped_no_pmid:
        warnings.append(
            f"{selection.dropped_no_pmid} search hit(s) had no pmid and were dropped"
        )
    if selection.dropped_below_min_score:
        warnings.append(
            f"{selection.dropped_below_min_score} scored hit(s) fell below min_score"
        )
    if failed_pmids:
        warnings.append(
            "publications could not be fetched: " + ", ".join(str(p) for p in failed_pmids)
        )
    return warnings


#: What the model is told when there is nothing to ground an answer in. Produced without an
#: LLM call: asking a model to answer from zero articles invites it to answer from memory,
#: which is the one failure the prompt exists to prevent (invariant 1).
NO_CONTEXT_ANSWER = (
    "No usable articles were retrieved for this question, so no grounded answer can be given."
)


async def synthesize(
    question: str,
    articles: Sequence[ArticleContext],
    synthesizer: Synthesizer,
    *,
    style: str = "prose",
) -> SynthesisOutput:
    """One LLM call over the fetched contexts, or a short-circuit when there are none.

    Articles without section text still go to the model — their matched sentences are real
    retrieved evidence and are rendered into the context block. `style` selects the output
    instruction: "prose" (default, one consolidated paragraph) or "bare" (only the
    requested items — the benchmark-overlap mode from the Trello evaluation card).
    """
    if not articles:
        return SynthesisOutput(text=NO_CONTEXT_ANSWER, insufficient_context=True)
    return await synthesizer(synthesis_messages(question, articles, style=style))


def validate(
    output: SynthesisOutput,
    fetched_pmids: Collection[int],
    *,
    warnings: Sequence[str] = (),
    articles: Sequence[ArticleContext] = (),
) -> Answer:
    """Turn the model's output into the pipeline's answer. Pure — no network, no LLM.

    Every citation must name a publication that was actually fetched; anything else is
    dropped and recorded, never shipped (invariant 3). Duplicates collapse to the first
    occurrence. `warnings` carries what the pipeline itself lost on the way (failed fetches,
    hits dropped in selection); the model never writes warnings (ADR-003).

    The answer also carries the distinct entities of its evidence: from the cited articles
    when there are citations, otherwise from every provided article (so entity ids surface
    even on model-less runs). Entities come from retrieval annotations, never from the model.
    """
    kept: list[int] = []
    hallucinated: list[int] = []
    for pmid in dict.fromkeys(output.citations):
        (kept if pmid in fetched_pmids else hallucinated).append(pmid)

    evidence = [a for a in articles if a.pmid in kept] if kept else list(articles)
    entities: dict[tuple[str, str], Entity] = {}
    for article in evidence:
        for entity in article.entities:
            entities.setdefault(entity.key, entity)

    collected = list(warnings)
    if hallucinated:
        collected.append(
            "dropped citations of publications that were never fetched: "
            + ", ".join(str(pmid) for pmid in hallucinated)
        )
    return Answer(
        text=output.text,
        citations=kept,
        insufficient_context=output.insufficient_context,
        warnings=collected,
        entities=list(entities.values()),
    )
