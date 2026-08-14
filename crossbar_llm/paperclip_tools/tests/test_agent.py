"""Graph-level tests for the Paperclip LangGraph.

All offline: a fake `PaperclipAdapterProtocol` is injected at the
`build_graph(adapter=...)` seam (mocking the tool-call boundary, not the MCP
wire protocol), and router/synthesizer/evaluator are swapped for deterministic
fakes via the `build_graph(router=..., synthesizer=..., evaluator=...)` seams.
"""
from __future__ import annotations

from crossbar_llm.paperclip_tools.agent import build_graph
from crossbar_llm.paperclip_tools.schemas import (
    PaperclipDepthEvaluation,
    PaperclipRouterDecision,
)
from crossbar_llm.paperclip_tools.adapter import (
    MapExtract,
    PaperclipError,
    PaperHit,
    PaperMeta,
    SearchResult,
    SqlResult,
)


def _meta(doc_id, **kw):
    base = dict(
        document_id=doc_id, pmid="1" + doc_id[-3:], doi="10.1/" + doc_id,
        title="Title " + doc_id, authors="A. Author", abstract="An abstract about the topic.",
        journal="J", pub_year=2024,
    )
    base.update(kw)
    return PaperMeta(**base)


class FakeAdapter:
    """Records calls and returns canned typed results."""

    def __init__(self, *, hits=None, search_error=None, meta_error_ids=(),
                 content=None, map_extracts=None, sql_result=None, sql_error=None,
                 filter_hits=None, filter_error=None, filter_none=False):
        self._hits = hits if hits is not None else [
            PaperHit(doc_id="PMC1", title="T1", source="pmc", date="2024"),
            PaperHit(doc_id="PMC2", title="T2", source="pmc", date="2023"),
        ]
        self._search_error = search_error
        self._meta_error_ids = set(meta_error_ids)
        self._content = content if content is not None else "L1: full body text"
        self._map_extracts = map_extracts  # dict doc_id -> text, or None
        self._sql_result = sql_result  # SqlResult, or None
        self._sql_error = sql_error
        self._filter_hits = filter_hits  # list[PaperHit], or None (echo input hits)
        self._filter_error = filter_error
        self._filter_none = filter_none  # simulate REST-unavailable (returns None)
        self.search_calls = []
        self.content_calls = []
        self.meta_calls = []
        self.map_calls = []
        self.sql_calls = []
        self.filter_calls = []

    async def search(self, query, *, source="pmc", limit=10, sort=None, year=None, ranking=None):
        self.search_calls.append({
            "query": query, "source": source, "limit": limit, "year": year, "ranking": ranking,
        })
        if self._search_error:
            raise PaperclipError(self._search_error)
        return SearchResult(hits=list(self._hits), search_id="s_fake")

    async def get_meta(self, doc_id, *, source="pmc"):
        self.meta_calls.append({"doc_id": doc_id, "source": source})
        if doc_id in self._meta_error_ids:
            raise PaperclipError(f"meta boom {doc_id}")
        if source in ("proteins", "uniprot"):
            return PaperMeta(
                document_id=doc_id, title=f"{doc_id} - Histone acetyltransferase",
                protein_name="Histone acetyltransferase KAT6A", gene_name="KAT6A",
                organism="Homo sapiens", uniprot_id="KAT6A_HUMAN",
            )
        return _meta(doc_id)

    async def get_content(self, doc_id, *, source="pmc", sections=None, max_lines=None):
        self.content_calls.append(
            {"doc_id": doc_id, "source": source, "sections": sections, "max_lines": max_lines}
        )
        return self._content

    async def run_map(self, search_id, question, *, limit=None):
        self.map_calls.append({"search_id": search_id, "question": question, "limit": limit})
        src = self._map_extracts or {}
        return [MapExtract(doc_id=d, text=t, success=True) for d, t in src.items()]

    async def sql(self, query, *, source=None):
        self.sql_calls.append({"query": query, "source": source})
        if self._sql_error:
            raise PaperclipError(self._sql_error)
        return self._sql_result if self._sql_result is not None else SqlResult()

    async def filter(self, search_id, query):
        self.filter_calls.append({"search_id": search_id, "query": query})
        if self._filter_error:
            raise PaperclipError(self._filter_error)
        if self._filter_none:
            return None
        hits = self._filter_hits if self._filter_hits is not None else list(self._hits)
        return SearchResult(hits=hits, search_id=search_id)


