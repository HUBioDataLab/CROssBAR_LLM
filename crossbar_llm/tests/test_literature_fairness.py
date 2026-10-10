"""Per-user fairness for the literature tools.

Two things must hold. The user a request belongs to has to reach the tool runs,
which start in tasks the endpoint spawns, and, in streamed responses, only after
the endpoint has returned. And the per-user share has to cap one user without
slowing anyone else, inside the single admission wait budget.

The share is tested at `LiteratureService._run_admitted`, where it lives, rather
than through `run()` and the request's tool switches: how tools are selected and
results shaped differs between branches, while the admission path is the same.
Request handling is tested on small apps carrying the same dependency, plus one
check that the real app applies it to every route.
"""
import asyncio

import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from crossbar_llm.api.core.browser_identity import _sign_browser_id
from crossbar_llm.api.core.rate_limit import limiter
from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.main import app
from crossbar_llm.api.services import literature_fairness
from crossbar_llm.api.services.literature_fairness import (
    PerUserLimiter,
    UserShareExhausted,
    bind_literature_user,
    literature_user,
)
from crossbar_llm.api.services.literature_service import (
    LiteratureService,
    _AdmissionRejected,
)

COOKIE = Settings().browser_cookie_name


# --- the user reaches the runs ------------------------------------------------


def _mini_app() -> FastAPI:
    """A small app wired the way `main.py` wires the real one."""
    mini = FastAPI(dependencies=[Depends(bind_literature_user)])

    async def _read():
        await asyncio.sleep(0)
        return literature_user.get()

    @mini.get("/who")
    async def who():
        return {"user": literature_user.get()}

    @mini.get("/spawned")
    async def spawned():
        # The service runs each tool in a task of its own.
        return {"user": await asyncio.create_task(_read())}

    @mini.get("/stream")
    async def stream():
        async def body():
            yield (await asyncio.create_task(_read())).encode()
        return StreamingResponse(body())

    return mini


def test_the_real_app_runs_the_hook_on_its_routes(monkeypatch):
    """Checked by behaviour, not by inspecting route objects: how FastAPI
    represents included routers changes between versions."""
    calls = []

    def record(request):
        calls.append(request.url.path)
        return "ip:test"

    monkeypatch.setattr(literature_fairness, "_request_user", record)
    was_enabled = limiter.enabled
    limiter.enabled = False
    try:
        with TestClient(app) as c:
            for path in ("/health", "/models"):
                c.get(path)
    finally:
        limiter.enabled = was_enabled

    assert calls == ["/health", "/models"]


def test_the_cookie_user_reaches_a_task_the_endpoint_spawns():
    with TestClient(_mini_app()) as c:
        c.cookies.set(COOKIE, _sign_browser_id("browser-123"))
        assert c.get("/spawned").json()["user"] == "browser:browser-123"


def test_the_user_reaches_a_streamed_response():
    """A streamed response runs its body after the endpoint has returned, in a
    task of its own. The user must still be visible there."""
    with TestClient(_mini_app()) as c:
        c.cookies.set(COOKIE, _sign_browser_id("browser-9"))
        assert c.get("/stream").text == "browser:browser-9"


def test_requests_without_a_cookie_fall_back_to_the_hashed_ip():
    with TestClient(_mini_app()) as c:
        user = c.get("/who").json()["user"]

    assert user.startswith("ip:")
    assert "testclient" not in user  # hashed, never the raw address


def test_each_request_gets_its_own_user():
    with TestClient(_mini_app()) as c:
        c.cookies.set(COOKIE, _sign_browser_id("first"))
        first = c.get("/who").json()["user"]
        c.cookies.set(COOKIE, _sign_browser_id("second"))
        second = c.get("/who").json()["user"]

    assert (first, second) == ("browser:first", "browser:second")


def test_a_bad_cookie_never_breaks_an_unrelated_route():
    """The hook runs on every route, including ones that ignore identity."""
    was_enabled = limiter.enabled
    limiter.enabled = False
    try:
        with TestClient(app) as c:
            c.cookies.set(COOKIE, "not-a-signed-value")
            assert c.get("/health").status_code == 200
    finally:
        limiter.enabled = was_enabled


# --- the share ------------------------------------------------------------------


def _service(**overrides) -> LiteratureService:
    settings = Settings(literature_tool_timeout_seconds=5.0)
    for key, value in overrides.items():
        setattr(settings, key, value)
    return LiteratureService(settings)


def _blocking_runner(release: asyncio.Event, started: list):
    async def runner():
        started.append(literature_user.get())
        await release.wait()
        return {"final_answer": "answer"}
    return runner


async def _as_user(user, service, tool, runner):
    """Admit and run as `user`, in a task of its own like a real request."""
    literature_user.set(user)
    return await service._run_admitted(tool, runner)


@pytest.mark.asyncio
async def test_one_user_is_capped_while_another_is_served():
    service = _service(paperclip_max_runs_per_user=3, literature_admission_wait_seconds=0.2)
    release, started = asyncio.Event(), []
    runner = _blocking_runner(release, started)

    hogs = [asyncio.create_task(_as_user("browser:A", service, "paperclip", runner))
            for _ in range(3)]
    await asyncio.sleep(0.05)

    # A's fourth is over their share and is turned away, with a reason that
    # tells them so. Bounded, so a broken cap fails here instead of hanging.
    with pytest.raises(_AdmissionRejected) as rejected:
        await asyncio.wait_for(_as_user("browser:A", service, "paperclip", runner), 2.0)
    assert "you already have 3 paperclip requests in progress" in rejected.value.warning

    # B, a different user, starts at once despite A's three.
    other = asyncio.create_task(_as_user("browser:B", service, "paperclip", runner))
    await asyncio.sleep(0.05)
    assert started.count("browser:B") == 1

    release.set()
    await asyncio.gather(*hogs, other)


