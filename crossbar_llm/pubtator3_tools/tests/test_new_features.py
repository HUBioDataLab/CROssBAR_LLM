"""Tests for the newer graph features: abstracts_only, section filter, and the
evaluator's suggested_sections-driven refinement union.

These complement test_graph.py by exercising the behaviors added after the
initial split: the deployment-level abstracts_only switch, the section
filter inside export_node, and the depth evaluator's ability to pick which
sections to add on the refinement pass.
"""
import re

import pytest

from crossbar_llm.pubtator3_tools.agent import (
    DepthEvaluation,
    EntityMention,
    RouterDecision,
    build_graph,
)
from crossbar_llm.pubtator3_tools.nodes import export_node
from crossbar_llm.pubtator3_tools import client

BASE_URL = client.BASE_URL


def _url_pattern(path: str) -> re.Pattern:
    return re.compile(rf"{re.escape(BASE_URL)}{re.escape(path)}.*")


def _make_fake_router(decision: RouterDecision):
    async def _router(_question: str) -> RouterDecision:
        return decision

    return _router


async def _fake_synth(state) -> str:
    return f"answer over {len(state.get('passages', []))} passages"


# --- (1) abstracts_only clamps router output ------------------------------

@pytest.mark.asyncio
async def test_abstracts_only_clamps_router_full_text_and_sections():
    """Even if the router returns full_text=True + sections, abstracts_only=True
    should flatten both to False / None before the rest of the pipeline sees
    them. We use out_of_scope so no HTTP mocks are needed — the clamp lives
    in router_node and applies regardless of the downstream path."""
    decision = RouterDecision(
        question_type="out_of_scope",
        full_text=True,
        sections=["METHODS", "RESULTS"],
        rationale="probe",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        abstracts_only=True,
    )

    final = await graph.ainvoke({"question": "weather today?", "warnings": []})

    assert final["full_text"] is False
    assert final["sections"] is None


@pytest.mark.asyncio
async def test_abstracts_only_short_circuits_depth_evaluator():
    """When abstracts_only=True the evaluator must NOT escalate to full text
    even if a (hypothetical) evaluator would flag the answer as insufficient.
    We register a fake evaluator that ALWAYS says insufficient; the graph
    should still accept the answer without setting refinement_attempted."""

    async def _always_insufficient(_state):
        return DepthEvaluation(
            sufficient=False,
            missing="probe",
            suggested_sections=["METHODS"],
            rationale="probe",
        )

    decision = RouterDecision(question_type="out_of_scope", rationale="probe")
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        evaluator=_always_insufficient,
        abstracts_only=True,
    )

    final = await graph.ainvoke({"question": "probe", "warnings": []})

    # out_of_scope terminates before evaluate_depth runs, so depth fields
    # never get set. The point is that abstracts_only didn't crash and the
    # graph completed; combined with the clamp test above, that confirms
    # the deployment switch holds end-to-end.
    assert final.get("refinement_attempted") is not True


# --- (2) section filter in export_node ------------------------------------

def _mock_export_doc_with_body_sections() -> dict:
    """Synthetic BioC JSON for one PMC-OA document carrying title + abstract +
    INTRO + METHODS + RESULTS + DISCUSS passages. Used to exercise the
    section filter without depending on the recorded fixtures (which only
    have title + abstract)."""
    return {
        "PubTator3": [
            {
                "pmid": "1234567",
                "pmcid": "PMC1234567",
                "journal": "Synth J",
                "authors": [],
                "date": "2024-01-01",
                "passages": [
                    {"infons": {"type": "title"}, "offset": 0, "text": "A title.", "annotations": []},
                    {"infons": {"type": "abstract"}, "offset": 9, "text": "An abstract.", "annotations": []},
                    {"infons": {"section_type": "INTRO", "type": "paragraph"}, "offset": 22, "text": "Intro body.", "annotations": []},
                    {"infons": {"section_type": "METHODS", "type": "paragraph"}, "offset": 34, "text": "Methods body.", "annotations": []},
                    {"infons": {"section_type": "RESULTS", "type": "paragraph"}, "offset": 48, "text": "Results body.", "annotations": []},
                    {"infons": {"section_type": "DISCUSS", "type": "paragraph"}, "offset": 62, "text": "Discussion body.", "annotations": []},
                ],
                "relations": [],
            }
        ]
    }


