import re

import pytest
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from crossbar_llm.pubtator3_tools.agent import (
    _router_decision_gaps,
    DepthEvaluation,
    EntityMention,
    RouterDecision,
    _ainvoke_structured_with_json_fallback,
    build_graph,
)
from crossbar_llm.pubtator3_tools.prompts import ROUTER_SYSTEM_PROMPT
from crossbar_llm.pubtator3_tools import client

BASE_URL = client.BASE_URL


def _url_pattern(path: str) -> re.Pattern:
    return re.compile(rf"{re.escape(BASE_URL)}{re.escape(path)}.*")


def _register_full_pipeline(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=fx("pubtator3_autocomplete_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/relations"),
        json=fx("pubtator3_relations_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )


def _make_fake_router(decision: RouterDecision):
    async def _router(_question: str) -> RouterDecision:
        return decision

    return _router


async def _fake_synth(state) -> str:
    pmids = sorted({p.pmid for p in state.get("passages", [])})
    return f"answer with {len(state.get('passages', []))} passages; pmids={pmids}"


class _StructuredNoneChatModel:
    def __init__(self, responses: list[str]):
        self.responses = responses

    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(lambda _: None)

    async def __call__(self, _input):
        return AIMessage(content=self.responses.pop(0))


def test_entity_mention_text_description_allows_canonical_normalization():
    description = EntityMention.model_fields["text"].description

    assert "canonical normalization is allowed" in description
    assert "BTK" in description
    assert "Do NOT invent" in description


def test_router_prompt_guides_gene_symbol_normalization_without_invention():
    assert "PubTator3's gene autocomplete" in ROUTER_SYSTEM_PROMPT
    assert "\"Bruton's tyrosine kinase\" -> text=\"BTK\"" in ROUTER_SYSTEM_PROMPT
    assert "the user mentioned RANKL" in ROUTER_SYSTEM_PROMPT


async def test_json_fallback_parses_router_when_structured_output_returns_none():
    chat_model = _StructuredNoneChatModel(responses=[
        """
        ```json
        {
          "question_type": "keyword_search",
          "mentions": [{"text": "SSRIs", "suggested_type": "chemical"}],
          "relation": null,
          "e2_type": null,
          "keyword_query": "SSRIs off-label use",
          "full_text": false,
          "rationale": "Off-label use is a literature keyword-search topic."
        }
        ```
        """
    ])
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Route the question."),
        ("human", "Question: {question}"),
    ])

    decision, used_fallback = await _ainvoke_structured_with_json_fallback(
        chat_model=chat_model,
        prompt=prompt,
        schema=RouterDecision,
        values={"question": "List the off-label use of SSRIs"},
        json_instruction="Return only JSON.",
    )

    assert used_fallback is True
    assert decision.question_type == "keyword_search"
    assert decision.keyword_query == "SSRIs off-label use"
    assert decision.mentions[0].text == "SSRIs"
    assert decision.mentions[0].suggested_type == "chemical"


async def test_json_fallback_parses_depth_eval_when_structured_output_returns_none():
    chat_model = _StructuredNoneChatModel(responses=[
        '{"sufficient": true, "missing": null, "rationale": "Specific entities are named."}'
    ])
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Evaluate answer depth."),
        ("human", "Question: {question}\nAnswer: {answer}"),
    ])

    verdict, used_fallback = await _ainvoke_structured_with_json_fallback(
        chat_model=chat_model,
        prompt=prompt,
        schema=DepthEvaluation,
        values={"question": "What is JAK1?", "answer": "JAK1 is a kinase."},
        json_instruction="Return only JSON.",
    )

    assert used_fallback is True
    assert verdict.sufficient is True
    assert verdict.missing is None


async def test_partner_discovery_flow(httpx_mock, fx):
    _register_full_pipeline(httpx_mock, fx)

    decision = RouterDecision(
        question_type="relation_partner_discovery",
        mentions=[EntityMention(text="JAK1", suggested_type="gene")],
        relation="negative_correlate",
        e2_type="Chemical",
        rationale="user asks for chemicals related to JAK1",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        max_partners=2,
        max_documents=5,
    )

    final = await graph.ainvoke({"question": "what chemicals correlate with JAK1?", "warnings": []})

    assert final["question_type"] == "relation_partner_discovery"
    assert "JAK1" in final["resolved"]
    assert len(final["partners"]) > 0
    assert len(final["queries_used"]) > 0
    assert all(q.startswith("relations:") for q in final["queries_used"])
    assert len(final["passages"]) > 0
    assert final["final_answer"] is not None
    assert "passages" in final["final_answer"]


