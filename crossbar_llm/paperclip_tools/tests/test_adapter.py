"""Unit tests for the Paperclip adapter's pure parsing/helper logic.

These run fully offline — they exercise the text/JSON parsers and REST-JSON
mapping against captured real-server output. The live round-trip (REST +
MCP fallback) is covered separately in test_paperclip_live.py (key-gated).
"""
from __future__ import annotations

import pytest

from crossbar_llm.paperclip_tools.nodes import citation_url, format_line_anchor
from crossbar_llm.paperclip_tools.adapter import (
    PaperclipError,
    _doc_root,
    _extract_json_object,
    _map_extract_from_text,
    _paper_hit_from_rest,
    _parse_map_results,
    _parse_protein_search,
    _parse_search,
    _parse_section_listing,
    _parse_sql_output,
    _select_section_files,
    _shell_quote,
    infer_source_from_doc_id,
)


def _patch_rest(monkeypatch, handler):
    """Install `handler(url, json, headers, timeout) -> response` as the REST
    layer. The adapter posts through a pooled `httpx.AsyncClient` (see
    `PaperclipAdapter._rest_client`), so the seam is `AsyncClient.post`, not a
    module-level function. `handler` may raise to simulate a transport failure.
    """
    async def fake_post(self, url, *, json, headers, timeout):
        return handler(url, json, headers, timeout)

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)



# Captured verbatim from `search -s pmc "..." -n 3` against the live server.
SEARCH_OUTPUT = """Found 3 papers  [s_c7326471]

  1. Metformin: Beyond Type 2 Diabetes Mellitus
     Rahnuma Ahmad, Mainul Haque
     PMC11486535 · PMC · 2024-10-17
     https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11486535/
     "This review examines metformin's effects on non-alcoholic fatty liver disease."

  2. Molecular mechanism of action of metformin: old or new insights?
     Graham Rena, Ewan R. Pearson, Kei Sakamoto
     PMC3737434 · biomedrxiv · 2013-07-09
     https://doi.org/10.1007/s00125-013-2991-0
     "This review summarizes recent research on metformin's molecular mechanisms."

  3. Adipsin and Leptin Levels in Type 2 Diabetic Patients
     Sura Khalid Mohammed, Zainab Haitham Fathi
     PMC11729846 · PMC · 2024-01-01
     https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11729846/
     "The study compared adipsin and leptin levels in type 2 diabetic patients."

[357ms, saved to s_c7326471]
"""

META_OUTPUT = """{
  "document_id": "PMC11486535",
  "pmc_id": "PMC11486535",
  "pmid": "39421288",
  "doi": "10.7759/cureus.71730",
  "title": "Metformin: Beyond Type 2 Diabetes Mellitus",
  "authors": "Rahnuma Ahmad, Mainul Haque",
  "abstract": "Metformin was developed from an offshoot of Guanidine.",
  "source": "pmc",
  "journal": "Cureus",
  "pub_year": 2024,
  "pub_date": "2024-10-17"
}
[75ms]
"""


def test_parse_search_extracts_all_hits():
    hits = _parse_search(SEARCH_OUTPUT)
    assert [h.doc_id for h in hits] == ["PMC11486535", "PMC3737434", "PMC11729846"]


def test_parse_search_fields():
    hits = _parse_search(SEARCH_OUTPUT)
    h0 = hits[0]
    assert h0.title == "Metformin: Beyond Type 2 Diabetes Mellitus"
    assert h0.authors == "Rahnuma Ahmad, Mainul Haque"
    assert h0.source == "PMC"
    assert h0.date == "2024-10-17"
    assert h0.url == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11486535/"
    assert h0.snippet.startswith("This review examines")
    # The "Found N papers" header line must not leak in as a hit.
    assert all("Found" not in h.title for h in hits)


def test_parse_search_empty():
    assert _parse_search("No results found.\n[12ms]") == []


def test_extract_json_object_strips_timing_footer():
    data = _extract_json_object(META_OUTPUT)
    assert data["doi"] == "10.7759/cureus.71730"
    assert data["pmid"] == "39421288"


def test_extract_json_object_raises_on_non_json():
    with pytest.raises(PaperclipError):
        _extract_json_object("just some prose, no object\n[5ms]")


def test_shell_quote_uses_single_quotes():
    """vsh mis-parses double-quoted args that contain both an inner quote and
    a newline (`parse error: No closing quotation`), so we single-quote."""
    assert _shell_quote("plain") == "'plain'"
    assert _shell_quote('a "b" c') == "'a \"b\" c'"
    # apostrophes must survive - "Alzheimer's disease" is an ordinary query
    assert _shell_quote("Alzheimer's") == "'Alzheimer'\\''s'"
    # the shape that actually broke: newline + embedded double quotes
    q = _shell_quote('Q?\n\n{"answer": "x"}')
    assert q.startswith("'") and q.endswith("'")
    assert '\\"' not in q  # no backslash-escaped quotes inside single quotes


