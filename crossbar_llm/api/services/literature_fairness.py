"""Per-user fairness for the literature tools.

Paperclip and PubTator3 are limited per account and per IP, and every user of
this server shares those limits. Without a per-user share, one person firing
several questions at once can occupy most of them while everyone else waits.
Measured live, the scarce Paperclip resource is its per-user search queue, and a
run makes one search at a time; so capping how many runs a user may have in
flight caps their share of the searches, without per-command bookkeeping.

A user queues first for their own share, then for the tool's global share,
within one shared wait budget. Someone over their share therefore never holds a
global slot while waiting, and so cannot block anyone else.

Who the user is comes from a context variable set once per request by
`bind_literature_user`, an app-level dependency. Keeping it out of the service
signatures means the request handlers and services pass nothing new around.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import AsyncIterator

from fastapi import Request

from crossbar_llm.agent_tools.logging_config import get_logger
from crossbar_llm.api.core.browser_identity import _load_browser_id
from crossbar_llm.api.core.rate_limit import rate_limit_key
from crossbar_llm.api.core.settings import Settings

logger = get_logger(__name__)

# The user a literature run is attributed to; None outside a request.
literature_user: ContextVar[str | None] = ContextVar("literature_user", default=None)


def _request_user(request: Request) -> str:
    """The browser id from the signed cookie, else the hashed client IP.

    The IP fallback covers clients without a cookie yet (a first visit) and
    scripts that never send one, which would otherwise escape the share. It is
    the same hashed key the API rate limiter uses, so no raw IP is kept.
    """
    signed = request.cookies.get(Settings().browser_cookie_name)
    if signed:
        try:
            return f"browser:{_load_browser_id(signed)}"
        except Exception:
            # A bad cookie is the route's business to reject, not ours: this
            # runs for every request, including ones that never look at it.
            pass
    return f"ip:{rate_limit_key(request)}"


async def bind_literature_user(request: Request) -> None:
    """App-level dependency: attribute this request's literature runs to its user.

    Must stay `async`. FastAPI runs a plain `def` dependency in a worker
    thread, and a context variable set there never reaches the endpoint (the
    endpoint sees None). An `async` dependency runs in the request's own task,
    so the value reaches the endpoint and every task it starts, a streamed
    response's included. No reset is needed: each request has its own context.
    """
    literature_user.set(_request_user(request))


class UserShareExhausted(Exception):
    """The user already holds their full share of a tool's runs."""

    def __init__(self, tool: str, limit: int):
        requests = "request" if limit == 1 else "requests"
        super().__init__(
            f"{tool} was skipped: you already have {limit} {tool} {requests} in "
            "progress. Additional requests may be waiting. Try again when one finishes."
        )
        self.tool = tool
        self.limit = limit


@dataclass
class _Share:
    slots: asyncio.Semaphore
    holders: int = 0          # runs holding a slot or queued for one


class PerUserLimiter:
    """At most N concurrent runs of a tool per user, FIFO within a user.

    One semaphore per (tool, user), created on first use and dropped as soon as
    nobody holds or waits for it, so the map does not grow with every browser
    that ever visited.
    """

    def __init__(self) -> None:
        self._shares: dict[tuple[str, str], _Share] = {}

    def active_users(self) -> int:
        return len(self._shares)

    @asynccontextmanager
    async def hold(
        self, tool: str, user: str, limit: int, timeout: float
    ) -> AsyncIterator[None]:
        key = (tool, user)
        share = self._shares.get(key)
        if share is None:
            share = self._shares[key] = _Share(asyncio.Semaphore(limit))
        # Each user may have at most one waiting request per active slot.
        # Otherwise one browser can fill the global waiting room by itself.
        if share.holders >= 2 * limit:
            raise UserShareExhausted(tool, limit)
        share.holders += 1
        acquired = False
        try:
            try:
                await asyncio.wait_for(share.slots.acquire(), timeout=max(0.0, timeout))
            except asyncio.TimeoutError:
                logger.warning(
                    "Literature run over the user's share",
                    event_type="literature_user_share_exhausted",
                    component="PerUserLimiter.hold",
                    tool=tool,
                    limit=limit,
                )
                raise UserShareExhausted(tool, limit) from None
            acquired = True
            yield
        finally:
            if acquired:
                share.slots.release()
            share.holders -= 1
            if share.holders == 0 and self._shares.get(key) is share:
                del self._shares[key]


class FairShare:
    """Applies `<tool>_max_runs_per_user` to the user bound to this request."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._limiter = PerUserLimiter()

    @property
    def limiter(self) -> PerUserLimiter:
        return self._limiter

    @asynccontextmanager
    async def hold(self, tool: str, deadline: float) -> AsyncIterator[None]:
        """Hold one of the user's runs of `tool`, queueing until `deadline`.

        A run with no user bound (benchmarks, scripts calling the service
        directly) or a tool with no per-user limit passes straight through.
        """
        user = literature_user.get()
        limit = getattr(self._settings, f"{tool}_max_runs_per_user", None)
        if user is None or limit is None:
            yield
            return
        remaining = deadline - asyncio.get_running_loop().time()
        async with self._limiter.hold(tool, user, limit, remaining):
            yield
