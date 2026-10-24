"""The models parse every captured response, and the contract they encode still holds.

These tests are also the executable record of the API contract: if NCBI changes the shape or a
fixture is recaptured, the assertions here are what tells us the observations in ADR-005 and
ADR-006 have gone stale.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crossbar_llm.litsense_tools.models import (
    UNSCORED_SENTINEL,
    Answer,
    Citation,
    FullText,
    Publication,
    SentenceHit,
)
from crossbar_llm.litsense_tools.tests.conftest import (
    FIXTURES,
    load_fixture,
    publication_fixtures,
    sentence_fixtures,
)

RERANKED = "sentences_what_is_the_role_of_tp53_mutations_in_colorectal_cancer_prog.json"
PLAIN = "sentences_rerank_false.json"
NO_ABSTRACT = "publication_1_no_abstract.json"
WITH_ABSTRACT = "publication_27863244.json"


# --- Sentence search -------------------------------------------------------------------


@pytest.mark.parametrize("path", sentence_fixtures(), ids=lambda p: p.stem[:40])
def test_every_sentence_fixture_parses(path: Path) -> None:
    hits = [SentenceHit.model_validate(h) for h in json.loads(path.read_text(encoding="utf-8"))]
    assert hits
    assert all(hit.text for hit in hits)


def test_search_returns_the_api_maximum() -> None:
    assert len(load_fixture(RERANKED)) == 100


def test_pmcid_and_section_and_annotations_are_nullable() -> None:
    hits = [SentenceHit.model_validate(h) for h in load_fixture(RERANKED)]
    assert any(hit.pmcid is None for hit in hits)
    assert any(hit.section is None for hit in hits)
    crispr = [
        SentenceHit.model_validate(h)
        for h in load_fixture("sentences_crispr_base_editing_off_target_effects.json")
    ]
    assert any(hit.annotations is None for hit in crispr)


def test_the_same_pmid_appears_in_several_hits() -> None:
    """Deduplication is our job — the endpoint returns sentences, not articles."""
    pmids = [h["pmid"] for h in load_fixture(RERANKED)]
    assert len(set(pmids)) < len(pmids)


def test_annotations_keep_the_pipe_delimited_shape() -> None:
    hits = [SentenceHit.model_validate(h) for h in load_fixture(RERANKED)]
    annotation = next(a for hit in hits if hit.annotations for a in hit.annotations)
    start, length, _type, _identifier = annotation.split("|", 3)
    assert start.isdigit() and length.isdigit()


# --- The score sentinel (ADR-006) ------------------------------------------------------


def test_unscored_hits_are_a_trailing_block_not_perfect_matches() -> None:
    """The 1.0 values sit *after* the descending scored hits, so they rank last, not first."""
    hits = [SentenceHit.model_validate(h) for h in load_fixture(RERANKED)]
    scored = [i for i, hit in enumerate(hits) if not hit.is_unscored]
    unscored = [i for i, hit in enumerate(hits) if hit.is_unscored]

    assert unscored, "fixture no longer exercises the sentinel; recheck ADR-006"
    assert min(unscored) > max(scored)


def test_scored_hits_are_ordered_by_descending_score() -> None:
    scores = [h.score for h in map(SentenceHit.model_validate, load_fixture(RERANKED))
              if h.score != UNSCORED_SENTINEL]
    assert all(a >= b for a, b in zip(scores, scores[1:], strict=False))


def test_without_rerank_every_score_is_the_sentinel() -> None:
    """Which is why `min_score` and cross-response score comparison are meaningless."""
    hits = [SentenceHit.model_validate(h) for h in load_fixture(PLAIN)]
    assert all(hit.is_unscored for hit in hits)


def test_a_query_with_no_real_answer_still_returns_a_full_page_of_hits() -> None:
    """Low relevance shows up as low scores, not as an empty response."""
    hits = [
        SentenceHit.model_validate(h)
        for h in load_fixture("sentences_zzzqx_nonexistent_biomedical_concept_wibble.json")
    ]
    assert len(hits) == 100
    assert max(hit.score for hit in hits) < 0.6


# --- Publication fetch (ADR-005) -------------------------------------------------------


@pytest.mark.parametrize("path", publication_fixtures(), ids=lambda p: p.stem[:40])
def test_every_publication_fixture_parses(path: Path) -> None:
    publication = Publication.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert publication.pmid > 0


@pytest.mark.parametrize("path", publication_fixtures(), ids=lambda p: p.stem[:40])
def test_documents_carry_title_and_abstract_and_nothing_else(path: Path) -> None:
    """The `section` knob cannot reach beyond these two — full text is not served here."""
    publication = Publication.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert [p.section for p in publication.passages] == ["title", "abstract"]


@pytest.mark.parametrize("path", publication_fixtures(), ids=lambda p: p.stem[:40])
def test_top_level_pmcid_is_never_populated(path: Path) -> None:
    """Even for articles that are in PMC — the pmcid lives in the title passage's infons."""
    publication = Publication.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert publication.pmcid is None


def test_abstract_and_title_are_extracted() -> None:
    publication = Publication.model_validate(load_fixture(WITH_ABSTRACT))
    assert publication.title is not None
    assert publication.title.startswith("Epigenetic Activation of WNT5A")
    assert publication.abstract is not None
    assert "Glioblastoma stem cells" in publication.abstract
    assert publication.journal == "Cell"
    assert publication.date is not None and publication.date.year == 2016
    assert len(publication.authors) == 33


