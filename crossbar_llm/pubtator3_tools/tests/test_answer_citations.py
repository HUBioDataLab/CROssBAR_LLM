"""How a PubTator3 answer's inline PMIDs become the run's reference list.

The answer used to end with a `References:` section the prompt required, which
duplicated the citations the API already returns separately.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from crossbar_llm.pubtator3_tools.agent import build_graph
from crossbar_llm.pubtator3_tools.answer_citations import resolve_answer_pmids
from crossbar_llm.pubtator3_tools.schemas import PubTator3Synthesis, RouterDecision
from crossbar_llm.pubtator3_tools.tests.test_graph import (
    _make_fake_router,
    _search_and_export_mocks,
)

# The answer reported against the merged orchestrator, trimmed.
REPORTED = (
    "Genes linked to psoriasis include IL22 and LCE3C [PMID:34853291], "
    "IL17A [PMID:34853779] and TNF [PMID:35801072, PMID:37664349].\n\n"
    "References:\n"
    "- PMID:34853291 — https://pubmed.ncbi.nlm.nih.gov/34853291/\n"
    "- PMID:34853779 — https://pubmed.ncbi.nlm.nih.gov/34853779/"
)
EVIDENCE = [34853291, 34853779, 35801072, 37664349, 36457676]


def test_reported_answer_loses_its_reference_section():
    text, pmids, warnings = resolve_answer_pmids(REPORTED, EVIDENCE)
    assert "References" not in text
    assert text.endswith("TNF [PMID:35801072, PMID:37664349].")
    # Cited order, not retrieval order; 36457676 was retrieved but not cited.
    assert pmids == ["34853291", "34853779", "35801072", "37664349"]
    assert warnings == []


def test_a_pmid_outside_the_evidence_is_dropped_and_reported():
    _, pmids, warnings = resolve_answer_pmids("X [PMID:34853291, PMID:999].", EVIDENCE)
    assert pmids == ["34853291"]
    assert len(warnings) == 1 and "PMID:999" in warnings[0]


def test_models_list_fills_in_only_without_inline_citations():
    _, pmids, _ = resolve_answer_pmids(
        "No markers.", EVIDENCE, cited=["PMID:36457676", "34853291"]
    )
    assert pmids == ["36457676", "34853291"]
    _, pmids, _ = resolve_answer_pmids("X [PMID:34853779].", EVIDENCE, cited=["36457676"])
    assert pmids == ["34853779"]


def _chat_model(structured):
    model = RunnableLambda(lambda _prompt: AIMessage(content="unused"))
    model.with_structured_output = lambda schema, **kwargs: RunnableLambda(
        lambda _values: structured
    )
    return model


async def test_graph_records_the_cited_pmids(httpx_mock, fx):
    _search_and_export_mocks(httpx_mock, fx)
    synthesis = PubTator3Synthesis(
        answer=(
            "Imatinib causes edema [PMID:33849366, PMID:1].\n\n"
            "References:\n- PMID:33849366"
        ),
        cited_pmids=["33849366", "1"],
    )
    graph = build_graph(
        chat_model=_chat_model(synthesis),
        router=_make_fake_router(
            RouterDecision(question_type="keyword_search", keyword_query="imatinib")
        ),
        abstracts_only=True,
    )
    final = await graph.ainvoke({"question": "Side effects of imatinib?", "warnings": []})
    assert final["final_answer"] == "Imatinib causes edema [PMID:33849366, PMID:1]."
    assert final["cited_pmids"] == ["33849366"]
    assert any("the answer cited PMID:1, which is not" in w for w in final["warnings"])


def test_prompt_asks_for_no_reference_section():
    from crossbar_llm.pubtator3_tools.prompts import SYNTHESIZE_SYSTEM_PROMPT as prompt

    assert "Do NOT write a `References:`" in prompt
    assert "ALWAYS end the answer with a `References:`" not in prompt
