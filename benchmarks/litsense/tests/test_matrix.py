"""The multi-model matrix pieces (ADR-010): the reasoning request, the shared on-disk
response cache, and the cross-run comparison report. No network, no model."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from litsense.report import comparison_data, load_runs, render_comparison, write_comparison
from crossbar_llm.litsense_tools.client import (
    LitSenseClient,
    PublicationNotFound,
    RateLimiter,
    ResponseCache,
)
from crossbar_llm.litsense_tools.config import Settings
from crossbar_llm.litsense_tools.llm import chat_model_kwargs, reasoning_request
from crossbar_llm.litsense_tools.tests.conftest import load_fixture

PMID = 27863244


# --- reasoning request -------------------------------------------------------------------


def test_reasoning_levels_map_to_openrouters_unified_object() -> None:
    assert reasoning_request(None) is None
    assert reasoning_request("none") == {"enabled": False}
    assert reasoning_request("medium") == {"effort": "medium"}


def test_no_reasoning_setting_adds_no_provider_kwargs() -> None:
    assert chat_model_kwargs(Settings(model="openai:openai/gpt-5.4")) == {}


def test_reasoning_travels_as_extra_body_with_require_parameters() -> None:
    settings = Settings(model="openai:openai/gpt-5.4", reasoning_effort="medium")
    assert chat_model_kwargs(settings) == {
        "extra_body": {
            "reasoning": {"effort": "medium"},
            "provider": {"require_parameters": True},
        }
    }


def test_provider_order_pins_upstream_providers_with_fallbacks() -> None:
    settings = Settings(
        model="openai:deepseek/deepseek-v4-pro", reasoning_effort="none",
        provider_order="Alibaba, DeepInfra",
    )
    assert chat_model_kwargs(settings) == {
        "extra_body": {
            "reasoning": {"enabled": False},
            "provider": {
                "order": ["Alibaba", "DeepInfra"],
                "allow_fallbacks": True,
                "require_parameters": True,
            },
        }
    }


def test_reasoning_on_another_provider_is_refused_not_ignored() -> None:
    settings = Settings(model="anthropic:claude-sonnet-4-6", reasoning_effort="low")
    with pytest.raises(ValueError, match="reasoning_effort"):
        chat_model_kwargs(settings)


def test_reasoning_effort_rejects_unknown_levels() -> None:
    with pytest.raises(ValueError):
        Settings(model="openai:x", reasoning_effort="ultra")


# --- on-disk response cache ---------------------------------------------------------------


class Counting:
    """A transport handler that counts requests and serves one canned response."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.count += 1
        return self.response


def client_with(handler: Counting, cache_dir: Path) -> LitSenseClient:
    settings = Settings(
        model="test:model", requests_per_second=10_000.0, http_cache_dir=str(cache_dir)
    )

    async def no_sleep(_: float) -> None:
        return None

    return LitSenseClient(
        settings,
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        sleep=no_sleep,
        limiter=RateLimiter(10_000.0, sleep=no_sleep),
    )


async def test_a_second_process_is_served_from_disk_and_never_reaches_ncbi(
    tmp_path: Path,
) -> None:
    handler = Counting(httpx.Response(200, json=load_fixture("publication_27863244.json")))
    first = client_with(handler, tmp_path)
    publication = await first.fetch_publication(PMID)
    await first.aclose()
    assert handler.count == 1
    assert first.cache is not None and (first.cache.misses, first.cache.hits) == (1, 0)

    second = client_with(handler, tmp_path)  # a fresh client = another process
    again = await second.fetch_publication(PMID)
    await second.aclose()
    assert handler.count == 1, "the cached response must satisfy the second process"
    assert again == publication
    assert second.cache is not None and (second.cache.misses, second.cache.hits) == (0, 1)
    assert not list(tmp_path.glob("*.lock")), "the claim is released after the fetch"


async def test_search_results_are_cached_by_full_url_including_the_query(
    tmp_path: Path,
) -> None:
    fixture = "sentences_what_is_the_role_of_tp53_mutations_in_colorectal_cancer_prog.json"
    handler = Counting(httpx.Response(200, json=load_fixture(fixture)))
    client = client_with(handler, tmp_path)
    await client.search_sentences("TP53")
    await client.search_sentences("TP53")
    await client.search_sentences("BRCA1")
    await client.aclose()
    assert handler.count == 2, "same query hits the cache; a different query does not"