def _router(qtype="keyword_search", *, source="pmc", query="topic query",
            full_text=False, sections=None, year=None, sql_query=None,
            map_question=None, analogical_query=None):
    async def fn(_question):
        return PaperclipRouterDecision(
            question_type=qtype, source=source, search_query=query,
            analogical_query=analogical_query,
            map_question=map_question if map_question is not None else query,
            full_text=full_text, sections=sections, year=year, sql_query=sql_query,
            rationale="test",
        )
    return fn


async def _synth(state):
    refs = " ".join(f"[{c.ref_num}]" for c in state.get("citations", []))
    return f"Answer citing {refs}. References: " + "; ".join(
        f"[{c.ref_num}] {c.doc_id} doi:{c.doi}" for c in state.get("citations", [])
    )


async def test_keyword_search_happy_path():
    adapter = FakeAdapter()
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter)
    out = await g.ainvoke({"question": "What treats X?"})
    assert out["question_type"] == "keyword_search"
    assert [h.doc_id for h in out["hits"]] == ["PMC1", "PMC2"]
    assert [c.ref_num for c in out["citations"]] == [1, 2]
    assert out["citations"][0].url == "https://citations.gxl.ai/papers/PMC1"
    assert "[1]" in out["final_answer"]
    # No full text requested -> no content fetch.
    assert adapter.content_calls == []


async def test_out_of_scope_short_circuits():
    adapter = FakeAdapter()
    g = build_graph(router=_router("out_of_scope"), synthesizer=_synth, adapter=adapter)
    out = await g.ainvoke({"question": "shortest path from A to B?"})
    assert out["question_type"] == "out_of_scope"
    assert out.get("final_answer") is None
    assert adapter.search_calls == []  # never retrieved


async def test_full_text_depth_fetches_content():
    adapter = FakeAdapter()
    # abstracts_only=False to allow the full-text path; use_map=False to isolate
    # it from map (which would otherwise supply the body server-side).
    g = build_graph(router=_router("full_text_depth", full_text=True),
                    synthesizer=_synth, adapter=adapter,
                    abstracts_only=False, use_map=False)
    out = await g.ainvoke({"question": "mechanism of X?"})
    assert out["full_text"] is True
    assert {c["doc_id"] for c in adapter.content_calls} == {"PMC1", "PMC2"}
    assert all(d.body == "L1: full body text" for d in out["documents"])
    # No section filter requested -> whole body.
    assert all(c["sections"] is None for c in adapter.content_calls)


async def test_section_filter_reaches_adapter():
    adapter = FakeAdapter()
    g = build_graph(
        router=_router("full_text_depth", full_text=True, sections=["methods"]),
        synthesizer=_synth,
        adapter=adapter,
        abstracts_only=False,
        use_map=False,
    )
    out = await g.ainvoke({"question": "what methods were used?"})
    assert out["sections"] == ["methods"]
    assert adapter.content_calls
    assert all(c["sections"] == ["methods"] for c in adapter.content_calls)


async def test_map_uses_map_question_not_raw_user_question():
    """map_question (the router's specific, enumerated-fields extraction
    question) must reach `run_map` — not the raw user question, and not
    search_query (keywords, a different purpose)."""
    adapter = FakeAdapter()
    g = build_graph(
        router=_router(
            query="metformin keywords",
            map_question="What is the specific molecular target and downstream pathway?",
        ),
        synthesizer=_synth,
        adapter=adapter,
        use_map=True,
    )
    await g.ainvoke({"question": "how does metformin work?"})
    assert adapter.map_calls
    assert adapter.map_calls[0]["question"] == (
        "What is the specific molecular target and downstream pathway?"
    )


async def test_map_extracts_used_as_evidence():
    adapter = FakeAdapter(map_extracts={"PMC1": "AMPK-Mff-Drp1 pathway (L34).",
                                        "PMC2": "not mentioned"})
    captured = {}

    async def synth(state):
        captured["docs"] = state.get("documents")
        return "answer [1][2]"

    g = build_graph(router=_router(), synthesizer=synth, adapter=adapter, use_map=True)
    out = await g.ainvoke({"question": "which pathway?"})
    assert adapter.map_calls and adapter.map_calls[0]["search_id"] == "s_fake"
    bodies = {d.doc_id: d.body for d in captured["docs"]}
    assert bodies["PMC1"] == "AMPK-Mff-Drp1 pathway (L34)."
    # map evidence is used even though full_text is False.
    assert out["full_text"] is False
    # no whole-body content fetch when map supplied the evidence.
    assert adapter.content_calls == []


