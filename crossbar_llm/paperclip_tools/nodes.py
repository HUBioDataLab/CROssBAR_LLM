"""Standalone LangGraph node functions for the Paperclip pipeline.

Each node is a plain coroutine `async def node(state, *, adapter, ...) -> dict`
returning a partial `PaperclipState` to merge. **No LLM lives here** — the
LLM-bound nodes (router, synthesize, evaluate_depth) live inside `build_graph`
because they close over the chat model and prompts. Everything here is pure data
plumbing around the never-raise Paperclip tool wrappers, so it is deterministic
and unit-testable with a fake adapter injected at the seam.
"""
from __future__ import annotations

import asyncio

from crossbar_llm.paperclip_tools.schemas import (
    Citation,
    PaperContext,
    PaperclipState,
)
from crossbar_llm.paperclip_tools.tools import (
    paperclip_filter,
    paperclip_get_content,
    paperclip_get_meta,
    paperclip_map,
    paperclip_search,
    paperclip_sql,
)
from crossbar_llm.paperclip_tools.adapter import (
    PaperclipAdapterProtocol,
    PaperMeta,
    infer_source_from_doc_id,
)

# Base search fan-out and the breadth-question fan-out.
_DEFAULT_LIMIT = 10
_BREADTH_LIMIT = 25
# Extra hits fetched beyond `max_documents` so uncitable hits can be backfilled
# from the buffer rather than shrinking the evidence set.
_BACKFILL_BUFFER = 4
# Wider fan-out when `filter` will run afterward. Confirmed live: filter can cut
# a ~14-hit fetch to single digits or zero, which `_BACKFILL_BUFFER`'s +4 cannot
# absorb — without this, a filtered search starves assembly below max_documents
# even when filter behaves correctly.
_FILTER_FETCH_LIMIT = 25

# Sources whose meta.json doesn't populate title/authors/abstract the way
# paper corpora do (confirmed live). Evidence for these falls back to the
# search hit's own title/snippet, which Paperclip does populate.
_REGULATORY_TRIAL_SOURCES = frozenset({
    "fda", "fda/us", "fda/jp", "fda/eu",
    "trials", "trials/us", "trials/eu", "trials/jp", "trials/cn",
})


def _add_warning(state: PaperclipState, msg: str) -> list[str]:
    return [*state.get("warnings", []), msg]


def citation_url(doc_id: str, source: str | None = None, *, line_anchor: str | None = None) -> str:
    """Build the citation URL for a doc id.

    Paper/FDA/trial corpora use Paperclip's citation host; the proteins corpus
    is a UniProt accession, so we link to UniProt directly (it has no gxl
    citation namespace, and no line concept — `line_anchor` is ignored there).

    `line_anchor` (e.g. `"L45"`, `"L45-L52"`, `"L45,120,210"` — see
    `format_line_anchor`) appends a `#<anchor>` fragment per Paperclip's own
    citation-format spec, pointing at the specific supporting line(s) instead
    of just the paper root."""
    src = (source or "").lower()
    if src in ("proteins", "uniprot") and not doc_id.startswith(("PMC", "bio_", "med_", "arx_")):
        return f"https://www.uniprot.org/uniprotkb/{doc_id}/entry"
    if doc_id.startswith("fda_"):
        ns = "fda"
    elif doc_id.startswith("tri_") or doc_id.startswith("NCT"):
        ns = "trials"
    else:
        ns = "papers"
    url = f"https://citations.gxl.ai/{ns}/{doc_id}"
    return f"{url}#{line_anchor}" if line_anchor else url


def format_line_anchor(lines: list[int]) -> str:
    """Render supporting line numbers as a citation fragment, per Paperclip's
    own format: single `L45`, contiguous range `L45-L52`, or a comma list
    `L45,120,210` for non-contiguous lines. Empty string for no lines."""
    uniq = sorted(set(lines))
    if not uniq:
        return ""
    if len(uniq) == 1:
        return f"L{uniq[0]}"
    if uniq == list(range(uniq[0], uniq[-1] + 1)):
        return f"L{uniq[0]}-L{uniq[-1]}"
    return "L" + ",".join(str(n) for n in uniq)