@pytest.mark.parametrize(
    "doc_id,expected_ns",
    [
        ("PMC123", "papers"),
        ("bio_abc", "papers"),
        ("fda_xyz", "fda"),
        ("NCT01234567", "trials"),
        ("tri_555", "trials"),
    ],
)
def test_citation_url_namespace(doc_id, expected_ns):
    assert citation_url(doc_id) == f"https://citations.gxl.ai/{expected_ns}/{doc_id}"


# Captured verbatim from `ls /papers/<id>/sections/` against the live server.
SECTIONS_LISTING = (
    "Title.lines  Metadata.lines  Abstract.lines  1. Introduction.lines  "
    "2. Materials and Methods.lines  2.1. Study Design.lines  "
    "2.10. Statistical Analysis.lines  3. Results.lines  "
    "3.4.1. Renal Function and Uric Acid Levels.lines  4. Discussion.lines  "
    "5. Conclusions.lines  References.lines\n"
    "  (read-only — use /.gxl/ for writable storage)\n[69ms]"
)


def test_parse_section_listing():
    names = _parse_section_listing(SECTIONS_LISTING)
    assert "Abstract" in names
    assert "2. Materials and Methods" in names
    assert "4. Discussion" in names
    # The read-only note and timing footer must not leak in as sections.
    assert not any("read-only" in n for n in names)
    assert not any("ms]" in n for n in names)


def test_select_sections_pulls_subsections_by_number():
    names = _parse_section_listing(SECTIONS_LISTING)
    methods = _select_section_files(names, ["methods"])
    # Section 2 top-level plus its 2.x subsections.
    assert "2. Materials and Methods" in methods
    assert "2.1. Study Design" in methods
    assert "2.10. Statistical Analysis" in methods
    # No cross-contamination from other numbered sections.
    assert "3. Results" not in methods


def test_select_sections_multiple_keywords():
    names = _parse_section_listing(SECTIONS_LISTING)
    picked = _select_section_files(names, ["discussion", "conclusion"])
    assert picked == ["4. Discussion", "5. Conclusions"]


def test_select_sections_no_match_returns_empty():
    names = _parse_section_listing(SECTIONS_LISTING)
    assert _select_section_files(names, ["methods"]) != []
    assert _select_section_files(["Foo", "Bar"], ["methods"]) == []


# --- proteins corpus parsing (different listing shape) ---------------------
PROTEIN_SEARCH = """Found 3 proteins  [s_38a63397]

  1. KAT7 - Histone acetyltransferase KAT7
     O95251
     Homo sapiens · 611 aa

  2. EP300 - Histone acetyltransferase p300
     Q09472
     Homo sapiens · 2414 aa

  3. KAT6B - Histone acetyltransferase KAT6B
     Q8WYB5
     Homo sapiens · 2073 aa

[84ms, saved to s_38a63397]
"""


def test_parse_protein_search():
    hits = _parse_protein_search(PROTEIN_SEARCH)
    assert [h.doc_id for h in hits] == ["O95251", "Q09472", "Q8WYB5"]
    assert hits[0].title == "KAT7 - Histone acetyltransferase KAT7"
    assert hits[0].source == "proteins"
    assert "611 aa" in hits[0].snippet


def test_doc_root_maps_source_to_vfs():
    assert _doc_root("pmc") == "papers"
    assert _doc_root("abstracts") == "papers"
    assert _doc_root("proteins") == "proteins"
    assert _doc_root("uniprot") == "proteins"
    assert _doc_root("fda/us") == "fda"
    assert _doc_root("trials") == "trials"
    assert _doc_root(None) == "papers"


# --- map full-results parsing ---------------------------------------------
MAP_RESULTS = """Map results: 2/2 tasks succeeded in 8846ms
Results ID: m_4a22ca90
Query: What is the mechanism?

--- [1/2] [success] Metformin Improves Mitochondrial Respiratory Activity ---
  doc_id: PMC6866677
  Metformin activates AMPK, which phosphorylates Mff (L34, L815-L818),
  recruiting Drp1 to drive mitochondrial fission.

--- [2/2] [failed] Some Other Paper ---
  doc_id: PMC12511219
  The mechanism is not fully clarified in this paper (L20).
"""


def test_parse_map_results():
    extracts = _parse_map_results(MAP_RESULTS)
    assert [e.doc_id for e in extracts] == ["PMC6866677", "PMC12511219"]
    assert extracts[0].success is True
    assert "phosphorylates Mff" in extracts[0].text
    assert extracts[1].success is False
    # Prose (no --output_schema) parses with no structured data — the
    # backward-compatible path.
    assert extracts[0].data is None


# Captured verbatim from a live `map --output_schema '{"answer":..., "found":...}'`
# call (docs/paperclip_rest_endpoint_findings.md capability-idea follow-up).
MAP_RESULTS_STRUCTURED = """Map results: 2/2 tasks succeeded in 3794ms
Results ID: m_9709a130
Query: What delivery vector or inhibitor mechanism was reported?

--- [1/2] [success] Impact of the clinically approved BTK inhibitors ---
  doc_id: PMC11677227
  {"answer": "All are covalent active site inhibitors, with the exception of the reversible active site inhibitor Pirtobrutinib.", "found": true, "_citations": [{"field": "answer", "line": 9, "content": "All are covalent active site inhibitors."}]}

--- [2/2] [success] Treatment of relapsed/refractory CLL with Zanubrutinib ---
  doc_id: PMC11039307
  {"answer": "Not found", "found": false, "_citations": []}
"""