async def test_map_extract_with_found_false_is_excluded_as_evidence():
    """`run_map` asks for an {answer, found} contract — when the model honors
    it, `found=False` means the paper explicitly doesn't address the
    question. That extract must be excluded from evidence entirely (falling
    back to the abstract), not used verbatim the way unstructured "not
    mentioned"-shaped prose used to be."""
    class StructuredMapAdapter(FakeAdapter):
        async def run_map(self, search_id, question, *, limit=None):
            self.map_calls.append({"search_id": search_id, "question": question, "limit": limit})
            return [
                MapExtract(
                    doc_id="PMC1", text="AMPK activation", success=True,
                    data={"answer": "AMPK activation", "found": True}, found=True,
                ),
                MapExtract(
                    doc_id="PMC2", text="Not found", success=True,
                    data={"answer": "Not found", "found": False}, found=False,
                ),
            ]

    adapter = StructuredMapAdapter()
    captured = {}

    async def synth(state):
        captured["docs"] = state.get("documents")
        return "answer [1][2]"

    g = build_graph(router=_router(), synthesizer=synth, adapter=adapter, use_map=True)
    await g.ainvoke({"question": "which pathway?"})
    bodies = {d.doc_id: d.body for d in captured["docs"]}
    assert bodies["PMC1"] == "AMPK activation"
    # PMC2's found=False extract must not be used as its evidence body.
    assert bodies["PMC2"] != "Not found"


async def test_map_citation_lines_anchor_the_citation_url():
    """A paper cited from map evidence must get a line-anchored URL built
    from Paperclip's own per-answer line provenance (`_citations`), not the
    blanket paper-root URL — the line-level citation architecture change."""
    class StructuredMapAdapter(FakeAdapter):
        async def run_map(self, search_id, question, *, limit=None):
            self.map_calls.append({"search_id": search_id, "question": question, "limit": limit})
            return [
                MapExtract(
                    doc_id="PMC1", text="AMPK activation (L6, L38, L40).", success=True,
                    found=True, citation_lines=[38, 6, 40],  # unsorted on purpose
                ),
                MapExtract(
                    doc_id="PMC2", text="mTOR inhibition (L24).", success=True,
                    found=True, citation_lines=[24],
                ),
            ]

    adapter = StructuredMapAdapter()
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter, use_map=True)
    out = await g.ainvoke({"question": "which pathway?"})
    urls = {c.doc_id: c.url for c in out["citations"]}
    assert urls["PMC1"] == "https://citations.gxl.ai/papers/PMC1#L6,38,40"
    assert urls["PMC2"] == "https://citations.gxl.ai/papers/PMC2#L24"


async def test_no_citation_lines_leaves_url_unanchored():
    """Abstract-only / no-map-citations evidence keeps the plain paper-root
    URL — there's nothing deterministic to anchor to."""
    adapter = FakeAdapter()  # use_map defaults False in build_graph's fake-adapter path here
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter, use_map=False)
    out = await g.ainvoke({"question": "topic"})
    assert out["citations"][0].url == "https://citations.gxl.ai/papers/PMC1"


async def test_backfill_replaces_uncitable_hit():
    # 4 hits; PMC2 has no metadata AND no title on the hit itself (genuinely
    # uncitable — nothing to recover from). With max_documents=3 we should
    # still get 3 citable docs by pulling in PMC4 from the buffer.
    hits = [
        PaperHit(doc_id="PMC1", title="T1", source="pmc"),
        PaperHit(doc_id="PMC2", title="", source="pmc"),
        PaperHit(doc_id="PMC3", title="T3", source="pmc"),
        PaperHit(doc_id="PMC4", title="T4", source="pmc"),
    ]
    adapter = FakeAdapter(hits=hits, meta_error_ids={"PMC2"})
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter, max_documents=3)
    out = await g.ainvoke({"question": "q"})
    doc_ids = [c.doc_id for c in out["citations"]]
    assert doc_ids == ["PMC1", "PMC3", "PMC4"]  # PMC2 dropped, PMC4 backfilled
    assert len(out["citations"]) == 3


async def test_proteins_source_threaded_and_cited():
    adapter = FakeAdapter(hits=[PaperHit(doc_id="Q92794", title="KAT6A", source="proteins")])
    g = build_graph(router=_router(source="proteins", full_text=True), synthesizer=_synth, adapter=adapter)
    out = await g.ainvoke({"question": "sequence length of KAT6A?"})
    # get_meta was called with source=proteins (not the default) — the path fix.
    assert adapter.meta_calls[0]["source"] == "proteins"
    cit = out["citations"][0]
    assert cit.url == "https://www.uniprot.org/uniprotkb/Q92794/entry"
    # proteins have no content.lines — no body fetch even with full_text=True.
    assert adapter.content_calls == []
    # a compact proteins summary is used as evidence.
    assert out["documents"][0].body and "UniProt" in out["documents"][0].body


