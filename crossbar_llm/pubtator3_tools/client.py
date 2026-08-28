"""Async client for the NCBI PubTator3 REST API.

Wraps four endpoints (entity autocomplete, relation discovery, article
search, BioC JSON export) with typed Pydantic models. End-to-end
orchestration lives in `crossbar_llm.pubtator3_tools.agent`.

API docs: https://www.ncbi.nlm.nih.gov/research/pubtator3/api
"""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Any, Callable, Literal, TypeVar
import httpx
import asyncio
import logging
import weakref
from aiolimiter import AsyncLimiter
import re

_log = logging.getLogger(__name__)

# --- Module constants ---------------------------------------------------------
BASE_URL = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api"
USER_AGENT = "CROssBAR-LLM/0.1 (+https://github.com/HUBioDataLab/CROssBAR_LLM)"
DEFAULT_TIMEOUT_S = 15.0
RATE_LIMIT_PER_SECOND = 3          # PubTator3 IP-wide policy
RATE_LIMIT_TIME_PERIOD_S = 1
EXPORT_PMID_BATCH = 100            # /publications/export/biocjson cap per call
RETRY_429_BACKOFF_S = 2.0          # backoff before the single retry attempt

# HTTP statuses we treat as transient (worth one retry). 429 = rate limit;
# 502/503/504 = upstream gateway / availability glitches NCBI hits intermittently.
TRANSIENT_STATUSES = frozenset({429, 502, 503, 504})

# Full-text papers from /publications/export/biocjson include boilerplate
# sections (competing interests, acknowledgements, supplementary-material
# references, bibliography, etc.) that carry no scientific content but inflate
# the synthesizer's prompt. Drop them at parse time.
SKIP_SECTION_TYPES = frozenset({
    "COMP_INT",
    "ACK_FUND",
    "AUTH_CONT",
    "SUPPL",
    "REF",
    "ABBR",
    "KEYWORDS",
    "APPENDIX",
    "REVIEW_INFO",
})

ABSTRACT_ONLY_SECTIONS = frozenset({"title", "abstract", "TITLE", "ABSTRACT"})

# --- Per-loop singletons ------------------------------------------------------
# httpx.AsyncClient and aiolimiter.AsyncLimiter are both bound to the event loop
# that creates them, so re-using a module-level instance across `asyncio.run`
# calls (tests, scripts) crashes with "Event loop is closed". Keying by the
# running loop fixes that without losing connection pooling within one loop.
_clients_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = weakref.WeakKeyDictionary()
_limiters_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncLimiter]" = weakref.WeakKeyDictionary()

class EntityCandidate(BaseModel):
    """Represents a single entity match from the autocomplete API."""
    accession: str = Field(alias="_id")           # Map "_id" from API to "accession"
    name: str
    # Known values: gene, chemical, disease, species, variant, cellline. Kept as
    # a plain str rather than a Literal: PubTator3 is an evolving service, and
    # pinning the enum meant one unfamiliar concept type raised for the whole
    # batch, discarding every other candidate in the response.
    biotype: str
    db_id: str
    db: str                                       # "ncbi_gene", etc.
    description: str = ""
    match: str = ""

    model_config = ConfigDict(populate_by_name=True)  # Allow both "_id" and "accession"

class RelatedEntity(BaseModel):
    """Represents a related entity from the related-entities API."""
    # Known values: associate, cause, compare, cotreat, drug_interact, inhibit,
    # interact, negative_correlate, positive_correlate, prevent, stimulate,
    # treat. Plain str for the same reason as `EntityCandidate.biotype` — a
    # single new relation type used to discard the entire partner list.
    type: str
    source: str
    target: str
    publications: int

class SearchHit(BaseModel):
    """One article hit from PubTator3 search."""
    pmid: int
    title: str
    journal: str | None = None
    date: str | None = None
    authors: list[str] = []
    doi: str | None = None
    score: float | None = None
    # raw highlight (keep for debugging)
    text_hl: str | None = None
    snippet: str | None = None

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def _populate_snippet(self) -> "SearchHit":
        if self.snippet is None and self.text_hl is not None:
            self.snippet = _clean_snippet(self.text_hl)
        return self
    
class PassageAnnotation(BaseModel):
    """Represents a single annotated entity mention in a passage."""
    text: str
    type: str
    accession: str | None = None
    identifier: str | None = None
    offset: int
    length: int

class Passage(BaseModel):
    """Represents a single passage (e.g. title, abstract section) of a PubTator3 article."""
    pmid: int
    pmcid: str | None = None
    title: str
    section: str
    text: str
    offset: int
    annotations: list[PassageAnnotation] = []

