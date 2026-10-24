"""HTTP access to the LitSense 2.0 API.

One `LitSenseClient` wrapping a single shared `httpx.AsyncClient`, with a global rate limiter,
bounded concurrency, retry with backoff on transient failures, and a per-pmid cache (ADR-002).

Nothing above this module imports httpx. Failures surface as four exceptions:

``PublicationNotFound``
    The pmid does not resolve. Permanent — the caller drops that article and moves on.
``FullTextNotFound``
    The BioC-PMC service has no full text for the pmcid (ADR-009). Permanent — the caller
    keeps the abstract it already has. Detected by shape, not status: the service answers
    "no result" as **200 with an HTML error page**.
``LitSenseUnavailable``
    Transport failure, timeout, or a transient server error that survived every retry. The
    service, not the request, is the problem.
``LitSenseError``
    Anything else the API rejected — a 4xx that is our own fault. Never retried, because
    repeating a malformed request just spends someone else's rate limit.

The one unpleasant detail is deliberate: an unresolvable pmid comes back as **500**, not 404,
so the retry logic sniffs the response body before deciding a 5xx is worth repeating. See
ADR-005; without that check, ten bad pmids in a fan-out become forty requests against a service
that allows us one per second.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import random
import time
from collections.abc import Awaitable, Callable
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx

from crossbar_llm.litsense_tools.config import Settings
from crossbar_llm.litsense_tools.models import FullText, Publication, SentenceHit

#: Substring NCBI puts in the `detail` of the 500 it returns for a pmid that does not resolve.
#: Matching on it is the only way to tell a permanent miss from a real server error.
PUBLICATION_MISSING_MARKER = "publication not found"

SENTENCES_PATH = "/api/sentences/"
PUBLICATION_PATH = "/publication/{pmid}"

SleepFn = Callable[[float], Awaitable[None]]


class LitSenseError(Exception):
    """Base class for every error this package raises out of the HTTP layer."""


class LitSenseUnavailable(LitSenseError):
    """The API could not be reached, timed out, or kept failing after retries."""


class PublicationNotFound(LitSenseError):
    """The publication endpoint has no record for the requested pmid."""

    def __init__(self, pmid: int) -> None:
        super().__init__(f"no publication for pmid {pmid}")
        self.pmid = pmid


class FullTextNotFound(LitSenseError):
    """The BioC-PMC service has no full text for the requested pmcid (ADR-009)."""

    def __init__(self, pmcid: str) -> None:
        super().__init__(f"no full text for pmcid {pmcid}")
        self.pmcid = pmcid


class RateLimiter:
    """Spaces outbound requests so that no more than `rate_per_second` leave per second.

    One instance per client, shared by every call site. Slots are handed out under a lock and
    each caller waits for its own, so the spacing holds no matter how many coroutines are
    queued behind it.
    """

    def __init__(self, rate_per_second: float, *, sleep: SleepFn = asyncio.sleep) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self.interval = 1.0 / rate_per_second
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._next_slot: float | None = None

    async def acquire(self) -> None:
        loop = asyncio.get_running_loop()
        async with self._lock:
            now = loop.time()
            slot = now if self._next_slot is None else max(now, self._next_slot)
            delay = slot - now
            if delay > 0:
                await self._sleep(delay)
            self._next_slot = slot + self.interval


class ResponseCache:
    """An on-disk cache of final GET responses, shared by every process pointed at it.

    ADR-010. One file per URL (`<sha256>.json`: url, status, content-type, body text),
    written atomically, so parallel benchmark runs over the same questions make **one**
    request to NCBI per URL between them and all see identical retrieval. A miss is
    guarded by a lock file: the first process to claim a URL fetches it, the others wait
    for the file to appear (polling) instead of asking NCBI for the same thing. A lock
    older than `lock_timeout_s` is treated as abandoned (a killed run) and taken over.

    Only *final* responses are stored — the ones the client would not retry: 200s
    (including the BioC-PMC "no result" HTML page, which is permanent), 404s and the
    500 that means "publication not found" (ADR-005). Nothing here is a seam the graph
    sees: the client asks the cache first and NCBI second, that is all.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        lock_timeout_s: float = 120.0,
        poll_interval_s: float = 0.5,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock_timeout_s = lock_timeout_s
        self.poll_interval_s = poll_interval_s
        self._sleep = sleep
        self.hits = 0
        self.misses = 0

    # --- paths ---------------------------------------------------------------------

    @staticmethod
    def key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:40]

    def path(self, url: str) -> Path:
        return self.directory / f"{self.key(url)}.json"

    def lock_path(self, url: str) -> Path:
        return self.directory / f"{self.key(url)}.lock"

    # --- read / write --------------------------------------------------------------

    def load(self, url: str) -> httpx.Response | None:
        """The cached response for `url`, or None. A half-written file is a miss."""
        path = self.path(url)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(record, dict) or record.get("url") != url:
            return None
        headers = {"Content-Type": record.get("content_type") or "application/octet-stream"}
        return httpx.Response(
            int(record["status"]),
            headers=headers,
            content=str(record.get("body", "")).encode("utf-8"),
            request=httpx.Request("GET", url),
        )

    def store(self, url: str, response: httpx.Response) -> None:
        """Write atomically: a reader never sees a partial file (it sees no file)."""
        record = {
            "url": url,
            "status": response.status_code,
            "content_type": response.headers.get("Content-Type"),
            "body": response.text,
            "stored_at": time.time(),
        }
        path = self.path(url)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    # --- the cross-process miss protocol -------------------------------------------

    async def acquire(self, url: str) -> httpx.Response | None:
        """Return the cached response, or claim the right to fetch `url` and return None.

        While another process holds the claim, wait for its result rather than fetching
        too. The caller that receives None must `release(url)` once it stored (or gave
        up on) the response.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.lock_timeout_s
        while True:
            cached = self.load(url)
            if cached is not None:
                self.hits += 1
                return cached
            if self._try_lock(url):
                self.misses += 1
                return None
            if loop.time() >= deadline or self._lock_is_stale(url):
                self.release(url)  # abandoned by a dead process: take it over
                continue
            await self._sleep(self.poll_interval_s)

    def release(self, url: str) -> None:
        with contextlib.suppress(OSError):
            self.lock_path(url).unlink()

    def _try_lock(self, url: str) -> bool:
        try:
            fd = os.open(self.lock_path(url), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        return True

    def _lock_is_stale(self, url: str) -> bool:
        try:
            age = time.time() - self.lock_path(url).stat().st_mtime
        except OSError:
            return False
        return age > self.lock_timeout_s


class LitSenseClient:
    """The only thing in the package that talks to NCBI.

    Usage::

        async with LitSenseClient(settings) as client:
            hits = await client.search_sentences("...")
            publication = await client.fetch_publication(hits[0].pmid)
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: SleepFn = asyncio.sleep,
        limiter: RateLimiter | None = None,
        cache: ResponseCache | None = None,
    ) -> None:
        """`limiter` is the seam for handing several clients the same budget.

        Left alone, each client builds its own from `Settings`. Pass one in when more than one
        client has to share a single rate limit — the limit belongs to the service, not to us.
        `cache` is the on-disk response cache (ADR-010); left alone it is built from
        `Settings.http_cache_dir`, and absent when that is None.
        """
        self._settings = settings
        self._sleep = sleep
        if cache is None and settings.http_cache_dir:
            cache = ResponseCache(settings.http_cache_dir, sleep=sleep)
        self._cache = cache
        self._client = httpx.AsyncClient(
            base_url=settings.api_base_url,
            timeout=settings.request_timeout_s,
            headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
            transport=transport,
            follow_redirects=True,
        )
        self._limiter = limiter or RateLimiter(settings.requests_per_second, sleep=sleep)
        self._concurrency = asyncio.Semaphore(settings.max_concurrency)
        self._publications: dict[int, Publication] = {}
        self._full_texts: dict[str, FullText] = {}

    # --- lifecycle ---------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # --- public API --------------------------------------------------------------------

    async def search_sentences(
        self,
        query: str,
        *,
        limit: int | None = None,
        rerank: bool | None = None,
    ) -> list[SentenceHit]:
        """Retrieve sentences matching `query`.

        `limit` is the API's own result-count parameter; the server caps it at 100 whatever we
        ask for. Defaults come from `Settings`, so call sites do not carry their own.
        """
        params: dict[str, Any] = {
            "query": query,
            "rerank": "true" if (self._settings.rerank if rerank is None else rerank) else "false",
            "limit": self._settings.top_k_sentences if limit is None else limit,
        }
        response = await self._get(SENTENCES_PATH, params)
        self._raise_for_status(response)

        payload = response.json()
        if not isinstance(payload, list):
            raise LitSenseError(f"search returned {type(payload).__name__}, expected a list")
        return [SentenceHit.model_validate(item) for item in payload]

    async def fetch_publication(self, pmid: int) -> Publication:
        """Fetch one publication, from cache when we have already seen it.

        Raises `PublicationNotFound` for a pmid that does not resolve — a routine outcome
        during a fan-out, not a pipeline failure.
        """
        cached = self._publications.get(pmid)
        if cached is not None:
            return cached

        response = await self._get(PUBLICATION_PATH.format(pmid=pmid))
        if response.status_code == httpx.codes.NOT_FOUND or reports_missing_publication(response):
            raise PublicationNotFound(pmid)
        self._raise_for_status(response)

        publication = Publication.model_validate(response.json())
        self._publications[pmid] = publication
        return publication

    async def fetch_full_text(self, pmcid: str) -> FullText:
        """Fetch one article's BioC full text, from cache when already seen (ADR-009).

        The service lives outside the LitSense root, so the URL is absolute (the shared
        limiter still paces it — the rate limit belongs to NCBI, not to one endpoint). It
        wants the ``PMC`` prefix, and it signals "no result" as 200 + an HTML error page:
        an unparseable or shapeless body IS the not-found signal, raised as
        `FullTextNotFound` — permanent, never retried.
        """
        cached = self._full_texts.get(pmcid)
        if cached is not None:
            return cached

        response = await self._get(self._settings.full_text_url.format(pmcid=pmcid))
        self._raise_for_status(response)
        try:
            payload = response.json()
        except ValueError:
            raise FullTextNotFound(pmcid) from None

        # Observed wrapper: a list of BioC collections, the article at [0]["documents"][0].
        documents = payload[0].get("documents") if (
            isinstance(payload, list) and payload and isinstance(payload[0], dict)
        ) else None
        if not documents or not isinstance(documents[0], dict):
            raise FullTextNotFound(pmcid)

        full_text = FullText.model_validate({"pmcid": pmcid, **documents[0]})
        self._full_texts[pmcid] = full_text
        return full_text

    @property
    def cached_pmids(self) -> frozenset[int]:
        """Which publications this client already holds. Diagnostics only."""
        return frozenset(self._publications)

    # --- request plumbing --------------------------------------------------------------

    @property
    def cache(self) -> ResponseCache | None:
        """The on-disk response cache in use, if any. Diagnostics only."""
        return self._cache

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """Rate-limited GET with retry, behind the on-disk cache when one is configured.

        Returns any response the caller still needs to classify — including 4xx and permanent
        5xx. Raises `LitSenseUnavailable` only once retrying has stopped being worthwhile.
        """
        if self._cache is None:
            return await self._get_uncached(path, params)
        url = str(self._client.build_request("GET", path, params=params).url)
        cached = await self._cache.acquire(url)
        if cached is not None:
            return cached
        try:
            response = await self._get_uncached(path, params)
            self._cache.store(url, response)  # only final responses get this far
            return response
        finally:
            self._cache.release(url)

    async def _get_uncached(
        self, path: str, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        attempts = self._settings.max_retries + 1
        failure = "no attempt was made"

        for attempt in range(attempts):
            response: httpx.Response | None = None
            async with self._concurrency:
                await self._limiter.acquire()
                try:
                    response = await self._client.get(path, params=params)
                except httpx.TransportError as exc:
                    failure = f"{type(exc).__name__}: {exc}"

            if response is not None:
                if not self._is_retryable(response):
                    return response
                failure = f"HTTP {response.status_code}"

            if attempt < attempts - 1:
                await self._sleep(self._backoff_seconds(attempt, response))

        raise LitSenseUnavailable(f"GET {path} failed after {attempts} attempts ({failure})")

    def _is_retryable(self, response: httpx.Response) -> bool:
        """Transient server-side conditions only.

        A 5xx that is really "this pmid does not exist" is excluded: retrying it is guaranteed
        to fail again and costs a rate-limit slot each time (ADR-005).
        """
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            return True
        if response.is_server_error:
            return not reports_missing_publication(response)
        return False

    def _backoff_seconds(self, attempt: int, response: httpx.Response | None) -> float:
        """`Retry-After` when the server sent one, otherwise exponential with equal jitter."""
        if response is not None:
            retry_after = retry_after_seconds(response)
            if retry_after is not None:
                return retry_after
        window: float = self._settings.retry_backoff_base_s * (2.0**attempt)
        return window / 2 + random.uniform(0, window / 2)

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = extract_detail(response)
        if response.is_server_error:
            raise LitSenseUnavailable(f"HTTP {response.status_code} from the API: {detail}")
        raise LitSenseError(f"HTTP {response.status_code} from the API: {detail}")


def extract_detail(response: httpx.Response) -> str:
    """The API's `detail` string, or a short slice of whatever it sent instead."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(payload, dict) and "detail" in payload:
        return str(payload["detail"])
    return str(payload)[:200]


def reports_missing_publication(response: httpx.Response) -> bool:
    """True when the body says the pmid does not resolve, whatever status code it arrived with."""
    return PUBLICATION_MISSING_MARKER in extract_detail(response).casefold()


def retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse `Retry-After`, in either of its two legal forms. None when absent or malformed."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    now = target.now(tz=target.tzinfo)
    return max(0.0, (target - now).total_seconds())