async def test_abstracts_only_clamps_sections():
    adapter = FakeAdapter()
    g = build_graph(
        router=_router("full_text_depth", full_text=True, sections=["results"]),
        synthesizer=_synth,
        adapter=adapter,
        abstracts_only=True,
    )
    out = await g.ainvoke({"question": "results?"})
    assert out["sections"] is None          # clamped
    assert adapter.content_calls == []       # no body fetched at all


async def test_zero_result_falls_back_to_an_unscoped_search():
    """A scoped search that finds nothing retries unscoped.

    The retry used to target `-s abstracts`, which Paperclip's `help search`
    lists but which is not a real corpus (absent from `ls /`, returns "No papers
    found" for every query) — so the fallback could never recover anything.
    """
    class TwoPhase(FakeAdapter):
        async def search(self, query, *, source="pmc", limit=10, sort=None, year=None, ranking=None):
            self.search_calls.append({
                "query": query, "source": source, "limit": limit, "year": year, "ranking": ranking,
            })
            if source == "pmc":
                return SearchResult(hits=[], search_id=None)
            return SearchResult(
                hits=[PaperHit(doc_id="PMC9", title="Fallback", source="pmc", date="2022")],
                search_id="s_fb",
            )

    adapter = TwoPhase()
    g = build_graph(router=_router(source="pmc"), synthesizer=_synth, adapter=adapter)
    out = await g.ainvoke({"question": "obscure topic"})
    assert [c["source"] for c in adapter.search_calls] == ["pmc", None]
    assert [h.doc_id for h in out["hits"]] == ["PMC9"]
    assert any("fell back to an unscoped search" in w for w in out["warnings"])


async def test_unscoped_zero_result_does_not_retry_itself():
    """An already-unscoped, unranked search that finds nothing must not repeat
    the identical query — that returns the same nothing and costs a round trip."""
    adapter = FakeAdapter(hits=[])
    g = build_graph(router=_router(source=None), synthesizer=_synth, adapter=adapter)
    out = await g.ainvoke({"question": "genuinely unmatched topic"})
    assert len(adapter.search_calls) == 1
    assert out["hits"] == []


async def test_search_error_never_raises():
    adapter = FakeAdapter(search_error="transport exploded")
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter)
    out = await g.ainvoke({"question": "anything"})
    # Degrades to an empty-but-complete run with a warning, not an exception.
    assert out["hits"] == []
    assert out["citations"] == []
    assert any("search failed" in w for w in out["warnings"])


async def test_uncitable_hit_is_dropped():
    # No title on the hit itself either -> nothing to recover from, genuinely
    # uncitable.
    hits = [
        PaperHit(doc_id="PMC1", title="T1", source="pmc"),
        PaperHit(doc_id="PMC2", title="", source="pmc"),
    ]
    adapter = FakeAdapter(hits=hits, meta_error_ids={"PMC2"})
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter)
    out = await g.ainvoke({"question": "topic"})
    # PMC2's meta failed -> dropped; only PMC1 survives as citable.
    assert [c.doc_id for c in out["citations"]] == ["PMC1"]
    assert any("uncitable" in w for w in out["warnings"])


async def test_get_meta_failure_recovers_metadata_from_hit():
    """A get_meta failure must not drop an otherwise-good hit when the search
    hit itself already carries usable metadata (title/authors/doi/pub_year/
    snippet) — confirmed live this happens for some `abstracts` (OpenAlex-
    backed) hits even though a direct get_meta retry with the identical
    doc_id succeeds (an intermittent server-side inconsistency, not a
    parsing bug). Recover a citable PaperMeta from the hit instead."""
    hits = [
        PaperHit(
            doc_id="oa_W123", title="Recovered Title", authors="A. Author",
            doi="10.1/recovered", date="2020", source="abstracts",
            snippet="A recovered abstract snippet.",
        ),
    ]
    adapter = FakeAdapter(hits=hits, meta_error_ids={"oa_W123"})
    g = build_graph(router=_router(source="abstracts"), synthesizer=_synth, adapter=adapter)
    out = await g.ainvoke({"question": "topic"})
    assert [c.doc_id for c in out["citations"]] == ["oa_W123"]
    cit = out["citations"][0]
    assert cit.title == "Recovered Title"
    assert cit.doi == "10.1/recovered"
    doc = out["documents"][0]
    assert doc.meta.abstract == "A recovered abstract snippet."
    assert any("recovered from search hit" in w for w in out["warnings"])