def test_parse_map_results_structured_output_schema():
    extracts = _parse_map_results(MAP_RESULTS_STRUCTURED)
    assert [e.doc_id for e in extracts] == ["PMC11677227", "PMC11039307"]

    found = extracts[0]
    assert found.text == (
        "All are covalent active site inhibitors, with the exception of the "
        "reversible active site inhibitor Pirtobrutinib."
    )
    assert found.data is not None
    assert found.data["found"] is True
    assert found.data["_citations"][0]["line"] == 9
    assert found.found is True
    assert found.citation_lines == [9]

    not_found = extracts[1]
    assert not_found.text == "Not found"
    assert not_found.data["found"] is False
    assert not_found.found is False
    assert not_found.citation_lines == []


# Captured verbatim from a live `map --output_schema` call where the server
# echoed the schema's own `properties` structure back with `answer`/`found`
# nested inside `answer` instead of flat — confirmed live, not rare (a whole
# 3-paper batch returned this shape in one observed run). Regression fixture
# for the crash this used to cause (dict assigned to MapExtract.text) and the
# found-detection bug (a bare `.data.get("found", True)` defaulted to True
# here since "found" isn't a top-level key in this shape).
MAP_RESULTS_NESTED_MALFORMED = """Map results: 2/2 tasks succeeded in 2749ms
Results ID: m_c9a73dbe
Query: What is the molecular mechanism of action of metformin?

--- [1/2] [success] Understanding the action mechanisms of metformin ---
  doc_id: PMC11010946
  {"answer": {"answer": "Not found", "found": false}, "_citations": []}

--- [2/2] [success] Metformin's multifaceted role in colorectal cancer ---
  doc_id: PMC12595195
  {"answer": {"answer": "At the molecular level, metformin activates AMPK.", "found": true}, "_citations": [{"field": "answer", "line": 24, "content": "At molecular level, metformin activates AMPK and inhibits cell proliferation."}]}
"""


def test_parse_map_results_handles_nested_malformed_shape():
    """Must not crash (the dict-into-str bug), and must correctly detect
    found=False/True even though neither is a top-level key in this shape."""
    extracts = _parse_map_results(MAP_RESULTS_NESTED_MALFORMED)
    assert [e.doc_id for e in extracts] == ["PMC11010946", "PMC12595195"]

    not_found = extracts[0]
    assert not_found.text == "Not found"
    assert not_found.found is False
    assert not_found.citation_lines == []

    found = extracts[1]
    assert found.text == "At the molecular level, metformin activates AMPK."
    assert found.found is True
    assert found.citation_lines == [24]


def test_map_extract_from_text_found_none_when_contract_not_honored():
    """Prose (the model ignored `_MAP_JSON_CONTRACT`) leaves `found` unknown,
    not False — a paper with no found signal must still be treated as usable
    evidence (see assemble_context_node). Inline line refs are still salvaged.
    """
    extract = _map_extract_from_text("PMC1", "Metformin activates AMPK (L34).", success=True)
    assert extract.found is None
    assert extract.citation_lines == [34]


def test_map_extract_from_text_falls_back_to_prose_on_bad_json():
    """A block starting with `{` but not valid/schema-shaped JSON must not
    crash parsing — just treated as prose, same as before schemas existed."""
    extract = _map_extract_from_text("PMC1", "{not actually json", success=True)
    assert extract.text == "{not actually json"
    assert extract.data is None


def test_map_extract_from_text_requires_answer_key():
    """JSON without an `answer` key (e.g. a genuinely different schema) is
    not assumed to match our shape — falls back to raw text rather than
    guessing at a field name."""
    extract = _map_extract_from_text("PMC1", '{"other_field": "x"}', success=True)
    assert extract.data is None
    assert extract.text == '{"other_field": "x"}'


def test_citation_url_proteins_links_to_uniprot():
    assert citation_url("Q92794", "proteins") == "https://www.uniprot.org/uniprotkb/Q92794/entry"
    # paper ids keep the gxl namespace regardless.
    assert citation_url("PMC123", "pmc") == "https://citations.gxl.ai/papers/PMC123"


def test_citation_url_appends_line_anchor():
    assert (
        citation_url("PMC123", "pmc", line_anchor="L45")
        == "https://citations.gxl.ai/papers/PMC123#L45"
    )


def test_citation_url_no_anchor_when_none_given():
    assert citation_url("PMC123", "pmc", line_anchor=None) == "https://citations.gxl.ai/papers/PMC123"
    assert citation_url("PMC123", "pmc", line_anchor="") == "https://citations.gxl.ai/papers/PMC123"


