"""Never-raise wrappers around the Paperclip MCP adapter.

Paperclip is consumed by a deterministic adapter node, not by the
orchestrating LLM. So these are not LLM-facing LangChain `@tool`s over a global
client (as PubTator3's are); they are internal coroutines that take the injected
`PaperclipAdapterProtocol` (the single test seam) and wrap each call so it
**never raises** — failures come back in the `error` field. Nodes then decide how
to degrade, which is what keeps the graph robust to a single failing MCP call.
"""
from __future__ import annotations

from pydantic import BaseModel

from crossbar_llm.paperclip_tools.adapter import (
    MapExtract,
    PaperclipAdapterProtocol,
    PaperHit,
    PaperMeta,
)


class SearchOutput(BaseModel):
    hits: list[PaperHit] = []
    search_id: str | None = None
    error: str | None = None


class MetaOutput(BaseModel):
    meta: PaperMeta | None = None
    error: str | None = None


class ContentOutput(BaseModel):
    doc_id: str
    content: str = ""
    error: str | None = None


class MapOutput(BaseModel):
    extracts: list[MapExtract] = []
    error: str | None = None


class SqlOutput(BaseModel):
    columns: list[str] = []
    rows: list[dict] = []
    error: str | None = None


class FilterOutput(BaseModel):
    hits: list[PaperHit] = []
    skipped: bool = False
    error: str | None = None


async def paperclip_search(
    adapter: PaperclipAdapterProtocol,
    query: str,
    *,
    source: str | None = None,
    limit: int = 10,
    sort: str | None = None,
    year: str | None = None,
    ranking: str | None = None,
) -> SearchOutput:
    """Run a Paperclip search. Returns ranked hits + the result-set id, or an
    error envelope.

    `source=None` (the default) searches broadly across the general
    literature corpora in one call. Pass an explicit `source` only for a
    narrow corpus (fda/trials/proteins/pdb/chembl/a single preprint server).

    `ranking="analogical"` (analogical_search route only) finds papers
    sharing the same structural method across domains rather than the same
    topic — requires `query` to be a method/problem-description sentence,
    not keywords (see `PaperclipRouterDecision.analogical_query`).

    An empty `hits` list with no `error` means the query genuinely matched
    nothing (the node's fallback path handles that).
    """
    try:
        result = await adapter.search(
            query, source=source, limit=limit, sort=sort, year=year, ranking=ranking
        )
        return SearchOutput(hits=result.hits, search_id=result.search_id)
    except Exception as e:
        return SearchOutput(error=f"{type(e).__name__}: {e}")


async def paperclip_get_meta(
    adapter: PaperclipAdapterProtocol, doc_id: str, *, source: str = "pmc"
) -> MetaOutput:
    """Fetch a record's `meta.json` — the citable-ID record (DOI/PMID, or the
    UniProt fields for the proteins corpus)."""
    try:
        meta = await adapter.get_meta(doc_id, source=source)
        return MetaOutput(meta=meta)
    except Exception as e:
        return MetaOutput(error=f"{type(e).__name__}: {e}")


async def paperclip_get_content(
    adapter: PaperclipAdapterProtocol,
    doc_id: str,
    *,
    source: str = "pmc",
    sections: list[str] | None = None,
    max_lines: int | None = None,
) -> ContentOutput:
    """Fetch full-text body for a document (the depth knob).

    `sections` (e.g. ["methods", "results"]) restricts retrieval to those body
    sections; omit it for the whole body.
    """
    try:
        content = await adapter.get_content(
            doc_id, source=source, sections=sections, max_lines=max_lines
        )
        return ContentOutput(doc_id=doc_id, content=content)
    except Exception as e:
        return ContentOutput(doc_id=doc_id, error=f"{type(e).__name__}: {e}")


async def paperclip_map(
    adapter: PaperclipAdapterProtocol,
    search_id: str,
    question: str,
    *,
    limit: int | None = None,
) -> MapOutput:
    """Run Paperclip's `map` over a saved search result set — a server-side,
    full-text, per-paper extraction of `question`. Never raises."""
    try:
        extracts = await adapter.run_map(search_id, question, limit=limit)
        return MapOutput(extracts=extracts)
    except Exception as e:
        return MapOutput(error=f"{type(e).__name__}: {e}")


_SELECT_ONLY_ERROR = "Only SELECT queries are allowed."
_MULTI_STATEMENT_ERROR = "Only a single statement is allowed."

# A leading `WITH ... SELECT` is an ordinary read-only aggregate and the router
# can legitimately emit one, so the prefix check accepts it too.
_READ_ONLY_PREFIXES = ("SELECT", "WITH")


def _is_single_read_only_statement(query: str) -> str | None:
    """Return an error string if `query` isn't a single read-only statement.

    Prefix-matching alone was not the "defense in depth" the docstring claimed:
    `SELECT 1; DROP TABLE documents` starts with SELECT and sailed through.
    Paperclip enforces read-only server-side, so this was never the only guard,
    but a check that misses the obvious case is worse than no check at all
    because it reads as protection.
    """
    stripped = query.strip().rstrip(";").strip()
    if not stripped.upper().startswith(_READ_ONLY_PREFIXES):
        return _SELECT_ONLY_ERROR
    # A `;` with anything after it means a second statement was appended.
    if ";" in stripped:
        return _MULTI_STATEMENT_ERROR
    return None


async def paperclip_sql(
    adapter: PaperclipAdapterProtocol,
    query: str,
    *,
    source: str | None = None,
) -> SqlOutput:
    """Run a read-only SQL query against Paperclip's `documents` table.

    Rejects anything not starting with `SELECT` (case-insensitive) BEFORE
    sending it — defense in depth against the router LLM emitting something
    else, on top of (not instead of) the server's own read-only enforcement.
    Never raises.
    """
    guard_error = _is_single_read_only_statement(query)
    if guard_error:
        return SqlOutput(error=guard_error)
    try:
        result = await adapter.sql(query, source=source)
        return SqlOutput(columns=result.columns, rows=result.rows)
    except Exception as e:
        return SqlOutput(error=f"{type(e).__name__}: {e}")


async def paperclip_filter(
    adapter: PaperclipAdapterProtocol, search_id: str, query: str
) -> FilterOutput:
    """Trim a saved search result set to relevant papers via Paperclip's
    server-side relevance filter. Never raises.

    `adapter.filter()` returns `None` when REST is unavailable (filter has no
    MCP fallback) — that's surfaced as `skipped=True`, not `error`, so callers
    can tell "filtering wasn't possible, use the unfiltered hits" apart from
    "filtering actually failed".
    """
    try:
        result = await adapter.filter(search_id, query)
        if result is None:
            return FilterOutput(skipped=True)
        return FilterOutput(hits=result.hits)
    except Exception as e:
        return FilterOutput(error=f"{type(e).__name__}: {e}")


__all__ = [
    "SearchOutput",
    "MetaOutput",
    "ContentOutput",
    "MapOutput",
    "SqlOutput",
    "FilterOutput",
    "paperclip_search",
    "paperclip_get_meta",
    "paperclip_get_content",
    "paperclip_map",
    "paperclip_sql",
    "paperclip_filter",
]