async def test_depth_refinement_refetches_with_full_text():
    adapter = FakeAdapter()

    async def insufficient_once(state):
        # Flag shallow only while still abstracts-only; sufficient after refetch.
        if state.get("full_text"):
            return PaperclipDepthEvaluation(sufficient=True, rationale="deep now")
        return PaperclipDepthEvaluation(
            sufficient=False, missing="no mechanism described", rationale="shallow"
        )

    g = build_graph(
        router=_router("keyword_search", full_text=False),
        synthesizer=_synth,
        evaluator=insufficient_once,
        adapter=adapter,
        # Depth loop requires the full-text lever; isolate from map.
        abstracts_only=False,
        use_map=False,
    )
    out = await g.ainvoke({"question": "how does X work?"})
    assert out["refinement_attempted"] is True
    assert out["full_text"] is True
    # After refinement, content was fetched for the papers.
    assert adapter.content_calls, "expected full-text refetch on refinement"


async def test_abstracts_only_clamps_full_text_and_skips_depth():
    adapter = FakeAdapter()
    g = build_graph(
        router=_router("full_text_depth", full_text=True),
        synthesizer=_synth,
        adapter=adapter,
        abstracts_only=True,
    )
    out = await g.ainvoke({"question": "mechanism?"})
    assert out["full_text"] is False           # router choice clamped
    assert adapter.content_calls == []          # no body fetched
    assert out["depth_skip_reason"] == "abstracts_only enabled"


async def test_broad_source_infers_per_hit_root():
    """`source=None` (the new default) can return hits from mixed corpora in
    one result set — get_meta/citation URLs must resolve each hit's VFS root
    from its own doc_id shape, not a single blanket source."""
    hits = [
        PaperHit(doc_id="PMC1", title="Paper", source="pmc"),
        PaperHit(doc_id="fda_abc123", title="Some FDA doc", source="fda"),
    ]
    adapter = FakeAdapter(hits=hits)
    g = build_graph(router=_router(source=None), synthesizer=_synth, adapter=adapter)
    out = await g.ainvoke({"question": "q"})
    assert out["source"] is None  # router's broad choice threaded through unchanged
    meta_sources = {m["doc_id"]: m["source"] for m in adapter.meta_calls}
    assert meta_sources["PMC1"] == "pmc"
    assert meta_sources["fda_abc123"] == "fda"
    fda_cit = next(c for c in out["citations"] if c.doc_id == "fda_abc123")
    assert fda_cit.url == "https://citations.gxl.ai/fda/fda_abc123"


async def test_fda_trials_evidence_fallback_from_hit_snippet():
    """Regression test: fda/trials meta.json doesn't populate title/abstract
    the way paper corpora do (confirmed empty live). The context block and
    citation must fall back to the search hit's own title/snippet, which
    Paperclip DOES populate — mirrors the existing proteins-summary pattern."""
    class FdaEmptyMeta(FakeAdapter):
        async def get_meta(self, doc_id, *, source="pmc"):
            self.meta_calls.append({"doc_id": doc_id, "source": source})
            if source in ("fda", "trials"):
                return PaperMeta(document_id=doc_id, title="", abstract="")
            return _meta(doc_id)

    hits = [PaperHit(
        doc_id="fda_xyz", title="KEYTRUDA QLEX review", source="fda",
        snippet="Merck submitted a BLA for pembrolizumab.",
    )]
    adapter = FdaEmptyMeta(hits=hits)
    g = build_graph(router=_router(source="fda"), synthesizer=_synth, adapter=adapter)
    out = await g.ainvoke({"question": "pembrolizumab approval"})
    doc = out["documents"][0]
    assert doc.meta.title == "KEYTRUDA QLEX review"
    assert doc.meta.abstract == "Merck submitted a BLA for pembrolizumab."
    assert out["citations"][0].title == "KEYTRUDA QLEX review"


# --- sql_aggregate routing (docs/paperclip_rest_endpoint_findings.md §12) --

async def test_sql_aggregate_success_skips_search_and_assemble():
    """A successful SQL route must go straight to synthesis — no search/
    get_meta/get_content calls, since there's nothing to retrieve."""
    sql_result = SqlResult(columns=["n"], rows=[{"n": "217217"}])
    adapter = FakeAdapter(sql_result=sql_result)
    captured = {}

    async def synth(state):
        captured["state"] = state
        return "There are 217217 matching documents."

    g = build_graph(
        router=_router("sql_aggregate", sql_query="SELECT COUNT(*) AS n FROM documents"),
        synthesizer=synth,
        adapter=adapter,
    )
    out = await g.ainvoke({"question": "how many fda documents are there?"})

    assert adapter.sql_calls == [
        {"query": "SELECT COUNT(*) AS n FROM documents", "source": "pmc"}
    ]
    assert adapter.search_calls == []
    assert adapter.meta_calls == []
    assert out["sql_rows"] == [{"n": "217217"}]
    assert out["sql_error"] is None
    assert out["final_answer"] == "There are 217217 matching documents."
    # No retrieval lever to pull -> depth evaluation short-circuits.
    assert out["depth_skip_reason"] == "sql_aggregate has no full-text escalation lever"
    # The synthesizer (fake or real) sees the raw state either way.
    assert captured["state"]["sql_query"] == "SELECT COUNT(*) AS n FROM documents"


