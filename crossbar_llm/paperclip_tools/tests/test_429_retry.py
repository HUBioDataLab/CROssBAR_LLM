"""A Paperclip 429 is retried patiently, boundedly, and without hogging a slot.

Live (2026-09-22), Paperclip answered a full per-user search queue with
`429 "Per-user search queue is full (6/6)"` and `Retry-After: 15`, and its docs
say to wait and retry. Before this, a 429 was final, so that user lost their
whole Paperclip answer. These tests pin the retry rules: honour Retry-After,
back off without one, stop after a bounded number of tries, never retry the
daily-capped commands, and never hold a connection while waiting.
"""
from __future__ import annotations

import asyncio
import email.utils
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from crossbar_llm.paperclip_tools import adapter as adapter_module
from crossbar_llm.paperclip_tools.adapter import (
    PaperclipAdapter,
    PaperclipError,
    _parse_retry_after,
)

QUEUE_FULL = '{"detail":"Per-user search queue is full (6/6)"}'
DAILY_LIMIT = '{"detail":"You\'ve hit the daily limit on map/verify operations (100/day)."}'


def _response(status, *, text="", headers=None, payload=None):
    request = httpx.Request("POST", adapter_module.REST_URL)
    if payload is not None:
        return httpx.Response(status, json=payload, headers=headers, request=request)
    return httpx.Response(status, text=text, headers=headers, request=request)


@pytest.fixture
def scripted(monkeypatch):
    """Serve a scripted list of responses and record every wait instead of sleeping."""
    state = {"responses": [], "posts": [], "waits": []}

    async def fake_post(self, url, *, json, headers, timeout):
        state["posts"].append(json["command"])
        return state["responses"].pop(0)

    async def record_wait(seconds):
        state["waits"].append(seconds)

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr(adapter_module, "_sleep", record_wait)
    return state


def _adapter(**kwargs):
    return PaperclipAdapter(api_key="k", disable_rest=False, **kwargs)


async def test_queue_full_waits_retry_after_then_succeeds(scripted):
    scripted["responses"] = [
        _response(429, text=QUEUE_FULL, headers={"Retry-After": "15"}),
        _response(200, payload={"output": "ok"}),
    ]

    data = await _adapter()._run_rest("search", '"EGFR" -n 10')

    assert data["output"] == "ok"
    assert scripted["posts"] == ["search", "search"]
    # Never earlier than Retry-After; jitter only ever adds, at most 3 s.
    assert len(scripted["waits"]) == 1
    assert 15.0 <= scripted["waits"][0] <= 18.0


async def test_without_retry_after_it_backs_off_exponentially(scripted):
    scripted["responses"] = [
        _response(429, text=QUEUE_FULL),
        _response(429, text=QUEUE_FULL),
        _response(200, payload={"output": "ok"}),
    ]

    await _adapter()._run_rest("cat", "/papers/PMC1/meta.json")

    first, second = scripted["waits"]
    assert 2.0 <= first <= 2.4
    assert 4.0 <= second <= 4.8


async def test_retries_are_bounded(scripted):
    scripted["responses"] = [
        _response(429, text=QUEUE_FULL, headers={"Retry-After": "1"}) for _ in range(3)
    ]

    with pytest.raises(PaperclipError, match="429"):
        await _adapter(max_429_retries=2)._run_rest("search", '"q" -n 10')

    assert scripted["posts"] == ["search"] * 3
    assert len(scripted["waits"]) == 2


async def test_zero_retries_restores_fail_fast(scripted):
    scripted["responses"] = [_response(429, text=QUEUE_FULL, headers={"Retry-After": "1"})]

    with pytest.raises(PaperclipError, match="429"):
        await _adapter(max_429_retries=0)._run_rest("search", '"q" -n 10')

    assert scripted["waits"] == []


@pytest.mark.parametrize("verb", ["map", "verify"])
async def test_daily_capped_commands_are_never_retried(scripted, verb):
    """A 429 here means the day's 100 are spent; waiting cannot fix that."""
    scripted["responses"] = [_response(429, text=DAILY_LIMIT, headers={"Retry-After": "1"})]

    with pytest.raises(PaperclipError, match="429"):
        await _adapter()._run_rest(verb, "--from s_1 \"q\"")

    assert scripted["waits"] == []