def test_citation_url_line_anchor_ignored_for_uniprot():
    """Proteins have no line-numbered content.lines — a line anchor makes no
    sense there and must not leak into the UniProt URL."""
    assert (
        citation_url("Q92794", "proteins", line_anchor="L45")
        == "https://www.uniprot.org/uniprotkb/Q92794/entry"
    )


@pytest.mark.parametrize("lines,expected", [
    ([], ""),
    ([45], "L45"),
    ([45, 46, 47], "L45-L47"),
    ([210, 45, 120], "L45,120,210"),  # non-contiguous: sorted, comma list
    ([45, 45], "L45"),  # dedup
])
def test_format_line_anchor(lines, expected):
    assert format_line_anchor(lines) == expected


# --- REST migration fixes (docs/paperclip_rest_endpoint_findings.md §6) ----

def test_arxiv_doc_id_not_truncated():
    """Regression test for the arXiv ID truncation bug: `arx_2002.06616` was
    being parsed as `arx_2002` because the old regex was a hex-digit class
    that stopped at the literal `.` in the ID."""
    text = (
        "Found 1 papers  [s_abc]\n\n"
        "  1. A paper about transformers\n"
        "     Some Author\n"
        "     arx_2002.06616 · arXiv · 2020-02-16\n"
        "     https://doi.org/10.1016/example\n"
        '     "a snippet"\n'
    )
    hits = _parse_search(text)
    assert len(hits) == 1
    assert hits[0].doc_id == "arx_2002.06616"


def test_pdb_and_chembl_map_to_proteins_root():
    """Regression test: `-s pdb`/`-s chembl` used to fall through to the
    `"papers"` default root (not in `_SOURCE_ROOT`), routing them to the
    wrong parser and silently returning zero hits."""
    assert _doc_root("pdb") == "proteins"
    assert _doc_root("chembl") == "proteins"


def test_infer_source_from_doc_id():
    """Per-hit source inference used when a search is broad/unscoped and a
    single result set mixes corpora (get_meta/get_content/citation URLs need
    a per-hit VFS root, not one blanket source)."""
    assert infer_source_from_doc_id("PMC12345") == "pmc"
    assert infer_source_from_doc_id("bio_abc123") == "pmc"
    assert infer_source_from_doc_id("med_abc123") == "pmc"
    assert infer_source_from_doc_id("arx_2002.06616") == "pmc"
    assert infer_source_from_doc_id("fda_abc123") == "fda"
    assert infer_source_from_doc_id("tri_abc123") == "trials"
    assert infer_source_from_doc_id("NCT01234567") == "trials"
    assert infer_source_from_doc_id("P04637") == "proteins"


def test_paper_hit_from_rest_maps_structured_fields():
    """Maps the REST path's `result_data.papers[i]` dict shape (confirmed
    live — docs/paperclip_rest_endpoint_findings.md §5.1) into `PaperHit`."""
    hit = _paper_hit_from_rest({
        "document_id": "PMC8261291",
        "source": "biomedrxiv",
        "score": 0.8721041,
        "corpus": "pmc",
        "backend": "qdrant",
        "title": "Some title",
        "tldr": "a summary",
        "doi": "10.3389/fimmu.2021.687458",
        "authors": "A. Author",
        "pub_date": "2021-06-23",
        "pub_year": 2021,
    })
    assert hit.doc_id == "PMC8261291"
    assert hit.title == "Some title"
    assert hit.snippet == "a summary"
    assert hit.score == 0.8721041
    assert hit.corpus == "pmc"
    assert hit.backend == "qdrant"
    assert hit.doi == "10.3389/fimmu.2021.687458"
    assert hit.pub_year == 2021
    assert hit.date == "2021-06-23"


def test_paper_hit_from_rest_falls_back_to_abstract_snippet():
    """Some payloads use `abstract_snippet` instead of `tldr` — confirmed for
    a plain pmc hit shape in the same live response."""
    hit = _paper_hit_from_rest({
        "document_id": "PMC5392013",
        "title": "A paper",
        "abstract_snippet": "the snippet text",
    })
    assert hit.snippet == "the snippet text"


def test_paper_hit_from_rest_tolerates_missing_document_id():
    """Defensive: proteins/fda/trials REST field shapes are unverified (open
    question in the migration plan) — must not crash on an unexpected shape."""
    hit = _paper_hit_from_rest({"accession": "P04637", "title": "TP53"})
    assert hit.doc_id == "P04637"


