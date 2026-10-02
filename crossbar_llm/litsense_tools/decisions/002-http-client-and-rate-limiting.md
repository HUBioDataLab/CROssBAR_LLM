# ADR-002 — HTTP client, rate limiting, and caching

**Status:** Accepted

## Context

The LitSense 2.0 API is a free public NCBI service, rate-limited to roughly one request per
second, capped at 100 results per query. A single question triggers one search call plus up to
`max_articles` publication calls. With `max_articles = 10`, a naive concurrent fan-out sends 10
requests essentially simultaneously — an immediate violation, and a good way to get an IP
blocked from a service we don't control and can't appeal to.

## Decision

One `LitSenseClient` class wrapping a single shared `httpx.AsyncClient`.

- **Global rate limiter.** One limiter instance held by the client, applied to every outbound
  request regardless of call site. Not per-node, not per-endpoint. Concurrency is bounded by an
  `asyncio.Semaphore`; `max_concurrency` defaults to 1 and is config-driven so it can be raised
  if the published limit ever changes.
- **Retry with exponential backoff and jitter** on 429 and 5xx, capped at a small number of
  attempts. Honor `Retry-After` when present. Never retry 4xx other than 429.
- **Per-pmid response cache**, in-memory, for the process lifetime. Repeated questions in one
  session and duplicate pmids across nodes cost nothing.
- **Explicit timeout** on every request from `request_timeout_s`. No unbounded waits.
- **Descriptive User-Agent** identifying the tool. We are a guest on someone's infrastructure.
- **Partial failure is not fatal.** If some publication fetches fail or time out, the pipeline
  proceeds with what it has and records the missing pmids in state. The answer is degraded, not
  absent.

The client raises typed exceptions (`LitSenseUnavailable`, `PublicationNotFound`) rather than
leaking `httpx` types upward. Nothing above `client.py` imports httpx.

## Rationale

A single choke point is the only arrangement that can actually enforce a global limit — any
per-call-site scheme drifts the moment a new call site is added. Keeping httpx contained also
means the graph nodes are testable with a fake client and no transport mocking.

## Consequences

- With `max_concurrency = 1`, fetching 10 abstracts takes roughly 10 seconds. This is the
  dominant latency of the pipeline and it is accepted. If latency becomes a problem, the answer
  is a smaller `max_articles`, not a higher request rate.
- The cache is per-process and vanishes on exit. A persistent cache is a possible later
  addition; it is deliberately not in v1.

## Amendment — implementation, 2026-08-06

**Status:** Accepted — 2026-08-10, provisionally, together with ADR-005 and ADR-006. Four
things this ADR did not settle, decided while writing `client.py`.

**Transport errors and timeouts are retried like 5xx.** This ADR named 429 and 5xx. A connection
reset or a timeout is transient in exactly the same way and there is no reason to treat it as
final. `httpx.TransportError` — the base class covering both — is retried with the same backoff.

**A non-retryable 4xx raises `LitSenseError`, not `LitSenseUnavailable`.** A 400 means we built a
bad request; the service is fine. Calling that "unavailable" would send whoever reads the log
looking at NCBI instead of at our own code. The two named exceptions stay as specified and the
base class carries the third case.

**An unresolvable pmid is classified by response body, not status code.** Required by ADR-005:
the API reports it as a 500, and this ADR's retry rule would otherwise turn every missing pmid
into four requests. `_is_retryable` checks the body before agreeing a 5xx is transient.

**The limiter is injectable.** `LitSenseClient(settings, limiter=...)` lets several clients share
one budget. The default is still one limiter per client built from `Settings`, so the "single
shared limiter" property is unchanged for the pipeline, which uses exactly one client. This also
makes the limiter's pacing observable in tests separately from retry backoff.

Consequence: the client now retries on conditions this ADR did not enumerate. The worst case is
bounded by `max_retries` and every retry still passes through the global limiter, so a retry
storm cannot exceed the configured request rate — it can only spend it.
