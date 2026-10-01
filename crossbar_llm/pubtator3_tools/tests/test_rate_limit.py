"""Tests for the swappable PubTator3 rate-limiter backends.

The 3 req/s ceiling is NCBI's and applies per IP, so these pin the two things
that make multi-replica deployment safe: that the client honours an installed
limiter at all, and that a per-replica share actually divides the budget.
"""
import asyncio
import pytest

from crossbar_llm.pubtator3_tools import client as pt_client
from crossbar_llm.pubtator3_tools.rate_limit import (
    StaticShareLimiter,
    install_static_share_limiter,
)


@pytest.fixture(autouse=True)
def _restore_default_limiter():
    yield
    pt_client.set_limiter_factory(None)


def test_single_replica_keeps_the_default_limiter():
    assert install_static_share_limiter(1) is None
    assert pt_client._limiter_factory is None


def test_share_divides_the_ip_wide_budget():
    limiter = install_static_share_limiter(3)
    assert limiter.max_rate == pytest.approx(pt_client.RATE_LIMIT_PER_SECOND / 3)
    assert pt_client._limiter_factory is limiter


def test_high_replica_count_stretches_the_window_instead_of_rounding_to_zero():
    # 3 req/s over 12 replicas is 0.25 req/s, which aiolimiter rejects as a
    # rate. It must become 1 per 4s, not 0 per second (which never admits).
    limiter = StaticShareLimiter(replica_count=12)
    assert limiter.max_rate >= 1
    assert limiter.max_rate / limiter.time_period == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_installed_limiter_is_used_by_the_client():
    calls = []

    class _Fake:
        async def __aenter__(self): calls.append("acquire"); return self
        async def __aexit__(self, *a): return False

    pt_client.set_limiter_factory(lambda: _Fake())
    async with pt_client._limiter():
        pass
    assert calls == ["acquire"]


@pytest.mark.asyncio
async def test_share_limiter_actually_throttles():
    limiter = StaticShareLimiter(replica_count=3, max_rate=3, time_period=1)
    start = asyncio.get_running_loop().time()
    for _ in range(3):
        async with limiter():
            pass
    elapsed = asyncio.get_running_loop().time() - start
    # 1 req/s share: three acquisitions cannot complete instantly.
    assert elapsed >= 1.5