async def test_known_pair_flow_skips_partner_discovery(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=fx("pubtator3_autocomplete_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )
    # /relations is intentionally unmocked — pytest-httpx fails on contact.

    decision = RouterDecision(
        question_type="relation_known_pair",
        mentions=[
            EntityMention(text="metformin", suggested_type="chemical", role="e1"),
            EntityMention(text="type 2 diabetes", suggested_type="disease", role="e2"),
        ],
        relation="treat",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
    )

    final = await graph.ainvoke(
        {"question": "does metformin treat type 2 diabetes?", "warnings": []}
    )

    assert final["question_type"] == "relation_known_pair"
    assert final.get("partners", []) == []
    assert len(final["queries_used"]) == 1
    assert final["queries_used"][0].startswith("relations:treat|")
    assert final["final_answer"] is not None


async def test_out_of_scope_terminates_without_tool_calls(httpx_mock):
    decision = RouterDecision(
        question_type="out_of_scope",
        mentions=[],
        rationale="not a literature lookup question",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
    )

    final = await graph.ainvoke(
        {"question": "what's the FDA approval history of metformin?", "warnings": []}
    )

    assert final["question_type"] == "out_of_scope"
    assert final.get("final_answer") is None
    assert final.get("passages", []) == []
    assert final.get("partners", []) == []


async def test_single_node_flow(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=fx("pubtator3_autocomplete_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="single_node",
        mentions=[EntityMention(text="JAK1", suggested_type="gene")],
        rationale="single entity question",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
    )

    final = await graph.ainvoke({"question": "tell me about JAK1", "warnings": []})

    assert final["question_type"] == "single_node"
    assert len(final["queries_used"]) == 1
    assert final["queries_used"][0].startswith("@GENE_")
    assert final["final_answer"] is not None


async def test_router_failure_falls_back_to_keyword_search(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )

    async def _broken_router(_question: str) -> RouterDecision:
        # Simulate a provider-side schema validation rejection.
        raise ValueError("invented relation 'target' is not in the enum")

    graph = build_graph(router=_broken_router, synthesizer=_fake_synth)

    final = await graph.ainvoke(
        {"question": "Which drugs target proteins associated with Alzheimer disease?", "warnings": []}
    )

    assert final["question_type"] == "keyword_search"
    assert final["keyword_query"] == (
        "Which drugs target proteins associated with Alzheimer disease?"
    )
    assert any("router failed" in w for w in final["warnings"])
    assert final["queries_used"] == [final["keyword_query"]]
    assert final["final_answer"] is not None


async def test_keyword_search_flow_skips_resolve_and_partner_discovery(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )
    # No /entity/autocomplete/ or /relations mocks — pytest-httpx fails if hit.

    decision = RouterDecision(
        question_type="keyword_search",
        mentions=[],
        keyword_query="imatinib side effects",
        rationale="side effects aren't a PubTator3 entity type but the literature is",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
    )

    final = await graph.ainvoke(
        {"question": "What are the side effects of imatinib?", "warnings": []}
    )

    assert final["question_type"] == "keyword_search"
    assert final["keyword_query"] == "imatinib side effects"
    assert final.get("resolved", {}) == {}
    assert final.get("partners", []) == []
    assert final["queries_used"] == ["imatinib side effects"]
    assert final["final_answer"] is not None


async def test_keyword_search_with_empty_query_falls_back_to_question(httpx_mock):
    """An empty `keyword_query` must not mean "issue no query at all".

    keyword_search is the one route with no accession or relation expression
    to search instead, so a router slip that leaves `keyword_query` null used
    to send the question straight to synthesis with zero evidence. The
    question text is a valid PubMed expression; we search it verbatim.
    """
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json={"results": [], "count": 0},
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="keyword_search",
        keyword_query="",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
    )

    final = await graph.ainvoke({"question": "vague", "warnings": []})

    assert final["question_type"] == "keyword_search"
    assert final["queries_used"] == ["vague"]
    assert any("without a keyword_query" in w for w in final.get("warnings", []))
    assert final["final_answer"] is not None


async def test_keyword_search_with_no_query_and_no_question_warns(httpx_mock):
    """Nothing to search at all — the original warning still fires."""
    decision = RouterDecision(
        question_type="keyword_search",
        keyword_query="",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
    )

    final = await graph.ainvoke({"question": "", "warnings": []})

    assert final["queries_used"] == []
    assert any(
        "needs a non-empty keyword_query" in w for w in final.get("warnings", [])
    )
    assert final["final_answer"] is not None


async def test_full_text_defaults_to_false_when_router_omits_it(httpx_mock, fx):
    _register_full_pipeline(httpx_mock, fx)

    # Router decision without `full_text` -> Pydantic default is False.
    decision = RouterDecision(
        question_type="relation_partner_discovery",
        mentions=[EntityMention(text="JAK1", suggested_type="gene")],
        relation="negative_correlate",
        e2_type="Chemical",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        max_partners=1,
        max_documents=3,
    )

    await graph.ainvoke({"question": "...", "warnings": []})

    export_requests = httpx_mock.get_requests(
        url=_url_pattern("/publications/export/biocjson")
    )
    assert len(export_requests) >= 1
    assert all(req.url.params["full"] == "false" for req in export_requests)


async def test_full_text_true_propagates_to_export_call(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=fx("pubtator3_autocomplete_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="single_node",
        mentions=[EntityMention(text="JAK1", suggested_type="gene")],
        full_text=True,
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        max_documents=3,
    )

    final = await graph.ainvoke({"question": "...", "warnings": []})

    assert final["full_text"] is True
    export_requests = httpx_mock.get_requests(
        url=_url_pattern("/publications/export/biocjson")
    )
    assert all(req.url.params["full"] == "true" for req in export_requests)


async def test_unresolvable_entity_falls_back_to_router_keyword_query(httpx_mock):
    """When single_node entity resolution fails, search_node should fall
    back to the router-supplied `keyword_query` rather than bail silently.
    The fallback may still find nothing — that's fine — but the fallback
    query MUST be attempted and recorded in queries_used."""
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=[],
        is_reusable=True,
    )
    # Fallback hits search with 0 results (no recovery possible here).
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json={"results": [], "count": 0},
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="single_node",
        mentions=[EntityMention(text="ZZZNotARealEntity")],
        keyword_query="ZZZNotARealEntity background",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
    )

    final = await graph.ainvoke({"question": "tell me about ZZZNotARealEntity", "warnings": []})

    assert "ZZZNotARealEntity" in final.get("unresolved", [])
    # The fallback fired with the router-supplied keyword_query.
    assert final.get("queries_used", []) == ["ZZZNotARealEntity background"]
    # Fallback search returned 0 hits, so passages still empty.
    assert final.get("passages", []) == []
    assert final["final_answer"] is not None
    assert any("falling back to keyword search" in w for w in final.get("warnings", []))


def _make_fake_evaluator(verdict: DepthEvaluation, call_log: list | None = None):
    async def _evaluator(state):
        if call_log is not None:
            call_log.append({
                "answer": state.get("final_answer"),
                "full_text": state.get("full_text"),
            })
        return verdict
    return _evaluator


async def test_depth_evaluator_no_loop_when_sufficient(httpx_mock, fx):
    _register_full_pipeline(httpx_mock, fx)

    decision = RouterDecision(
        question_type="relation_partner_discovery",
        mentions=[EntityMention(text="JAK1", suggested_type="gene")],
        relation="negative_correlate",
        e2_type="Chemical",
    )
    call_log: list = []
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        evaluator=_make_fake_evaluator(
            DepthEvaluation(sufficient=True, missing=None), call_log
        ),
        max_partners=1,
        max_documents=3,
    )

    final = await graph.ainvoke({"question": "...", "warnings": []})

    assert final["depth_sufficient"] is True
    assert final.get("refinement_attempted", False) is False
    # Evaluator was called exactly once.
    assert len(call_log) == 1
    # Export endpoint hit exactly once (no refinement loop).
    export_calls = httpx_mock.get_requests(
        url=_url_pattern("/publications/export/biocjson")
    )
    assert len(export_calls) == 1