async def test_slow_command_uses_slow_timeout_on_rest(monkeypatch):
    """Regression test: `map`/`ask-image` used to share the same flat 60s
    timeout as every other command, despite the module's own comment noting
    they can be slow — a real risk once `use_map=True` became the default.
    The real gxl_paperclip SDK gives these a 300s timeout; we now match
    that for the REST path, which sets it precisely per-call."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"output": "", "result_id": None, "result_data": None}

    def fake_post(url, json, headers, timeout):
        captured["timeout"] = timeout
        return FakeResponse()

    _patch_rest(monkeypatch, fake_post)

    adapter = PaperclipAdapter(timeout_s=60.0, slow_timeout_s=300.0)
    await adapter._run_rest("search", '"x" -n 5')
    assert captured["timeout"] == 60.0

    await adapter._run_rest("map", '--from s_x "q"')
    assert captured["timeout"] == 300.0


# --- sql routing (docs/paperclip_rest_endpoint_findings.md §12) --------------

# Captured verbatim from a live `sql -s fda "SELECT COUNT(*) AS n FROM documents"`.
SQL_SINGLE_COLUMN = """n
------
217217
(1 row, 14ms)
"""

# Captured verbatim from a live multi-column query (no -s: spans multiple shards).
SQL_MULTI_COLUMN = """title                                                        | doi                       | source
-------------------------------------------------------------+---------------------------+-------
Transcriptomic Profiling of Orbital Fat Tissue and Ocular... | 10.1167/iovs.66.15.71     | pmc
Btk inhibitor ibrutinib reduces inflammatory myeloid cell... | 10.1186/s10020-018-0069-7 | pmc
(2 rows, 379ms) [bioRxiv (0 rows) + PMC (2 rows)]
"""

SQL_ERROR = """ERR: sql: Only SELECT queries are allowed.
[exit 1]
"""


def test_parse_sql_output_single_column():
    result = _parse_sql_output(SQL_SINGLE_COLUMN)
    assert result.columns == ["n"]
    assert result.rows == [{"n": "217217"}]


def test_parse_sql_output_multi_column_strips_shard_footer():
    result = _parse_sql_output(SQL_MULTI_COLUMN)
    assert result.columns == ["title", "doi", "source"]
    assert len(result.rows) == 2
    assert result.rows[0]["doi"] == "10.1167/iovs.66.15.71"
    assert result.rows[0]["source"] == "pmc"
    # The "(N rows, Xms) [...]" footer must not leak in as a fake row.
    assert all("rows" not in r.get("title", "") for r in result.rows)


def test_parse_sql_output_raises_on_server_error():
    """The server reports query errors (bad SQL, non-SELECT, statement
    timeout) as `ERR: ...` text with a 200/success transport response, not a
    transport-level failure — must be surfaced as PaperclipError ourselves."""
    with pytest.raises(PaperclipError, match="Only SELECT queries are allowed"):
        _parse_sql_output(SQL_ERROR)


def test_parse_sql_output_empty_result():
    result = _parse_sql_output("(0 rows, 5ms)\n")
    assert result.columns == []
    assert result.rows == []


# --- filter (server-side relevance trim, REST-only) -------------------------

def _rest_adapter(monkeypatch, response_json):
    """A PaperclipAdapter whose REST layer returns `response_json`."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return response_json

    _patch_rest(monkeypatch, lambda url, json, headers, timeout: FakeResponse())
    return PaperclipAdapter()


async def test_filter_maps_rest_papers_to_hits(monkeypatch):
    adapter = _rest_adapter(monkeypatch, {
        "output": "Filtered 2 -> 1 relevant papers.",
        "result_id": "s_fake",
        "result_data": {"papers": [{"document_id": "PMC1", "title": "T1"}]},
    })
    result = await adapter.filter("s_fake", "relevance query")
    assert result is not None
    assert result.search_id == "s_fake"
    assert [h.doc_id for h in result.hits] == ["PMC1"]


async def test_filter_raises_on_server_err(monkeypatch):
    adapter = _rest_adapter(monkeypatch, {
        "output": "ERR: filter: no such search id\n[exit 1]",
        "result_id": None,
        "result_data": None,
    })
    with pytest.raises(PaperclipError, match="no such search id"):
        await adapter.filter("s_bogus", "q")


async def test_filter_returns_none_when_rest_disabled(monkeypatch):
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    monkeypatch.setenv("PAPERCLIP_DISABLE_REST", "1")
    adapter = PaperclipAdapter()
    assert await adapter.filter("s_fake", "q") is None


async def test_filter_returns_none_on_rest_unavailable(monkeypatch):
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)

    def broken_post(url, json, headers, timeout):
        raise ConnectionError("refused")

    _patch_rest(monkeypatch, broken_post)
    adapter = PaperclipAdapter()
    assert await adapter.filter("s_fake", "q") is None


# --- ranking (docs/paperclip_rest_endpoint_findings.md §15) ----------------

