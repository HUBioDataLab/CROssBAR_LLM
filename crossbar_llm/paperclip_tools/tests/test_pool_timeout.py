"""Client-side limits on Paperclip commands in flight.

Live, the binding limit was Paperclip's per-user search queue (10 concurrent
searches passed, 15 drew 429s), while 30 concurrent reads all passed. So
commands draw one of three permits, shared by REST and MCP: searches (10),
reads (30) and long commands (8). These tests pin that each kind is capped and
queues rather than fails, that reads never wait behind searches, and that pool
exhaustion never spills onto the MCP transport — which Paperclip counts
against the same account.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from crossbar_llm.paperclip_tools import adapter as adapter_module
from crossbar_llm.paperclip_tools.adapter import (
    ACCOUNT_MAX_LONG_IN_FLIGHT,
    ACCOUNT_MAX_SHORT_IN_FLIGHT,
    DEFAULT_MAX_READS_IN_FLIGHT,
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


def test_permit_and_pool_defaults():
    adapter = PaperclipAdapter(api_key="k")
    assert adapter._permit_limits == {"search": 10, "read": 30, "long": 8}
    # The pool fits every permit at once, so a permitted command never waits
    # for a connection.
    assert adapter._max_connections == 10 + 30 + 8


@pytest.mark.parametrize(
    "command, kind",
    [
        ("search", "search"),
        ("sql", "search"),
        ("filter", "search"),
        ("lookup", "search"),  # unknown verbs get the strictest permit
        ("cat", "read"),
        ("head", "read"),
        ("ls", "read"),
        ("map", "long"),
        ("verify", "long"),
    ],
)
def test_commands_draw_the_right_permit(command, kind):
    assert adapter_module._command_kind(f"{command} some args") == kind


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


@pytest.mark.parametrize(
    "verb, raw, cap",
    [
        ("search", '"query {i}"', ACCOUNT_MAX_SHORT_IN_FLIGHT),
        ("cat", "/papers/PMC{i}/meta.json", DEFAULT_MAX_READS_IN_FLIGHT),
    ],
)
async def test_permits_cap_commands_in_flight_and_queue_the_rest(monkeypatch, verb, raw, cap):
    """Against a real local HTTP server: more simultaneous commands than the
    kind's permits never have more than that many in flight, and all complete."""
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
                *(adapter._run_rest(verb, raw.format(i=i)) for i in range(cap + 15))
            )
        finally:
            # Close the client BEFORE the server: on Python 3.12 the server's
            # exit waits for open connections, and httpx keeps them alive.
            await adapter.aclose()

    assert len(results) == cap + 15
    assert all(r.get("output") == "ok" for r in results)
    assert state["peak"] == cap


async def test_reads_do_not_wait_behind_searches(monkeypatch):
    """The point of separate read permits: with every search permit held (as
    when searches sit in Paperclip's search queue), a metadata read still runs
    at once instead of queueing behind them."""
    searching = 0
    all_searching = asyncio.Event()
    release = asyncio.Event()

    class FakeClient:
        async def post(self, url, **kwargs):
            nonlocal searching
            if kwargs["json"]["command"] == "search":
                searching += 1
                if searching == ACCOUNT_MAX_SHORT_IN_FLIGHT:
                    all_searching.set()
                await release.wait()
            return httpx.Response(200, json={"output": "ok"}, request=httpx.Request("POST", url))

    adapter = PaperclipAdapter(api_key="k", disable_rest=False, pool_timeout_s=10.0)
    monkeypatch.setattr(adapter, "_rest_client", lambda: FakeClient())
    searches = [
        asyncio.create_task(adapter._run_rest("search", f'"query {i}"'))
        for i in range(ACCOUNT_MAX_SHORT_IN_FLIGHT)
    ]
    try:
        await asyncio.wait_for(all_searching.wait(), timeout=1.0)
        # Bounded: if reads shared the search permits, this read would wait
        # for `release`, which only comes after it.
        read = await asyncio.wait_for(
            adapter._run_rest("cat", "/papers/PMC1/meta.json"), timeout=1.0
        )
        assert read["output"] == "ok"
    finally:
        release.set()
        await asyncio.gather(*searches)


