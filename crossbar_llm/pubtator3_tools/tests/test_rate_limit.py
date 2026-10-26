"""Tests for the swappable PubTator3 rate-limiter backends.

The 3 req/s ceiling is NCBI's and applies per IP, so these pin the two things
that make multi-replica deployment safe: that the client honours an installed
limiter at all, and that a per-replica share actually divides the budget.
"""
import asyncio
import httpx
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


@pytest.mark.asyncio
async def test_429_honors_retry_after_without_holding_a_connection(monkeypatch):
    responses = [
        httpx.Response(429, headers={"Retry-After": "4"}, request=httpx.Request("GET", "https://example.org")),
        httpx.Response(200, request=httpx.Request("GET", "https://example.org")),
    ]
    calls = []
    delays = []

    class FakeClient:
        async def request(self, *args, **kwargs):
            calls.append(args)
            return responses.pop(0)

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(pt_client, "_client", lambda: FakeClient())
    monkeypatch.setattr(pt_client, "_sleep", fake_sleep)
    response = await pt_client._request("GET", "/search/")
    assert response.status_code == 200
    assert len(calls) == 2
    assert delays == [4.0]


@pytest.mark.asyncio
async def test_429_excessive_retry_after_fails_without_retry(monkeypatch):
    calls = []

    class FakeClient:
        async def request(self, *args, **kwargs):
            calls.append(args)
            return httpx.Response(
                429,
                headers={"Retry-After": "3600"},
                request=httpx.Request("GET", "https://example.org"),
            )

    async def must_not_wait(seconds):
        # A Retry-After past the cap must fail at once. Without this stub, a
        # regression would really sleep for the hour the header asks for.
        raise AssertionError(f"waited {seconds}s instead of failing fast")

    monkeypatch.setattr(pt_client, "_client", lambda: FakeClient())
    monkeypatch.setattr(pt_client, "_sleep", must_not_wait)
    with pytest.raises(httpx.HTTPStatusError):
        await pt_client._request("GET", "/search/")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_pooled_client_is_closed_on_shutdown():
    loop = asyncio.get_running_loop()

    class FakeClient:
        is_closed = False

        async def aclose(self):
            self.is_closed = True

    cli = FakeClient()
    pt_client._clients_by_loop[loop] = cli
    await pt_client.aclose_client()
    assert cli.is_closed
    assert loop not in pt_client._clients_by_loop