async def test_search_threads_ranking_flag_into_rest_raw_args(monkeypatch):
    """`ranking` must reach the REST `raw` command string as `--ranking
    <value>`, and must be omitted entirely when not given (the default
    `hybrid` ranking every other route relies on)."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"output": "Found 0 papers  [s_x]", "result_id": "s_x", "result_data": {"papers": []}}

    def fake_post(url, json, headers, timeout):
        captured["raw"] = json["raw"]
        return FakeResponse()

    _patch_rest(monkeypatch, fake_post)
    adapter = PaperclipAdapter()

    await adapter.search("a method-description sentence", source="arxiv", ranking="analogical")
    assert "--ranking analogical" in captured["raw"]

    await adapter.search("plain keywords", source="pmc")
    assert "--ranking" not in captured["raw"]


# `meta.json` for a conference poster (PMC4043507-shaped): the server sends an
# explicit null for fields the record genuinely lacks.
META_WITH_NULLS = {
    "document_id": "PMC4043507",
    "title": "Autosomal dominant mutation in COL7A1 gene",
    "authors": None,
    "abstract": None,
    "doi": "10.1186/1755-8166-7-S1-P58",
    "journal": "Molecular Cytogenetics",
    "pub_year": 2014,
}


def test_paper_meta_accepts_explicit_nulls():
    from crossbar_llm.paperclip_tools.adapter import PaperMeta

    meta = PaperMeta.model_validate(META_WITH_NULLS)
    assert meta.abstract == ""
    assert meta.authors == ""
    # non-null fields still survive — the point is to keep the record, not blank it
    assert meta.journal == "Molecular Cytogenetics"
    assert meta.pub_year == 2014
    assert meta.title.startswith("Autosomal dominant")


def test_paper_meta_missing_keys_still_default():
    from crossbar_llm.paperclip_tools.adapter import PaperMeta

    meta = PaperMeta.model_validate({"document_id": "PMC1"})
    assert (meta.title, meta.authors, meta.abstract) == ("", "", "")


# Captured verbatim from a live REST `map` using _MAP_JSON_CONTRACT (no
# --output_schema, which 500s on REST). Note the inline (L..) refs and the
# absence of any `_citations` field.
MAP_CONTRACT_OUTPUT = """Map results: 5/5 tasks succeeded in 2385ms
Results ID: m_3a13abd2

--- [1/5] [success] The Off-Label Use of SSRIs for Sexual Behavior Management ---
  doc_id: PMC12524134
  {"answer": "This paper reports the off-label use of SSRIs for managing inappropriate sexual behaviors (L8, L14-L16, L72). It also mentions premature ejaculation (L21).", "found": true}

--- [2/5] [success] GenVarFormer: Predicting gene expression from mutations ---
  doc_id: arx_2509.25573
  {"answer": "", "found": false}
"""


def test_parse_map_results_json_contract_without_citations_field():
    """The REST path gets no `_citations`, so line anchors must come from the
    model's inline (L..) refs — otherwise every REST map citation loses its
    line anchor."""
    extracts = _parse_map_results(MAP_CONTRACT_OUTPUT)
    assert len(extracts) == 2

    first = extracts[0]
    assert first.found is True
    assert first.text.startswith("This paper reports")
    # L14-L16 expands so format_line_anchor can re-collapse contiguous runs
    assert first.citation_lines == [8, 14, 15, 16, 21, 72]

    # found=False survives — assemble_context_node drops these as non-evidence
    assert extracts[1].found is False


def test_map_citation_lines_from_text_handles_ranges_and_noise():
    from crossbar_llm.paperclip_tools.adapter import _map_citation_lines_from_text

    assert _map_citation_lines_from_text("no refs here") == []
    assert _map_citation_lines_from_text("(L5)") == [5]
    assert _map_citation_lines_from_text("(L5, L9)") == [5, 9]
    assert _map_citation_lines_from_text("(L20-L23)") == [20, 21, 22, 23]
    assert _map_citation_lines_from_text("(L20-23)") == [20, 21, 22, 23]
    # reversed range still yields the span, not an empty set
    assert _map_citation_lines_from_text("(L23-L20)") == [20, 21, 22, 23]
    # an over-wide range keeps endpoints instead of exploding the anchor
    assert _map_citation_lines_from_text("(L10-L900)") == [10, 900]
    # LEKTI / L1 cell lines etc. must not be read as line refs
    assert _map_citation_lines_from_text("LEKTI protein and SPINK5") == []


def test_map_citation_lines_prefers_server_citations_over_inline():
    """When Paperclip does supply `_citations` (the MCP path), it wins — it's
    server-computed rather than model-emitted."""
    raw = ('{"answer": "Metformin activates AMPK (L999).", "found": true, '
           '"_citations": [{"field": "answer", "line": 24, "content": "..."}]}')
    extract = _map_extract_from_text("PMC1", raw, success=True)
    assert extract.citation_lines == [24]


@pytest.mark.parametrize("status", [401, 429])
async def test_rest_auth_and_quota_errors_do_not_fall_back_to_mcp(monkeypatch, status):
    """401/429 are account-level verdicts. MCP uses the same key against the
    same quota, so falling back can only add latency and noise — these must
    surface directly instead of being swallowed as 'REST unavailable'."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter, PaperclipError

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)

    class FakeResponse:
        status_code = status
        text = '{"detail":"You\'ve hit the daily limit on map/verify operations (100/day)."}'

    _patch_rest(monkeypatch, lambda *a, **kw: FakeResponse())

    async def fail_mcp(self, command):
        raise AssertionError("must not fall back to MCP on an account-level error")

    monkeypatch.setattr(PaperclipAdapter, "_run", fail_mcp)

    with pytest.raises(PaperclipError) as exc:
        await PaperclipAdapter().run_map("s_1", "q")
    assert str(status) in str(exc.value)


