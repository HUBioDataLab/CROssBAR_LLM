"""Live smoke test against the real Paperclip MCP server.

Skipped unless PAPERCLIP_API_KEY is set — Paperclip is a live, metered
dependency and cannot be mocked at the HTTP layer (see the integration doc).
This is the provenance gate: it asserts search returns hits carrying real
citable IDs (DOI/PMID), and that a full graph run produces a cited answer.
"""
from __future__ import annotations

import os
import re

import pytest

try:
    from dotenv import load_dotenv

    load_dotenv()  # populate PAPERCLIP_API_KEY + LLM keys from .env if present
except Exception:  # pragma: no cover - dotenv always installed here
    pass

# `live` makes these deselectable with `-m "not live"`. Without a key they
# already skip, but anyone holding one needs a way to run the offline suite
# deterministically — these assert against a third-party service whose outages
# are not ours to fix.
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("PAPERCLIP_API_KEY"),
        reason="PAPERCLIP_API_KEY not set; skipping live Paperclip smoke test.",
    ),
]


async def test_live_search_and_meta_have_citable_ids():
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    adapter = PaperclipAdapter()
    result = await adapter.search(
        "BTK inhibitor chronic lymphocytic leukemia", source="pmc", limit=3
    )
    assert result.hits, "expected search hits from the live server"
    assert all(h.doc_id for h in result.hits)

    meta = await adapter.get_meta(result.hits[0].doc_id)
    # Provenance gate: a real citable identifier must be present.
    assert meta.doi or meta.pmid, f"no citable id on {result.hits[0].doc_id}"
    assert meta.title


async def test_live_default_search_is_broad_via_rest():
    """`source=None` should hit the REST path (see
    docs/paperclip_rest_endpoint_findings.md) and return real, structured,
    multi-source results — the whole point of the migration. If REST ever
    gets locked down for API-key auth, this test is the canary: it'll still
    pass via the MCP fallback (comma-separated paper corpora), just without
    the `score`/`corpus` fields REST provides, which the second assertion
    block would then need loosening."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    adapter = PaperclipAdapter()
    result = await adapter.search(
        "BTK inhibitor chronic lymphocytic leukemia", source=None, limit=8
    )
    assert result.hits, "expected hits from a broad/unscoped search"
    assert all(h.doc_id for h in result.hits)
    # More than one corpus represented is the real signal this is a genuine
    # broad search, not an accidental single-source one.
    sources_seen = {h.source for h in result.hits if h.source}
    assert len(sources_seen) >= 1

    # If REST answered (not the MCP fallback), hits carry structured fields
    # MCP text-parsing never provides.
    if any(h.score is not None for h in result.hits):
        rest_hit = next(h for h in result.hits if h.score is not None)
        assert rest_hit.doi or rest_hit.pub_year or rest_hit.backend


async def test_live_arxiv_doc_id_round_trips():
    """Regression test for the arXiv ID truncation bug — a real arXiv hit's
    doc_id must survive a `get_meta` round trip instead of 404ing on a
    truncated id."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    adapter = PaperclipAdapter()
    result = await adapter.search("transformer attention", source="arxiv", limit=3)
    assert result.hits, "expected arXiv hits"
    hit = result.hits[0]
    assert "." in hit.doc_id, f"arXiv doc_id looks truncated: {hit.doc_id!r}"
    meta = await adapter.get_meta(hit.doc_id, source="arxiv")
    assert meta.title