async def test_depth_evaluator_triggers_refinement_when_insufficient(httpx_mock, fx):
    _register_full_pipeline(httpx_mock, fx)

    decision = RouterDecision(
        question_type="relation_partner_discovery",
        mentions=[EntityMention(text="JAK1", suggested_type="gene")],
        relation="negative_correlate",
        e2_type="Chemical",
    )
    # First call: insufficient. Second call (after refinement) won't matter
    # because evaluate_depth_node short-circuits on refinement_attempted.
    call_log: list = []
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        evaluator=_make_fake_evaluator(
            DepthEvaluation(sufficient=False, missing="no mechanism"), call_log
        ),
        max_partners=1,
        max_documents=3,
    )

    final = await graph.ainvoke({"question": "...", "warnings": []})

    # After the cap fires, the second evaluate short-circuits to True. What
    # persists is the side-effect of the first verdict: refinement happened.
    assert final["refinement_attempted"] is True
    assert final["full_text"] is True
    # Two synthesize passes -> two export calls (one with full=false, one with full=true).
    export_calls = httpx_mock.get_requests(
        url=_url_pattern("/publications/export/biocjson")
    )
    assert len(export_calls) == 2
    full_params = [c.url.params["full"] for c in export_calls]
    assert full_params == ["false", "true"]
    # Evaluator runs once on the first answer; the second pass short-circuits.
    assert len(call_log) == 1
    # Warning is recorded so the user sees why the loop fired.
    assert any("shallow" in w for w in final["warnings"])


