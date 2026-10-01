import asyncio
import os
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from crossbar_llm.agent_tools.callback_handler import UsageMetricsCallback
from crossbar_llm.api.schemas.requests import DbSearchRequest, LiteratureToolsConfig
from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.services.literature_service import LiteratureService
from crossbar_llm.paperclip_tools.adapter import PaperclipConfigError


def _settings(timeout: float = 1.0) -> Settings:
    # The real Settings object, not a stub: these tests exercise code that
    # reads a growing set of tuning fields, and a hand-rolled namespace would
    # drift out of sync with it silently.
    return Settings(literature_tool_timeout_seconds=timeout)


def _payload(tools: LiteratureToolsConfig) -> DbSearchRequest:
    return DbSearchRequest(
        provider="openai",
        model="gpt-4o-mini",
        question="What is the role of EGFR in cancer?",
        execution_mode="generate_and_run",
        literature_tools=tools,
    )


@pytest.mark.asyncio
async def test_disabled_tools_are_not_run(monkeypatch):
    service = LiteratureService(_settings())

    async def unexpected(*args, **kwargs):
        raise AssertionError("disabled literature tool was invoked")

    monkeypatch.setattr(service, "_run_paperclip", unexpected)
    monkeypatch.setattr(service, "_run_pubtator3", unexpected)

    result = await service.run(
        question="test",
        payload=_payload(LiteratureToolsConfig()),
        callback=UsageMetricsCallback("session", strict=False),
    )

    assert result == {}


@pytest.mark.asyncio
async def test_enabled_tools_run_in_parallel(monkeypatch):
    service = LiteratureService(_settings())
    started = {"paperclip": asyncio.Event(), "pubtator3": asyncio.Event()}
    release = asyncio.Event()

    async def paperclip(*args, **kwargs):
        started["paperclip"].set()
        await release.wait()
        return {"final_answer": "Paperclip answer", "citations": [], "warnings": []}

    async def pubtator3(*args, **kwargs):
        started["pubtator3"].set()
        await release.wait()
        return {"final_answer": "PubTator3 answer", "documents": [], "warnings": []}

    monkeypatch.setattr(service, "_run_paperclip", paperclip)
    monkeypatch.setattr(service, "_run_pubtator3", pubtator3)

    task = asyncio.create_task(
        service.run(
            question="test",
            payload=_payload(LiteratureToolsConfig(paperclip=True, pubtator3=True)),
            callback=UsageMetricsCallback("session", strict=False),
        )
    )
    await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values())), 1)
    release.set()
    result = await task

    assert list(result) == ["paperclip", "pubtator3"]
    assert result["paperclip"].answer == "Paperclip answer"
    assert result["pubtator3"].answer == "PubTator3 answer"


@pytest.mark.asyncio
async def test_one_tool_failure_does_not_discard_the_other(monkeypatch):
    service = LiteratureService(_settings())

    async def paperclip(*args, **kwargs):
        raise RuntimeError("Paperclip unavailable")

    async def pubtator3(*args, **kwargs):
        return {"final_answer": "PubTator3 answer", "documents": [], "warnings": []}

    monkeypatch.setattr(service, "_run_paperclip", paperclip)
    monkeypatch.setattr(service, "_run_pubtator3", pubtator3)

    result = await service.run(
        question="test",
        payload=_payload(LiteratureToolsConfig(paperclip=True, pubtator3=True)),
        callback=UsageMetricsCallback("session", strict=False),
    )

    assert result["paperclip"].status == "failed"
    assert result["pubtator3"].status == "completed"