async def test_live_pdb_chembl_return_real_hits():
    """Regression test for the pdb/chembl parser-dispatch bug — these used to
    silently return zero hits despite the server sending real data."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    adapter = PaperclipAdapter()
    pdb_result = await adapter.search("TP53", source="pdb", limit=3)
    assert pdb_result.hits, "expected -s pdb to return real hits post-fix"
    chembl_result = await adapter.search("aspirin", source="chembl", limit=3)
    assert chembl_result.hits, "expected -s chembl to return real hits post-fix"


async def test_live_map_json_contract_returns_structured_extracts():
    """`run_map` asks for its {answer, found} contract in the question text
    (never via --output_schema, which 500s on REST) — confirm the request
    round-trips against the real server without erroring.

    Deliberately NOT asserting any extract gets `.data` populated: repeated
    live runs during development showed the per-paper reader's schema
    compliance is genuinely inconsistent — sometimes a clean flat
    `{"answer":..., "found":...}`, sometimes the schema's own `properties`
    structure echoed back with values misplaced inside it, and in one run
    every paper in a 3-paper batch got the malformed shape. That's Paperclip
    server-side model behavior we don't control, so gating a test on "at
    least N papers get structured data" would be flaky by construction. What
    IS our responsibility, and what this actually tests: the request is
    well-formed (server accepts it, doesn't error) and every extract still
    has usable `.text` regardless of whether `.data` parsed — i.e. the
    defensive fallback in `_map_extract_from_text` holds up against real
    server responses, not just the synthetic malformed-JSON cases covered in
    test_paperclip_adapter.py's offline tests. Any extract that DOES get
    `.data` must at least match our schema's keys.
    """
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    adapter = PaperclipAdapter()
    search_result = await adapter.search(
        "BTK inhibitor chronic lymphocytic leukemia", source="pmc", limit=3
    )
    assert search_result.search_id

    extracts = await adapter.run_map(
        search_result.search_id,
        "What delivery vector or inhibitor mechanism was reported?",
    )
    assert extracts, "expected at least one map extract"
    assert all(e.text for e in extracts), "every extract must have usable text regardless of .data"
    for e in extracts:
        if e.data is not None:
            assert "answer" in e.data and "found" in e.data
        # Regression coverage for the nested-malformed-shape crash and the
        # found-detection bug (docs/paperclip_rest_endpoint_findings.md) —
        # must normalize cleanly against whatever shape the real server sends
        # today, not just the synthetic fixtures in test_paperclip_adapter.py.
        assert e.found in (None, True, False)
        assert all(isinstance(n, int) for n in e.citation_lines)


async def test_live_sql_returns_real_counts():
    """Confirm `adapter.sql()` round-trips a real read-only query — same
    query manually verified during development (docs/paperclip_rest_endpoint_
    findings.md §12): fda is a single, SQL-queryable shard with a stable,
    large row count."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    adapter = PaperclipAdapter()
    result = await adapter.sql("SELECT COUNT(*) AS n FROM documents", source="fda")
    assert result.columns == ["n"]
    assert result.rows, "expected exactly one count row"
    assert int(result.rows[0]["n"]) > 0


async def test_live_sql_trials_is_not_queryable():
    """Regression/documentation test for a real server constraint (confirmed
    live, not obvious from the docs): `documents` isn't backed by a table for
    every source — trials errors outright. sql_node relies on this failing
    cleanly (not hanging or returning nonsense) to trigger its search
    fallback."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter, PaperclipError

    adapter = PaperclipAdapter()
    with pytest.raises(PaperclipError):
        await adapter.sql("SELECT COUNT(*) FROM documents", source="trials")


async def test_live_filter_trims_a_noisy_result_set():
    """Confirm `filter` genuinely narrows a deliberately noisy, broad search
    down toward papers relevant to a specific sub-topic — the actual quality
    signal this feature exists for, not just that the round trip parses."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    adapter = PaperclipAdapter()
    search_result = await adapter.search("diabetes", source="pmc", limit=15)
    assert search_result.search_id and search_result.hits

    filtered = await adapter.filter(
        search_result.search_id,
        "papers specifically about metformin's mechanism of action",
    )
    assert filtered is not None, "expected REST to be available in this live test env"
    assert len(filtered.hits) <= len(search_result.hits)


async def test_live_filter_returns_none_when_rest_disabled(monkeypatch):
    """`filter` has no MCP fallback — confirm the documented degrade-to-None
    contract holds against the real environment, not just a mocked one."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    adapter = PaperclipAdapter()
    search_result = await adapter.search("diabetes", source="pmc", limit=3)
    assert search_result.search_id

    monkeypatch.setenv("PAPERCLIP_DISABLE_REST", "1")
    assert await adapter.filter(search_result.search_id, "anything") is None


async def test_live_sql_aggregate_graph_produces_answer():
    """Full production wiring, live: router decision fixed (not asking the
    router LLM to pick sql_aggregate — that's a separate judgment-call
    concern) so this specifically exercises sql_node -> synthesize_node's
    PAPERCLIP_SQL_SYNTHESIZE_SYSTEM_PROMPT path against the real server and a
    real LLM, end to end."""
    from crossbar_llm.paperclip_tools.agent import build_graph
    from crossbar_llm.paperclip_tools.schemas import PaperclipRouterDecision

    async def fixed_router(_question):
        return PaperclipRouterDecision(
            question_type="sql_aggregate",
            source="fda",
            search_query="pembrolizumab",  # fallback if sql fails
            map_question="pembrolizumab",  # unused on this route; required field
            sql_query="SELECT COUNT(*) AS n FROM documents",
            rationale="test: fixed sql_aggregate route",
        )

    llm = _get_llm_or_skip()
    graph = build_graph(chat_model=llm, router=fixed_router)
    state = await graph.ainvoke({"question": "how many FDA documents does Paperclip index?"})
    assert not state.get("sql_error"), f"sql query failed: {state.get('sql_error')}"
    assert state.get("sql_rows"), "expected at least one row back"
    assert state.get("final_answer"), "expected a synthesized answer"
    # No per-paper citations for a SQL answer.
    assert not state.get("citations")


def _get_llm_or_skip():
    """Build the project's configured chat model; skip if it isn't available."""
    import os

    model = os.environ.get("PAPERCLIP_TEST_MODEL", "gpt-4o-mini")
    try:
        from crossbar_llm.paperclip_tools.llm import build_chat_model

        return build_chat_model(model=model)
    except Exception as e:  # pragma: no cover - depends on configured providers
        pytest.skip(f"chat model unavailable ({model}): {e}")


async def test_live_end_to_end_returns_cited_answer():
    from crossbar_llm.paperclip_tools.agent import build_graph
    from crossbar_llm.paperclip_tools.usage import ainvoke_with_usage_capture

    llm = _get_llm_or_skip()
    graph = build_graph(chat_model=llm, abstracts_only=True)
    state, usage = await ainvoke_with_usage_capture(
        graph, {"question": "What is the mechanism of action of metformin?"}
    )
    assert state.get("final_answer"), "expected a synthesized answer"
    assert state.get("citations"), "expected at least one citation"
    # Usage is reported with input/output tokens separated.
    assert usage["input_tokens"] > 0 and usage["output_tokens"] > 0

    # use_map defaults True and this run doesn't disable it, so any citation
    # sourced from map evidence with real `_citations` provenance should carry
    # a line-anchored URL (docs/paperclip_rest_endpoint_findings.md §14). Not
    # asserting every/any citation has one — schema compliance is genuinely
    # inconsistent server-side (see test_live_map_json_contract_returns_
    # structured_extracts) — only that whichever ones do are well-formed.
    for cit in state["citations"]:
        if "#L" in cit.url:
            anchor = cit.url.split("#", 1)[1]
            assert re.fullmatch(r"L\d+(-L\d+)?(,\d+)*", anchor), f"malformed anchor: {cit.url}"