def _proteins_summary(meta) -> str:
    """A compact evidence string for a proteins-corpus hit (which has no
    abstract or full text — deeper feature/domain data lives in the UniProt SQL
    views, not fetched here)."""
    parts = [
        meta.protein_name or meta.title,
        f"gene {meta.gene_name}" if meta.gene_name else "",
        meta.organism or "",
        f"UniProt {meta.uniprot_id or meta.accession or meta.document_id}",
    ]
    return "; ".join(p for p in parts if p)


async def search_node(
    state: PaperclipState,
    *,
    adapter: PaperclipAdapterProtocol,
    max_documents: int = 10,
    use_filter: bool = False,
) -> dict:
    """Run the primary search, with a zero-result free-text fallback.

    Fetches a few more hits than `max_documents` (the backfill buffer) so
    `assemble` can replace uncitable hits instead of shrinking the evidence set.
    `source=None` (the router's default) searches broadly across the general
    literature corpora in one call rather than guessing a single corpus — see
    `PaperclipAdapter.search`.
    The router always fills `search_query`, so any route can degrade to a
    broader retry rather than returning "no information": if the primary search
    yields nothing, we retry once against the broad `abstracts` corpus.

    `analogical_search` (§5.13) uses `analogical_query` — a method/problem-
    description sentence, not keywords — for the PRIMARY call only, with
    `ranking="analogical"`. The zero-result fallback always uses
    `search_query` (keywords) with the default ranking, same as every other
    route: a keyword-shaped retry is a more useful safety net than repeating
    an unranked analogical query, and matches `search_query`'s own documented
    role as the universal fallback.

    `use_filter=True` widens the fetch to `_FILTER_FETCH_LIMIT` (unless
    `list_breadth`, which is already wide and which `filter_node` skips
    outright) — confirmed live that `filter` can cut a fetch down to single
    digits or zero, and the normal backfill buffer alone leaves no room for
    that cut on top of the usual uncitable-hit backfill.
    """
    question_type = state.get("question_type")
    search_query = (state.get("search_query") or state.get("question") or "").strip()
    analogical_query = (state.get("analogical_query") or "").strip()
    use_analogical = question_type == "analogical_search" and bool(analogical_query)
    query = analogical_query if use_analogical else search_query
    ranking = "analogical" if use_analogical else None
    source = state.get("source")
    year = state.get("year")
    if question_type == "list_breadth":
        limit = _BREADTH_LIMIT
    elif use_filter:
        limit = max(_FILTER_FETCH_LIMIT, max_documents + _BACKFILL_BUFFER)
    else:
        limit = max(_DEFAULT_LIMIT, max_documents + _BACKFILL_BUFFER)

    warnings = list(state.get("warnings", []))
    queries_used: list[str] = []

    if not query:
        warnings.append("no search query available; nothing to retrieve.")
        return {"hits": [], "search_id": None, "queries_used": [], "warnings": warnings}

    out = await paperclip_search(adapter, query, source=source, limit=limit, year=year, ranking=ranking)
    queries_used.append(f"[{source or 'broad'}{' analogical' if use_analogical else ''}] {query}")
    hits = list(out.hits) if not out.error else []
    search_id = out.search_id
    if out.error:
        warnings.append(f"search failed for '{query}' (-s {source}): {out.error}")

    # Zero-result fallback: drop the corpus scope, the year filter and any
    # analogical ranking, and retry unscoped with the plain keyword
    # `search_query` — a keyword retry is the useful safety net here. Only run
    # it when that actually differs from what was just tried; an identical
    # repeat would return the same nothing.
    #
    # This used to retry against `-s abstracts`, which is listed in Paperclip's
    # own `help search` but is not a real corpus: it is absent from `ls /` and
    # returns "No papers found" for every query tried, so the fallback could
    # never recover anything.
    retry_differs = bool(source or year or ranking or query != search_query)
    if not hits and retry_differs:
        fb_out = await paperclip_search(adapter, search_query, source=None, limit=limit)
        queries_used.append(f"[broad] {search_query}")
        if fb_out.error:
            warnings.append(f"fallback broad search failed: {fb_out.error}")
        elif fb_out.hits:
            warnings.append(
                f"primary search returned 0 results; fell back to an unscoped "
                f"search ({len(fb_out.hits)} hits)."
            )
            hits = list(fb_out.hits)
            search_id = fb_out.search_id
            source = None

    if not hits:
        warnings.append("No papers found for the query.")

    return {
        "hits": hits,
        "search_id": search_id,
        "source": source,
        "queries_used": queries_used,
        "warnings": warnings,
    }