async def test_a_daily_limit_body_is_final_for_any_command(scripted):
    scripted["responses"] = [_response(429, text=DAILY_LIMIT, headers={"Retry-After": "1"})]

    with pytest.raises(PaperclipError):
        await _adapter()._run_rest("search", '"q" -n 10')

    assert scripted["waits"] == []


async def test_a_wait_longer_than_the_cap_fails_fast(scripted):
    """Holding a user's request for an hour is worse than failing that tool."""
    scripted["responses"] = [_response(429, text=QUEUE_FULL, headers={"Retry-After": "3600"})]

    with pytest.raises(PaperclipError, match="429"):
        await _adapter(max_retry_wait_s=30.0)._run_rest("search", '"q" -n 10')

    assert scripted["waits"] == []


async def test_401_is_never_retried(scripted):
    scripted["responses"] = [_response(401, text="bad key", headers={"Retry-After": "1"})]

    with pytest.raises(PaperclipError, match="401"):
        await _adapter()._run_rest("search", '"q" -n 10')

    assert scripted["waits"] == []


async def test_exhausted_retries_do_not_fall_back_to_mcp(scripted, monkeypatch):
    """MCP shares the account's limits, so it is no escape from a 429."""
    scripted["responses"] = [
        _response(429, text=QUEUE_FULL, headers={"Retry-After": "1"}) for _ in range(3)
    ]
    adapter = _adapter()

    async def mcp_must_not_run(command):
        raise AssertionError(f"fell back to MCP for {command!r}")

    monkeypatch.setattr(adapter, "_run", mcp_must_not_run)

    with pytest.raises(PaperclipError, match="429"):
        await adapter._execute("cat", "/papers/PMC1/meta.json")


def test_retry_after_parses_seconds_and_http_dates():
    assert _parse_retry_after("15") == 15.0
    assert _parse_retry_after(" 2.5 ") == 2.5
    assert _parse_retry_after("-4") == 0.0
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("soon") is None

    when = datetime.now(timezone.utc) + timedelta(seconds=10)
    parsed = _parse_retry_after(email.utils.format_datetime(when, usegmt=True))
    assert 8.0 <= parsed <= 10.0


async def test_a_waiting_retry_does_not_hold_a_connection(monkeypatch):
    """Against a real local server with a ONE-connection pool: while the
    rejected search sits out its Retry-After, another command must get the
    connection. If the wait held it, the cat would queue behind the retry."""
    seen: list[str] = []
    rejected_once = False

    async def handle(reader, writer):
        nonlocal rejected_once
        try:
            while True:
                head = await reader.readuntil(b"\r\n\r\n")
                length = 0
                for line in head.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":", 1)[1])
                command = json.loads(await reader.readexactly(length))["command"]
                seen.append(command)
                if command == "search" and not rejected_once:
                    rejected_once = True
                    body, status = QUEUE_FULL.encode(), b"429 Too Many Requests"
                    extra = b"Retry-After: 0.4\r\n"
                else:
                    body, status, extra = b'{"output": "ok"}', b"200 OK", b""
                writer.write(
                    b"HTTP/1.1 " + status + b"\r\nContent-Type: application/json\r\n"
                    + extra + b"Content-Length: %d\r\n\r\n%s" % (len(body), body)
                )
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setattr(adapter_module, "REST_URL", f"http://127.0.0.1:{port}/")

    adapter = _adapter(max_connections=1, pool_timeout_s=5.0, max_retry_wait_s=5.0)
    async with server:
        try:
            search = asyncio.create_task(adapter._run_rest("search", '"q" -n 10'))
            await asyncio.sleep(0.15)  # the 429 is back; the retry is waiting
            cat = await asyncio.wait_for(
                adapter._run_rest("cat", "/papers/PMC1/meta.json"), timeout=0.3
            )
            retried = await search
        finally:
            # Close the client BEFORE the server: on Python 3.12 the server's
            # exit waits for open connections, and httpx keeps them alive.
            await adapter.aclose()

    assert cat["output"] == "ok"
    assert retried["output"] == "ok"
    assert seen == ["search", "cat", "search"]