async def test_sql_aggregate_falls_back_to_search_on_query_error():
    """A failed SQL query (bad syntax, unsupported source, timeout) must not
    fail the run — falls back to a normal keyword search using the router's
    search_query, exactly like the zero-result search fallback."""
    adapter = FakeAdapter(sql_error="relation \"documents\" does not exist")
    g = build_graph(
        router=_router(
            "sql_aggregate", source="pmc", query="fallback keywords",
            sql_query="SELECT COUNT(*) FROM documents WHERE source = 'trials'",
        ),
        synthesizer=_synth,
        adapter=adapter,
    )
    out = await g.ainvoke({"question": "how many trials are there?"})

    assert adapter.sql_calls, "expected the sql node to have tried the query"
    assert adapter.search_calls, "expected fallback to the search path"
    assert adapter.search_calls[0]["query"] == "fallback keywords"
    # paperclip_sql's never-raise wrapper formats errors as "{type}: {msg}",
    # same convention as every other tool wrapper in this codebase.
    assert out["sql_error"] == 'PaperclipError: relation "documents" does not exist'
    # Fell through to the normal paper-citation path, not left empty.
    assert out["citations"]
    assert "[1]" in out["final_answer"]


async def test_sql_aggregate_with_no_query_falls_back_to_search():
    """Defensive: if the router somehow set sql_aggregate without filling
    sql_query, sql_node must degrade to the search fallback, not crash."""
    adapter = FakeAdapter()
    g = build_graph(
        router=_router("sql_aggregate", source="pmc", query="fallback keywords", sql_query=None),
        synthesizer=_synth,
        adapter=adapter,
    )
    out = await g.ainvoke({"question": "how many?"})
    assert adapter.sql_calls == []  # never even attempted
    assert adapter.search_calls
    assert out["sql_error"] == "no query"


# --- filter (server-side relevance trim, opt-in) --------------------------

async def test_filter_skipped_by_default():
    adapter = FakeAdapter()
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter)
    await g.ainvoke({"question": "topic"})
    assert adapter.filter_calls == []


async def test_filter_trims_hits_when_enabled():
    hits = [
        PaperHit(doc_id="PMC1", title="T1", source="pmc"),
        PaperHit(doc_id="PMC2", title="T2", source="pmc"),
    ]
    adapter = FakeAdapter(hits=hits, filter_hits=[hits[0]])
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter, use_filter=True)
    out = await g.ainvoke({"question": "topic"})
    assert adapter.filter_calls and adapter.filter_calls[0]["search_id"] == "s_fake"
    assert [c.doc_id for c in out["citations"]] == ["PMC1"]


async def test_filter_reverts_to_unfiltered_on_empty_result():
    adapter = FakeAdapter(filter_hits=[])
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter, use_filter=True)
    out = await g.ainvoke({"question": "topic"})
    assert [c.doc_id for c in out["citations"]] == ["PMC1", "PMC2"]
    assert any("filter removed all hits" in w for w in out["warnings"])


async def test_filter_reverts_to_unfiltered_on_error():
    adapter = FakeAdapter(filter_error="filter boom")
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter, use_filter=True)
    out = await g.ainvoke({"question": "topic"})
    assert [c.doc_id for c in out["citations"]] == ["PMC1", "PMC2"]
    assert any("filter failed" in w for w in out["warnings"])


async def test_filter_skipped_when_rest_unavailable():
    adapter = FakeAdapter(filter_none=True)
    g = build_graph(router=_router(), synthesizer=_synth, adapter=adapter, use_filter=True)
    out = await g.ainvoke({"question": "topic"})
    assert adapter.filter_calls  # was attempted
    assert [c.doc_id for c in out["citations"]] == ["PMC1", "PMC2"]  # unfiltered
    assert not any("filter" in w for w in out["warnings"])  # skipped, not a warning-worthy event