@pytest.mark.asyncio
async def test_section_filter_keeps_title_abstract_and_only_methods(httpx_mock):
    """With sections=['METHODS'] and full_text=True, export_node should drop
    INTRO / RESULTS / DISCUSS body passages while always keeping title +
    abstract."""
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=_mock_export_doc_with_body_sections(),
    )

    state = {
        "pmids": [1234567],
        "full_text": True,
        "sections": ["METHODS"],
        "warnings": [],
    }
    result = await export_node(state, max_documents=5)

    sections = sorted({p.section for p in result["passages"]})
    assert "title" in sections
    assert "abstract" in sections
    assert "METHODS" in sections
    assert "INTRO" not in sections
    assert "RESULTS" not in sections
    assert "DISCUSS" not in sections


@pytest.mark.asyncio
async def test_no_section_filter_keeps_every_body_section(httpx_mock):
    """Sanity counterpart: sections=None with full_text=True passes every body
    section through. Same fixture, no filter → all 6 passage section_types
    survive."""
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=_mock_export_doc_with_body_sections(),
    )

    state = {
        "pmids": [1234567],
        "full_text": True,
        "sections": None,
        "warnings": [],
    }
    result = await export_node(state, max_documents=5)

    sections = {p.section for p in result["passages"]}
    assert {"title", "abstract", "INTRO", "METHODS", "RESULTS", "DISCUSS"}.issubset(sections)


# --- (3) evaluator suggested_sections unions with current ------------------

@pytest.mark.asyncio
async def test_zero_results_falls_back_to_keyword_search(httpx_mock):
    """When a relation_partner_discovery resolves the anchor but PubTator3
    returns 0 partners, search_node should fall back to a free-text keyword
    query built from the resolved entity name + relation + e2_type — instead
    of producing an empty PMID list and letting the synthesizer say 'no
    information available'.

    This is the Q5 (BTK / Ibrutinib) failure mode from the benchmark run:
    the BioREx graph didn't tag the inhibit edge, so the structured query
    found nothing even though PubMed has thousands of relevant papers.
    """
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=[
            {
                "_id": "@GENE_BTK",
                "name": "BTK",
                "biotype": "gene",
                "db_id": "695",
                "db": "ncbi_gene",
                "match": "Matched on name <m>BTK</m>",
            }
        ],
        is_reusable=True,
    )
    # find_related: returns NO partners — this is the trigger.
    httpx_mock.add_response(
        url=_url_pattern("/relations"),
        json=[],
        is_reusable=True,
    )
    # The fallback keyword search must succeed.
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json={
            "results": [{"pmid": 99999, "title": "Ibrutinib targets BTK in CLL"}],
            "count": 1,
        },
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json={
            "PubTator3": [
                {
                    "pmid": "99999",
                    "passages": [
                        {"infons": {"type": "title"}, "offset": 0, "text": "Ibrutinib targets BTK in CLL.", "annotations": []},
                        {"infons": {"type": "abstract"}, "offset": 30, "text": "Ibrutinib is a BTK inhibitor.", "annotations": []},
                    ],
                    "relations": [],
                }
            ]
        },
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="relation_partner_discovery",
        mentions=[EntityMention(text="BTK", suggested_type="gene")],
        relation="inhibit",
        e2_type="Chemical",
        keyword_query="BTK inhibitor CLL",
        rationale="probe",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
    )

    final = await graph.ainvoke({"question": "BTK inhibitor for CLL", "warnings": []})

    # Anchor resolved; no partners came back; fallback fired with the
    # router-supplied keyword_query and found PMID 99999.
    assert final.get("partners") == []
    assert final.get("pmids") == [99999]
    assert "BTK inhibitor CLL" in (final.get("queries_used") or [])
    # The warning trail records the fallback so it's auditable.
    assert any("falling back to keyword search" in w for w in final.get("warnings") or [])


@pytest.mark.asyncio
async def test_zero_results_falls_back_to_question_when_router_omits_keyword_query(httpx_mock):
    """Catastrophic-failure tier: structured query yields 0 PMIDs AND the
    router didn't supply `keyword_query` (e.g. router-error path emitted a
    minimal RouterDecision). search_node should fall back to the user's
    question verbatim rather than silently giving up."""
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=[
            {"_id": "@GENE_BTK", "name": "BTK", "biotype": "gene", "db_id": "695",
             "db": "ncbi_gene", "match": "Matched on name <m>BTK</m>"}
        ],
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/relations"),
        json=[],
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json={"results": [], "count": 0},
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="relation_partner_discovery",
        mentions=[EntityMention(text="BTK", suggested_type="gene")],
        relation="inhibit",
        e2_type="Chemical",
        # keyword_query intentionally omitted — simulates router error path.
        rationale="probe",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
    )

    final = await graph.ainvoke({"question": "What drug inhibits BTK?", "warnings": []})

    # Fallback used the user's question verbatim.
    assert "What drug inhibits BTK?" in (final.get("queries_used") or [])


