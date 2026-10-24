"""The client's behaviour, driven entirely through a fake transport.

No test here opens a socket. What is worth testing about this module is not that httpx works —
it is the retry policy, and specifically that the one failure mode NCBI reports as a 5xx but
means permanently is not retried (ADR-005).
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from crossbar_llm.litsense_tools.client import (
    FullTextNotFound,
    LitSenseClient,
    LitSenseError,
    LitSenseUnavailable,
    PublicationNotFound,
    RateLimiter,
    retry_after_seconds,
)
from crossbar_llm.litsense_tools.config import Settings
from crossbar_llm.litsense_tools.models import Publication, SentenceHit
from crossbar_llm.litsense_tools.tests.conftest import load_fixture

RERANKED = "sentences_what_is_the_role_of_tp53_mutations_in_colorectal_cancer_prog.json"
PUBLICATION = "publication_27863244.json"
PMID = 27863244


class SleepRecorder:
    """Stands in for `asyncio.sleep` so timing tests assert on delays instead of waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class Handler:
    """A scripted transport handler that records the requests it received."""

    def __init__(self, *responses: httpx.Response) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._responses[min(len(self.requests) - 1, len(self._responses) - 1)]

    @property
    def count(self) -> int:
        return len(self.requests)


class FailingHandler:
    """Raises a transport error for the first `failures` requests, then succeeds."""

    def __init__(self, failures: int, success: httpx.Response) -> None:
        self.failures = failures
        self.success = success
        self.count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.count += 1
        if self.count <= self.failures:
            raise httpx.ConnectError("connection refused", request=request)
        return self.success


def make_settings(**overrides: object) -> Settings:
    """Settings tuned for tests: no provider required, no real waiting."""
    defaults: dict[str, object] = {
        "model": "test:model",
        "requests_per_second": 10_000.0,
        "retry_backoff_base_s": 1.0,
        "max_retries": 3,
    }
    return Settings(**{**defaults, **overrides})  # type: ignore[arg-type]


class Harness:
    """A client plus the two clocks it waits on, kept apart so each can be asserted alone."""

    def __init__(
        self, client: LitSenseClient, backoff: SleepRecorder, paced: SleepRecorder
    ) -> None:
        self.client = client
        self.backoff = backoff
        self.paced = paced


def make_client(handler: object, **overrides: object) -> Harness:
    """Build a client whose retry backoff and rate limiting sleep on separate recorders.

    Sharing one recorder would mix the limiter's pacing into the backoff assertions, and the
    two are answers to different questions.
    """
    settings = make_settings(**overrides)
    backoff, paced = SleepRecorder(), SleepRecorder()
    client = LitSenseClient(
        settings,
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        sleep=backoff,
        limiter=RateLimiter(settings.requests_per_second, sleep=paced),
    )
    return Harness(client, backoff, paced)


def ok(fixture: str) -> httpx.Response:
    return httpx.Response(200, json=load_fixture(fixture))


# --- search ----------------------------------------------------------------------------


async def test_search_parses_hits_and_sends_the_configured_parameters() -> None:
    handler = Handler(ok(RERANKED))
    harness = make_client(handler, top_k_sentences=25)

    async with harness.client as client:
        hits = await client.search_sentences("tp53 colorectal")

    assert len(hits) == 100
    assert all(isinstance(hit, SentenceHit) for hit in hits)

    request = handler.requests[0]
    assert request.url.path.endswith("/api/sentences/")
    assert request.url.params["query"] == "tp53 colorectal"
    assert request.url.params["rerank"] == "true"
    assert request.url.params["limit"] == "25"
    assert "litsense-agent" in request.headers["user-agent"]


async def test_rerank_can_be_overridden_per_call() -> None:
    handler = Handler(ok(RERANKED))
    harness = make_client(handler)

    async with harness.client as client:
        await client.search_sentences("q", rerank=False)

    assert handler.requests[0].url.params["rerank"] == "false"


async def test_search_rejects_a_payload_that_is_not_a_list() -> None:
    harness = make_client(Handler(httpx.Response(200, json={"detail": "surprise"})))

    async with harness.client as client:
        with pytest.raises(LitSenseError, match="expected a list"):
            await client.search_sentences("q")


# --- publication fetch -----------------------------------------------------------------


async def test_fetch_publication_parses_the_document_and_sends_no_parameters() -> None:
    """The `?section=` parameter is ignored by the API, so we never send one (ADR-005)."""
    handler = Handler(ok(PUBLICATION))
    harness = make_client(handler)

    async with harness.client as client:
        publication = await client.fetch_publication(PMID)

    assert isinstance(publication, Publication)
    assert publication.abstract is not None
    assert handler.requests[0].url.path.endswith(f"/publication/{PMID}")
    assert not handler.requests[0].url.params