class DocumentRelation(BaseModel):
    """Represents a single BioREx-extracted relation between two entities in a PubTator3 article.

    `pmid` is included so that when a flat list of relations is surfaced
    across multiple documents (e.g. by the LangGraph export node), each
    entry retains its provenance.

    Both PubTator3-style accessions (`role1_accession`, `role2_accession`,
    e.g. `@GENE_JAK1`) and underlying database identifiers (`role1_identifier`,
    `role2_identifier`, e.g. `MESH:D008687` for chemicals/diseases or a bare
    NCBI Gene ID for genes) are surfaced. CROssBAR's knowledge graph keys
    on the database identifiers, so the latter is what to use for joins.
    """
    pmid: int
    type: str
    role1_accession: str | None = None
    role1_identifier: str | None = None
    role2_accession: str | None = None
    role2_identifier: str | None = None
    score: float

class PubTator3Document(BaseModel):
    """Represents a full PubTator3 document with passages and relations."""
    pmid: int
    pmcid: str | None = None
    title: str
    journal: str | None = None
    authors: list[str] = []
    date: str | None = None
    passages: list[Passage] = []
    relations: list[DocumentRelation] = []

_Parsed = TypeVar("_Parsed")


def _parse_items(
    raw: Any, build: Callable[[Any], _Parsed], *, what: str
) -> list[_Parsed]:
    """Parse a list of API records, skipping the ones that don't parse.

    Every record used to be built in one list comprehension, so a single
    unparseable entry raised for the whole batch and the caller saw an empty
    result — one unfamiliar relation type discarded all 352 partners. Skip the
    bad record instead, and log how many were dropped so a schema drift on
    PubTator3's side is visible rather than silent.

    A response that isn't a list at all (an error envelope, say) yields `[]`
    rather than raising.
    """
    if not isinstance(raw, list):
        _log.warning("pubtator3 %s: expected a list, got %s", what, type(raw).__name__)
        return []
    parsed: list[_Parsed] = []
    skipped = 0
    for item in raw:
        try:
            parsed.append(build(item))
        except Exception:
            skipped += 1
    if skipped:
        _log.warning(
            "pubtator3 %s: skipped %d/%d unparseable record(s)", what, skipped, len(raw)
        )
    return parsed


def _client() -> httpx.AsyncClient:
    """Lazy per-loop async HTTP client (one instance per running event loop)."""
    loop = asyncio.get_running_loop()
    cli = _clients_by_loop.get(loop)
    if cli is None:
        cli = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=DEFAULT_TIMEOUT_S,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )
        _clients_by_loop[loop] = cli
    return cli

def _limiter() -> AsyncLimiter:
    """Lazy per-loop rate limiter — RATE_LIMIT_PER_SECOND req/s, IP-wide."""
    loop = asyncio.get_running_loop()
    lim = _limiters_by_loop.get(loop)
    if lim is None:
        lim = AsyncLimiter(max_rate=RATE_LIMIT_PER_SECOND, time_period=RATE_LIMIT_TIME_PERIOD_S)
        _limiters_by_loop[loop] = lim
    return lim

async def _request(method: str, path: str, *, params: dict | None = None) -> httpx.Response:
    """Make an HTTP request with rate limiting and a single transient-failure retry.

    - 3 req/s ceiling enforced via the per-loop limiter (token bucket).
    - Retries once after RETRY_429_BACKOFF_S seconds when the first attempt
      either returns a status in TRANSIENT_STATUSES (429, 502, 503, 504) or
      raises a transport-level error (connection dropped, read timeout,
      RemoteProtocolError, etc. — anything subclassing httpx.RequestError).
    - Persistent failures raise (HTTPStatusError for status codes,
      httpx.RequestError for transport errors).
    """
    async def _attempt() -> tuple[httpx.Response | None, Exception | None]:
        try:
            async with _limiter():
                return await _client().request(method, path, params=params), None
        except httpx.RequestError as e:
            return None, e

    response, error = await _attempt()
    needs_retry = error is not None or (
        response is not None and response.status_code in TRANSIENT_STATUSES
    )
    if needs_retry:
        await asyncio.sleep(RETRY_429_BACKOFF_S)
        response, error = await _attempt()

    if error is not None:
        raise error
    assert response is not None  # one of (response, error) is always set
    response.raise_for_status()
    return response


async def autocomplete(query: str, *, concept: str | None = None, limit: int = 5) -> list[EntityCandidate]:
    """Resolve free-text entity names to PubTator3 accessions."""
    params = {"query": query, "limit": limit}
    if concept:
        params["concept"] = concept
    
    response = await _request("GET", "/entity/autocomplete/", params=params)
    raw = response.json()
    
    return _parse_items(
        raw, lambda item: EntityCandidate(**item), what="autocomplete"
    )

async def find_related(e1: str, *, relation: str, e2_type: str) -> list[RelatedEntity]:
    """Find related entities of a specific type for a given entity."""
    params = {"e1": e1, "type": relation, "e2": e2_type}
    response = await _request("GET", "/relations", params=params)
    raw = response.json()
    
    return _parse_items(raw, lambda item: RelatedEntity(**item), what="relations")

def _clean_snippet(text: str | None) -> str | None:
    if not text:
        return text

    # initial simple version
    return re.sub(
        r"@(?:<m>)?[A-Z]+_[^\s<]+(?:</m>)? @\S+ @@@(.+?)@@@",
        r"\1",
        text,
    )