async def test_pool_size_is_configurable():
    adapter = PaperclipAdapter(api_key="k", max_connections=4)
    client = adapter._rest_client()
    try:
        pool = client._transport._pool
        assert pool._max_connections == 4
        assert pool._max_keepalive_connections == 2
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "command, cap",
    [
        ("search -s pmc query {i}", ACCOUNT_MAX_SHORT_IN_FLIGHT),
        ("cat /papers/{i}", DEFAULT_MAX_READS_IN_FLIGHT),
    ],
)
async def test_mcp_fallback_caps_commands_and_queues_the_rest(monkeypatch, command, cap):
    state = {"in_flight": 0, "peak": 0}

    class FakeTool:
        async def ainvoke(self, args):
            state["in_flight"] += 1
            state["peak"] = max(state["peak"], state["in_flight"])
            await asyncio.sleep(0.01)
            state["in_flight"] -= 1
            return "ok"

    async def fake_tool(**kwargs):
        return FakeTool()

    monkeypatch.setattr(adapter_module, "_paperclip_tool", fake_tool)
    adapter = PaperclipAdapter(api_key="k", disable_rest=True, pool_timeout_s=2.0)
    results = await asyncio.gather(
        *(adapter._run(command.format(i=i)) for i in range(cap + 15))
    )
    assert results == ["ok"] * (cap + 15)
    assert state["peak"] == cap


async def test_mcp_map_uses_the_long_command_limit(monkeypatch):
    entered = 0
    release = asyncio.Event()

    class FakeTool:
        async def ainvoke(self, args):
            nonlocal entered
            entered += 1
            await release.wait()
            return "ok"

    async def fake_tool(**kwargs):
        return FakeTool()

    monkeypatch.setattr(adapter_module, "_paperclip_tool", fake_tool)
    adapter = PaperclipAdapter(api_key="k", disable_rest=True, pool_timeout_s=0.05)
    active = [
        asyncio.create_task(adapter._run("map --from s_1 question"))
        for _ in range(ACCOUNT_MAX_LONG_IN_FLIGHT)
    ]
    try:
        await asyncio.sleep(0.01)
        assert entered == ACCOUNT_MAX_LONG_IN_FLIGHT
        # Bounded: if map drew a search or read permit, this ninth call
        # would get a permit and block on `release`, hanging the suite.
        with pytest.raises(PaperclipError, match="no free Paperclip command slot"):
            await asyncio.wait_for(adapter._run("map --from s_1 question"), timeout=1.0)
    finally:
        release.set()
    await asyncio.gather(*active)


async def test_rest_and_mcp_share_the_account_permit(monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()

    class FakeClient:
        async def post(self, url, **kwargs):
            entered.set()
            await release.wait()
            return httpx.Response(200, json={"output": "ok"}, request=httpx.Request("POST", url))

    class FakeTool:
        async def ainvoke(self, args):
            raise AssertionError("MCP should wait while REST holds the only slot")

    async def fake_tool(**kwargs):
        return FakeTool()

    adapter = PaperclipAdapter(api_key="k", max_connections=1, pool_timeout_s=0.03)
    monkeypatch.setattr(adapter, "_rest_client", lambda: FakeClient())
    monkeypatch.setattr(adapter_module, "_paperclip_tool", fake_tool)
    rest = asyncio.create_task(adapter._run_rest("search", '"query"'))
    await entered.wait()
    with pytest.raises(PaperclipError, match="no free Paperclip command slot"):
        await adapter._run("search -s pmc query")
    release.set()
    assert (await rest)["output"] == "ok"
