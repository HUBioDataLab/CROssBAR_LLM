"""Thin typed async adapter over Paperclip, with two transports.

Paperclip (https://paperclip.gxl.ai) exposes the same command set two ways: a
first-class MCP server, and a REST endpoint (`/api/cli/execute`) that turns
out to also accept our API key even though it's undocumented for that auth
mode. **REST is primary** (it supports a genuine
unscoped/all-sources `search` and returns structured JSON, neither of which
MCP's `search` allows); **MCP is the fallback** (documented, guaranteed to
keep working, used automatically whenever REST fails or is disabled via
`PAPERCLIP_DISABLE_REST=1`).

This module wraps both transports behind typed helpers (`search`, `get_meta`,
`get_content`) so the rest of the agent never sees raw command strings, REST
JSON, or the MCP protocol. `PaperclipAdapterProtocol` is the single injectable
seam: tests pass a fake with the same signatures into `build_graph(adapter=...)`;
production uses `PaperclipAdapter`. (Renamed from `mcp_adapter.py`/
`PaperclipMCPAdapter` once REST became primary; not `PaperclipClient` since
that collides with the real `gxl_paperclip` SDK's own class name.)

Design notes:
- **No agent logic here.** Typed models in, typed models out. Retrieval choices
  (source, depth, fallback) live in the node layer.
- **Per-event-loop singletons** for the MCP client + loaded tool, keyed in a
  `WeakKeyDictionary`, so `asyncio.run` in tests/scripts doesn't hit "event loop
  is closed" (mirrors `pubtator3/client.py`).
- Command errors surface as `PaperclipError`; the tool layer converts those to
  never-raise error envelopes. REST failures surface as
  `PaperclipRestUnavailable` internally, caught by `_execute`/`search` to
  trigger the MCP fallback — they never escape this module as that type.

No client-side rate limiter is applied: Paperclip publishes no request-rate
policy, so throttling would be guesswork. Add one here if the server later
documents limits.

CLI facts pinned against the live server:
- `search -s <source> "<query>" -n <N>` — over MCP, the `-s` source flag is
  REQUIRED (confirmed live, contradicts Paperclip's own docs/help text). Over
  REST, `-s` is optional and omitting it searches broadly across sources —
  `source=None` uses this; the MCP fallback substitutes a paper-corpora list
  since MCP has no unscoped mode.
- `cat /papers/<doc_id>/meta.json` — clean JSON: pmid, doi, pmc_id, title,
  authors, abstract, journal, pub_year, ... (the citable-ID source).
- `cat`/`head /papers/<doc_id>/content.lines` — line-numbered `L<n>: ...` body.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import weakref
from typing import Literal, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field, field_validator

# --- Module constants ---------------------------------------------------------
MCP_URL = "https://paperclip.gxl.ai/mcp"
# Undocumented for API-key auth, but confirmed working and used as the primary
# transport anyway. `PAPERCLIP_DISABLE_REST=1` forces MCP-only — a safety valve
# if this endpoint ever changes or locks down.
REST_URL = "https://paperclip.gxl.ai/api/cli/execute"
DISABLE_REST_ENV = "PAPERCLIP_DISABLE_REST"
API_KEY_ENV = "PAPERCLIP_API_KEY"
DEFAULT_TIMEOUT_S = 60.0            # search/cat/head/ls — typically fast
# `map`/`ask-image` read full text server-side and can take minutes. 480s, not
# 300s: 300 is langchain_mcp_adapters' default `sse_read_timeout`, and sitting on
# that edge lets a merely-slow job look like a dead stream and trigger a
# reconnect — a path confirmed to fail auth server-side.
SLOW_TIMEOUT_S = 480.0
_SLOW_COMMANDS = frozenset({"map", "ask-image"})
DEFAULT_SOURCE = "pmc"
DEFAULT_CONTENT_MAX_LINES = 400    # cap full-text body pulled per paper

_log = logging.getLogger(__name__)

# Paperclip source scopes accepted by `search -s`. Kept as a Literal so the tool
# and router schemas can reference one canonical list.
PaperclipSource = Literal[
    "pmc",
    "biorxiv",
    "medrxiv",
    "arxiv",
    "fda",
    "fda/us",
    "fda/jp",
    "fda/eu",
    "trials",
    "trials/us",
    "trials/eu",
    "trials/jp",
    "trials/cn",
    "proteins",
    "pdb",
    "chembl",
]

# Document-id prefixes Paperclip uses across corpora, for parsing search output
# and for choosing the citation-URL namespace. arXiv ids are `YYMM.NNNNN`
# (contain a literal dot) -- NOT a hex-digit class, unlike bio_/med_'s hashes.
_DOC_ID_RE = re.compile(r"(PMC\d+|bio_[0-9a-fA-F]+|med_[0-9a-fA-F]+|arx_[\w.]+|fda_\w+|tri_\w+|NCT\w+)")
# Trailing timing/footer lines the CLI appends, e.g. "[75ms]" or
# "[357ms, saved to s_c7326471]". Stripped before JSON parsing.
_TIMING_FOOTER_RE = re.compile(r"^\s*\[\d+ms.*\]\s*$", re.MULTILINE)

# Canonical body-section names the router/nodes can request, mapped to the
# lowercase keywords we match against Paperclip's per-paper section filenames
# (which vary: "2. Materials and Methods", "3. Results", "5. Conclusions", ...).
# Title + abstract are NOT here — abstracts come from meta.json and are the
# default depth; these are the *body* sections fetched only for full-text depth.
PaperclipSectionName = Literal[
    "introduction",
    "methods",
    "results",
    "discussion",
    "conclusion",
]

SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "introduction": ("introduction", "background"),
    "methods": ("method", "materials and methods", "methodology", "experimental"),
    "results": ("result", "findings"),
    "discussion": ("discussion",),
    "conclusion": ("conclusion",),
}

# One directory listing entry ends in ".lines"; names may contain single spaces
# ("2. Materials and Methods"), while entries are separated by 2+ spaces.
_SECTION_FILE_RE = re.compile(r"(?P<name>.+?)\.lines(?=\s{2,}|\s*$)")

# Maps a search `-s <source>` scope to the read-only VFS root the corpus lives
# under. The paper corpora all live under /papers/; regulatory, trials, and
# proteins have their own roots. Used to address `meta.json` / `content.lines`
# for a hit (proteins are NOT under /papers/ — the earlier bug).
_SOURCE_ROOT: dict[str, str] = {
    "pmc": "papers",
    "papers": "papers",  # the _BROAD_MCP_SOURCES alias, made explicit rather
    # than relying on the dict's own fallback default to resolve it the same way
    "biorxiv": "papers",
    "medrxiv": "papers",
    "arxiv": "papers",
    "fda": "fda",
    "fda/us": "fda",
    "fda/jp": "fda",
    "fda/eu": "fda",
    "trials": "trials",
    "trials/us": "trials",
    "trials/eu": "trials",
    "trials/jp": "trials",
    "trials/cn": "trials",
    "proteins": "proteins",
    "uniprot": "proteins",
    "pdb": "proteins",
    "chembl": "proteins",
}

# MCP has no unscoped search mode, so a broad/unscoped request falls back to
# this scope. `-s papers` is Paperclip's own documented alias for
# pmc+biorxiv+medrxiv+arxiv (confirmed live on both transports) — used
# instead of hand-joining those four so we track their definition if it
# changes. Deliberately excludes fda/trials/proteins: mixing those into one
# multi-source call was confirmed live to be slow and to silently drop them
# from the results.
_BROAD_MCP_SOURCES = "papers"

# The `s_xxxx` result-set id in a search footer, and the `m_xxxx` results id a
# map run reports. Both are needed to chain search -> map -> cat full results.
_SEARCH_ID_RE = re.compile(r"\[(s_[0-9a-fA-F]+)\]")
_MAP_ID_RE = re.compile(r"\b(m_[0-9a-fA-F]+)\b")
# Per-paper block header in the full map results file:
#   --- [1/3] [success] <title> ---
_MAP_BLOCK_RE = re.compile(r"^---\s*\[\d+/\d+\]\s*\[(?P<status>\w+)\].*?---\s*$", re.MULTILINE)

# Paperclip intermittently fails to resolve a search id it issued moments
# earlier — `ls /.gxl/` lists the result file while `map --from <id>` reports
# it missing, and consecutive identical calls disagree. Measured at ~2/10
# calls; a plain retry recovered about half. Server-side state we can't
# address from here (there is no session cookie to pin to an instance), so
# retry is the mitigation, not a fix.
#
# It arrives as HTTP 200 with `exit_code: 0` and the error only in the body
# text, so it MUST be detected by string match — no status code reveals it.
_MAP_NOT_FOUND = "Results not found"
_MAP_NOT_FOUND_RETRIES = 2
_MAP_RETRY_BACKOFF_S = 0.5

# The per-paper answer contract `run_map` asks for. Deliberately minimal —
# `found` lets us gate on "this paper doesn't address the question" explicitly
# instead of the old heuristic of treating any non-empty free-text answer as
# usable evidence. Kept as a dict because it documents the shape
# `_map_answer_and_found` parses; the wire format is the prompt text below.
MAP_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "Direct answer to the question from this paper, or empty if not addressed.",
        },
        "found": {
            "type": "boolean",
            "description": "Whether this paper actually addresses the question.",
        },
    },
    "required": ["answer", "found"],
}

# We ask for that contract in the QUESTION TEXT rather than via Paperclip's
# `--output_schema` flag, because that flag makes their REST endpoint return
# HTTP 500 for any schema value whatsoever — confirmed live down to an 18-byte
# `{"type": "object"}`, while the identical call succeeds over MCP. REST is our
# primary transport, and forcing every map onto MCP is what exposed us to their
# stream-resume auth failure, so the flag costs far more than it buys. The map
# model honors this instruction reliably; `_map_extract_from_text` parses the
# result identically either way.
#
# The one thing lost is Paperclip's automatic `_citations` field (server-computed
# line provenance), which only ships alongside `--output_schema`. The model still
# writes line refs inline in its answer, so `_map_citation_lines_from_text`
# recovers them — LLM-emitted rather than server-verified, but present.
_MAP_JSON_CONTRACT = (
    "Respond with ONLY a JSON object, no prose before or after, in exactly this form: "
    '{"answer": "<your answer, citing supporting line numbers inline like (L12, L20-L25)>", '
    '"found": true or false}. '
    'Set "found" to false if this paper does not address the question.'
)


class PaperclipError(RuntimeError):
    """A Paperclip command failed (transport, auth, or CLI-level error)."""


class PaperclipConfigError(PaperclipError):
    """The adapter is misconfigured (e.g. missing API key)."""


class PaperclipRestUnavailable(PaperclipError):
    """The REST endpoint failed (network, timeout, non-200, bad JSON) — signals
    the caller to fall back to the MCP path. Never raised past `_execute`."""


class PaperHit(BaseModel):
    """One ranked search result. `doc_id` is the stable handle for follow-up
    `get_meta` / `get_content` calls and for building citation URLs.

    `score`/`corpus`/`backend`/`doi`/`pub_year` are only populated when the
    hit came from the REST path's structured `result_data.papers` — they stay
    `None` on the MCP text-parsing fallback path (nothing was lost; those
    fields were never available there either)."""
    doc_id: str
    title: str = ""
    authors: str = ""
    source: str = ""
    date: str = ""
    url: str = ""
    snippet: str = ""
    score: float | None = None
    corpus: str | None = None
    backend: str | None = None
    doi: str | None = None
    pub_year: int | None = None


class PaperMeta(BaseModel):
    """Structured metadata from a corpus record's `meta.json` — the reliable
    provenance record the synthesis contract cites.

    Covers both the paper corpora (`doi`/`pmid`/`abstract`/`journal`) and the
    `proteins` corpus (`accession`/`uniprot_id`/`protein_name`/`gene_name`/
    `organism`), which has no DOI/abstract. `extra="ignore"` tolerates the
    schema differences between corpora."""
    document_id: str = Field(alias="document_id")
    pmc_id: str | None = None
    pmid: str | None = None
    doi: str | None = None
    title: str = ""
    authors: str = ""
    abstract: str = ""
    journal: str | None = None
    pub_year: int | None = None
    pub_date: str | None = None
    article_type: str | None = None
    source: str | None = None
    # proteins corpus fields
    accession: str | None = None
    uniprot_id: str | None = None
    protein_name: str | None = None
    gene_name: str | None = None
    organism: str | None = None

    model_config = {"populate_by_name": True, "extra": "ignore"}

    # meta.json carries an explicit `null` for these on records that genuinely
    # lack them (conference posters, meeting abstracts, editorials). A field
    # default only applies when the key is ABSENT, so without this a valid
    # `"abstract": null` response fails validation and the whole record is
    # discarded — which cost us the journal/article_type of ~30% of hits.
    @field_validator("title", "authors", "abstract", mode="before")
    @classmethod
    def _null_to_empty(cls, v):
        return "" if v is None else v


class SearchResult(BaseModel):
    """A search response: ranked hits plus the server-side result-set id
    (`s_xxxx`) that `map` operates on. The id survives across MCP calls (it is
    keyed by the API key/workspace, not the connection), so a later `run_map`
    can reference it."""
    hits: list[PaperHit] = []
    search_id: str | None = None


class SqlResult(BaseModel):
    """Rows from a Paperclip `sql` query, parsed from its ASCII table output.

    Unlike `search`/`map`, `sql` gives no structured JSON on either transport
    (confirmed live: REST's `result_data` is `null` for this command) — every
    row's values come back as strings, exactly as Paperclip renders them in
    its table (no numeric/type coercion). `documents` is not one unified
    table; see `PaperclipAdapter.sql`'s docstring for shard-scoping caveats
    confirmed live."""
    columns: list[str] = []
    rows: list[dict] = []


class MapExtract(BaseModel):
    """One paper's answer from a `map` run — a full-text-derived extraction of
    the question against a single paper (produced server-side, so it does not
    cost us full-body tokens).

    `data` carries the full parsed `{answer, found, _citations}` object when
    the server honored `MAP_OUTPUT_SCHEMA`, `None` if it fell back to raw
    prose (never assume it's populated). `found`/`citation_lines` are
    normalized projections of `data` — prefer these over reading `data`
    directly, since the server has been observed live to return the
    structured answer in two shapes for the same schema (flat, or a
    malformed nested echo of the schema's own `properties`);
    `_map_extract_from_text` normalizes both."""
    doc_id: str
    text: str = ""
    success: bool = True
    data: dict | None = None
    found: bool | None = None
    citation_lines: list[int] = []


@runtime_checkable
class PaperclipAdapterProtocol(Protocol):
    """The single injectable seam. Production is `PaperclipAdapter`; tests
    pass a fake implementing these coroutines."""

    async def search(
        self,
        query: str,
        *,
        source: str | None = None,
        limit: int = 10,
        sort: str | None = None,
        year: str | None = None,
        ranking: str | None = None,
    ) -> SearchResult: ...

    async def get_meta(self, doc_id: str, *, source: str = DEFAULT_SOURCE) -> PaperMeta: ...

    async def get_content(
        self,
        doc_id: str,
        *,
        source: str = DEFAULT_SOURCE,
        sections: list[str] | None = None,
        max_lines: int | None = None,
    ) -> str: ...

    async def run_map(
        self, search_id: str, question: str, *, limit: int | None = None
    ) -> list[MapExtract]: ...

    async def sql(self, query: str, *, source: str | None = None) -> SqlResult: ...

    async def filter(self, search_id: str, query: str) -> SearchResult | None: ...


# --- Per-loop singletons ------------------------------------------------------
# The MCP client + loaded tool are bound to the event loop that created them;
# key them by the running loop so repeated `asyncio.run` calls (tests, scripts)
# each get their own rather than reusing a closed-loop instance.
_tools_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, object]" = weakref.WeakKeyDictionary()


def _api_key() -> str:
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise PaperclipConfigError(
            f"{API_KEY_ENV} is not set; Paperclip requires an API key "
            f"(create one at https://paperclip.gxl.ai). "
        )
    return key


async def _paperclip_tool(*, timeout_s: float = DEFAULT_TIMEOUT_S):
    """Lazily load and cache the single `paperclip` MCP tool for this loop."""
    loop = asyncio.get_running_loop()
    tool = _tools_by_loop.get(loop)
    if tool is not None:
        return tool

    # Imported lazily so importing this module doesn't require the MCP client
    # (keeps `from ... import PaperHit` cheap for schema-only consumers).
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "paperclip": {
                "transport": "streamable_http",
                "url": MCP_URL,
                "headers": {"X-API-Key": _api_key()},
                "timeout": timeout_s,
                # Explicit, not left to the library default — see SLOW_TIMEOUT_S.
                "sse_read_timeout": timeout_s,
            }
        }
    )
    tools = await client.get_tools()
    if not tools:
        raise PaperclipError("Paperclip MCP server exposed no tools.")
    # The server exposes exactly one tool ("paperclip"); pick it by name if
    # present, else the first (defensive against future renames).
    tool = next((t for t in tools if t.name == "paperclip"), tools[0])
    _tools_by_loop[loop] = tool
    return tool


# REST returns the CLI's terminal output verbatim, ANSI colour codes included;
# MCP does not. Left in, they break parsers in non-obvious ways: the dim code
# `\x1b[2m` ends in the letter `m`, so `Results ID: \x1b[2mm_7049c74c` has no
# word boundary before the id and `_MAP_ID_RE`'s `\b` never matches. Strip at
# both transport boundaries so every parser downstream sees the same clean text.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _strip_timing(text: str) -> str:
    return _TIMING_FOOTER_RE.sub("", text).strip()


def _parse_section_listing(text: str) -> list[str]:
    """Parse `ls /papers/<id>/sections/` output into section basenames.

    The listing is space-separated `<Name>.lines` entries (names may contain
    single spaces; entries are separated by 2+ spaces), followed by a
    "(read-only ...)" note and a `[..ms]` footer. Returns names without the
    `.lines` suffix, e.g. ["Abstract", "1. Introduction", "3. Results", ...].
    """
    body = _strip_timing(text)
    # Drop the parenthetical read-only note line(s).
    body = "\n".join(
        ln for ln in body.splitlines() if not ln.strip().startswith("(")
    )
    return [m.group("name").strip() for m in _SECTION_FILE_RE.finditer(body)]


def _select_section_files(available: list[str], wanted: list[str]) -> list[str]:
    """Pick the section files that satisfy the requested canonical sections.

    Matching is keyword-based (see `SECTION_KEYWORDS`) against the paper's own
    section names. Because Paperclip splits a section into fine-grained
    subsection files ("2. Materials and Methods" + "2.1. Study Design" + ...),
    when a numbered top-level section matches a keyword we also pull all of its
    subsections (files sharing the same leading integer). Non-numbered sections
    (e.g. a bare "Conclusions") are matched by keyword directly.
    """
    keywords: list[str] = []
    for w in wanted:
        keywords.extend(SECTION_KEYWORDS.get(w.lower(), (w.lower(),)))

    matched_numbers: set[str] = set()
    for name in available:
        m = re.match(r"^(\d+)[.\s]", name)
        if m and any(kw in name.lower() for kw in keywords):
            matched_numbers.add(m.group(1))

    selected: list[str] = []
    for name in available:
        num = re.match(r"^(\d+)", name)
        if num and num.group(1) in matched_numbers:
            selected.append(name)
        elif not num and any(kw in name.lower() for kw in keywords):
            selected.append(name)
    return selected


def _extract_json_object(text: str) -> dict:
    """Pull the first top-level JSON object out of a CLI response (which may
    carry a trailing `[75ms]` timing footer)."""
    stripped = _strip_timing(text)
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(stripped):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(stripped[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise PaperclipError("Paperclip response did not contain a JSON object.")


def _parse_search(text: str) -> list[PaperHit]:
    """Parse the human-readable `search` listing into PaperHit rows.

    The format per hit is:

        1. <title>
           <authors>
           <doc_id> · <source> · <date>
           <url>
           "<snippet>"

    Only `doc_id` is load-bearing (it drives `get_meta`/`get_content` and the
    citation URL); title/snippet are captured as a cheap preview. Reliable
    fields (doi, pmid, authors, journal) come from `get_meta`, not from here.
    """
    hits: list[PaperHit] = []
    # Split into per-result blocks starting at "<n>. ".
    blocks = re.split(r"\n\s*\d+\.\s", "\n" + _strip_timing(text))
    for block in blocks[1:]:
        lines = [ln.rstrip() for ln in block.splitlines()]
        if not lines:
            continue
        title = lines[0].strip()
        m = _DOC_ID_RE.search(block)
        if not m:
            continue  # header line ("Found N papers") or a malformed block
        doc_id = m.group(1)

        authors = source = date = url = snippet = ""
        for ln in lines[1:]:
            s = ln.strip()
            if not s:
                continue
            if " · " in s and _DOC_ID_RE.search(s):
                parts = [p.strip() for p in s.split(" · ")]
                # parts: [<doc_id>, <source>, <date>]
                if len(parts) >= 2:
                    source = parts[1]
                if len(parts) >= 3:
                    date = parts[2]
            elif s.startswith("http"):
                url = s
            elif s.startswith('"') and s.endswith('"') and len(s) > 1:
                snippet = s[1:-1]
            elif not authors and not source and not url:
                # First non-empty line after the title, before the id line.
                authors = s
        hits.append(
            PaperHit(
                doc_id=doc_id, title=title, authors=authors,
                source=source, date=date, url=url, snippet=snippet,
            )
        )
    return hits


def _doc_root(source: str | None) -> str:
    """VFS root directory for a hit from the given search source."""
    return _SOURCE_ROOT.get((source or DEFAULT_SOURCE).lower(), "papers")


# UniProt accession format (proteins corpus doc ids), e.g. O95251, Q09472, P04637.
_UNIPROT_ACC_RE = re.compile(r"^[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$")


def infer_source_from_doc_id(doc_id: str) -> str:
    """Best-effort corpus guess from a doc_id's shape alone.

    Needed once a search can be broad/unscoped (multiple corpora in one
    result set, e.g. the REST default-all path, or the MCP fallback's
    comma-separated paper-corpora substitute): a single blanket `source`
    string is no longer necessarily correct for every hit, so per-hit
    follow-ups (`get_meta`/`get_content`/citation URLs) need to resolve each
    hit's own VFS root from its doc_id rather than the search-level source.
    Mirrors the prefix logic already used by `citation_url` in
    `paperclip_nodes.py`.
    """
    if doc_id.startswith(("PMC", "bio_", "med_", "arx_")):
        return "pmc"
    if doc_id.startswith("fda_"):
        return "fda"
    if doc_id.startswith(("tri_", "NCT")):
        return "trials"
    if _UNIPROT_ACC_RE.match(doc_id):
        return "proteins"
    return "pmc"


def _parse_protein_search(text: str) -> list[PaperHit]:
    """Parse the `-s proteins` listing, whose per-hit format differs from papers:

        1. KAT7 - Histone acetyltransferase KAT7
           O95251
           Homo sapiens · 611 aa

    The accession (line 2) is the `doc_id`; the title is line 1; the organism +
    length line becomes the snippet. No DOI/URL here (those come from get_meta).
    """
    hits: list[PaperHit] = []
    blocks = re.split(r"\n\s*\d+\.\s", "\n" + _strip_timing(text))
    for block in blocks[1:]:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        title = lines[0]
        acc = next((ln for ln in lines[1:] if _UNIPROT_ACC_RE.match(ln)), "")
        if not acc:
            continue
        snippet = next((ln for ln in lines[1:] if " · " in ln), "")
        hits.append(
            PaperHit(doc_id=acc, title=title, source="proteins", snippet=snippet)
        )
    return hits


def _map_answer_and_found(parsed: dict) -> tuple[str, bool | None]:
    """Normalize the two structured-answer shapes confirmed live for
    `MAP_OUTPUT_SCHEMA`: the flat `{"answer": str, "found": bool}` we
    requested, and a malformed nested echo of the schema's own `properties`,
    `{"answer": {"answer": str, "found": bool}}`. Returns `("", None)` if
    `answer` is neither a string nor this specific nested shape — never
    raises, so one paper's malformed response can't take down the batch."""
    answer = parsed.get("answer")
    found = parsed.get("found")
    if isinstance(answer, dict):
        found = answer.get("found", found)
        answer = answer.get("answer", "")
    if not isinstance(answer, str):
        answer = ""
    return answer, found if isinstance(found, bool) else None


def _map_citation_lines(parsed: dict) -> list[int]:
    """Extract Paperclip's own line-level provenance for the `answer` field —
    `_citations`, an automatic bonus field added regardless of the requested
    schema (confirmed live: `[{"field": "answer", "line": <int>, "content":
    "<supporting text>"}, ...]`, a top-level key in both known `answer`
    shapes). Sorted + deduped; empty if absent/malformed. This is the
    deterministic, server-provided data line-level citation URLs are built
    from — not something the synthesizing LLM has to identify or copy."""
    raw = parsed.get("_citations")
    if not isinstance(raw, list):
        return []
    lines = {
        c["line"] for c in raw
        if isinstance(c, dict) and isinstance(c.get("line"), int)
    }
    return sorted(lines)


# Line refs the map model writes inline in its answer: "(L8, L14-L16, L72)".
# Matches a single `L12` or a range `L20-L25` / `L20-25`.
_INLINE_LINE_REF_RE = re.compile(r"\bL(\d+)(?:\s*-\s*L?(\d+))?")

# Only refs inside a parenthesised group that contains NOTHING BUT refs are
# accepted. Biomedical prose is full of `L<n>`-shaped tokens that are not line
# numbers at all — L1CAM, the L1/L2 vertebrae, the L5 nerve root, L3-stage
# larvae — and a bare scan turns each into a citation anchor pointing at a line
# that does not support the claim. `_MAP_JSON_CONTRACT` asks for the
# parenthesised form, and every ref observed live uses it, so requiring it
# costs nothing real and removes the whole class of false positive.
_PAREN_GROUP_RE = re.compile(r"\(([^)]{1,200})\)")
_REF_SEPARATORS_ONLY_RE = re.compile(r"^[\s,;.&+]*(?:and[\s,;.&+]*)*$", re.IGNORECASE)

# A range wider than this is almost certainly the model gesturing at a whole
# section rather than citing specific support; keep its endpoints instead of
# expanding it into a citation anchor with hundreds of line numbers.
_MAX_LINE_RANGE_SPAN = 25


def _map_citation_lines_from_text(answer: str) -> list[int]:
    """Recover supporting line numbers from line refs the model wrote inline
    in its answer — the fallback for `_citations`, which only arrives with
    `--output_schema` (see `_MAP_JSON_CONTRACT` for why we can't use that).

    Ranges are expanded so `format_line_anchor` can re-collapse them into a
    `#L20-L25` anchor; over-wide ranges keep only their endpoints. Only
    citation-shaped parenthesised groups are read — see `_PAREN_GROUP_RE`."""
    lines: set[int] = set()
    for group in _PAREN_GROUP_RE.findall(answer):
        matches = list(_INLINE_LINE_REF_RE.finditer(group))
        if not matches:
            continue
        # Anything left after removing the refs must be pure separators,
        # otherwise this is prose that merely contains an `L<n>`-shaped token.
        if not _REF_SEPARATORS_ONLY_RE.match(_INLINE_LINE_REF_RE.sub("", group)):
            continue
        for m in matches:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else start
            if end < start:
                start, end = end, start
            if end - start > _MAX_LINE_RANGE_SPAN:
                lines.update((start, end))
            else:
                lines.update(range(start, end + 1))
    return sorted(lines)


def _map_extract_from_text(doc_id: str, raw_text: str, success: bool) -> MapExtract:
    """Build a `MapExtract` from one paper's raw map answer.

    `raw_text` is a JSON string matching `MAP_OUTPUT_SCHEMA` when the server
    honored the requested schema, or plain prose otherwise (schema not
    applied for that paper, or an older/non-schema call). Best-effort: try
    JSON first, fall back to treating it as prose — never raises, since a
    single paper's shape shouldn't take down the whole map result set.
    """
    stripped = raw_text.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and "answer" in parsed:
            answer, found = _map_answer_and_found(parsed)
            # `_citations` when the server supplied it, else the model's own
            # inline refs — see `_map_citation_lines_from_text`.
            citation_lines = _map_citation_lines(parsed) or _map_citation_lines_from_text(answer)
            return MapExtract(
                doc_id=doc_id, text=answer, success=success, data=parsed,
                found=found, citation_lines=citation_lines,
            )
    return MapExtract(
        doc_id=doc_id, text=raw_text, success=success,
        citation_lines=_map_citation_lines_from_text(raw_text),
    )


def _parse_map_results(text: str) -> list[MapExtract]:
    """Parse the full `cat /.gxl/map_<id>.txt` results into per-paper extracts.

    Blocks look like:
        --- [1/3] [success] <title> ---
          doc_id: PMC12511219
          <multi-line answer, JSON or prose — see _map_extract_from_text>
    """
    body = _strip_timing(text)
    extracts: list[MapExtract] = []
    matches = list(_MAP_BLOCK_RE.finditer(body))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block = body[start:end].strip()
        did_m = re.search(r"doc_id:\s*(\S+)", block)
        if not did_m:
            continue
        doc_id = did_m.group(1)
        # Answer text is everything after the doc_id line.
        answer = block[did_m.end():].strip()
        extracts.append(
            _map_extract_from_text(doc_id, answer, m.group("status").lower() == "success")
        )
    return extracts


# Trailing "(N rows, Xms) [shard breakdown]" or "(1 row, Xms)" line `sql`
# appends after its ASCII table. Distinct from `_TIMING_FOOTER_RE` (which
# only matches `[NNms]`-only lines) since this one starts with `(`, not `[`.
_SQL_FOOTER_RE = re.compile(r"^\(\d+ rows?,\s*[\d.]+ms\).*$", re.MULTILINE)


def _parse_sql_output(text: str) -> SqlResult:
    """Parse `sql`'s ASCII table output — confirmed identical on REST and MCP
    (no structured JSON available for this command on either transport,
    unlike search/map). Shape:

        title                | doi           | source
        ---------------------+---------------+-------
        Some Paper Title...  | 10.1/xyz      | pmc
        (1 row, 14ms)

    Raises `PaperclipError` on a server-reported query error (e.g. a
    non-SELECT statement, unknown column, or the 15s statement timeout) —
    these come back as `ERR: sql: <message>` in `output` with HTTP 200 /
    MCP success, not as a transport-level failure, so we must check for the
    prefix ourselves rather than relying on `_run`/`_run_rest` to raise.
    """
    stripped = _strip_timing(text).strip()
    if stripped.startswith("ERR:"):
        raise PaperclipError(stripped.splitlines()[0][len("ERR:"):].strip())
    body = _SQL_FOOTER_RE.sub("", stripped).rstrip()
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) < 2:
        return SqlResult(columns=[], rows=[])
    columns = [c.strip() for c in lines[0].split("|")]
    rows: list[dict] = []
    for ln in lines[2:]:  # lines[1] is the "---+---+---" divider
        cells = [c.strip() for c in ln.split("|")]
        if len(cells) != len(columns):
            continue  # malformed row (shouldn't happen); skip rather than misalign
        rows.append(dict(zip(columns, cells)))
    return SqlResult(columns=columns, rows=rows)


def _shell_quote(s: str) -> str:
    """Quote an argument for Paperclip's server-side `vsh` parser.

    Single-quote style, not the double quotes used in Paperclip's own CLI
    examples. Their double-quote handling breaks when an argument contains
    BOTH an embedded double quote and a newline — confirmed live as
    `ERR: vsh: parse error: No closing quotation`, with either feature alone
    parsing fine. That combination is exactly the shape of
    `_MAP_JSON_CONTRACT`, and an LLM-written query could reproduce it
    anywhere else too. Single quotes with `'\\''` escaping parsed correctly
    for every combination tested: embedded double quotes, newlines,
    apostrophes ("Alzheimer's"), and all of them together.
    """
    return "'" + s.replace("'", "'\\''") + "'"


def _paper_hit_from_rest(p: dict) -> PaperHit:
    """Map one entry of the REST path's structured `result_data.papers` into
    a `PaperHit` — no regex needed (unlike the MCP text-parsing fallback).

    Field shape confirmed live for pmc/biorxiv hits (see
    fda/trials/proteins shape
    is unverified (open question in the migration plan) — fall back
    defensively rather than assume every field is present.
    """
    doc_id = str(p.get("document_id") or p.get("id") or p.get("accession") or "")
    pub_year = p.get("pub_year")
    date = p.get("pub_date") or (str(pub_year) if pub_year else "")
    return PaperHit(
        doc_id=doc_id,
        title=p.get("title") or "",
        authors=p.get("authors") or "",
        source=p.get("source") or p.get("corpus") or "",
        date=date,
        url=p.get("url") or "",
        snippet=p.get("tldr") or p.get("abstract_snippet") or "",
        score=p.get("score"),
        corpus=p.get("corpus"),
        backend=p.get("backend"),
        doi=p.get("doi"),
        pub_year=pub_year,
    )


def _hits_from_rest_payload(
    data: dict, output_text: str, source: str | None
) -> list[PaperHit]:
    """Extract hits from a REST search/filter response.

    Prefers the structured `result_data.papers`, but falls back to parsing the
    text listing when that key is absent. The server intermittently returns a
    complete listing in `output` — "Found 5 papers", every record present, a
    valid result id — while omitting `result_data` entirely. Reading only the
    structured field reported those searches as zero-hit (measured at ~14% of
    calls), which then tripped the node's zero-result fallback as though
    nothing had matched.

    The text parsers are the same ones the MCP path uses, which never has
    `result_data` at all — so this is a fallback we already trust.
    """
    result_data = data.get("result_data")
    papers = None
    if isinstance(result_data, dict):
        papers = result_data.get("papers")
        if papers is None:
            papers = result_data.get("results")
    if papers:
        return [_paper_hit_from_rest(p) for p in papers if isinstance(p, dict)]
    parse = _parse_protein_search if _doc_root(source) == "proteins" else _parse_search
    return parse(output_text)


# Set once per process the first time a REST call fails and we fall back to
# MCP — logged once, not per-call, so a down/locked-down REST endpoint is
# noticeable without spamming logs for the rest of the session.
_rest_fallback_warned = False


def _warn_rest_fallback(err: Exception) -> None:
    global _rest_fallback_warned
    if not _rest_fallback_warned:
        _rest_fallback_warned = True
        _log.warning(
            "Paperclip REST endpoint (%s) unavailable, falling back to MCP: %s",
            REST_URL, err,
        )


class PaperclipAdapter:
    """Production adapter: issues CLI command strings to the single `paperclip`
    MCP tool and parses the responses into typed models."""

    def __init__(
        self,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        slow_timeout_s: float = SLOW_TIMEOUT_S,
    ):
        self._timeout_s = timeout_s
        self._slow_timeout_s = slow_timeout_s
        # One pooled HTTP client per event loop, per adapter. Per-loop because
        # an AsyncClient binds to the loop it was created on; per-adapter (not
        # module-global) because `build_graph` constructs one adapter per run,
        # so pooling stays scoped to a single user's request rather than shared
        # across everyone.
        self._clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = (
            weakref.WeakKeyDictionary()
        )

    def _rest_client(self) -> "httpx.AsyncClient":
        """The pooled client for this loop, created on first use.

        Reusing one client keeps connections alive across calls, so the
        ~14-wide `asyncio.gather` fan-out in `assemble_context_node` stops
        paying a fresh TCP + TLS handshake per document.
        """
        loop = asyncio.get_running_loop()
        client = self._clients.get(loop)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                # Keep-alive headroom for the fan-out; `max_connections` caps
                # how hard one request can hit Paperclip concurrently.
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
                follow_redirects=True,
            )
            self._clients[loop] = client
        return client

    async def aclose(self) -> None:
        """Release pooled connections. Optional — clients are garbage-collected
        with their loop — but lets long-lived callers clean up deterministically."""
        for client in list(self._clients.values()):
            if not client.is_closed:
                await client.aclose()
        self._clients.clear()

    async def _run(self, command: str) -> str:
        """Invoke the `paperclip` tool with one command; return its text output.

        Raises `PaperclipError` on transport / auth / CLI-level failures so the
        tool layer can wrap it in a never-raise envelope. This is the MCP
        path — kept exactly as before, since it's now the fallback path
        `_execute` uses when REST is unavailable, and must stay correct on
        its own (not just until the REST migration lands).

        The underlying MCP client is a per-event-loop singleton
        (`_paperclip_tool`) with ONE fixed transport-level timeout baked in
        at creation — `ainvoke()` calls on it can't override it per-call. So
        this always requests the client with `_slow_timeout_s`: MCP is now
        the fallback path only (REST is primary), so a generous ceiling here
        costs nothing on the common path, and avoids under-timing out a
        `map` call that happens to fall back to MCP.
        """
        tool = await _paperclip_tool(timeout_s=self._slow_timeout_s)
        try:
            out = await tool.ainvoke({"command": command})
        except PaperclipError:
            raise
        except Exception as e:  # ToolException, transport errors, timeouts
            raise PaperclipError(f"{type(e).__name__}: {e}") from e
        return _strip_ansi(out if isinstance(out, str) else str(out))

    async def _run_rest(self, verb: str, raw: str) -> dict:
        """POST to the REST execute endpoint — see
        Undocumented for API-key auth but confirmed working. Raises
        `PaperclipRestUnavailable` on any failure (never `PaperclipError`
        directly) so `_execute`/`search` can catch specifically that and
        fall back to MCP, without swallowing genuine config errors (a
        missing API key fails identically on both transports, so there's no
        point falling back for that case — `_api_key()` is called outside
        the try so `PaperclipConfigError` propagates immediately).

        REST timeouts are set per-call (unlike MCP's fixed client-level
        one), so `map`/`ask-image` get `_slow_timeout_s` precisely — no need
        for MCP's blanket-generous workaround here.

        The API key is sent per-request rather than baked into the pooled
        client's headers, so rotating `PAPERCLIP_API_KEY` takes effect without
        rebuilding the client.
        """
        if os.environ.get(DISABLE_REST_ENV):
            raise PaperclipRestUnavailable(f"disabled via {DISABLE_REST_ENV}")
        key = _api_key()

        timeout = self._slow_timeout_s if verb in _SLOW_COMMANDS else self._timeout_s
        try:
            resp = await self._rest_client().post(
                REST_URL,
                json={"command": verb, "raw": raw},
                headers={"X-API-Key": key},
                timeout=timeout,
            )
        except Exception as e:  # network errors, timeouts
            raise PaperclipRestUnavailable(f"{type(e).__name__}: {e}") from e
        # 401/429 are account-level verdicts, not transport failures: MCP
        # carries the same key against the same quota, so falling back to it
        # can only burn time and produce a confusing retry storm. Raise the
        # base error so `_execute` doesn't catch it and callers see the real
        # reason (`map` is capped at 100/day, resetting midnight UTC).
        if resp.status_code in (401, 429):
            raise PaperclipError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.status_code != 200:
            raise PaperclipRestUnavailable(f"HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError as e:
            raise PaperclipRestUnavailable(f"invalid JSON response: {e}") from e
        if not isinstance(data, dict):
            raise PaperclipRestUnavailable("REST response was not a JSON object.")
        if isinstance(data.get("output"), str):
            data["output"] = _strip_ansi(data["output"])
        return data

    async def _execute(self, verb: str, raw: str) -> tuple[str, str | None]:
        """Try REST first, fall back to MCP on any REST failure. Returns
        `(output_text, result_id)`.

        Used for `cat`/`ls`/`head`/`map` — commands where the raw argument
        string is identical on both transports. `search` does NOT use this;
        it needs a different raw string per transport when `source` is
        omitted (REST: no `-s` at all, for the real all-sources default;
        MCP: substitute a source list, since MCP requires `-s`) — see
        `search()`.
        """
        try:
            data = await self._run_rest(verb, raw)
            return data.get("output", ""), data.get("result_id")
        except PaperclipRestUnavailable as e:
            _warn_rest_fallback(e)
        full_command = f"{verb} {raw}".strip() if raw else verb
        text = await self._run(full_command)
        return text, None

    async def search(
        self,
        query: str,
        *,
        source: str | None = None,
        limit: int = 10,
        sort: str | None = None,
        year: str | None = None,
        ranking: str | None = None,
    ) -> SearchResult:
        """Search Paperclip. `source=None` searches broadly (the default) —
        REST supports this natively (Paperclip's own documented default);
        MCP requires an explicit `-s`, so the fallback path substitutes a
        fast, same-shaped multi-source list (`_BROAD_MCP_SOURCES`) instead.
        The two transports genuinely differ here.

        `ranking` (e.g. `"analogical"` — confirmed live to work over REST,
        same `result_data.papers` shape as the default `hybrid` ranking) is
        REST-only, deliberately not threaded into the MCP fallback command:
        it's a quality/relevance-mode knob, not a correctness requirement, so
        it degrades to the default ranking rather than failing when REST is
        unavailable — same philosophy as `filter`.
        """
        base_args = f"{_shell_quote(query)} -n {int(limit)}"
        # `--all` means "search all papers, not just recent" — without it the
        # server silently applies a recency restriction and returns far fewer
        # results than `-n` asks for. Measured over 8 benchmark queries at
        # `-n 14`: 5.0 hits without it, 13.6 with. It also surfaces the older
        # canonical papers a factual question usually needs — the Denosumab
        # question returns the 2007-2014 RANKL literature with it, and only
        # 2025-2026 papers without. `--year` is a deliberate recency filter, so
        # the two are mutually exclusive.
        if not year:
            base_args += " --all"
        if sort:
            base_args += f" --sort {sort}"
        if year:
            base_args += f" --year {year}"

        rest_raw = f"-s {source} {base_args}" if source else base_args
        if ranking:
            rest_raw += f" --ranking {ranking}"
        try:
            data = await self._run_rest("search", rest_raw)
        except PaperclipRestUnavailable as e:
            _warn_rest_fallback(e)
        else:
            output_text = data.get("output", "")
            hits = _hits_from_rest_payload(data, output_text, source)
            id_m = _SEARCH_ID_RE.search(output_text)
            result_id = data.get("result_id") or (id_m.group(1) if id_m else None)
            return SearchResult(hits=hits, search_id=result_id)

        # MCP fallback: `-s` is mandatory. Substitute the broad paper-corpora
        # list when the caller wanted a default/unscoped search.
        mcp_source = source or _BROAD_MCP_SOURCES
        cmd = f"search -s {mcp_source} {base_args}"
        raw = await self._run(cmd)
        id_m = _SEARCH_ID_RE.search(raw)
        parse = _parse_protein_search if _doc_root(mcp_source) == "proteins" else _parse_search
        return SearchResult(
            hits=parse(raw),
            search_id=id_m.group(1) if id_m else None,
        )

    async def get_meta(self, doc_id: str, *, source: str = DEFAULT_SOURCE) -> PaperMeta:
        root = _doc_root(source)
        raw, _ = await self._execute("cat", f"/{root}/{doc_id}/meta.json")
        data = _extract_json_object(raw)
        return PaperMeta.model_validate(data)

    async def list_sections(self, doc_id: str, *, source: str = DEFAULT_SOURCE) -> list[str]:
        """List a document's available body-section names (without `.lines`)."""
        root = _doc_root(source)
        text, _ = await self._execute("ls", f"/{root}/{doc_id}/sections/")
        return _parse_section_listing(text)

    async def get_content(
        self,
        doc_id: str,
        *,
        source: str = DEFAULT_SOURCE,
        sections: list[str] | None = None,
        max_lines: int | None = None,
    ) -> str:
        """Fetch full-text body for a document.

        `sections=None` returns the whole line-numbered body (`content.lines`),
        capped at `max_lines`. When `sections` is given (canonical names like
        "methods", "discussion"), only the matching per-section files are
        fetched and concatenated — cheaper and more focused than the whole body.
        Falls back to the whole body if the requested sections can't be matched.
        """
        root = _doc_root(source)
        n = DEFAULT_CONTENT_MAX_LINES if max_lines is None else int(max_lines)

        if not sections:
            text, _ = await self._execute("head", f"-n {n} /{root}/{doc_id}/content.lines")
            return _strip_timing(text)

        available = await self.list_sections(doc_id, source=source)
        selected = _select_section_files(available, sections)
        if not selected:
            # Requested sections not present under their expected names — return
            # the whole body rather than nothing, so depth retrieval still works.
            text, _ = await self._execute("head", f"-n {n} /{root}/{doc_id}/content.lines")
            return _strip_timing(text)

        # Budget the per-section line cap so the concatenation stays near `n`.
        per_section = max(20, n // len(selected))
        blocks: list[str] = []
        for name in selected:
            path = _shell_quote(f"/{root}/{doc_id}/sections/{name}.lines")
            text, _ = await self._execute("head", f"-n {per_section} {path}")
            block = _strip_timing(text)
            if block:
                blocks.append(f"## {name}\n{block}")
        return "\n\n".join(blocks)

    async def run_map(
        self, search_id: str, question: str, *, limit: int | None = None
    ) -> list[MapExtract]:
        """Run Paperclip's `map` over a saved search result set.

        `map` reads each paper's FULL TEXT server-side and answers `question`
        per paper — a high-recall extraction that costs Paperclip's tokens, not
        ours. Returns one `MapExtract` per paper. We parse the full results file
        (`/.gxl/map_<id>.txt`) for the complete answers (the inline listing is
        truncated).

        Asks for `MAP_OUTPUT_SCHEMA`'s shape via `_MAP_JSON_CONTRACT` appended
        to the question, NOT via `--output_schema` (which 500s on REST — see
        that constant). `_map_extract_from_text` falls back to raw prose per
        paper if the model doesn't honor it, so it's never a hard requirement.

        Retries `_MAP_NOT_FOUND` in place: Paperclip intermittently cannot
        resolve a search id it just issued, and a plain retry recovers about
        half of those (see `_MAP_NOT_FOUND` for the mechanism).
        """
        full_question = f"{question}\n\n{_MAP_JSON_CONTRACT}"
        raw_args = f"--from {search_id} {_shell_quote(full_question)}"
        if limit:
            raw_args += f" -n {int(limit)}"

        for attempt in range(_MAP_NOT_FOUND_RETRIES + 1):
            out, _ = await self._execute("map", raw_args)
            if _MAP_NOT_FOUND not in out:
                break
            if attempt < _MAP_NOT_FOUND_RETRIES:
                await asyncio.sleep(_MAP_RETRY_BACKOFF_S * (attempt + 1))
        else:
            raise PaperclipError(
                f"map could not resolve search id {search_id} after "
                f"{_MAP_NOT_FOUND_RETRIES + 1} attempts."
            )

        # A server-side failure arrives as HTTP 200 with `ERR: <message>` in the
        # body, so it must be read out of the text. Surface that message
        # verbatim — reporting only "no results id" hides the cause and makes a
        # server outage look like a parsing bug on our side.
        stripped = out.strip()
        if stripped.startswith("ERR:"):
            raise PaperclipError(stripped.splitlines()[0][len("ERR:"):].strip())
        map_m = _MAP_ID_RE.search(out)
        if not map_m:
            raise PaperclipError(
                f"map returned no results id; output was: {stripped[:200]!r}"
            )
        full, _ = await self._execute("cat", f"/.gxl/map_{map_m.group(1)}.txt")
        return _parse_map_results(full)

    async def sql(self, query: str, *, source: str | None = None) -> SqlResult:
        """Run a read-only SQL `SELECT` against Paperclip's `documents` table.

        Server-enforced: `SELECT`-only, 15s statement timeout, 200-row cap
        regardless of the query's own `LIMIT`. No structured JSON on either
        transport — `_parse_sql_output` parses the ASCII table and raises
        `PaperclipError` on a server-reported query error.

        Confirmed live, caveats not obvious from the docs:
        - `documents` is sharded, not unified: omitting `source` queries only
          `arxiv`/`biorxiv`/`medrxiv`/`pmc` (same as `_BROAD_MCP_SOURCES`),
          not "all". A `WHERE source = 'x'` clause only filters *within*
          whatever shard(s) `source=` already selected.
        - `source="trials"`/`"proteins"` error with `relation "documents"
          does not exist` — not SQL-queryable via this table at all.
        - `abstract_text ILIKE '%...%'` over the full pmc/arxiv shards
          (millions of rows, unindexed for this) reliably hits the timeout —
          use SQL for structured-column aggregates, not free-text search.
        """
        raw = _shell_quote(query)
        if source:
            raw = f"-s {source} {raw}"
        out, _ = await self._execute("sql", raw)
        return _parse_sql_output(out)

    async def filter(self, search_id: str, query: str) -> SearchResult | None:
        """Trim a saved search result set to relevant papers via Paperclip's
        server-side LLM relevance judgment. MUTATES `search_id` in place
        (confirmed live) — a later `run_map` against the same id sees the
        trimmed set too.

        REST-only: `filter`'s text output only reports before/after counts,
        never the surviving hit list, so there's no way to reconstruct
        results from MCP's text output the way `search`/`map`/`sql` can.
        Returns `None` (not an error) when REST is unavailable — a quality
        improvement, not a correctness requirement, so it degrades by doing
        nothing rather than falling back to MCP; callers should treat `None`
        as "use the original unfiltered hits."

        Doesn't use `--require N`: confirmed live it doesn't block the trim,
        it just adds an `ERR:`-prefixed warning on top of the same (possibly
        empty) result — no simpler than handling an empty result ourselves.
        """
        if os.environ.get(DISABLE_REST_ENV):
            return None
        raw = f"--from {search_id} {_shell_quote(query)}"
        try:
            data = await self._run_rest("filter", raw)
        except PaperclipRestUnavailable as e:
            _warn_rest_fallback(e)
            return None
        output_text = data.get("output", "")
        if output_text.strip().startswith("ERR:"):
            raise PaperclipError(output_text.strip().splitlines()[0][len("ERR:"):].strip())
        result_data = data.get("result_data")
        papers = None
        if isinstance(result_data, dict):
            papers = result_data.get("papers")
            if papers is None:
                papers = result_data.get("results")
        if papers is None:
            # Same intermittent `result_data` omission handled in
            # `_hits_from_rest_payload` — but filter's text output is only a
            # summary ("Filtered: 5 -> 2 papers"), with no listing to parse.
            # Report it as "couldn't filter" (caller keeps the unfiltered
            # hits) rather than as "filter removed everything".
            return None
        hits = [_paper_hit_from_rest(p) for p in papers if isinstance(p, dict)]
        return SearchResult(hits=hits, search_id=search_id)


__all__ = [
    "MCP_URL",
    "REST_URL",
    "DISABLE_REST_ENV",
    "API_KEY_ENV",
    "MAP_OUTPUT_SCHEMA",
    "PaperclipSource",
    "PaperclipSectionName",
    "SECTION_KEYWORDS",
    "PaperHit",
    "PaperMeta",
    "SearchResult",
    "SqlResult",
    "MapExtract",
    "PaperclipError",
    "PaperclipConfigError",
    "PaperclipRestUnavailable",
    "infer_source_from_doc_id",
    "PaperclipAdapterProtocol",
    "PaperclipAdapter",
]