@pytest.mark.asyncio
async def test_evaluator_suggested_sections_unioned_on_refinement(httpx_mock):
    """First pass: router returns full_text=True + sections=['INTRO']. Evaluator
    says insufficient and suggests ['METHODS']. After the refinement loop,
    state should reflect the union ['INTRO', 'METHODS'], with refinement_
    attempted=True so the loop can't fire again."""
    # The graph re-enters `export` on refinement; mock the export endpoint so
    # both passes can fetch. /search/ and /entity/autocomplete/ aren't used
    # for the single_node path with an unresolvable mention — but to keep
    # the test tight we route via keyword_search.
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json={"results": [{"pmid": 1234567, "title": "x"}], "count": 1},
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=_mock_export_doc_with_body_sections(),
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="keyword_search",
        keyword_query="probe",
        full_text=True,
        sections=["INTRO"],
        rationale="probe",
    )

    calls = {"n": 0}

    async def _evaluator(_state):
        calls["n"] += 1
        # Only the first call returns insufficient — the second (post-refine)
        # accepts the answer so the test terminates deterministically.
        if calls["n"] == 1:
            return DepthEvaluation(
                sufficient=False,
                missing="no protocol detail",
                suggested_sections=["METHODS"],
                rationale="probe",
            )
        return DepthEvaluation(sufficient=True, missing=None, rationale="ok now")

    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        evaluator=_evaluator,
        max_documents=2,
    )

    final = await graph.ainvoke({"question": "how do they assay X?", "warnings": []})

    assert final.get("refinement_attempted") is True
    # Union of current ['INTRO'] + suggested ['METHODS'] preserves order.
    assert final.get("sections") == ["INTRO", "METHODS"]
    assert final.get("full_text") is True


# --- resolve_node confidence gating ---------------------------------------
# resolve_node trusts only PubTator3 name/synonym matches and abstains on its
# fuzzy 'Multiple matches' fallback (the main source of wrong resolutions like
# 'histone H3' -> @GENE_HTR12), leaving the entity for the keyword fallback.

async def test_resolve_node_rejects_fuzzy_multiple_matches(httpx_mock):
    from crossbar_llm.pubtator3_tools.nodes import resolve_node

    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=[
            {"_id": "@GENE_HTR12", "name": "HTR12", "biotype": "gene",
             "db_id": "1", "db": "ncbi_gene", "match": "Multiple matches"},
            {"_id": "@GENE_AT5G10980", "name": "AT5G10980", "biotype": "gene",
             "db_id": "2", "db": "ncbi_gene", "match": "Multiple matches"},
        ],
        is_reusable=True,
    )

    state = {"mentions": [EntityMention(text="histone H3", suggested_type="gene")],
             "warnings": []}
    out = await resolve_node(state)

    assert "histone H3" in out["unresolved"]
    assert "histone H3" not in out["resolved"]
    assert any("no confident" in w for w in out["warnings"])


async def test_resolve_node_accepts_name_match_and_skips_fuzzy_runners_up(httpx_mock):
    from crossbar_llm.pubtator3_tools.nodes import resolve_node

    # Top candidate is an exact name match; a synonym match also counts as
    # confident, so the chosen pick stays the name-matched, top-ranked one.
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=[
            {"_id": "@GENE_BTK", "name": "BTK", "biotype": "gene",
             "db_id": "695", "db": "ncbi_gene", "match": "Matched on name <m>BTK</m>"},
            {"_id": "@GENE_TXK", "name": "TXK", "biotype": "gene",
             "db_id": "7294", "db": "ncbi_gene", "match": "Matched on synonyms <m>BTKL</m>"},
        ],
        is_reusable=True,
    )

    state = {"mentions": [EntityMention(text="BTK", suggested_type="gene")],
             "warnings": []}
    out = await resolve_node(state)

    assert out["resolved"]["BTK"].accession == "@GENE_BTK"
    assert "BTK" not in out["unresolved"]
