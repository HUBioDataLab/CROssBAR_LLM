"""How a Paperclip answer cites papers, and how its reference list is built.

The case these pin down was reported against the merged orchestrator: an
answer that used only the third, fifth and sixth retrieved papers read
"[3, 5, 6]", and wrote its own `References:` list into the text while the API
returned all six papers as citations.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from crossbar_llm.paperclip_tools.adapter import PaperMeta
from crossbar_llm.paperclip_tools.agent import _format_documents, build_graph
from crossbar_llm.paperclip_tools.answer_citations import (
    resolve_answer_citations,
    source_labels,
    strip_reference_section,
)
from crossbar_llm.paperclip_tools.schemas import (
    Citation,
    PaperclipCitedSource,
    PaperclipSynthesis,
    PaperContext,
)
from crossbar_llm.paperclip_tools.tests.test_agent import FakeAdapter, _router


def _citation(n, doc_id, *, pmid=None, pmcid=None, doi=None, url=None):
    return Citation(
        ref_num=n, doc_id=doc_id, pmid=pmid, pmcid=pmcid, doi=doi,
        url=url or f"https://citations.gxl.ai/papers/{doc_id}",
    )


# Six retrieved papers; the answer below uses the 3rd, 5th and 6th.
SIX = [
    _citation(1, "PMC100", pmid="100"),
    _citation(2, "PMC200", pmid="200"),
    _citation(3, "PMC3771250", pmid="24069534", doi="10.1155/2013/613086"),
    _citation(4, "PMC400", pmid="400"),
    _citation(5, "PMC11122105", doi="10.3390/jpm14050535"),
    _citation(6, "PMC9026189", pmid="35694715"),
]


def test_labels_prefer_pmid_then_pmcid_then_doi_then_doc_id():
    labels = source_labels([
        _citation(1, "PMC1", pmid="11", doi="10.1/a"),
        _citation(2, "PMC2", doi="10.1/b"),
        _citation(3, "oa_W3", doi="10.1/c"),
        _citation(4, "fda_abc"),
        _citation(5, "PMC5", pmid="not-a-pmid"),  # malformed: skipped
        _citation(6, "PMC6", pmid="11"),           # same PMID as PMC1
    ])
    assert labels == {
        "PMC1": "PMID:11",
        "PMC2": "PMCID:PMC2",
        "oa_W3": "DOI:10.1/c",
        "fda_abc": "Paperclip:fda_abc",
        "PMC5": "PMCID:PMC5",
        "PMC6": "PMCID:PMC6",
    }


def test_evidence_is_labelled_by_identifier_not_by_position():
    docs = [PaperContext(doc_id=c.doc_id, meta=PaperMeta(document_id=c.doc_id, title=c.doc_id))
            for c in SIX]
    evidence = _format_documents({"documents": docs, "citations": SIX})
    assert "[PMID:24069534] PMC3771250" in evidence
    assert "[PMCID:PMC11122105] PMC11122105" in evidence
    assert "[3]" not in evidence
    # URLs are no longer the model's business: it writes no reference list.
    assert "URL:" not in evidence


def test_reported_answer_cites_three_papers_numbered_from_one():
    answer = (
        "Psoriasis is polygenic; reviews name TNFα, IL23 and PSORS1 "
        "[PMID:24069534, PMCID:PMC11122105, PMID:35694715].\n\n"
        "References:\n"
        "[PMID:24069534] Prieto-Pérez R. Genetics of Psoriasis. — https://citations.gxl.ai/papers/PMC3771250\n"
        "[PMCID:PMC11122105] Dascălu RC. Review. — https://citations.gxl.ai/papers/PMC11122105"
    )
    text, citations, warnings = resolve_answer_citations(answer, SIX)
    assert text == (
        "Psoriasis is polygenic; reviews name TNFα, IL23 and PSORS1 "
        "[PMID:24069534, PMCID:PMC11122105, PMID:35694715]."
    )
    assert [c.doc_id for c in citations] == ["PMC3771250", "PMC11122105", "PMC9026189"]
    assert [c.ref_num for c in citations] == [1, 2, 3]
    assert warnings == []


def test_citation_order_follows_the_answer_not_retrieval():
    answer = "B [PMID:35694715]. A [PMID:100]. B again [PMID:35694715]."
    _, citations, _ = resolve_answer_citations(answer, SIX)
    assert [c.doc_id for c in citations] == ["PMC9026189", "PMC100"]


def test_a_paper_can_be_cited_by_any_of_its_identifiers():
    answer = "X [DOI:10.1155/2013/613086]. Y [PMCID:PMC9026189]."
    _, citations, _ = resolve_answer_citations(answer, SIX)
    assert [c.doc_id for c in citations] == ["PMC3771250", "PMC9026189"]


def test_an_invented_identifier_is_dropped_and_reported():
    _, citations, warnings = resolve_answer_citations("X [PMID:999, PMID:100].", SIX)
    assert [c.doc_id for c in citations] == ["PMC100"]
    assert len(warnings) == 1 and "PMID:999" in warnings[0]


def test_no_citations_when_the_answer_cites_nothing():
    text, citations, _ = resolve_answer_citations(
        "The retrieved papers do not address this question.", SIX
    )
    assert citations == []
    assert text == "The retrieved papers do not address this question."


def test_models_list_fills_in_only_when_the_answer_has_no_inline_citations():
    cited = [PaperclipCitedSource(source="PMID:400"), PaperclipCitedSource(source="PMID:100")]
    _, citations, _ = resolve_answer_citations("No markers here.", SIX, cited=cited)
    assert [c.doc_id for c in citations] == ["PMC400", "PMC100"]
    # With inline citations, the text wins: the list cannot add a paper the
    # reader never saw cited.
    _, citations, _ = resolve_answer_citations("X [PMID:200].", SIX, cited=cited)
    assert [c.doc_id for c in citations] == ["PMC200"]


def test_doi_with_parentheses_survives_parsing():
    paper = _citation(1, "oa_W1", doi="10.1016/S0140-6736(20)30183-5")
    _, citations, _ = resolve_answer_citations(
        "Early cases (see [DOI:10.1016/S0140-6736(20)30183-5]).", [paper]
    )
    assert [c.doc_id for c in citations] == ["oa_W1"]


def test_reference_headings_are_stripped_but_prose_is_not():
    for heading in ("References:", "**References**", "## Sources", "References"):
        assert strip_reference_section(f"Answer [PMID:1].\n\n{heading}\n- PMID:1") == (
            "Answer [PMID:1]."
        )
    prose = "Answer.\nReferences to IL-17 recur across studies [PMID:1]."
    assert strip_reference_section(prose) == prose
    # Nothing but a list: there is no answer to keep, so it is left as is.
    assert strip_reference_section("References:\n- PMID:1") == "References:\n- PMID:1"


def test_line_anchor_is_added_only_for_lines_shown_in_the_evidence():
    paper = _citation(1, "PMC1", pmid="11")
    mapped = _citation(2, "PMC2", pmid="22", url="https://citations.gxl.ai/papers/PMC2#L7")
    docs = [
        PaperContext(doc_id="PMC1", meta=PaperMeta(document_id="PMC1"),
                     body="L45: first\nL46: second\nL47: third"),
        PaperContext(doc_id="PMC2", meta=PaperMeta(document_id="PMC2"), body="L7: mapped"),
    ]
    cited = [
        PaperclipCitedSource(source="PMID:11", lines="L45-L46, L900"),  # L900 not shown
        PaperclipCitedSource(source="PMID:22", lines="L7"),
    ]
    _, citations, _ = resolve_answer_citations(
        "X [PMID:11]. Y [PMID:22].", [paper, mapped], documents=docs, cited=cited
    )
    assert citations[0].url == "https://citations.gxl.ai/papers/PMC1#L45-L46"
    # A map extraction's own anchor is kept as Paperclip pinned it.
    assert citations[1].url == "https://citations.gxl.ai/papers/PMC2#L7"


def _chat_model(*, structured, prose="unused"):
    """Structured output returns `structured`; a plain call returns `prose`."""
    model = RunnableLambda(lambda _prompt: AIMessage(content=prose))
    model.with_structured_output = lambda schema, **kwargs: RunnableLambda(
        lambda _values: structured
    )
    return model


async def test_graph_returns_only_the_cited_papers_in_citation_order():
    synthesis = PaperclipSynthesis(
        answer="Y [PMCID:PMC2]. X [PMCID:PMC1].",
        cited=[PaperclipCitedSource(source="PMCID:PMC2"), PaperclipCitedSource(source="PMCID:PMC1")],
    )
    graph = build_graph(chat_model=_chat_model(structured=synthesis), router=_router(),
                        adapter=FakeAdapter())
    out = await graph.ainvoke({"question": "What treats X?", "warnings": []})
    assert out["final_answer"] == "Y [PMCID:PMC2]. X [PMCID:PMC1]."
    assert [(c.ref_num, c.doc_id) for c in out["citations"]] == [(1, "PMC2"), (2, "PMC1")]


async def test_graph_reads_citations_from_prose_when_structured_output_fails():
    prose = "Only the first applies [PMCID:PMC1].\n\nReferences:\n[PMCID:PMC1] Paper one"
    graph = build_graph(chat_model=_chat_model(structured=None, prose=prose),
                        router=_router(), adapter=FakeAdapter())
    out = await graph.ainvoke({"question": "What treats X?", "warnings": []})
    assert out["final_answer"] == "Only the first applies [PMCID:PMC1]."
    assert [c.doc_id for c in out["citations"]] == ["PMC1"]
    assert any("citations were read from the answer text" in w for w in out["warnings"])


def test_prompt_asks_for_labels_and_no_reference_section():
    from crossbar_llm.paperclip_tools.prompts import PAPERCLIP_SYNTHESIZE_SYSTEM_PROMPT as prompt

    assert "Do NOT write a `References:`" in prompt
    assert "[PMID:12345678]" in prompt
    assert "ALWAYS end with a `References:`" not in prompt