async def test_a_second_fetch_of_the_same_pmid_is_served_from_cache() -> None:
    handler = Handler(ok(PUBLICATION))
    harness = make_client(handler)

    async with harness.client as client:
        first = await client.fetch_publication(PMID)
        second = await client.fetch_publication(PMID)

    assert first is second
    assert handler.count == 1
    assert client.cached_pmids == frozenset({PMID})


async def test_the_cache_is_keyed_by_pmid() -> None:
    handler = Handler(ok(PUBLICATION), ok("publication_39039912.json"))
    harness = make_client(handler)

    async with harness.client as client:
        await client.fetch_publication(PMID)
        await client.fetch_publication(39039912)

    assert handler.count == 2


# --- the failure that matters (ADR-005) ------------------------------------------------


async def test_an_unresolvable_pmid_arrives_as_a_500_and_is_never_retried() -> None:
    """The whole point: retrying this would burn four rate-limit slots to fail four times."""
    handler = Handler(httpx.Response(500, json=load_fixture("publication_unresolvable.json")))
    harness = make_client(handler)

    async with harness.client as client:
        with pytest.raises(PublicationNotFound) as caught:
            await client.fetch_publication(999999999)

    assert caught.value.pmid == 999999999
    assert handler.count == 1
    assert harness.backoff.delays == []


async def test_a_404_is_also_a_missing_publication_and_is_not_retried() -> None:
    handler = Handler(httpx.Response(404, json=load_fixture("publication_non_numeric.json")))
    harness = make_client(handler)

    async with harness.client as client:
        with pytest.raises(PublicationNotFound):
            await client.fetch_publication(1)

    assert handler.count == 1


async def test_a_genuine_server_error_is_still_retried() -> None:
    """A 500 without the marker is transient as far as we can tell, so it gets the retries."""
    handler = Handler(httpx.Response(500, json={"detail": "database is on fire"}))
    harness = make_client(handler, max_retries=2)

    async with harness.client as client:
        with pytest.raises(LitSenseUnavailable):
            await client.fetch_publication(PMID)

    assert handler.count == 3


# --- retry policy ----------------------------------------------------------------------


async def test_a_429_is_retried_and_retry_after_is_honoured() -> None:
    handler = Handler(
        httpx.Response(429, headers={"Retry-After": "2"}, json={"detail": "slow down"}),
        ok(PUBLICATION),
    )
    harness = make_client(handler)

    async with harness.client as client:
        publication = await client.fetch_publication(PMID)

    assert publication.pmid == PMID
    assert handler.count == 2
    assert harness.backoff.delays == [2.0]


async def test_retries_are_exhausted_and_reported_as_unavailable() -> None:
    handler = Handler(httpx.Response(503, json={"detail": "unavailable"}))
    harness = make_client(handler, max_retries=3)

    async with harness.client as client:
        with pytest.raises(LitSenseUnavailable, match="after 4 attempts"):
            await client.search_sentences("q")

    assert handler.count == 4
    assert len(harness.backoff.delays) == 3


async def test_backoff_grows_exponentially_and_carries_jitter() -> None:
    handler = Handler(httpx.Response(503, json={"detail": "unavailable"}))
    harness = make_client(handler, max_retries=3, retry_backoff_base_s=1.0)

    async with harness.client as client:
        with pytest.raises(LitSenseUnavailable):
            await client.search_sentences("q")

    assert 0.5 <= harness.backoff.delays[0] <= 1.0
    assert 1.0 <= harness.backoff.delays[1] <= 2.0
    assert 2.0 <= harness.backoff.delays[2] <= 4.0


async def test_a_4xx_that_is_our_fault_is_not_retried() -> None:
    handler = Handler(httpx.Response(400, json={"detail": "bad query"}))
    harness = make_client(handler)

    async with harness.client as client:
        with pytest.raises(LitSenseError) as caught:
            await client.search_sentences("q")

    assert not isinstance(caught.value, LitSenseUnavailable)
    assert handler.count == 1


async def test_transport_errors_are_retried_then_succeed() -> None:
    handler = FailingHandler(2, ok(PUBLICATION))
    harness = make_client(handler)

    async with harness.client as client:
        publication = await client.fetch_publication(PMID)

    assert publication.pmid == PMID
    assert handler.count == 3
    assert len(harness.backoff.delays) == 2


async def test_a_transport_error_that_never_clears_is_unavailable() -> None:
    handler = FailingHandler(99, ok(PUBLICATION))
    harness = make_client(handler, max_retries=1)

    async with harness.client as client:
        with pytest.raises(LitSenseUnavailable, match="ConnectError"):
            await client.fetch_publication(PMID)

    assert handler.count == 2