async def sql_node(state: PaperclipState, *, adapter: PaperclipAdapterProtocol) -> dict:
    """Run the router's SQL query for `question_type == "sql_aggregate"`.

    SQL is a precision tool for structured aggregates (counts/rankings by
    source, year, journal, ...) and can legitimately fail in ways full-text
    search wouldn't — a malformed query, an unsupported source (trials/
    proteins aren't SQL-queryable at all — confirmed live, see
    `PaperclipAdapter.sql`), or the server's 15s statement timeout on an
    unindexed pattern. On failure this does NOT fail the run: it records
    `sql_error` and leaves `hits`/`search_id` unset, so the graph's
    conditional edge can route to the normal `search` node instead, using
    the router's `search_query` fallback exactly like the zero-result path.
    """
    query = (state.get("sql_query") or "").strip()
    source = state.get("source")
    warnings = list(state.get("warnings", []))

    if not query:
        warnings.append("sql_aggregate route had no sql_query; falling back to search.")
        return {"sql_error": "no query", "warnings": warnings}

    out = await paperclip_sql(adapter, query, source=source)
    if out.error:
        warnings.append(f"SQL query failed ({out.error}); falling back to search.")
        return {"sql_error": out.error, "warnings": warnings}

    return {
        "sql_columns": out.columns,
        "sql_rows": out.rows,
        "sql_error": None,
        "warnings": warnings,
    }


