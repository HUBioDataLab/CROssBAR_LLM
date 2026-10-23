"""The `citations` the API returns for a literature tool are the papers its
answer cites, in the order it cites them — not every paper retrieved."""
from __future__ import annotations

from types import SimpleNamespace

from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.services.literature_service import LiteratureService
from crossbar_llm.paperclip_tools.schemas import Citation


def _service(**overrides) -> LiteratureService:
    settings = Settings()
    for name, value in overrides.items():
        setattr(settings, name, value)
    return LiteratureService(settings)


def _documents(*pmids):
    return [SimpleNamespace(pmid=int(p), title=f"paper {p}", pmcid=None) for p in pmids]


def test_pubtator3_citations_follow_the_answer():
    result = _service()._normalize(
        "pubtator3",
        {
            "final_answer": "X [PMID:3]. Y [PMID:1].",
            "documents": _documents(1, 2, 3),
            "cited_pmids": ["3", "1"],
        },
        {},
        "pubtator3.",
    )
    assert [c["pmid"] for c in result.citations] == ["3", "1"]
    assert result.citations[0] == {
        "pmid": "3",
        "title": "paper 3",
        "pmcid": None,
        "url": "https://pubmed.ncbi.nlm.nih.gov/3/",
    }


def test_pubtator3_answer_citing_nothing_returns_no_citations():
    result = _service()._normalize(
        "pubtator3",
        {"final_answer": "Not supported.", "documents": _documents(1, 2), "cited_pmids": []},
        {},
        "pubtator3.",
    )
    assert result.citations == []


def test_pubtator3_without_a_synthesis_step_lists_every_document():
    result = _service()._normalize(
        "pubtator3", {"final_answer": None, "documents": _documents(1, 1, 2)}, {}, "pubtator3."
    )
    assert [c["pmid"] for c in result.citations] == ["1", "2"]


def test_citations_are_capped():
    result = _service(literature_max_citations=2)._normalize(
        "pubtator3",
        {"final_answer": "", "documents": _documents(1, 2, 3), "cited_pmids": ["3", "2", "1"]},
        {},
        "pubtator3.",
    )
    assert [c["pmid"] for c in result.citations] == ["3", "2"]


def test_paperclip_citations_are_passed_through_in_answer_order():
    cited = [
        Citation(ref_num=1, doc_id="PMC9", pmid="9", url="https://citations.gxl.ai/papers/PMC9"),
        Citation(ref_num=2, doc_id="PMC4", pmid="4", url="https://citations.gxl.ai/papers/PMC4"),
    ]
    result = _service()._normalize(
        "paperclip", {"final_answer": "X [PMID:9]. Y [PMID:4].", "citations": cited}, {}, "paperclip."
    )
    assert [(c["ref_num"], c["doc_id"]) for c in result.citations] == [(1, "PMC9"), (2, "PMC4")]