async def test_depth_evaluator_skipped_when_full_text_already_true(httpx_mock, fx):
    # single_node skips /relations — register only what it actually calls.
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=fx("pubtator3_autocomplete_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="single_node",
        mentions=[EntityMention(text="JAK1", suggested_type="gene")],
        full_text=True,
    )
    call_log: list = []
    # Even if evaluator would flag insufficient, the node short-circuits
    # because full_text is already True (no escalation lever).
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        evaluator=_make_fake_evaluator(
            DepthEvaluation(sufficient=False, missing="should be ignored"), call_log
        ),
        max_documents=3,
    )

    final = await graph.ainvoke({"question": "...", "warnings": []})

    assert final["depth_sufficient"] is True
    assert final.get("refinement_attempted", False) is False
    # Evaluator was never invoked.
    assert len(call_log) == 0
    # Export fired once with full=true (router's decision).
    export_calls = httpx_mock.get_requests(
        url=_url_pattern("/publications/export/biocjson")
    )
    assert len(export_calls) == 1
    assert export_calls[0].url.params["full"] == "true"


async def test_depth_evaluator_skipped_when_no_passages(httpx_mock):
    # Unresolvable entity -> fallback keyword search returns nothing ->
    # no passages -> evaluator should short-circuit instead of trying to
    # deepen an empty answer.
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=[],
        is_reusable=True,
    )
    # Fallback keyword search also finds nothing — true data desert.
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json={"results": [], "count": 0},
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="single_node",
        mentions=[EntityMention(text="ZZZNotARealEntity")],
    )
    call_log: list = []
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        evaluator=_make_fake_evaluator(
            DepthEvaluation(sufficient=False, missing="should be ignored"), call_log
        ),
    )

    final = await graph.ainvoke({"question": "...", "warnings": []})

    assert final["depth_sufficient"] is True
    assert final.get("refinement_attempted", False) is False
    # Evaluator was never invoked because there are no passages.
    assert len(call_log) == 0


async def test_known_pair_falls_back_to_keyword_when_one_entity_unresolved(httpx_mock, fx):
    """When relation_known_pair has one mention that autocomplete can't
    resolve (e.g. a generic descriptor like 'antidote'), the search node
    should fall back to a keyword query instead of bailing silently."""
    # First mention resolves to the fixture's JAK1 candidates; second
    # returns an empty candidate list (unresolvable).
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=fx("pubtator3_autocomplete_example"),
    )
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=[],
    )
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="relation_known_pair",
        mentions=[
            EntityMention(text="benzodiazepine", suggested_type="chemical", role="e1"),
            EntityMention(text="antidote", role="e2"),
        ],
        relation="treat",
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        max_documents=2,
    )

    final = await graph.ainvoke({"question": "What is the antidote for benzodiazepine?", "warnings": []})

    queries = final.get("queries_used") or []
    assert len(queries) == 1
    # The fallback query is the resolved entity name + the unresolved
    # mention text + the relation verb.
    assert "JAK1" in queries[0] or "benzodiazepine" in queries[0].lower()
    assert "antidote" in queries[0]
    assert "treat" in queries[0]
    # The pipeline kept running — search returned hits, export returned docs.
    assert final.get("final_answer") is not None
    assert any("known-pair" in w and "fell back" in w for w in final.get("warnings", []))