async def search(text_query: str, *, page: int = 1) -> tuple[list[SearchHit], int]:
    """Search PubTator3 articles. Calls GET /search/. Returns (hits, total_count)."""
    params = {"text": text_query, "page": page}

    response = await _request("GET", "/search/", params=params)
    raw = response.json()

    hits = _parse_items(
        raw.get("results"), lambda item: SearchHit(**item), what="search"
    )
    total = raw.get("count", 0)

    return hits, total

def _safe_float(value, default: float = 0.0) -> float:
    """Coerce a possibly-None / possibly-string value to float. Defaults on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_annotation(raw: dict) -> PassageAnnotation:
    """One entity annotation from a passage. Returns None for unresolved entities."""
    infons = raw.get("infons") or {}
    if not infons.get("valid", True):
        return None
    locations = raw.get("locations") or [{}]
    loc = locations[0] or {}
    return PassageAnnotation(
        text=raw.get("text") or "",
        type=infons.get("type") or "",
        accession=infons.get("accession"),
        identifier=infons.get("identifier"),
        offset=loc.get("offset") or 0,
        length=loc.get("length") or 0,
    )

def _parse_passage(raw: dict, *, doc_pmid: int, doc_pmcid: str | None, doc_title: str) -> Passage | None:
    """One passage (title, abstract, or section) within a document.

    Returns None for boilerplate sections we drop entirely (see
    SKIP_SECTION_TYPES). Full-text passages carry their semantic role in
    `infons.section_type` (METHODS, RESULTS, COMP_INT, ...); abstract-mode
    passages carry it in `infons.type` (title, abstract).
    """
    infons = raw.get("infons") or {}
    section = infons.get("section_type") or infons.get("type") or ""
    if section in SKIP_SECTION_TYPES:
        return None
    annotations = [
        a for a in (_parse_annotation(x) for x in (raw.get("annotations") or []))
        if a is not None
    ]
    return Passage(
        pmid=doc_pmid,
        pmcid=doc_pmcid,
        title=doc_title,
        section=section,
        text=raw.get("text") or "",
        offset=raw.get("offset") or 0,
        annotations=annotations,
    )

def _parse_document_relation(raw: dict, *, doc_pmid: int) -> DocumentRelation:
    """One BioREx document-level relation. `doc_pmid` is threaded in so the
    relation keeps its provenance when flattened across multiple docs."""
    infons = raw.get("infons") or {}
    role1 = infons.get("role1") or {}
    role2 = infons.get("role2") or {}
    return DocumentRelation(
        pmid=doc_pmid,
        type=infons.get("type") or "",
        role1_accession=role1.get("accession"),
        role1_identifier=role1.get("identifier"),
        role2_accession=role2.get("accession"),
        role2_identifier=role2.get("identifier"),
        score=_safe_float(infons.get("score")),
    )

def _parse_document(raw: dict) -> PubTator3Document:
    """One doc within the {'PubTator3': [...]} array."""
    pmid = int(raw["pmid"])
    pmcid = raw.get("pmcid")

    title = ""
    for p in raw.get("passages") or []:
        if (p.get("infons") or {}).get("type") == "title":
            title = p.get("text") or ""
            break

    passages = [
        p for p in (
            _parse_passage(raw_p, doc_pmid=pmid, doc_pmcid=pmcid, doc_title=title)
            for raw_p in (raw.get("passages") or [])
        )
        if p is not None
    ]
    relations = [
        _parse_document_relation(r, doc_pmid=pmid)
        for r in (raw.get("relations") or [])
    ]

    return PubTator3Document(
        pmid=pmid,
        pmcid=pmcid,
        title=title,
        journal=raw.get("journal"),
        authors=raw.get("authors", []),
        date=raw.get("date"),
        passages=passages,
        relations=relations,
    )

async def export_biocjson(pmids: list[int], *, full: bool = True) -> list[PubTator3Document]:
    """GET /publications/export/biocjson. Chunks PMIDs into batches of
    EXPORT_PMID_BATCH so the URL doesn't blow up on long lists. Missing
    PMIDs are silently dropped by the API. Batches run concurrently; the
    rate limiter still serialises them at RATE_LIMIT_PER_SECOND req/s."""
    if not pmids:
        return []

    chunks = [
        pmids[i : i + EXPORT_PMID_BATCH]
        for i in range(0, len(pmids), EXPORT_PMID_BATCH)
    ]

    async def _fetch(chunk: list[int]) -> list[PubTator3Document]:
        params = {
            "pmids": ",".join(str(p) for p in chunk),
            "full": "true" if full else "false",
        }
        response = await _request("GET", "/publications/export/biocjson", params=params)
        raw = response.json()
        return _parse_items(
            raw.get("PubTator3"), _parse_document, what="export"
        )

    batches = await asyncio.gather(*(_fetch(c) for c in chunks))

    docs: list[PubTator3Document] = []
    for b in batches:
        docs.extend(b)
    return docs
