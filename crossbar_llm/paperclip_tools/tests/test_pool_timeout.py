"""The Paperclip connection pool is our client-side limit on commands in flight.

Paperclip documents 10 short commands in flight per account; live, the binding
limit was its per-user search queue (10 concurrent searches passed, 15 drew
429s). The REST pool defaults to 10, so these tests pin three things: the pool
really does cap concurrency, excess commands queue rather than fail, and pool
exhaustion never spills onto the MCP transport — which Paperclip counts
against the same account.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from crossbar_llm.paperclip_tools import adapter as adapter_module
from crossbar_llm.paperclip_tools.adapter import (
    ACCOUNT_MAX_SHORT_IN_FLIGHT,
    PaperclipAdapter,
    PaperclipError,
    PaperclipRestUnavailable,
)


class _RecordingClient:
    """Captures the Timeout object the adapter hands to httpx."""

    def __init__(self, raises: Exception | None = None):
        self.raises = raises
        self.timeout = None

    async def post(self, url, **kwargs):
        self.timeout = kwargs.get("timeout")
        if self.raises is not None:
            raise self.raises
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"output": "ok"}, request=request)


def test_pool_defaults_to_the_account_limit():
    assert ACCOUNT_MAX_SHORT_IN_FLIGHT == 10
    assert PaperclipAdapter(api_key="k")._max_connections == 10


async def test_pool_timeout_is_separate_from_the_call_timeout(monkeypatch):
    adapter = PaperclipAdapter(
        api_key="k", disable_rest=False, timeout_s=60.0, pool_timeout_s=10.0
    )
    client = _RecordingClient()
    monkeypatch.setattr(adapter, "_rest_client", lambda: client)

    await adapter._run_rest("search", "anything")

    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.read == 60.0
    # Waiting for a connection gets its own budget rather than the call's.
    assert client.timeout.pool == 10.0


async def test_pool_exhaustion_is_a_saturation_error_not_a_rest_outage(monkeypatch):
    adapter = PaperclipAdapter(
        api_key="k", disable_rest=False, max_connections=4, pool_timeout_s=10.0
    )
    client = _RecordingClient(raises=httpx.PoolTimeout("no free connection"))
    monkeypatch.setattr(adapter, "_rest_client", lambda: client)

    with pytest.raises(PaperclipError) as excinfo:
        await adapter._run_rest("search", "anything")

    # Not RestUnavailable: that type is what triggers the MCP fallback.
    assert not isinstance(excinfo.value, PaperclipRestUnavailable)
    message = str(excinfo.value)
    assert "no free Paperclip connection" in message
    assert "max_connections=4" in message


async def test_pool_exhaustion_does_not_fall_back_to_mcp(monkeypatch):
    """MCP shares the account's in-flight limit, so the overflow must not go
    there — it would just be rejected by Paperclip through a different door."""
    adapter = PaperclipAdapter(api_key="k", disable_rest=False, pool_timeout_s=10.0)
    client = _RecordingClient(raises=httpx.PoolTimeout("no free connection"))
    monkeypatch.setattr(adapter, "_rest_client", lambda: client)

    async def mcp_must_not_run(command):
        raise AssertionError(f"fell back to MCP for {command!r}")

    monkeypatch.setattr(adapter, "_run", mcp_must_not_run)

    with pytest.raises(PaperclipError, match="no free Paperclip connection"):
        await adapter._execute("cat", "/papers/PMC1/meta.json")


async def test_pool_caps_commands_in_flight_and_queues_the_rest(monkeypatch):
    """Against a real local HTTP server: 25 simultaneous commands through a
    10-connection pool never have more than 10 in flight, and all complete."""
    state = {"in_flight": 0, "peak": 0}

    async def handle(reader, writer):
        try:
            while True:
                head = await reader.readuntil(b"\r\n\r\n")
                length = 0
                for line in head.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":", 1)[1])
                await reader.readexactly(length)
                state["in_flight"] += 1
                state["peak"] = max(state["peak"], state["in_flight"])
                await asyncio.sleep(0.05)
                state["in_flight"] -= 1
                body = b'{"output": "ok"}'
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    b"Content-Length: %d\r\n\r\n%s" % (len(body), body)
                )
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setattr(adapter_module, "REST_URL", f"http://127.0.0.1:{port}/")

    adapter = PaperclipAdapter(api_key="k", disable_rest=False, pool_timeout_s=10.0)
    async with server:
        try:
            results = await asyncio.gather(
                *(adapter._run_rest("cat", f"/papers/PMC{i}/meta.json") for i in range(25))
            )
        finally:
            # Close the client BEFORE the server: on Python 3.12 the server's
            # exit waits for open connections, and httpx keeps them alive.
            await adapter.aclose()

    assert len(results) == 25
    assert all(r.get("output") == "ok" for r in results)
    assert state["peak"] == ACCOUNT_MAX_SHORT_IN_FLIGHT


async def test_pool_size_is_configurable():
    adapter = PaperclipAdapter(api_key="k", max_connections=4)
    client = adapter._rest_client()
    try:
        pool = client._transport._pool
        assert pool._max_connections == 4
        assert pool._max_keepalive_connections == 2
    finally:
        await client.aclose()