@pytest.mark.asyncio
async def test_tool_timeout_is_reported_per_tool(monkeypatch):
    service = LiteratureService(_settings(timeout=0.01))

    async def slow(*args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(service, "_run_paperclip", slow)

    result = await service.run(
        question="test",
        payload=_payload(LiteratureToolsConfig(paperclip=True)),
        callback=UsageMetricsCallback("session", strict=False),
    )

    assert result["paperclip"].status == "failed"
    assert "timed out" in result["paperclip"].warnings[0]


@pytest.mark.asyncio
async def test_malformed_tool_result_is_isolated(monkeypatch):
    service = LiteratureService(_settings())

    async def malformed(*args, **kwargs):
        return None

    async def valid(*args, **kwargs):
        return {"final_answer": "PubTator3 answer", "documents": [], "warnings": []}

    monkeypatch.setattr(service, "_run_paperclip", malformed)
    monkeypatch.setattr(service, "_run_pubtator3", valid)

    result = await service.run(
        question="test",
        payload=_payload(LiteratureToolsConfig(paperclip=True, pubtator3=True)),
        callback=UsageMetricsCallback("session", strict=False),
    )

    assert result["paperclip"].status == "failed"
    assert result["pubtator3"].status == "completed"


@pytest.mark.asyncio
async def test_paperclip_adapter_is_lazy_reused_and_closed(monkeypatch):
    created = []

    class Adapter:
        def __init__(self, **kwargs):
            self.close_count = 0
            self.kwargs = kwargs
            created.append(self)

        async def aclose(self):
            self.close_count += 1

    monkeypatch.setattr(
        "crossbar_llm.api.services.literature_service.PaperclipAdapter",
        Adapter,
    )
    settings = _settings()
    settings.env_settings = SimpleNamespace(
        paperclip_api_key=SecretStr("paperclip-test-key"),
        paperclip_disable_rest=True,
    )
    monkeypatch.delenv("PAPERCLIP_API_KEY", raising=False)
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)
    service = LiteratureService(settings)

    assert service.paperclip_adapter is None
    assert service._get_paperclip_adapter() is service._get_paperclip_adapter()
    assert len(created) == 1

    # Credentials are handed to the adapter directly. Exporting them to
    # os.environ instead would be a process-global side effect from a request
    # path, and would leak between tests and between tenants.
    assert created[0].kwargs["api_key"] == "paperclip-test-key"
    assert created[0].kwargs["disable_rest"] is True
    assert "PAPERCLIP_API_KEY" not in os.environ
    assert "PAPERCLIP_DISABLE_REST" not in os.environ

    await service.aclose()
    assert created[0].close_count == 1
    assert service.paperclip_adapter is None


@pytest.mark.asyncio
async def test_missing_paperclip_credentials_fail_only_that_tool(monkeypatch):
    """An unconfigured tool degrades to its own failure, not a 500."""
    service = LiteratureService(_settings())

    async def unconfigured(*args, **kwargs):
        raise PaperclipConfigError("PAPERCLIP_API_KEY is not set")

    async def pubtator3(*args, **kwargs):
        return {"final_answer": "PubTator3 answer", "documents": [], "warnings": []}

    monkeypatch.setattr(service, "_run_paperclip", unconfigured)
    monkeypatch.setattr(service, "_run_pubtator3", pubtator3)

    result = await service.run(
        question="test",
        payload=_payload(LiteratureToolsConfig(paperclip=True, pubtator3=True)),
        callback=UsageMetricsCallback("session", strict=False),
    )

    assert result["paperclip"].status == "failed"
    # A missing key is safe and actionable, so it is surfaced verbatim.
    assert "PAPERCLIP_API_KEY is not set" in result["paperclip"].warnings[0]
    assert result["pubtator3"].status == "completed"


@pytest.mark.asyncio
async def test_unexpected_failures_do_not_leak_upstream_detail(monkeypatch):
    """Arbitrary upstream error text must not reach the HTTP response."""
    service = LiteratureService(_settings())

    async def boom(*args, **kwargs):
        raise RuntimeError("https://paperclip.example/x?token=SUPERSECRET failed")

    monkeypatch.setattr(service, "_run_paperclip", boom)

    result = await service.run(
        question="test",
        payload=_payload(LiteratureToolsConfig(paperclip=True)),
        callback=UsageMetricsCallback("session", strict=False),
    )

    warning = result["paperclip"].warnings[0]
    assert "SUPERSECRET" not in warning
    assert "RuntimeError" in warning