async def test_full_text_false_filters_out_body_sections(httpx_mock, fx):
    """Even when PubTator3 returns body sections (review-article quirk),
    we must trim to title + abstract when the router asked for abstract mode."""
    # Synthetic doc carrying both abstract-mode passages (lowercase) and
    # body sections (uppercase section_type). full=false was requested but
    # PubTator3 returned everything anyway.
    raw_doc_with_body = {
        "PubTator3": [
            {
                "pmid": "55555555",
                "passages": [
                    {
                        "infons": {"type": "title"},
                        "offset": 0,
                        "text": "A real title passage.",
                        "annotations": [],
                    },
                    {
                        "infons": {"type": "abstract"},
                        "offset": 100,
                        "text": "A real abstract passage.",
                        "annotations": [],
                    },
                    {
                        "infons": {"section_type": "INTRO", "type": "paragraph"},
                        "offset": 500,
                        "text": "Intro body that should be filtered out in abstract mode.",
                        "annotations": [],
                    },
                    {
                        "infons": {"section_type": "METHODS", "type": "paragraph"},
                        "offset": 1500,
                        "text": "Methods body that should be filtered out.",
                        "annotations": [],
                    },
                    {
                        "infons": {"section_type": "RESULTS", "type": "paragraph"},
                        "offset": 2500,
                        "text": "Results body that should be filtered out.",
                        "annotations": [],
                    },
                ],
                "relations": [],
            }
        ]
    }

    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=fx("pubtator3_autocomplete_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=raw_doc_with_body,
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="single_node",
        mentions=[EntityMention(text="JAK1", suggested_type="gene")],
        full_text=False,
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        max_documents=1,
    )

    final = await graph.ainvoke({"question": "...", "warnings": []})

    sections = [p.section for p in final["passages"]]
    # Only title + abstract survive; INTRO/METHODS/RESULTS are filtered.
    assert set(sections) == {"title", "abstract"}
    assert "INTRO" not in sections
    assert "METHODS" not in sections
    assert "RESULTS" not in sections


async def test_full_text_true_keeps_body_sections(httpx_mock, fx):
    """Same fixture but with full_text=True — body sections must pass through."""
    raw_doc_with_body = {
        "PubTator3": [
            {
                "pmid": "55555556",
                "passages": [
                    {
                        "infons": {"section_type": "TITLE", "type": "title"},
                        "offset": 0,
                        "text": "Title.",
                        "annotations": [],
                    },
                    {
                        "infons": {"section_type": "ABSTRACT", "type": "paragraph"},
                        "offset": 100,
                        "text": "Abstract.",
                        "annotations": [],
                    },
                    {
                        "infons": {"section_type": "METHODS", "type": "paragraph"},
                        "offset": 500,
                        "text": "Methods body.",
                        "annotations": [],
                    },
                ],
                "relations": [],
            }
        ]
    }

    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=fx("pubtator3_autocomplete_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=raw_doc_with_body,
        is_reusable=True,
    )

    decision = RouterDecision(
        question_type="single_node",
        mentions=[EntityMention(text="JAK1", suggested_type="gene")],
        full_text=True,
    )
    graph = build_graph(
        router=_make_fake_router(decision),
        synthesizer=_fake_synth,
        max_documents=1,
    )

    final = await graph.ainvoke({"question": "...", "warnings": []})

    sections = {p.section for p in final["passages"]}
    assert "METHODS" in sections
    assert "TITLE" in sections
    assert "ABSTRACT" in sections


def test_nodes_star_import_does_not_break():
    """`__all__` must only name things the module actually defines."""
    import crossbar_llm.pubtator3_tools.nodes as nodes

    missing = [n for n in nodes.__all__ if not hasattr(nodes, n)]
    assert not missing, f"__all__ names absent from module: {missing}"
    exec("from crossbar_llm.pubtator3_tools.nodes import *", {})

def _capturing_chat_model(seen: list[str]):
    """A chat model stand-in that records the rendered synthesis prompt."""

    async def _call(prompt_value):
        seen.append(prompt_value.to_string())
        return AIMessage(content="synthesized answer")

    model = RunnableLambda(_call)
    # build_graph only reaches for structured output on the router/evaluator
    # paths, both bypassed here; this keeps the duck-type complete.
    model.with_structured_output = lambda schema, **kwargs: RunnableLambda(
        lambda _: None
    )
    return model