async def test_a_permanent_missing_publication_is_cached_too(tmp_path: Path) -> None:
    handler = Counting(
        httpx.Response(
            500, json={"detail": "Can not retrieve publications : Publication not found"}
        )
    )
    for _ in range(2):
        client = client_with(handler, tmp_path)
        with pytest.raises(PublicationNotFound):
            await client.fetch_publication(1)
        await client.aclose()
    assert handler.count == 1


async def test_a_half_written_cache_file_is_a_miss_not_a_crash(tmp_path: Path) -> None:
    handler = Counting(httpx.Response(200, json=load_fixture("publication_27863244.json")))
    client = client_with(handler, tmp_path)
    assert client.cache is not None
    url = f"{client._client.base_url}publication/{PMID}"  # noqa: SLF001 — cache key check
    client.cache.path(url).write_text('{"url": "', encoding="utf-8")
    await client.fetch_publication(PMID)
    await client.aclose()
    assert handler.count == 1
    assert client.cache.load(url) is not None, "the fetch repaired the broken entry"


async def test_a_waiter_gets_the_response_another_process_stores(tmp_path: Path) -> None:
    """Lock held elsewhere: the client polls instead of fetching, then reads the file."""
    stored = httpx.Response(200, json={"from": "other process"})
    url = "https://example.org/x"
    cache = ResponseCache(tmp_path, lock_timeout_s=60.0)
    assert cache._try_lock(url)  # noqa: SLF001 — simulate the other process's claim

    async def other_process_finishes(_: float) -> None:
        cache.store(url, stored)
        cache.release(url)

    waiting = ResponseCache(tmp_path, lock_timeout_s=60.0, sleep=other_process_finishes)
    response = await waiting.acquire(url)
    assert response is not None and response.json() == {"from": "other process"}
    assert (waiting.hits, waiting.misses) == (1, 0)


async def test_an_abandoned_lock_is_taken_over_after_the_timeout(tmp_path: Path) -> None:
    url = "https://example.org/y"
    cache = ResponseCache(tmp_path, lock_timeout_s=0.0)
    assert cache._try_lock(url)  # noqa: SLF001 — a process that died holding the claim
    fresh = ResponseCache(tmp_path, lock_timeout_s=0.0)
    assert await fresh.acquire(url) is None, "the stale lock was broken and re-taken"
    assert fresh.lock_path(url).exists()


def test_no_cache_dir_means_no_cache() -> None:
    client = LitSenseClient(Settings(model="test:model"))
    assert client.cache is None
    asyncio.run(client.aclose())


# --- cross-run comparison -----------------------------------------------------------------


def _question(hit: bool, judge: int, tokens: int, reasoning: int = 0) -> dict[str, object]:
    return {
        "question": "Q?", "reference_answers": ["x"], "generated_answer": "x",
        "cited_pmids": [], "answer_insufficient_context": not hit, "answer_warnings": [],
        "error": None, "elapsed_s": 5.0,
        "biological_relevance_check": {"is_biomedical_question": True, "reason": ""},
        "full_text_refinement": None,
        "answer_overlap": {"hit": hit, "recall": 1.0 if hit else 0.0,
                           "matched_items": [], "missed_items": []},
        "retrieved_evidence_overlap": {"hit": True, "recall": 1.0,
                                       "matched_items": [], "missed_items": []},
        "llm_judge": {"score": judge, "informativeness": judge, "clarity": 5,
                      "matched_items": [], "missed_items": [], "rationale": ""},
        "agent_tokens": {"input": tokens - 50, "output": 50, "reasoning": reasoning,
                         "cache_read": 0, "total": tokens, "calls": 2},
        "judge_tokens": {"input": 100, "output": 20, "reasoning": 0, "cache_read": 0,
                         "total": 120, "calls": 1},
    }