@pytest.mark.asyncio
async def test_enabled_tool_without_a_question_is_reported_as_skipped(monkeypatch):
    """Resuming with no checkpointed question must say so, not stay silent."""
    service = LiteratureService(_settings())

    async def unexpected(*args, **kwargs):
        raise AssertionError("literature tool ran without a question")

    monkeypatch.setattr(service, "_run_paperclip", unexpected)

    result = await service.run(
        question="   ",
        payload=_payload(LiteratureToolsConfig(paperclip=True)),
        callback=UsageMetricsCallback("session", strict=False),
    )

    assert result["paperclip"].status == "skipped"
    assert "no question" in result["paperclip"].warnings[0]


def test_tool_usage_slices_by_node_name_prefix():
    """Pins the contract `_tool_usage` depends on.

    Per-tool usage is recovered by matching the `node_name` prefix each agent
    tags its LLM calls with. Renaming a node without updating the prefix would
    otherwise empty this out with no test failing.
    """
    service = LiteratureService(_settings())
    summary = {
        "per_node_usage": {
            "paperclip.router": {"total_tokens": 10, "call_count": 1},
            "paperclip.synthesize": {"total_tokens": 30, "call_count": 2},
            "pubtator3.router": {"total_tokens": 7, "call_count": 1},
        },
        "aggregated_usage": {
            "models_by_node": {"paperclip.router": ["gpt-4o-mini"]},
        },
    }

    paperclip = service._tool_usage(summary, "paperclip.")

    assert set(paperclip["per_node_usage"]) == {
        "paperclip.router",
        "paperclip.synthesize",
    }
    assert paperclip["aggregated_usage"]["totals"]["total_tokens"] == 40
    assert paperclip["call_count"] == 3
    # `totals` keeps exactly the core agent's shape, so the two are comparable.
    assert "call_count" not in paperclip["aggregated_usage"]["totals"]
    assert service._tool_usage(summary, "nothing.") == {}


