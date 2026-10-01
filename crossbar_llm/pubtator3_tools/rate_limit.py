"""Rate-limiter backends for the PubTator3 client.

PubTator3's 3 req/s ceiling is enforced by NCBI **per IP**, not per process. The
client's default limiter is per-event-loop, which is exactly right for a single
instance and wrong the moment a second replica shares an egress IP: each one
independently allows 3 req/s and NCBI sees the sum.

`client.set_limiter_factory()` is the seam. This module holds the backends that
plug into it:

- `StaticShareLimiter` — divides the budget by a configured replica count. No
  new dependencies, never exceeds the ceiling, but wastes budget when replicas
  are idle and must be updated when you rescale.
- A shared coordinated limiter (Redis or similar) is the better answer at more
  than a couple of replicas; it lives outside this module so the tool package
  stays dependency-free.

Both are async context managers, matching `aiolimiter.AsyncLimiter`.
"""
from __future__ import annotations

import asyncio
import weakref

from aiolimiter import AsyncLimiter

from crossbar_llm.pubtator3_tools.client import (
    RATE_LIMIT_PER_SECOND,
    RATE_LIMIT_TIME_PERIOD_S,
    set_limiter_factory,
)


class StaticShareLimiter:
    """Enforce this replica's fixed share of an IP-wide budget.

    With `replica_count=N` each instance allows `RATE_LIMIT_PER_SECOND / N`
    requests per second, so the total across N replicas stays at or under the
    ceiling no matter how the load balancer distributes work. Correct without
    coordination, at the cost of throughput when replicas are unevenly busy.

    Limiters are kept per event loop for the same reason the client's default
    is: an `AsyncLimiter` binds to the loop that created it.
    """

    def __init__(
        self,
        *,
        replica_count: int = 1,
        max_rate: float = RATE_LIMIT_PER_SECOND,
        time_period: float = RATE_LIMIT_TIME_PERIOD_S,
    ):
        if replica_count < 1:
            raise ValueError("replica_count must be at least 1")
        self.replica_count = replica_count
        self.time_period = time_period
        # aiolimiter requires a positive rate, so a very high replica count
        # stretches the window rather than rounding the rate down to zero.
        self.max_rate = max_rate / replica_count
        if self.max_rate < 1:
            self.time_period = time_period / self.max_rate
            self.max_rate = 1.0
        self._by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncLimiter]" = (
            weakref.WeakKeyDictionary()
        )

    def __call__(self) -> AsyncLimiter:
        loop = asyncio.get_running_loop()
        limiter = self._by_loop.get(loop)
        if limiter is None:
            limiter = AsyncLimiter(
                max_rate=self.max_rate, time_period=self.time_period
            )
            self._by_loop[loop] = limiter
        return limiter


def install_static_share_limiter(replica_count: int) -> StaticShareLimiter | None:
    """Point the PubTator3 client at a per-replica share of the IP-wide budget.

    A `replica_count` of 1 restores the default limiter rather than installing
    an equivalent one, so the single-instance path keeps its original
    behaviour exactly.
    """
    if replica_count <= 1:
        set_limiter_factory(None)
        return None
    limiter = StaticShareLimiter(replica_count=replica_count)
    set_limiter_factory(limiter)
    return limiter


__all__ = ["StaticShareLimiter", "install_static_share_limiter"]