async def test_filter_skipped_for_list_breadth():
    adapter = FakeAdapter()
    g = build_graph(router=_router("list_breadth"), synthesizer=_synth, adapter=adapter, use_filter=True)
    await g.ainvoke({"question": "list all X"})
    assert adapter.filter_calls == []


async def test_use_filter_widens_search_fetch():
    """Confirmed live: `filter` can cut a fetch down to single digits or
    zero. search_node must fetch a much larger candidate pool when
    use_filter=True so filter has room to trim without starving
    assemble_context_node below max_documents (the backfill-gap bug)."""
    adapter = FakeAdapter()
    g = build_graph(
        router=_router("keyword_search"), synthesizer=_synth, adapter=adapter,
        use_filter=True, max_documents=7,
    )
    await g.ainvoke({"question": "topic"})
    assert adapter.search_calls
    assert adapter.search_calls[0]["limit"] == 25  # _FILTER_FETCH_LIMIT


async def test_use_filter_false_keeps_normal_fetch_size():
    adapter = FakeAdapter()
    g = build_graph(
        router=_router("keyword_search"), synthesizer=_synth, adapter=adapter,
        use_filter=False, max_documents=7,
    )
    await g.ainvoke({"question": "topic"})
    assert adapter.search_calls[0]["limit"] == 11  # max(10, 7 + 4), unchanged


# --- analogical_search (docs/paperclip_rest_endpoint_findings.md §15) -----

async def test_analogical_search_uses_analogical_query_and_ranking():
    """The primary search call for analogical_search must use
    `analogical_query` (a method-description sentence) with
    `ranking="analogical"` — NOT the keyword-shaped `search_query`."""
    adapter = FakeAdapter()
    g = build_graph(
        router=_router(
            "analogical_search", source=None, query="BTK inhibitor CLL",
            analogical_query="correcting for a systematic detection bias with an unknown mechanism",
        ),
        synthesizer=_synth, adapter=adapter,
    )
    await g.ainvoke({"question": "what other fields use a technique like this?"})
    assert adapter.search_calls
    call = adapter.search_calls[0]
    assert call["query"] == "correcting for a systematic detection bias with an unknown mechanism"
    assert call["ranking"] == "analogical"


async def test_analogical_search_zero_result_fallback_uses_keywords_no_ranking():
    """The zero-result fallback must retry with the keyword-shaped
    `search_query` and the default ranking — never repeat the unranked
    analogical sentence, and never carry `ranking="analogical"` into the
    fallback call."""
    class EmptyPrimary(FakeAdapter):
        async def search(self, query, *, source="pmc", limit=10, sort=None, year=None, ranking=None):
            self.search_calls.append({
                "query": query, "source": source, "limit": limit, "year": year, "ranking": ranking,
            })
            if ranking == "analogical":
                return SearchResult(hits=[], search_id=None)
            return SearchResult(hits=list(self._hits), search_id="s_fb")

    adapter = EmptyPrimary()
    g = build_graph(
        router=_router(
            "analogical_search", source=None, query="BTK inhibitor CLL",
            analogical_query="a method-description sentence",
        ),
        synthesizer=_synth, adapter=adapter,
    )
    out = await g.ainvoke({"question": "what other fields use a technique like this?"})
    assert len(adapter.search_calls) == 2
    assert adapter.search_calls[0]["ranking"] == "analogical"
    assert adapter.search_calls[1]["query"] == "BTK inhibitor CLL"
    assert adapter.search_calls[1]["ranking"] is None
    assert out["hits"], "expected the keyword fallback to succeed"


async def test_analogical_search_without_analogical_query_falls_back_to_keyword_query():
    """Defensive: if the router somehow set analogical_search without filling
    `analogical_query` (should not happen per the schema, but must not crash
    or silently search for nothing), search_node must fall back to the
    keyword `search_query` rather than an empty query."""
    adapter = FakeAdapter()
    g = build_graph(
        router=_router("analogical_search", source=None, query="BTK inhibitor CLL", analogical_query=None),
        synthesizer=_synth, adapter=adapter,
    )
    await g.ainvoke({"question": "q"})
    assert adapter.search_calls
    assert adapter.search_calls[0]["query"] == "BTK inhibitor CLL"
    assert adapter.search_calls[0]["ranking"] is None


async def test_ordinary_keyword_search_never_gets_ranking():
    """Regression guard: adding the analogical route must not leak
    `ranking="analogical"` into any other question_type's search call."""
    adapter = FakeAdapter()
    g = build_graph(router=_router("keyword_search"), synthesizer=_synth, adapter=adapter)
    await g.ainvoke({"question": "what is the mechanism of metformin?"})
    assert adapter.search_calls
    assert all(c["ranking"] is None for c in adapter.search_calls)