def _run_folder(
    root: Path, label: str, *, hits: list[bool], reasoning: str | None, pricing: bool,
    stamp: str = "20260922-120000",
) -> Path:
    run_dir = root / f"{stamp}-{label}"
    run_dir.mkdir()
    questions = [_question(h, 5 if h else 0, 1000, 300 if reasoning else 0) for h in hits]
    block = {
        "run_info": {"model": f"openai:{label}"},
        "grounding_modes": ["abstracts_only"],
        "results_by_grounding_mode": {"abstracts_only": {"per_question": questions}},
    }
    (run_dir / "bioasq-factoid-100.json").write_text(
        json.dumps({"bioasq-factoid-100": block}), encoding="utf-8"
    )
    (run_dir / "manifest.json").write_text(json.dumps({
        "label": label, "model": f"openai:{label}", "reasoning_effort": reasoning,
        "judge_model": "openai:judge", "grounding_modes": ["abstracts_only"],
        "started": "2026-09-22T12:00:00", "finished": "2026-09-22T13:00:00",
        "files": ["bioasq-factoid-100.json"],
    }), encoding="utf-8")
    if pricing:
        (run_dir / "pricing.json").write_text(json.dumps({
            "model": {"prompt": "0.000001", "completion": "0.000002"},
            "judge": {"prompt": "0.0000001", "completion": "0.0000002"},
        }), encoding="utf-8")
    return run_dir


def test_comparison_puts_one_row_per_run_with_cost_and_reasoning_tokens(tmp_path: Path) -> None:
    a = _run_folder(tmp_path, "model-a", hits=[True, True, False], reasoning=None, pricing=True)
    b = _run_folder(tmp_path, "model-b", hits=[True, False, False], reasoning="medium",
                    pricing=False)
    runs = load_runs([a, b])
    data = comparison_data(runs)

    cells = data["cells_by_dataset_mode_run"]["bioasq-factoid-100"]["abstracts_only"]
    assert cells["model-a"]["hit_rate"] == pytest.approx(0.667, abs=1e-3)
    assert cells["model-b"]["hit_rate"] == pytest.approx(0.333, abs=1e-3)
    assert cells["model-a"]["mean_reasoning_tokens"] == 0
    assert cells["model-b"]["mean_reasoning_tokens"] == 300
    # 3 questions × (950 in × 1e-6 + 50 out × 2e-6) = 0.00315 USD
    assert cells["model-a"]["cost_usd"] == pytest.approx(0.00315)
    assert cells["model-a"]["judge_cost_usd"] == pytest.approx(3 * (100e-7 + 20 * 2e-7))
    assert cells["model-b"]["cost_usd"] is None, "no pricing.json → no cost, not a guess"

    summary = {r["label"]: r for r in data["runs"]}
    assert summary["model-b"]["reasoning_effort"] == "medium"
    assert summary["model-a"]["cost_usd"] == pytest.approx(0.00315)

    report = render_comparison(runs)
    assert "| model-a |" in report and "| model-b (reasoning=medium) |" in report
    assert "### hit rate" in report and "### reasoning tokens / Q" in report
    assert "### bioasq-factoid-100 — abstracts_only" in report
    assert "$0.00" in report  # cost column rendered for the priced run


def test_two_runs_with_the_same_label_are_told_apart_by_folder(tmp_path: Path) -> None:
    a = _run_folder(tmp_path, "same", hits=[True], reasoning=None, pricing=False,
                    stamp="20260901-100000")
    b = _run_folder(tmp_path, "same", hits=[False], reasoning=None, pricing=False,
                    stamp="20260922-100000")
    runs = load_runs([a, b])
    assert {r["label"] for r in runs} == {a.name, b.name}
    cells = comparison_data(runs)["cells_by_dataset_mode_run"]
    cells = cells["bioasq-factoid-100"]["abstracts_only"]
    assert cells[a.name]["hit_rate"] == 1.0 and cells[b.name]["hit_rate"] == 0.0


def test_write_comparison_emits_markdown_and_json(tmp_path: Path) -> None:
    # pricing.json sits next to the dataset files and must not be read as one (the
    # 2026-09-22 waiter crashed on exactly this).
    a = _run_folder(tmp_path, "only", hits=[True], reasoning=None, pricing=True)
    out = write_comparison([a], tmp_path / "COMPARISON.md", json_out=tmp_path / "c.json")
    assert out.read_text(encoding="utf-8").startswith("# LitSense agent — multi-model comparison")
    payload = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    assert payload["datasets"] == ["bioasq-factoid-100"]
    assert payload["grounding_modes"] == ["abstracts_only"]