async def test_rest_client_is_pooled_per_adapter(monkeypatch):
    """The client must be reused across calls — that reuse is the whole point
    (measured ~37% faster on sequential calls by skipping the TLS handshake).
    A fresh client per call would silently undo it."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    adapter = PaperclipAdapter()
    assert adapter._rest_client() is adapter._rest_client()

    # ...but scoped per adapter, never global: build_graph() makes one adapter
    # per run, so two concurrent users must not share a connection pool.
    assert PaperclipAdapter()._rest_client() is not adapter._rest_client()

    await adapter.aclose()


async def test_aclose_is_idempotent(monkeypatch):
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    adapter = PaperclipAdapter()
    adapter._rest_client()
    await adapter.aclose()
    await adapter.aclose()


# Captured verbatim from a live REST `map` — REST returns the CLI's coloured
# terminal output, MCP does not.
MAP_OUTPUT_WITH_ANSI = (
    "\x1b[1mMap complete: 3/3 papers\x1b[0m\nResults ID: \x1b[2mm_7049c74c\x1b[0m\n"
)


def test_map_id_survives_ansi_colour_codes():
    """The dim code `\\x1b[2m` ends in the letter `m`, so it butts against the
    `m_...` id and kills `_MAP_ID_RE`'s leading `\\b`. Stripping ANSI at the
    transport boundary is what keeps the id findable."""
    from crossbar_llm.paperclip_tools.adapter import _MAP_ID_RE, _strip_ansi

    assert _MAP_ID_RE.search(MAP_OUTPUT_WITH_ANSI) is None  # the trap
    assert _MAP_ID_RE.search(_strip_ansi(MAP_OUTPUT_WITH_ANSI)).group(1) == "m_7049c74c"


def test_strip_ansi_is_idempotent_and_preserves_text():
    from crossbar_llm.paperclip_tools.adapter import _strip_ansi

    clean = _strip_ansi(MAP_OUTPUT_WITH_ANSI)
    assert clean == "Map complete: 3/3 papers\nResults ID: m_7049c74c\n"
    assert _strip_ansi(clean) == clean  # MCP output is already clean; no-op there


async def test_run_rest_strips_ansi_from_output(monkeypatch):
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"output": MAP_OUTPUT_WITH_ANSI, "result_id": None}

    _patch_rest(monkeypatch, lambda *a, **kw: FakeResponse())
    data = await PaperclipAdapter()._run_rest("map", "--from s_1 'q'")
    assert "\x1b" not in data["output"]


# Captured verbatim from a live REST search that returned a full listing in
# `output` but omitted `result_data` entirely (~8% of calls). ANSI already
# stripped, as `_run_rest` does before any parsing.
REST_PAYLOAD_NO_RESULT_DATA = {
    "output": (
        "Found 2 papers  [s_42d99d49]\n"
        "\n"
        "  1. Molecular Mechanism of Huanglian Jiedu Decoction in Alzheimer's Disease\n"
        "     Qiuyan Ye, Xue Li, Wei Gao\n"
        "     bio_75ad981a7345 · bioRxiv · 2024-05-15\n"
        "     https://doi.org/10.1101/2024.05.15.594364\n"
        '     "Network pharmacology analysis of the decoction."\n'
        "\n"
        "  2. Adipsin and Leptin Levels in Type 2 Diabetic Patients\n"
        "     Sura Khalid Mohammed\n"
        "     PMC11729846 · PMC · 2024-01-01\n"
        "     https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11729846/\n"
        '     "The study compared adipsin and leptin levels."\n'
        "\n"
        "[357ms, saved to s_42d99d49]\n"
    ),
    "exit_code": 0,
    "result_id": "s_42d99d49",
    "result_data": None,
}


def test_rest_hits_recovered_when_result_data_missing():
    """The server intermittently returns a complete listing while omitting
    `result_data`. Reading only the structured field reported those searches
    as zero-hit, which then tripped the node's zero-result fallback as though
    nothing matched. Parse the text listing instead."""
    from crossbar_llm.paperclip_tools.adapter import _hits_from_rest_payload

    hits = _hits_from_rest_payload(
        REST_PAYLOAD_NO_RESULT_DATA, REST_PAYLOAD_NO_RESULT_DATA["output"], None
    )
    assert [h.doc_id for h in hits] == ["bio_75ad981a7345", "PMC11729846"]
    assert hits[0].title.startswith("Molecular Mechanism")


def test_rest_hits_prefer_structured_result_data():
    """When `result_data` IS present it wins — it carries score/doi/pub_year
    that the text listing doesn't have."""
    from crossbar_llm.paperclip_tools.adapter import _hits_from_rest_payload

    payload = {
        "output": REST_PAYLOAD_NO_RESULT_DATA["output"],  # says 2 papers
        "result_data": {"papers": [{"document_id": "PMC1", "title": "T", "doi": "10.1/x"}]},
    }
    hits = _hits_from_rest_payload(payload, payload["output"], None)
    assert [h.doc_id for h in hits] == ["PMC1"]
    assert hits[0].doi == "10.1/x"