async def assemble_context_node(
    state: PaperclipState,
    *,
    adapter: PaperclipAdapterProtocol,
    max_documents: int = 7,
    content_max_lines: int | None = None,
    use_map: bool = False,
) -> dict:
    """Enrich hits into citable context for synthesis.

    For each hit we fetch `meta.json` (the citable DOI/PMID record). Evidence
    body per paper is, in priority order:
      1. a `map` extraction (full-text-derived, server-side) when `use_map`;
      2. full body / target sections when `full_text` depth is on;
      3. the abstract only (from meta), otherwise.
    Uncitable hits (metadata fetch fails) are dropped and **backfilled** from
    the remaining hits so we still reach `max_documents` citable papers.

    A paper cited from map evidence gets a **line-anchored** citation URL
    (`#L<n>`) built from Paperclip's own per-answer line provenance — see
    `adapter.py`'s `_map_citation_lines` and this module's `format_line_anchor`
    — instead of a blanket paper root link; abstract/full-text evidence has
    no such deterministic anchor (the synthesis prompt asks the model to
    self-cite a specific full-text line instead, when full-text evidence is
    used).

    `source` may now be `None` (broad/unscoped search) or a comma-separated
    list (the MCP fallback's paper-corpora substitute) — either way a single
    result set can mix corpora, so `get_meta`/`get_content`/citation URLs
    resolve each hit's VFS root from its own `doc_id` shape
    (`infer_source_from_doc_id`) rather than one blanket source string.
    """
    # Deduplicate by doc_id, keeping rank order: a broad search mixes corpora
    # and `filter` returns a server-rebuilt list, so one document can arrive
    # twice and would otherwise be cited as two independent references.
    seen: set[str] = set()
    hits = [
        h for h in (state.get("hits") or [])
        if h.doc_id and not (h.doc_id in seen or seen.add(h.doc_id))
    ]
    warnings = list(state.get("warnings", []))
    full_text = bool(state.get("full_text", False))
    sections = state.get("sections") or None
    source = state.get("source")
    # "papers" (the broad-search alias) and a comma list both mean "multiple
    # corpora in one result set" — resolve source per-hit in either case.
    is_broad = not source or source == "papers" or "," in source

    if not hits:
        return {"documents": [], "citations": []}

    # Resolve once per hit so `_one()` and the final assembly loop agree.
    hit_sources: dict[str, str] = {
        h.doc_id: (infer_source_from_doc_id(h.doc_id) if is_broad else source)
        for h in hits
    }

    # Optional map pass: one server-side call reads full text across the result
    # set and answers the question per paper. High-recall evidence at no full-
    # body token cost to us.
    map_extracts: dict[str, str] = {}
    map_citation_lines: dict[str, list[int]] = {}
    if use_map and state.get("search_id"):
        # map_question is a full extraction question, unlike search_query's
        # keywords — a vague one here yields vague per-paper answers and a
        # weaker found/not-found signal.
        map_question = state.get("map_question") or state.get("question", "")
        map_out = await paperclip_map(
            adapter, state["search_id"], map_question, limit=len(hits)
        )
        if map_out.error:
            warnings.append(f"map extraction failed: {map_out.error}; using abstracts.")
        else:
            # `run_map` asks for an {answer, found} contract. When the model
            # honored it, `.found is False` means this paper explicitly
            # doesn't address the question — exclude it rather than using
            # "not found"-shaped text as if it were evidence. `.found is None`
            # (contract not honored for that paper) is treated as usable.
            usable = [e for e in map_out.extracts if e.success and e.text and e.found is not False]
            map_extracts = {e.doc_id: e.text for e in usable}
            # Line-level provenance, so a citation points at the supporting
            # lines rather than the paper root. Server-computed when available,
            # else recovered from the model's inline refs.
            map_citation_lines = {e.doc_id: e.citation_lines for e in usable if e.citation_lines}

    async def _one(hit):
        hit_source = hit_sources[hit.doc_id]
        is_proteins_hit = hit_source in ("proteins", "uniprot", "pdb", "chembl")
        meta_out = await paperclip_get_meta(adapter, hit.doc_id, source=hit_source)
        # map ran once over the whole result set, so its evidence survives a
        # per-hit get_meta failure — look it up regardless.
        body = map_extracts.get(hit.doc_id)
        # A failed get_meta doesn't make the document unreachable — assembly
        # below recovers a citable record from the hit's own fields when it has
        # a title. So fetch the body for anything that will survive assembly,
        # independent of the get_meta outcome.
        will_be_citable = not (meta_out.error or meta_out.meta is None) or bool(hit.title)
        content_err = None
        if body is None and full_text and not is_proteins_hit and will_be_citable:
            content_out = await paperclip_get_content(
                adapter, hit.doc_id, source=hit_source,
                sections=sections, max_lines=content_max_lines,
            )
            if content_out.error:
                content_err = content_out.error
            else:
                body = content_out.content
        return hit, meta_out, body, content_err

    results = await asyncio.gather(*(_one(h) for h in hits))

    documents: list[PaperContext] = []
    citations: list[Citation] = []
    ref_num = 0
    for hit, meta_out, body, content_err in results:
        if len(documents) >= max_documents:
            break
        meta = meta_out.meta
        if meta_out.error or meta is None:
            if hit.title:
                # get_meta can fail intermittently even when the doc_id is
                # valid (confirmed live for some `abstracts`/OpenAlex hits —
                # a server-side inconsistency, not a parsing bug). Recover a
                # citable PaperMeta from the search hit's own fields rather
                # than dropping otherwise-good evidence — same "trust the
                # hit's own fields" pattern as the fda/trials fallback below.
                warnings.append(
                    f"could not fetch metadata for {hit.doc_id} "
                    f"({meta_out.error or 'no meta'}); recovered from search hit."
                )
                meta = PaperMeta(
                    document_id=hit.doc_id, title=hit.title, authors=hit.authors,
                    doi=hit.doi, pub_year=hit.pub_year, abstract=hit.snippet,
                )
            else:
                warnings.append(
                    f"could not fetch metadata for {hit.doc_id}; dropped "
                    f"(uncitable, backfilling): {meta_out.error or 'no meta'}."
                )
                continue
        if content_err:
            warnings.append(
                f"full text unavailable for {hit.doc_id}; using abstract only: {content_err}."
            )
        hit_source = hit_sources[hit.doc_id]
        is_proteins_hit = hit_source in ("proteins", "uniprot", "pdb", "chembl")
        # Proteins have no abstract/body — synthesise a compact evidence line.
        if is_proteins_hit and not body:
            body = _proteins_summary(meta)
        # fda/trials meta.json doesn't populate title/abstract like paper
        # corpora do (confirmed empty live) — backfill from the search hit's
        # own title/snippet, which Paperclip DOES populate, so both the
        # context block fed to the synthesizer (which reads meta.title/
        # meta.abstract directly) and the citation below see real content.
        if hit_source in _REGULATORY_TRIAL_SOURCES and not meta.title and not meta.abstract:
            meta.title = meta.title or hit.title
            meta.abstract = meta.abstract or hit.snippet
        ref_num += 1
        documents.append(PaperContext(doc_id=hit.doc_id, meta=meta, body=body))
        line_anchor = format_line_anchor(map_citation_lines.get(hit.doc_id, []))
        citations.append(
            Citation(
                ref_num=ref_num,
                doc_id=hit.doc_id,
                title=meta.title or meta.protein_name or hit.title,
                authors=meta.authors,
                journal=meta.journal or (meta.organism if is_proteins_hit else None),
                year=meta.pub_year,
                doi=meta.doi,
                pmid=meta.pmid,
                url=citation_url(hit.doc_id, hit_source, line_anchor=line_anchor),
            )
        )

    if not documents:
        warnings.append("No citable documents assembled from the search hits.")

    return {"documents": documents, "citations": citations, "warnings": warnings}


