"""`select` turns sentence hits into ranked articles (ADR-001, amended by ADR-006).

Pure-function tests: captured fixtures for the real response shapes, synthetic hits for the
corners the fixtures happen not to exercise (a null pmid has never been observed live).
"""

from __future__ import annotations

from crossbar_llm.litsense_tools.graph.nodes import relevance_warning, select
from crossbar_llm.litsense_tools.models import SentenceHit
from crossbar_llm.litsense_tools.tests.conftest import load_fixture

RERANKED = "sentences_what_is_the_role_of_tp53_mutations_in_colorectal_cancer_prog.json"
PLAIN = "sentences_rerank_false.json"


def fixture_hits(name: str) -> list[SentenceHit]:
    return [SentenceHit.model_validate(h) for h in load_fixture(name)]


def hit(pmid: int | None, score: float, text: str = "sentence") -> SentenceHit:
    return SentenceHit(pmid=pmid, score=score, text=text)


# --- Against the captured responses ----------------------------------------------------


def test_selects_at_most_max_articles_distinct_pmids() -> None:
    result = select(fixture_hits(RERANKED), max_articles=10)
    assert len(result.articles) == 10
    assert len(set(result.pmids)) == 10
    assert result.dropped_no_pmid == 0  # never observed live; pinned so we notice a change


def test_the_top_scored_hit_wins_the_top_slot() -> None:
    """Max-of-group ranking: the group holding the best scored sentence ranks first."""
    hits = fixture_hits(RERANKED)
    result = select(hits, max_articles=10)
    assert result.articles[0].pmid == hits[0].pmid


def test_unscored_only_groups_rank_below_every_scored_group() -> None:
    """The ADR-006 inversion guard: the sentinel tail must never sort to the top."""
    hits = fixture_hits(RERANKED)
    result = select(hits, max_articles=100)  # no truncation: rank all groups

    scored_pmids = {h.pmid for h in hits if not h.is_unscored and h.pmid is not None}
    ranks = {article.pmid: rank for rank, article in enumerate(result.articles)}
    unscored_only = [pmid for pmid in ranks if pmid not in scored_pmids]

    assert unscored_only, "fixture no longer has an unscored-only group; recheck ADR-006"
    worst_scored = max(ranks[pmid] for pmid in scored_pmids)
    assert all(ranks[pmid] > worst_scored for pmid in unscored_only)


def test_matched_sentences_travel_with_the_article_in_response_order() -> None:
    hits = fixture_hits(RERANKED)
    top = select(hits, max_articles=1).articles[0]
    expected = [h.text for h in hits if h.pmid == top.pmid]
    assert top.matched_sentences == expected
    assert len(expected) >= 1


def test_rerank_false_still_selects_without_scores() -> None:
    """Every hit is the sentinel: ranking degrades to group size then API order, not a crash."""
    result = select(fixture_hits(PLAIN), max_articles=10)
    assert len(result.articles) == 10
    sizes = [len(a.hits) for a in result.articles]
    assert sizes == sorted(sizes, reverse=True)


# --- Synthetic corners -----------------------------------------------------------------


def test_the_sentinel_is_not_a_score() -> None:
    """A raw max() over scores would rank B first on its 1.0 hit. It must not."""
    hits = [hit(1, 0.6), hit(2, 0.5), hit(2, 1.0)]
    assert select(hits, max_articles=2).pmids == [1, 2]


def test_unscored_hits_still_travel_with_a_scored_group() -> None:
    hits = [hit(1, 0.6, "scored"), hit(1, 1.0, "unscored tail")]
    top = select(hits, max_articles=1).articles[0]
    assert top.matched_sentences == ["scored", "unscored tail"]


def test_ties_break_by_hit_count_then_first_appearance() -> None:
    hits = [
        hit(1, 0.6),           # one hit, appears first
        hit(2, 0.6), hit(2, 0.4),  # same max score, two hits -> outranks 1
        hit(3, 0.6),           # same max score and count as 1, appears later
    ]
    assert select(hits, max_articles=3).pmids == [2, 1, 3]


def test_hits_without_pmid_are_dropped_and_counted() -> None:
    result = select([hit(None, 0.9), hit(1, 0.5)], max_articles=10)
    assert result.pmids == [1]
    assert result.dropped_no_pmid == 1


def test_min_score_applies_to_scored_hits_only() -> None:
    """The sentinel would clear any floor below 1.0; unscored hits must pass through (ADR-006)."""
    hits = [hit(1, 0.5, "too weak"), hit(2, 0.95, "strong"), hit(2, 1.0, "unscored")]
    result = select(hits, max_articles=10, min_score=0.9)
    assert result.pmids == [2]
    assert result.articles[0].matched_sentences == ["strong", "unscored"]
    assert result.dropped_below_min_score == 1


def test_zero_hits_is_a_valid_outcome() -> None:
    result = select([], max_articles=10)
    assert result.articles == []
    assert result.dropped_no_pmid == 0
    assert result.dropped_below_min_score == 0


# --- The low-relevance tripwire (ADR-007) ----------------------------------------------


def test_the_nonsense_query_fixture_trips_the_warning() -> None:
    """The API never returns nothing; a depressed score ceiling is its only tell."""
    hits = fixture_hits("sentences_zzzqx_nonexistent_biomedical_concept_wibble.json")
    warning = relevance_warning(hits, threshold=0.6)
    assert warning is not None
    assert "relevance is low" in warning


def test_a_real_question_fixture_does_not_trip_the_warning() -> None:
    assert relevance_warning(fixture_hits(RERANKED), threshold=0.6) is None


def test_the_warning_is_advisory_only_and_can_be_disabled() -> None:
    weak = [hit(1, 0.4)]
    assert relevance_warning(weak, threshold=None) is None
    assert relevance_warning([], threshold=0.6) is None  # zero hits has its own signal
    # selection is untouched either way
    assert select(weak, max_articles=10).pmids == [1]


def test_without_scores_the_warning_cannot_fire() -> None:
    """rerank=false leaves nothing to assess — documented in ADR-007, not worked around."""
    assert relevance_warning(fixture_hits(PLAIN), threshold=0.6) is None
