"""`synthesize` and `validate` (build order step 4), with a fake synthesizer — no LLM, no network.

`validate` is where invariant 3 lives: a citation the model invented must never survive.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import pytest

from crossbar_llm.litsense_tools.graph.nodes import NO_CONTEXT_ANSWER, synthesize, validate
from crossbar_llm.litsense_tools.models import ArticleContext, Entity, SynthesisOutput
from crossbar_llm.litsense_tools.prompts import Message, render_article, synthesis_messages


def article(pmid: int = 1, **overrides: object) -> ArticleContext:
    defaults: dict[str, object] = {
        "pmid": pmid,
        "title": f"Title {pmid}",
        "journal": "Cell",
        "date": datetime(2016, 11, 17),
        "section": "abstract",
        "text": f"Abstract text {pmid}.",
        "matched_sentences": [f"Matched sentence {pmid}."],
    }
    return ArticleContext(**{**defaults, **overrides})  # type: ignore[arg-type]


class FakeSynthesizer:
    """Returns a scripted output and records the messages it was called with."""

    def __init__(self, output: SynthesisOutput) -> None:
        self.output = output
        self.calls: list[list[Message]] = []

    async def __call__(self, messages: Sequence[Message]) -> SynthesisOutput:
        self.calls.append(list(messages))
        return self.output


# --- prompt rendering ------------------------------------------------------------------


def test_context_blocks_carry_pmid_text_and_matched_sentences() -> None:
    block = render_article(article(42))
    assert "[PMID 42]" in block
    assert "Title 42" in block
    assert "Abstract text 42." in block
    assert "- Matched sentence 42." in block
    assert "Cell, 2016" in block


def test_an_article_without_text_still_renders_its_matched_sentences() -> None:
    block = render_article(article(7, text=None))
    assert "(abstract not available for this article)" in block
    assert "- Matched sentence 7." in block


def test_messages_are_system_then_human_and_include_the_question() -> None:
    messages = synthesis_messages("What does TP53 do?", [article(1), article(2)])
    assert [role for role, _ in messages] == ["system", "human"]
    assert "What does TP53 do?" in messages[1][1]
    assert "[PMID 1]" in messages[1][1]
    assert "[PMID 2]" in messages[1][1]


# --- synthesize ------------------------------------------------------------------------


async def test_synthesize_passes_the_rendered_messages_to_the_model() -> None:
    fake = FakeSynthesizer(SynthesisOutput(text="answer", citations=[1]))
    output = await synthesize("question?", [article(1)], fake)
    assert output.text == "answer"
    assert len(fake.calls) == 1
    assert fake.calls[0] == synthesis_messages("question?", [article(1)])


async def test_zero_articles_short_circuits_without_an_llm_call() -> None:
    """Invariant 6: zero evidence is a valid outcome, and the model must not be consulted."""
    fake = FakeSynthesizer(SynthesisOutput(text="should never be produced"))
    output = await synthesize("question?", [], fake)
    assert fake.calls == []
    assert output.insufficient_context is True
    assert output.text == NO_CONTEXT_ANSWER
    assert output.citations == []


# --- validate --------------------------------------------------------------------------


def test_valid_citations_pass_through_in_order() -> None:
    answer = validate(SynthesisOutput(text="a", citations=[2, 1]), fetched_pmids={1, 2, 3})
    assert answer.citations == [2, 1]
    assert answer.warnings == []


def test_a_hallucinated_citation_is_dropped_and_recorded() -> None:
    answer = validate(SynthesisOutput(text="a", citations=[1, 999]), fetched_pmids={1})
    assert answer.citations == [1]
    assert len(answer.warnings) == 1
    assert "999" in answer.warnings[0]


def test_duplicate_citations_collapse_to_the_first_occurrence() -> None:
    answer = validate(SynthesisOutput(text="a", citations=[2, 1, 2, 1]), fetched_pmids={1, 2})
    assert answer.citations == [2, 1]


def test_pipeline_warnings_are_carried_and_the_flag_passes_through() -> None:
    answer = validate(
        SynthesisOutput(text="a", insufficient_context=True),
        fetched_pmids=set(),
        warnings=["fetch failed for pmid 5"],
    )
    assert answer.insufficient_context is True
    assert answer.warnings == ["fetch failed for pmid 5"]


def test_validate_never_invents_citations() -> None:
    answer = validate(SynthesisOutput(text="a"), fetched_pmids={1, 2})
    assert answer.citations == []


@pytest.mark.parametrize("fetched", [set(), {1}], ids=["nothing-fetched", "one-fetched"])
def test_all_hallucinated_citations_leave_an_empty_list(fetched: set[int]) -> None:
    answer = validate(SynthesisOutput(text="a", citations=[998, 999]), fetched_pmids=fetched)
    assert answer.citations == []
    assert len(answer.warnings) == 1


# --- output style ----------------------------------------------------------------------


def test_bare_style_appends_the_override_and_prose_does_not() -> None:
    prose = synthesis_messages("q", [article(1)])
    bare = synthesis_messages("q", [article(1)], style="bare")
    assert "ONLY the requested term(s)" not in prose[0][1]
    assert "ONLY the requested term(s)" in bare[0][1]
    assert bare[1][1] == prose[1][1]  # the evidence block is identical


async def test_synthesize_threads_the_style_through() -> None:
    fake = FakeSynthesizer(SynthesisOutput(text="a"))
    await synthesize("q", [article(1)], fake, style="bare")
    assert "ONLY the requested term(s)" in fake.calls[0][0][1]


# --- entities on the answer ------------------------------------------------------------


def entity(id_: str) -> Entity:
    return Entity(text=f"t{id_}", type="gene", id=id_)


def test_entities_come_from_cited_articles_only() -> None:
    articles = [
        article(1, entities=[entity("a")]),
        article(2, entities=[entity("b")]),
    ]
    answer = validate(
        SynthesisOutput(text="x", citations=[1]), fetched_pmids={1, 2}, articles=articles
    )
    assert [e.id for e in answer.entities] == ["a"]


def test_without_citations_entities_fall_back_to_every_article() -> None:
    articles = [article(1, entities=[entity("a")]), article(2, entities=[entity("b")])]
    answer = validate(SynthesisOutput(text="x"), fetched_pmids={1, 2}, articles=articles)
    assert [e.id for e in answer.entities] == ["a", "b"]


def test_duplicate_entities_across_articles_collapse() -> None:
    articles = [article(1, entities=[entity("a")]), article(2, entities=[entity("a")])]
    answer = validate(
        SynthesisOutput(text="x", citations=[1, 2]), fetched_pmids={1, 2}, articles=articles
    )
    assert [e.id for e in answer.entities] == ["a"]