@pytest.mark.asyncio
async def test_admission_limit_bounds_concurrent_runs_of_that_tool(monkeypatch):
    """A tool's limit caps how many of ITS runs are in flight at once."""
    settings = _settings()
    settings.pubtator3_max_concurrent_runs = 1
    service = LiteratureService(settings)

    in_flight = 0
    peak = 0
    release = asyncio.Event()

    async def tool(*args, **kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            await release.wait()
            return {"final_answer": "answer", "documents": [], "warnings": []}
        finally:
            in_flight -= 1

    monkeypatch.setattr(service, "_run_pubtator3", tool)

    tasks = [
        asyncio.create_task(
            service.run(
                question="test",
                payload=_payload(LiteratureToolsConfig(pubtator3=True)),
                callback=UsageMetricsCallback("session", strict=False),
            )
        )
        for _ in range(3)
    ]
    await asyncio.sleep(0.05)
    assert peak == 1, "several runs started despite a limit of 1"
    release.set()
    await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_tools_do_not_share_admission_capacity(monkeypatch):
    """A saturated PubTator3 must not turn Paperclip users away.

    With one shared pool, each tool's users took capacity from the other's even
    though the two are bottlenecked by entirely different things.
    """
    settings = _settings()
    settings.pubtator3_max_concurrent_runs = 1
    settings.paperclip_max_concurrent_runs = 1
    settings.literature_admission_wait_seconds = 0.01
    service = LiteratureService(settings)

    release = asyncio.Event()

    async def blocker(*args, **kwargs):
        await release.wait()
        return {"final_answer": "answer", "documents": [], "warnings": []}

    async def paperclip(*args, **kwargs):
        return {"final_answer": "answer", "citations": [], "warnings": []}

    monkeypatch.setattr(service, "_run_pubtator3", blocker)
    monkeypatch.setattr(service, "_run_paperclip", paperclip)

    hog = asyncio.create_task(
        service.run(
            question="test",
            payload=_payload(LiteratureToolsConfig(pubtator3=True)),
            callback=UsageMetricsCallback("session", strict=False),
        )
    )
    await asyncio.sleep(0.05)

    result = await service.run(
        question="test",
        payload=_payload(LiteratureToolsConfig(paperclip=True, pubtator3=True)),
        callback=UsageMetricsCallback("session", strict=False),
    )

    assert result["paperclip"].status == "completed"
    assert result["pubtator3"].status == "skipped"
    assert "pubtator3" in result["pubtator3"].warnings[0]
    release.set()
    await hog


@pytest.mark.asyncio
async def test_unlimited_tool_admits_every_run(monkeypatch):
    """`None` means no local limit — every run starts immediately."""
    settings = _settings()
    settings.paperclip_max_concurrent_runs = None
    settings.literature_admission_wait_seconds = 0.01
    service = LiteratureService(settings)

    started = 0
    release = asyncio.Event()

    async def tool(*args, **kwargs):
        nonlocal started
        started += 1
        await release.wait()
        return {"final_answer": "answer", "citations": [], "warnings": []}

    monkeypatch.setattr(service, "_run_paperclip", tool)

    tasks = [
        asyncio.create_task(
            service.run(
                question="test",
                payload=_payload(LiteratureToolsConfig(paperclip=True)),
                callback=UsageMetricsCallback("session", strict=False),
            )
        )
        for _ in range(25)
    ]
    await asyncio.sleep(0.05)
    assert started == 25
    release.set()
    results = await asyncio.gather(*tasks)
    assert all(r["paperclip"].status == "completed" for r in results)


@pytest.mark.asyncio
async def test_admission_wait_does_not_shorten_the_run_budget(monkeypatch):
    """Queueing for a slot must not be charged against the run's timeout.

    The run timeout starts only once a slot is granted. Here a run queues for
    longer than the entire run timeout and must still complete, because its
    own clock hasn't started yet while it waits.
    """
    settings = _settings(timeout=0.3)
    settings.pubtator3_max_concurrent_runs = 1
    settings.literature_admission_wait_seconds = 2.0
    service = LiteratureService(settings)

    async def tool(*args, **kwargs):
        await asyncio.sleep(0.25)  # just inside the 0.3s run budget
        return {"final_answer": "answer", "documents": [], "warnings": []}

    monkeypatch.setattr(service, "_run_pubtator3", tool)

    # Two runs through one slot: the second queues ~0.25s, then runs 0.25s.
    # Its total (~0.5s) exceeds the 0.3s run timeout, so it would fail if
    # queueing were charged against that budget.
    results = await asyncio.gather(
        *(
            service.run(
                question="test",
                payload=_payload(LiteratureToolsConfig(pubtator3=True)),
                callback=UsageMetricsCallback("session", strict=False),
            )
            for _ in range(2)
        )
    )

    assert [r["pubtator3"].status for r in results] == ["completed", "completed"]


@pytest.mark.asyncio
async def test_saturation_reports_skipped_not_timed_out(monkeypatch):
    """A run that never got a slot must not masquerade as a slow upstream."""
    settings = _settings()
    settings.pubtator3_max_concurrent_runs = 1
    settings.literature_admission_wait_seconds = 0.01
    service = LiteratureService(settings)

    release = asyncio.Event()

    async def blocker(*args, **kwargs):
        await release.wait()
        return {"final_answer": "answer", "documents": [], "warnings": []}

    monkeypatch.setattr(service, "_run_pubtator3", blocker)

    hog = asyncio.create_task(
        service.run(
            question="test",
            payload=_payload(LiteratureToolsConfig(pubtator3=True)),
            callback=UsageMetricsCallback("session", strict=False),
        )
    )
    await asyncio.sleep(0.05)

    result = await service.run(
        question="test",
        payload=_payload(LiteratureToolsConfig(pubtator3=True)),
        callback=UsageMetricsCallback("session", strict=False),
    )

    assert result["pubtator3"].status == "skipped"
    assert "capacity" in result["pubtator3"].warnings[0]
    release.set()
    await hog
