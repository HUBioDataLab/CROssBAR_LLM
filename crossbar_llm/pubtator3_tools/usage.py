"""Token-usage capture / logging helpers for the PubTator3 graph.

Both helpers wrap a graph invocation in `get_usage_metadata_callback`,
which aggregates `usage_metadata` from every chat-model call made under
the context — router, synthesizer, depth evaluator, JSON fallbacks.
Use `ainvoke_with_usage_logging` for fire-and-forget log lines and
`ainvoke_with_usage_capture` when the caller needs the totals
programmatically (benchmark runner, etc.).
"""
from __future__ import annotations

import logging

from langchain_core.callbacks import get_usage_metadata_callback


_usage_logger = logging.getLogger("crossbar_llm.pubtator3.usage")


def _flatten_usage(usage_metadata: dict) -> dict:
    """Collapse {model: {input,output,total,...}} into one totals dict.

    Sums across models so a single run that touches router + synthesizer +
    evaluator (possibly different model versions for each) reports one
    consolidated number per field. Pulls out provider sub-buckets we care
    about (reasoning, cache_read) when present.
    """
    flat = {
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cache_read_tokens": 0,
        "total_tokens": 0,
        "by_model": {},
    }
    for model, usage in usage_metadata.items():
        in_details = usage.get("input_token_details") or {}
        out_details = usage.get("output_token_details") or {}
        flat["input_tokens"] += usage.get("input_tokens") or 0
        flat["output_tokens"] += usage.get("output_tokens") or 0
        flat["total_tokens"] += usage.get("total_tokens") or 0
        flat["reasoning_tokens"] += out_details.get("reasoning") or 0
        flat["cache_read_tokens"] += in_details.get("cache_read") or 0
        flat["by_model"][model] = dict(usage)
    return flat


async def ainvoke_with_usage_capture(graph, state: dict, **kwargs) -> tuple[dict, dict]:
    """Like `ainvoke_with_usage_logging` but returns the usage instead of logging.

    Returns `(state, usage)` where `usage` is the flat-totals dict produced by
    `_flatten_usage` — handy for benchmarks that need to record tokens per
    question alongside the answer.
    """
    with get_usage_metadata_callback() as cb:
        result = await graph.ainvoke(state, **kwargs)
    return result, _flatten_usage(cb.usage_metadata)


async def ainvoke_with_usage_logging(graph, state: dict, **kwargs) -> dict:
    """Invoke `graph` and log aggregated LLM token usage for the run.

    Totals are logged per model name at INFO level on
    `crossbar_llm.pubtator3.usage`.
    """
    with get_usage_metadata_callback() as cb:
        result = await graph.ainvoke(state, **kwargs)
    for model, usage in cb.usage_metadata.items():
        in_details = usage.get("input_token_details") or {}
        out_details = usage.get("output_token_details") or {}
        reasoning = out_details.get("reasoning")
        cache_read = in_details.get("cache_read")
        _usage_logger.info(
            "pubtator3 llm usage model=%s input=%s output=%s reasoning=%s "
            "cache_read=%s total=%s",
            model,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            reasoning,
            cache_read,
            usage.get("total_tokens"),
        )
    return result


__all__ = [
    "_flatten_usage",
    "ainvoke_with_usage_capture",
    "ainvoke_with_usage_logging",
]