async def test_evidence_block_is_capped_and_truncation_is_disclosed(httpx_mock, fx):
    """max_documents bounds papers, not text — the evidence block needs its own cap.

    Without it an export whose abstracts split into hundreds of passages built
    a synthesis prompt that overran the provider's context limit and returned a
    hard 400 instead of an answer.
    """
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )
    seen: list[str] = []

    decision = RouterDecision(
        question_type="keyword_search",
        keyword_query="imatinib side effects",
    )
    graph = build_graph(
        chat_model=_capturing_chat_model(seen),
        router=_make_fake_router(decision),
        abstracts_only=True,
        max_evidence_chars=200,
    )

    final = await graph.ainvoke(
        {"question": "What are the side effects of imatinib?", "warnings": []}
    )

    assert final["final_answer"] == "synthesized answer"
    assert len(seen) == 1
    prompt_text = seen[0]
    assert "further evidence line(s) were omitted" in prompt_text
    # The cap trims at a line boundary, so at least one passage survives.
    assert "[PMID:" in prompt_text


async def test_evidence_block_is_not_truncated_under_a_generous_budget(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )
    seen: list[str] = []

    decision = RouterDecision(
        question_type="keyword_search",
        keyword_query="imatinib side effects",
    )
    graph = build_graph(
        chat_model=_capturing_chat_model(seen),
        router=_make_fake_router(decision),
        abstracts_only=True,
    )

    await graph.ainvoke(
        {"question": "What are the side effects of imatinib?", "warnings": []}
    )

    assert "further evidence line(s) were omitted" not in seen[0]

class _ScriptedRouterChatModel:
    """Hands back a scripted RouterDecision per structured-output call."""

    def __init__(self, decisions: list[RouterDecision]):
        self.decisions = list(decisions)
        self.calls = 0

    def with_structured_output(self, schema, **kwargs):
        async def _next(_values):
            self.calls += 1
            return self.decisions.pop(0)

        return RunnableLambda(_next)


def _incomplete_partner_discovery() -> RouterDecision:
    """What weak models actually emit: the flat field, not the nested list."""
    return RouterDecision(
        question_type="relation_partner_discovery",
        mentions=[],
        relation="inhibit",
        e2_type=None,
    )


def _search_and_export_mocks(httpx_mock, fx) -> None:
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )


def test_router_gaps_flags_each_routes_required_fields():
    assert _router_decision_gaps(_incomplete_partner_discovery()) == [
        "`mentions` must hold exactly one anchor entity",
        "`e2_type` is required",
    ]
    assert _router_decision_gaps(
        RouterDecision(question_type="keyword_search", keyword_query="  ")
    ) == ["`keyword_query` is required"]
    # A complete decision has no gaps.
    assert _router_decision_gaps(
        RouterDecision(
            question_type="relation_partner_discovery",
            mentions=[EntityMention(text="BTK", suggested_type="gene")],
            relation="inhibit",
            e2_type="Chemical",
        )
    ) == []


async def test_router_downgrades_an_incomplete_decision(httpx_mock, fx):
    _search_and_export_mocks(httpx_mock, fx)
    chat_model = _ScriptedRouterChatModel([_incomplete_partner_discovery()])

    graph = build_graph(
        chat_model=chat_model,
        synthesizer=_fake_synth,
        abstracts_only=True,
    )
    final = await graph.ainvoke({"question": "BTK inhibitors?", "warnings": []})

    # Exactly one router call: the guard costs no extra LLM round trip.
    assert chat_model.calls == 1
    assert final["question_type"] == "keyword_search"
    assert final["keyword_query"] == "BTK inhibitors?"
    assert any("downgraded to keyword_search" in w for w in final["warnings"])


async def test_router_guard_can_be_disabled(httpx_mock, fx):
    _search_and_export_mocks(httpx_mock, fx)
    chat_model = _ScriptedRouterChatModel([_incomplete_partner_discovery()])

    graph = build_graph(
        chat_model=chat_model,
        synthesizer=_fake_synth,
        abstracts_only=True,
        router_guard=False,
    )
    final = await graph.ainvoke({"question": "BTK inhibitors?", "warnings": []})

    assert chat_model.calls == 1
    assert final["question_type"] == "relation_partner_discovery"
    assert not any("downgraded" in w for w in final["warnings"])