def test_rest_genuinely_empty_search_stays_empty():
    """A real zero-result search must NOT be rescued into phantom hits."""
    from crossbar_llm.paperclip_tools.adapter import _hits_from_rest_payload

    payload = {"output": "No results found.\n[12ms]", "result_data": None}
    assert _hits_from_rest_payload(payload, payload["output"], None) == []


async def test_filter_reports_skipped_when_result_data_missing(monkeypatch):
    """filter's text output is only a summary ("Filtered: 5 -> 2 papers") with
    no listing, so a missing `result_data` must degrade to "couldn't filter"
    (None -> caller keeps unfiltered hits), never to "removed everything"."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "output": "Filtered: 5 → 2 papers (3 removed as irrelevant) in 374ms",
                "result_id": "s_1",
                "result_data": None,
            }

    _patch_rest(monkeypatch, lambda *a, **kw: FakeResponse())
    assert await PaperclipAdapter().filter("s_1", "q") is None


@pytest.mark.parametrize(
    "query,should_reach_server",
    [
        ("SELECT 1", True),
        ("SELECT COUNT(*) FROM documents;", True),          # trailing ; is fine
        ("WITH x AS (SELECT 1) SELECT * FROM x", True),     # CTEs are read-only
        ("SELECT 1; DROP TABLE documents", False),
        ("select 1; delete from documents", False),
        ("DROP TABLE documents", False),
    ],
)
async def test_sql_guard_rejects_appended_statements(query, should_reach_server):
    """The prefix check alone let `SELECT 1; DROP TABLE ...` through — it starts
    with SELECT. Paperclip enforces read-only server-side, so this was never the
    only guard, but a check that misses the obvious case reads as protection
    without being any."""
    from crossbar_llm.paperclip_tools.tools import paperclip_sql
    from crossbar_llm.paperclip_tools.adapter import SqlResult

    seen = []

    class Adapter:
        async def sql(self, q, *, source=None):
            seen.append(q)
            return SqlResult(columns=[], rows=[])

    out = await paperclip_sql(Adapter(), query)
    assert bool(seen) is should_reach_server
    assert (out.error is None) is should_reach_server


async def test_search_requests_the_full_corpus_by_default(monkeypatch):
    """Without `--all` the server silently limits results to recent papers:
    measured 5.0 hits vs 13.6 at `-n 14`, and the Denosumab question came back
    with only 2025-2026 papers instead of the 2008-2014 RANKL literature."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"output": "Found 0 papers  [s_x]", "result_id": "s_x",
                    "result_data": {"papers": []}}

    def fake_post(url, json, headers, timeout):
        captured["raw"] = json["raw"]
        return FakeResponse()

    _patch_rest(monkeypatch, fake_post)
    adapter = PaperclipAdapter()

    await adapter.search("metformin", limit=14)
    assert "--all" in captured["raw"]

    # `--year` is an explicit recency filter, so the two must not be combined.
    await adapter.search("metformin", limit=14, year="2024")
    assert "--all" not in captured["raw"]
    assert "--year 2024" in captured["raw"]


def test_abstracts_is_not_an_allowed_scope():
    """`help search` advertises `-s abstracts`, but it is absent from `ls /` and
    returns "No papers found" for every query — so the router must not be able
    to choose it, and the zero-result fallback must not target it."""
    from typing import get_args

    from crossbar_llm.paperclip_tools.schemas import PaperclipSourceChoice
    from crossbar_llm.paperclip_tools.adapter import PaperclipSource, _SOURCE_ROOT

    assert "abstracts" not in get_args(PaperclipSourceChoice)
    assert "abstracts" not in get_args(PaperclipSource)
    assert "abstracts" not in _SOURCE_ROOT


async def test_map_surfaces_the_server_error_message(monkeypatch):
    """A server-side map failure arrives as HTTP 200 with `ERR: <message>` in
    the body. Reporting only "no results id" hid a real Paperclip outage
    (`ERR: map: 'tpm_used'`) behind what looked like our own parsing bug."""
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter, PaperclipError

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"output": "ERR: map: 'tpm_used'\n[exit 1]", "result_id": None}

    _patch_rest(monkeypatch, lambda *a, **kw: FakeResponse())

    with pytest.raises(PaperclipError) as exc:
        await PaperclipAdapter().run_map("s_1", "q")
    assert "tpm_used" in str(exc.value)


async def test_map_reports_unparseable_output_verbatim(monkeypatch):
    from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter, PaperclipError

    monkeypatch.setenv("PAPERCLIP_API_KEY", "test-key")
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"output": "something unexpected entirely", "result_id": None}

    _patch_rest(monkeypatch, lambda *a, **kw: FakeResponse())

    with pytest.raises(PaperclipError) as exc:
        await PaperclipAdapter().run_map("s_1", "q")
    assert "something unexpected" in str(exc.value)