async def test_duplicate_doc_ids_yield_one_document_and_one_citation():
    """A result set can carry the same document twice — broad search mixes
    corpora, and `filter` returns a server-rebuilt list. Left undeduplicated,
    one paper occupies two `max_documents` slots, is fetched twice, and appears
    as two numbered references the synthesizer can cite as independent
    support."""
    from crossbar_llm.paperclip_tools.nodes import assemble_context_node

    adapter = FakeAdapter()
    state = {
        "hits": [
            PaperHit(doc_id="PMC1", title="T1", source="pmc"),
            PaperHit(doc_id="PMC1", title="T1", source="pmc"),
            PaperHit(doc_id="PMC2", title="T2", source="pmc"),
        ],
        "warnings": [],
    }
    out = await assemble_context_node(state, adapter=adapter, max_documents=5, use_map=False)

    assert [d.doc_id for d in out["documents"]] == ["PMC1", "PMC2"]
    assert [c.ref_num for c in out["citations"]] == [1, 2]
    fetched = [c["doc_id"] for c in adapter.meta_calls]
    assert fetched.count("PMC1") == 1  # not fetched twice


async def test_meta_recovered_hit_still_gets_full_text():
    """get_meta failing does not make the document unreachable — assembly
    recovers a citable record from the hit's own fields. The body must still be
    fetched, or every such paper silently drops to abstract-only in depth mode.
    """
    from crossbar_llm.paperclip_tools.nodes import assemble_context_node

    adapter = FakeAdapter(meta_error_ids=["PMC1"])
    state = {
        "hits": [PaperHit(doc_id="PMC1", title="T1", source="pmc", snippet="snip")],
        "warnings": [],
        "full_text": True,
    }
    out = await assemble_context_node(state, adapter=adapter, max_documents=5, use_map=False)

    assert [d.doc_id for d in out["documents"]] == ["PMC1"]
    assert out["documents"][0].body, "recovered hit lost its full text"
    assert [c["doc_id"] for c in adapter.content_calls] == ["PMC1"]


async def test_uncitable_hit_does_not_waste_a_content_fetch():
    """The converse: a hit that will be dropped (meta failed AND no title to
    recover from) must not pay for a full-text fetch first."""
    from crossbar_llm.paperclip_tools.nodes import assemble_context_node

    adapter = FakeAdapter(meta_error_ids=["PMC9"])
    state = {
        "hits": [PaperHit(doc_id="PMC9", title="", source="pmc")],
        "warnings": [],
        "full_text": True,
    }
    out = await assemble_context_node(state, adapter=adapter, max_documents=5, use_map=False)

    assert out["documents"] == []
    assert adapter.content_calls == []


async def test_degenerate_answer_run_is_trimmed_and_warned():
    """A model that locks into repeating one character must not reach the caller.

    Observed on llama-3.3-70b: a complete answer, then ~6k `!` after the last
    reference URL. The prose is salvageable, so the run is cut rather than the
    answer dropped.
    """
    async def degenerate(state):
        return "Real answer. References: [1] PMC1" + "!" * 6161

    g = build_graph(router=_router(), synthesizer=degenerate, adapter=FakeAdapter())
    out = await g.ainvoke({"question": "What treats X?"})

    assert out["final_answer"] == "Real answer. References: [1] PMC1!!!"
    assert any("degenerate character run" in w for w in out["warnings"])


async def test_legitimate_punctuation_survives_and_warns_nothing():
    # The table alignment row is the case that matters: it runs well past the
    # punctuation threshold, and trimming it stops the table rendering.
    answer = (
        "Section\n" + "=" * 40 + "\nDone... see [1] --- and [2].\n"
        "| Gene | p |\n|" + "-" * 30 + "|" + "-" * 30 + "|\n| TP53 | .01 |"
    )

    async def punctuated(state):
        return answer

    g = build_graph(router=_router(), synthesizer=punctuated, adapter=FakeAdapter())
    out = await g.ainvoke({"question": "What treats X?"})

    assert out["final_answer"] == answer
    assert not any("degenerate" in w for w in out["warnings"])


async def test_degeneration_on_a_rule_character_is_still_caught():
    """A run far past any real rule is degeneration whatever the character is."""
    async def degenerate(state):
        return "Real answer." + "-" * 6000

    g = build_graph(router=_router(), synthesizer=degenerate, adapter=FakeAdapter())
    out = await g.ainvoke({"question": "What treats X?"})

    assert out["final_answer"] == "Real answer.---"
    assert any("degenerate character run" in w for w in out["warnings"])