@pytest.mark.asyncio
async def test_a_queued_run_starts_when_its_users_share_frees():
    service = _service(pubtator3_max_runs_per_user=1, literature_admission_wait_seconds=2.0)
    release, started = asyncio.Event(), []
    runner = _blocking_runner(release, started)

    first = asyncio.create_task(_as_user("browser:A", service, "pubtator3", runner))
    await asyncio.sleep(0.05)
    second = asyncio.create_task(_as_user("browser:A", service, "pubtator3", runner))
    await asyncio.sleep(0.05)
    assert len(started) == 1  # the second waits in A's own queue

    release.set()
    await asyncio.gather(first, second)
    assert len(started) == 2


@pytest.mark.asyncio
async def test_a_server_at_capacity_is_reported_as_such_not_as_the_users_share():
    """Only an exhausted personal share gets the personal message."""
    service = _service(
        pubtator3_max_runs_per_user=3, pubtator3_max_concurrent_runs=1,
        literature_admission_wait_seconds=0.1,
    )
    release, started = asyncio.Event(), []
    runner = _blocking_runner(release, started)

    hog = asyncio.create_task(_as_user("browser:A", service, "pubtator3", runner))
    await asyncio.sleep(0.05)
    with pytest.raises(_AdmissionRejected) as rejected:
        await _as_user("browser:B", service, "pubtator3", runner)
    assert rejected.value.warning is None  # falls back to the capacity message

    release.set()
    await hog


@pytest.mark.asyncio
async def test_both_queues_share_one_wait_budget():
    """Waiting for the user's share and then for the tool's capacity must not
    add up to more than `literature_admission_wait_seconds`."""
    service = _service(
        pubtator3_max_runs_per_user=1, pubtator3_max_concurrent_runs=1,
        literature_admission_wait_seconds=0.4,
    )
    a_release, b_release = asyncio.Event(), asyncio.Event()

    async def runner():
        await (a_release if literature_user.get() == "browser:A" else b_release).wait()
        return {"final_answer": "answer"}

    a_first = asyncio.create_task(_as_user("browser:A", service, "pubtator3", runner))
    await asyncio.sleep(0.02)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    a_second = asyncio.create_task(_as_user("browser:A", service, "pubtator3", runner))
    await asyncio.sleep(0.2)
    # A's first run ends: A's share frees, but B takes the tool's only slot.
    b_run = asyncio.create_task(_as_user("browser:B", service, "pubtator3", runner))
    await asyncio.sleep(0)
    a_release.set()

    with pytest.raises(_AdmissionRejected):
        await a_second
    assert loop.time() - t0 < 0.55  # one 0.4 s budget, not 0.4 s per queue

    b_release.set()
    await asyncio.gather(a_first, b_run)


@pytest.mark.asyncio
async def test_runs_without_a_user_are_not_capped():
    """Benchmarks and scripts calling the service directly have no user."""
    service = _service(paperclip_max_runs_per_user=1)
    release, started = asyncio.Event(), []
    runner = _blocking_runner(release, started)

    runs = [asyncio.create_task(service._run_admitted("paperclip", runner))
            for _ in range(4)]
    await asyncio.sleep(0.05)
    assert len(started) == 4

    release.set()
    await asyncio.gather(*runs)


@pytest.mark.asyncio
async def test_a_disabled_share_is_not_applied():
    service = _service(paperclip_max_runs_per_user=None)
    release, started = asyncio.Event(), []
    runner = _blocking_runner(release, started)

    runs = [asyncio.create_task(_as_user("browser:A", service, "paperclip", runner))
            for _ in range(5)]
    await asyncio.sleep(0.05)
    assert len(started) == 5

    release.set()
    await asyncio.gather(*runs)


@pytest.mark.asyncio
async def test_idle_users_are_forgotten():
    """One entry per browser that ever visited would grow without bound."""
    limiter_ = PerUserLimiter()
    for user in ("a", "b", "c"):
        async with limiter_.hold("paperclip", user, limit=2, timeout=1.0):
            assert limiter_.active_users() >= 1
    assert limiter_.active_users() == 0

    # Including after a rejection.
    async with limiter_.hold("paperclip", "a", limit=1, timeout=1.0):
        with pytest.raises(UserShareExhausted):
            async with limiter_.hold("paperclip", "a", limit=1, timeout=0.01):
                pass
    assert limiter_.active_users() == 0


@pytest.mark.asyncio
async def test_a_cancelled_waiter_releases_nothing_it_never_held():
    """A request abandoned while queued must not free a slot it never got."""
    limiter_ = PerUserLimiter()
    holding, release = asyncio.Event(), asyncio.Event()

    async def holder():
        async with limiter_.hold("paperclip", "a", limit=1, timeout=1.0):
            holding.set()
            await release.wait()

    async def waiter():
        async with limiter_.hold("paperclip", "a", limit=1, timeout=5.0):
            pass

    h = asyncio.create_task(holder())
    await holding.wait()
    w = asyncio.create_task(waiter())
    await asyncio.sleep(0.02)
    w.cancel()
    with pytest.raises(asyncio.CancelledError):
        await w

    # The holder still has the only slot: a third caller must still wait.
    with pytest.raises(UserShareExhausted):
        async with limiter_.hold("paperclip", "a", limit=1, timeout=0.05):
            pass

    release.set()
    await h
    assert limiter_.active_users() == 0