async def filter_node(
    state: PaperclipState, *, adapter: PaperclipAdapterProtocol, use_filter: bool = False
) -> dict:
    """Trim search hits to relevant ones via Paperclip's `filter`, before the
    more expensive per-hit get_meta/get_content/map work in
    `assemble_context_node`.

    Opt-in (`use_filter`, off by default) and REST-only (see
    `PaperclipAdapter.filter`) — a quality improvement, never a correctness
    requirement, so any failure/unavailability/empty result reverts to the
    original unfiltered hits rather than failing the run. Skipped for
    `list_breadth`: that route wants broad coverage, which relevance-filtering
    would fight against.
    """
    if not use_filter:
        return {}
    hits = state.get("hits") or []
    search_id = state.get("search_id")
    warnings = list(state.get("warnings", []))
    if not hits or not search_id or state.get("question_type") == "list_breadth":
        return {}

    query = state.get("question") or state.get("search_query") or ""
    out = await paperclip_filter(adapter, search_id, query)
    if out.error:
        warnings.append(f"filter failed ({out.error}); using unfiltered results.")
        return {"warnings": warnings}
    if out.skipped:
        return {}
    if not out.hits:
        warnings.append("filter removed all hits as irrelevant; using unfiltered results.")
        return {"warnings": warnings}
    return {"hits": out.hits, "warnings": warnings}


__all__ = [
    "_add_warning",
    "citation_url",
    "format_line_anchor",
    "search_node",
    "sql_node",
    "filter_node",
    "assemble_context_node",
]