async def test_httpx_exceptions_never_escape_the_client() -> None:
    """Nothing above client.py imports httpx, so nothing above it can catch an httpx error."""
    harness = make_client(FailingHandler(99, ok(PUBLICATION)), max_retries=0)

    async with harness.client as client:
        with pytest.raises(LitSenseError):
            await client.fetch_publication(PMID)


# --- rate limiting ---------------------------------------------------------------------


async def test_the_rate_limiter_spaces_requests_out() -> None:
    """Real sleeps, deliberately: this is the one behaviour a fake clock would not prove.

    Elapsed time is measured on the loop's own clock — the one the limiter schedules on.
    Even so, the loop fires timers up to one clock resolution *early* on purpose
    (`BaseEventLoop._clock_resolution` slack), and on Windows the monotonic clock's
    resolution is ~15.6ms, so the assertion allows exactly that much.
    """
    limiter = RateLimiter(50.0)
    clock = asyncio.get_running_loop().time
    resolution = time.get_clock_info("monotonic").resolution
    started = clock()

    await asyncio.gather(*(limiter.acquire() for _ in range(3)))

    assert clock() - started >= 2 * limiter.interval - resolution


async def test_one_limiter_paces_every_endpoint() -> None:
    """The limit belongs to the service, so search and fetch queue behind the same one."""
    handler = Handler(ok(RERANKED), ok(PUBLICATION))
    harness = make_client(handler, requests_per_second=2.0)

    async with harness.client as client:
        await client.search_sentences("q")
        await client.fetch_publication(PMID)

    assert harness.paced.delays, "the second request should have waited for its slot"
    assert harness.backoff.delays == [], "waiting for a slot is not a retry"


async def test_rate_limiter_rejects_a_nonsense_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        RateLimiter(0.0)


# --- Retry-After parsing ---------------------------------------------------------------


def test_retry_after_accepts_seconds() -> None:
    assert retry_after_seconds(httpx.Response(429, headers={"Retry-After": "5"})) == 5.0


def test_retry_after_accepts_an_http_date() -> None:
    header = {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}
    parsed = retry_after_seconds(httpx.Response(429, headers=header))
    assert parsed == 0.0  # in the past, so no wait — but parsed rather than ignored


def test_retry_after_is_absent_or_unparseable() -> None:
    assert retry_after_seconds(httpx.Response(429)) is None
    assert retry_after_seconds(httpx.Response(429, headers={"Retry-After": "soon"})) is None


# --- full text (ADR-009) ---------------------------------------------------------------

FULLTEXT_WRAPPER = [
    {
        "source": "PMC",
        "documents": [
            {
                "id": "5320931",
                "passages": [
                    {"infons": {"section_type": "TITLE", "type": "front"}, "text": "A title"},
                    {"infons": {"section_type": "INTRO", "type": "paragraph"}, "text": "Intro."},
                    {"infons": {"section_type": "REF", "type": "ref"}, "text": "A reference"},
                ],
            }
        ],
    }
]

BIOC_HTML_ERROR = httpx.Response(
    200,
    text="[Error] : No result can be found. <BR><HR><B> ...",
    headers={"content-type": "text/html"},
)


async def test_fetch_full_text_unwraps_the_collection_and_keeps_narrative_sections() -> None:
    handler = Handler(httpx.Response(200, json=FULLTEXT_WRAPPER))
    harness = make_client(handler)
    async with harness.client as client:
        full = await client.fetch_full_text("PMC5320931")
    assert full.pmcid == "PMC5320931"
    assert "PMC5320931" in str(handler.requests[0].url)
    body = full.body(max_chars=10_000)
    assert body == "Intro."  # TITLE and REF are not narrative


async def test_a_200_html_error_page_is_full_text_not_found_and_never_retried() -> None:
    handler = Handler(BIOC_HTML_ERROR)
    harness = make_client(handler)
    async with harness.client as client:
        with pytest.raises(FullTextNotFound):
            await client.fetch_full_text("PMC999999999")
    assert handler.count == 1


async def test_full_text_is_cached_per_pmcid() -> None:
    handler = Handler(httpx.Response(200, json=FULLTEXT_WRAPPER))
    harness = make_client(handler)
    async with harness.client as client:
        first = await client.fetch_full_text("PMC5320931")
        second = await client.fetch_full_text("PMC5320931")
    assert handler.count == 1
    assert first is second


async def test_a_shapeless_json_body_is_also_full_text_not_found() -> None:
    handler = Handler(httpx.Response(200, json={"unexpected": "shape"}))
    harness = make_client(handler)
    async with harness.client as client:
        with pytest.raises(FullTextNotFound):
            await client.fetch_full_text("PMC1")
