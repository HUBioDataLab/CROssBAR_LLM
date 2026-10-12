# Literature tool capacity

The literature tools are optional branches of the synchronous chat request. The
core graph and the selected literature graphs run concurrently, and the response
waits for both. A long queue therefore raises chat latency as well as literature
latency. Tune for the *whole request* rather than upstream calls alone.

## Controls in this service

| Control | Paperclip | PubTator3 |
| --- | --- | --- |
| Active agent graphs per process | `paperclip_max_concurrent_runs=20` | `pubtator3_max_concurrent_runs=50` |
| Additional runs waiting per process | `paperclip_max_pending_runs=40` | `pubtator3_max_pending_runs=50` |
| Run slots per browser | `paperclip_max_runs_per_user=3` | `pubtator3_max_runs_per_user=3` |
| Queue wait deadline | `literature_admission_wait_seconds=30` | same |
| Run deadline after admission | `literature_tool_timeout_seconds=180` | same |
| Upstream calls in flight | Shared REST/MCP command permits and REST HTTP pool: `paperclip_max_connections=10` | HTTPX default pool |
| Upstream rate | Paperclip account limit and bounded 429 retries | local 3 requests/s limiter, divided by `pubtator3_replica_count` |

The per-user share is acquired before the global run slot, so one browser
cannot hold a global slot while waiting on its own quota. A browser may queue
one extra run for each of its active slots. A tool's active plus pending cap is
checked before either wait; this bounds the memory used by waiting tasks.
Cancellation, deadline expiry and normal completion release the reservation.
When the waiting room is full, that literature branch is returned as `skipped`
and the core answer can still complete. The log event `literature_run_admitted`
records queue wait time and outstanding runs; `literature_tool_not_admitted`
records rejection. Watch their counts and latency percentiles before raising
the caps.

The Paperclip HTTP connection pool is a **second**, command-level queue. It
reuses sockets and limits concurrent REST commands; it does not bound the
number of agent graphs or HTTP requests waiting in the app. Paperclip's 429
retry respects `Retry-After` and releases the connection while sleeping.
Both transports share short-command (10) and long-command (8) permits,
further reduced by `paperclip_max_connections` when configured lower. A 429
backoff releases its permit before sleeping.
PubTator3 also respects a bounded `Retry-After` on its single 429 retry.

These values are `Settings` model defaults, not environment variables. Change
them in `crossbar_llm/api/core/settings.py` (or add a deployment settings
provider) and run load tests with realistic question mixes before changing
production capacity. A larger queue does not increase upstream throughput.

## Multiple workers or replicas

All run caps, per-user shares, and waiting rooms above are **process local**.
The API request limits also use SlowAPI's default in-memory store. A deployment
with multiple workers multiplies these capacities, even on one host. Paperclip
limits are per account across every key user and process. PubTator3 is treated
as an egress-IP budget in this client; `pubtator3_replica_count` divides that
budget statically and needs to match the number of workers sharing the IP.
Static division leaves unused capacity when one replica is idle.

Before scaling workers, coordinate rate and concurrency limits in a shared
store or a dedicated literature worker service. Scope the Paperclip limiter to
the account and the PubTator3 limiter to the actual egress identity. Use
leases with expiry for in-flight limits so crashed workers do not hold slots
forever. Keep a short local waiting room in each worker even with shared
limits. If a user-facing request must wait longer than the chat latency target,
move the literature work to durable jobs with a job ID, progress endpoint,
idempotency key, cancellation, and a retention deadline; a longer HTTP wait
is not a durable queue.

## Next throughput work

1. Measure per-tool queue wait, upstream status (especially 429), pool timeout,
   command latency, run duration, and upstream calls per completed answer. Alert
   when rejection or timeout rates rise. Do not log API keys or question text.
2. Cache stable article exports and metadata by PMID/document ID with an
   explicit TTL. Coalesce simultaneous fetches of the same document. Cache
   search results only with a shorter TTL and a key that includes all filters;
   freshness and citation quality matter.
3. Review Paperclip's now-documented `/api/v1` search and document endpoints
   as a replacement for the undocumented CLI execute endpoint. Verify feature
   parity for the current cross-corpus search, saved result IDs, map and line
   provenance before migrating. Keep the MCP fallback capacity controlled
   during any migration.
4. For higher sustained traffic, obtain a higher upstream quota or spread
   independently authenticated account workloads where the provider permits
   it. Neither connection pooling nor retries can exceed a provider's
   sustained quota.

Provider and client references:
[Paperclip rate limits](https://paperclip.gxl.ai/docs),
[HTTPX pool limits](https://www.python-httpx.org/advanced/resource-limits/),
[HTTPX pool timeout](https://www.python-httpx.org/advanced/timeouts/), and
[AWS guidance on bounded queues](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_mitigate_interaction_failure_fail_fast.html).