def test_a_missing_abstract_is_an_empty_passage_and_reads_as_none() -> None:
    publication = Publication.model_validate(load_fixture(NO_ABSTRACT))
    assert [p.section for p in publication.passages] == ["title", "abstract"]
    assert publication.abstract is None
    assert publication.title == "Formate assay in body fluids: application in methanol poisoning."


def test_section_lookup_is_case_insensitive_and_misses_return_none() -> None:
    publication = Publication.model_validate(load_fixture(WITH_ABSTRACT))
    assert publication.section_text("ABSTRACT") == publication.abstract
    assert publication.section_text("METHODS") is None


def test_the_section_query_parameter_is_ignored_by_the_api() -> None:
    """Three different `?section=` values returned byte-identical documents."""
    plain = load_fixture("publication_39039912.json")
    for section in ("abstract", "methods", "not_a_real_section"):
        assert load_fixture(f"publication_39039912_section_{section}.json") == plain


# --- Failure modes ---------------------------------------------------------------------


def test_an_unresolvable_pmid_is_reported_as_a_500() -> None:
    """A permanent condition dressed as a server error — it must not be retried (ADR-005)."""
    body = load_fixture("publication_unresolvable.json")
    assert body == {"detail": "Can not retrieve publications : Publication not found"}
    probe = next(p for p in load_fixture("probes.json")
                 if p["label"] == "publication: pmid that does not resolve")
    assert probe["status"] == 500


def test_a_non_numeric_pmid_is_reported_as_a_404() -> None:
    body = load_fixture("publication_non_numeric.json")
    assert body == {"detail": "This resource is not available"}
    probe = next(p for p in load_fixture("probes.json")
                 if p["label"] == "publication: non-numeric pmid")
    assert probe["status"] == 404


# --- Our own contract ------------------------------------------------------------------


def test_answer_defaults_are_the_empty_grounded_answer() -> None:
    answer = Answer(text="")
    assert answer.citations == []
    assert answer.insufficient_context is False
    assert answer.warnings == []


def test_citation_resolves_to_a_pubmed_url() -> None:
    assert Citation(pmid=27863244).url == "https://pubmed.ncbi.nlm.nih.gov/27863244/"


def test_fixtures_directory_is_populated() -> None:
    assert FIXTURES.is_dir()
    assert len(sentence_fixtures()) >= 3
    assert len(publication_fixtures()) >= 3


# --- Entities (Trello: return entity ids) ----------------------------------------------


def test_entities_parse_start_length_type_id() -> None:
    hit = SentenceHit(
        text="TP53 mutations drive cancer.",
        score=0.9,
        annotations=["0|4|gene|7157", "21|6|disease|MESH:D009369"],
    )
    assert [e.model_dump() for e in hit.entities] == [
        {"text": "TP53", "type": "gene", "id": "7157"},
        {"text": "cancer", "type": "disease", "id": "MESH:D009369"},
    ]


def test_entity_ids_may_contain_pipes_and_malformed_annotations_are_skipped() -> None:
    hit = SentenceHit(
        text="0123456789",
        score=0.9,
        annotations=[
            "0|3|chemical|MESH:D1|extra",  # id keeps everything after the third pipe
            "not-an-annotation",
            "x|3|gene|1",  # non-numeric start
            "2|0|gene|1",  # zero length
            "4|2|gene|",  # empty id
            "8|5|gene|42",  # runs past the end: text truncates, id kept
        ],
    )
    assert [(e.text, e.type, e.id) for e in hit.entities] == [
        ("012", "chemical", "MESH:D1|extra"),
        ("89", "gene", "42"),
    ]


def test_hits_without_annotations_have_no_entities() -> None:
    assert SentenceHit(text="t", score=0.9).entities == []
    assert SentenceHit(text="t", score=0.9, annotations=[]).entities == []


@pytest.mark.parametrize("path", sentence_fixtures(), ids=lambda p: p.stem[:40])
def test_captured_annotations_parse_into_entities(path: Path) -> None:
    """Every annotated hit in every fixture yields entities with non-empty type and id."""
    hits = [SentenceHit.model_validate(h) for h in json.loads(path.read_text(encoding="utf-8"))]
    annotated = [h for h in hits if h.annotations]
    for hit in annotated:
        for entity in hit.entities:
            assert entity.type and entity.id


# --- BioC-PMC full text (ADR-009) ------------------------------------------------------


def test_the_captured_full_text_fixture_parses_and_yields_a_narrative_body() -> None:
    payload = load_fixture("pmc_fulltext_bioc-pmc_fixture_article.json")
    document = payload[0]["documents"][0]
    full = FullText.model_validate({"pmcid": "PMC5320931", **document})
    assert len(full.passages) == 222  # as captured
    body = full.body(max_chars=30_000)
    assert body is not None
    assert len(body) <= 30_000
    assert "WNT5A" in body  # the article is about WNT5A — the narrative made it in


def test_the_body_cap_cuts_at_a_passage_boundary_and_truncates_the_last() -> None:
    full = FullText(
        pmcid="PMC1",
        passages=[
            {"infons": {"section_type": "INTRO"}, "text": "12345"},
            {"infons": {"section_type": "RESULTS"}, "text": "abcdefghij"},
            {"infons": {"section_type": "REF"}, "text": "never included"},
        ],
    )
    # The cap bounds the JOINED string: separators count, the last passage is truncated.
    assert full.body(max_chars=8) == "12345\n\na"
    assert full.body(max_chars=100) == "12345\n\nabcdefghij"


def test_a_full_text_without_narrative_sections_has_no_body() -> None:
    full = FullText(
        pmcid="PMC1",
        passages=[{"infons": {"section_type": "REF"}, "text": "refs only"}],
    )
    assert full.body(max_chars=100) is None
