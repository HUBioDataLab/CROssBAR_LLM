"""Orchestration for the optional Paperclip and PubTator3 agents."""

from __future__ import annotations

import asyncio
from typing import Any
from collections.abc import Awaitable, Callable, Iterable

from crossbar_llm.agent_tools.callback_handler import UsageMetricsCallback, usage_slice
from crossbar_llm.agent_tools.config import ReasoningConfig
from crossbar_llm.agent_tools.logging_config import get_logger
from crossbar_llm.api.core.settings import Settings
from crossbar_llm.api.schemas.requests import ModelConfigRequest
from crossbar_llm.api.schemas.responses import AgentRunResult
from crossbar_llm.paperclip_tools.adapter import PaperclipAdapter, PaperclipConfigError
from crossbar_llm.paperclip_tools.agent import build_graph as build_paperclip_graph
from crossbar_llm.paperclip_tools.llm import build_chat_model as build_paperclip_model
from crossbar_llm.pubtator3_tools.agent import build_graph as build_pubtator3_graph
from crossbar_llm.pubtator3_tools.llm import build_chat_model as build_pubtator3_model
from crossbar_llm.pubtator3_tools.rate_limit import install_static_share_limiter

logger = get_logger(__name__)


class _AdmissionRejected(Exception):
    """This process had no capacity to start the tool within the wait window."""

    def __init__(self, tool: str):
        super().__init__(f"{tool} was not admitted")
        self.tool = tool

class LiteratureService:
    """Run enabled literature agents concurrently on the FastAPI event loop."""

    def __init__(self, settings: Settings):
        self.settings = settings
        # Keep the adapter long-lived once used, but do not construct it for
        # requests that leave Paperclip disabled.
        self.paperclip_adapter: PaperclipAdapter | None = None
        # Admission control, one semaphore per tool. The tools are bottlenecked
        # by different things (Paperclip by its connection pool and server-side
        # limit, PubTator3 by NCBI's IP-wide rate), so one shared pool only let
        # each tool's users take capacity from the other's. Created lazily
        # because a Semaphore binds to the running loop.
        self._admission: dict[str, asyncio.Semaphore] = {}
        # Divide PubTator3's IP-wide budget across replicas. Configured once at
        # construction rather than per request: the limiter is process-global
        # state inside the client.
        install_static_share_limiter(settings.pubtator3_replica_count)

    def _admission_limit(self, name: str) -> int | None:
        return getattr(self.settings, f"{name}_max_concurrent_runs", None)

    def _admission_slot(self, name: str) -> asyncio.Semaphore | None:
        """The tool's semaphore, or None when that tool has no local limit."""
        limit = self._admission_limit(name)
        if limit is None:
            return None
        slot = self._admission.get(name)
        if slot is None:
            slot = self._admission[name] = asyncio.Semaphore(limit)
        return slot

    async def _run_admitted(
        self,
        name: str,
        runner: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Run one tool, but only once this process has capacity for it.

        Two phases, strictly in sequence: queue for a slot (at most
        `literature_admission_wait_seconds`), then run (at most
        `literature_tool_timeout_seconds`). The run's timeout starts only once
        a slot is granted, so queueing never shortens a run's budget — a longer
        wait trades response time for more requests served, and nothing else.
        """
        slot = self._admission_slot(name)
        if slot is not None:
            try:
                await asyncio.wait_for(
                    slot.acquire(),
                    timeout=self.settings.literature_admission_wait_seconds,
                )
            except asyncio.TimeoutError:
                raise _AdmissionRejected(name) from None
        try:
            return await asyncio.wait_for(
                runner(), timeout=self.settings.literature_tool_timeout_seconds
            )
        finally:
            if slot is not None:
                slot.release()

    def _get_paperclip_adapter(self) -> PaperclipAdapter:
        # No await between the check and the assignment, so concurrent requests
        # on the event loop cannot race into building two adapters here.
        if self.paperclip_adapter is None:
            env_settings = getattr(self.settings, "env_settings", None)
            configured_key = getattr(env_settings, "paperclip_api_key", None)
            self.paperclip_adapter = PaperclipAdapter(
                # Passed in rather than exported to `os.environ`: settings come
                # from a .env that pydantic-settings reads privately, and a
                # service has no business mutating process-global state to
                # smuggle them into a library.
                api_key=(
                    configured_key.get_secret_value() if configured_key else None
                ),
                disable_rest=getattr(env_settings, "paperclip_disable_rest", None),
                max_connections=self.settings.paperclip_max_connections,
                pool_timeout_s=self.settings.paperclip_pool_timeout_seconds,
            )
        return self.paperclip_adapter

    async def aclose(self) -> None:
        if self.paperclip_adapter is not None:
            await self.paperclip_adapter.aclose()
            self.paperclip_adapter = None

    @staticmethod
    def _model_kwargs(
        payload: ModelConfigRequest,
        callback: UsageMetricsCallback,
    ) -> dict[str, Any]:
        return {
            "model": payload.model,
            "provider": payload.provider,
            "callbacks": [callback],
            "reasoning": ReasoningConfig(
                enabled=payload.reasoning_enabled,
                effort=payload.reasoning_effort,
            ),
        }

    @staticmethod
    def _tool_usage(
        summary: dict[str, Any],
        prefix: str,
    ) -> dict[str, Any]:
        """Slice one tool's share out of the shared request-level usage summary.

        Depends on every literature LLM call tagging `node_name` with the
        tool's prefix; `test_literature_service.py` pins that contract, because
        a renamed node would otherwise empty this out in silence.

        Note the returned figures are also part of the response's top-level
        `usage` — this is a breakdown of that total, not an addition to it.
        """
        return usage_slice(summary, lambda node: node.startswith(prefix))

    def _paperclip_citations(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        citations = state.get("citations") or []
        return [
            citation.model_dump(mode="json")
            if hasattr(citation, "model_dump")
            else dict(citation)
            for citation in citations[: self.settings.literature_max_citations]
        ]

    def _pubtator_citations(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        seen_pmids: set[str] = set()
        for document in state.get("documents") or []:
            if len(citations) >= self.settings.literature_max_citations:
                break
            pmid = getattr(document, "pmid", None)
            if pmid is None:
                continue
            pmid = str(pmid)
            if pmid in seen_pmids:
                continue
            seen_pmids.add(pmid)
            citations.append(
                {
                    "pmid": pmid,
                    "title": getattr(document, "title", ""),
                    "pmcid": getattr(document, "pmcid", None),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                }
            )
        return citations

    async def _run_paperclip(
        self,
        *,
        question: str,
        payload: ModelConfigRequest,
        callback: UsageMetricsCallback,
    ) -> dict[str, Any]:
        model = build_paperclip_model(**self._model_kwargs(payload, callback))
        graph = build_paperclip_graph(
            chat_model=model,
            adapter=self._get_paperclip_adapter(),
            max_documents=self.settings.paperclip_max_documents,
            abstracts_only=self.settings.paperclip_abstracts_only,
            use_map=self.settings.paperclip_use_map,
        )
        return await graph.ainvoke({"question": question, "warnings": []})

    async def _run_pubtator3(
        self,
        *,
        question: str,
        payload: ModelConfigRequest,
        callback: UsageMetricsCallback,
    ) -> dict[str, Any]:
        model = build_pubtator3_model(**self._model_kwargs(payload, callback))
        graph = build_pubtator3_graph(
            chat_model=model,
            max_documents=self.settings.pubtator3_max_documents,
            abstracts_only=self.settings.pubtator3_abstracts_only,
        )
        return await graph.ainvoke({"question": question, "warnings": []})

    @staticmethod
    def _failure_warning(name: str, error: BaseException) -> str:
        """User-facing text for a failed tool.

        A missing key is the one case where the upstream message is both safe
        and genuinely actionable, so it is passed through. Everything else is
        reported by type only — upstream error strings can carry URLs with
        credentials in the query, and this text goes straight into an HTTP
        response. The full exception is logged.
        """
        if isinstance(error, PaperclipConfigError):
            return f"{name} is not configured: {error}"
        return (
            f"{name} failed with {type(error).__name__}. "
            "See the server logs for details."
        )

    def _failed(
        self,
        name: str,
        warning: str,
        summary: dict[str, Any],
        usage_prefix: str,
    ) -> AgentRunResult:
        return AgentRunResult(
            status="failed",
            warnings=[warning],
            # Tokens spent before the failure were still spent — report them.
            usage=self._tool_usage(summary, usage_prefix),
        )

    def _runner(
        self,
        name: str,
        *,
        question: str,
        payload: ModelConfigRequest,
        callback: UsageMetricsCallback,
    ) -> Callable[[], Awaitable[dict[str, Any]]]:
        if name == "paperclip":
            return lambda: self._run_paperclip(
                question=question, payload=payload, callback=callback
            )
        if name == "pubtator3":
            return lambda: self._run_pubtator3(
                question=question, payload=payload, callback=callback
            )
        raise ValueError(f"Unknown literature tool: {name!r}")

    async def run(
        self,
        *,
        question: str,
        tools: Iterable[str],
        payload: ModelConfigRequest,
        callback: UsageMetricsCallback,
    ) -> dict[str, AgentRunResult]:
        """Run several tools concurrently; one tool's failure never hides another's."""
        selected = list(dict.fromkeys(tools))
        if not selected:
            return {}
        results = await asyncio.gather(
            *(
                self.run_tool(
                    name, question=question, payload=payload, callback=callback
                )
                for name in selected
            )
        )
        return dict(zip(selected, results))

    async def run_tool(
        self,
        name: str,
        *,
        question: str,
        payload: ModelConfigRequest,
        callback: UsageMetricsCallback,
    ) -> AgentRunResult:
        """Run one tool and report how it went.

        Every failure of the tool becomes a `failed` or `skipped` result, so the
        caller can run tools side by side without one taking the others down.
        Only cancellation propagates: that is the caller stopping the work.
        """
        runner = self._runner(name, question=question, payload=payload, callback=callback)
        usage_prefix = f"{name}."

        if not question or not question.strip():
            # The caller asked for this tool but has no question to run it on.
            # Say so rather than returning nothing, which reads as "never asked".
            return AgentRunResult(
                status="skipped",
                warnings=[
                    f"{name} was skipped: no question was available for this request."
                ],
            )

        try:
            raw = await self._run_admitted(name, runner)
        except _AdmissionRejected:
            # Not a failure of the tool — this server was saturated. Says so
            # plainly so the operator sees capacity, not flakiness.
            limit = self._admission_limit(name)
            logger.warning(
                "Literature tool not admitted",
                event_type="literature_tool_not_admitted",
                component="LiteratureService.run_tool",
                tool=name,
                max_concurrent=limit,
                waited_seconds=self.settings.literature_admission_wait_seconds,
            )
            return AgentRunResult(
                status="skipped",
                warnings=[
                    f"{name} was skipped: the server is at its capacity of "
                    f"{limit} concurrent {name} runs. Try again shortly."
                ],
            )
        except asyncio.TimeoutError:
            return self._failed(
                name,
                f"{name} timed out after "
                f"{self.settings.literature_tool_timeout_seconds:g} seconds.",
                callback.get_summary(),
                usage_prefix,
            )
        except Exception as error:
            logger.error(
                "Literature tool failed",
                event_type="literature_tool_failed",
                component="LiteratureService.run_tool",
                tool=name,
                error_type=type(error).__name__,
                error=str(error),
                exc_info=error,
            )
            return self._failed(
                name,
                self._failure_warning(name, error),
                callback.get_summary(),
                usage_prefix,
            )
        return self._normalize(name, raw, callback.get_summary(), usage_prefix)

    def _normalize(
        self,
        name: str,
        raw: Any,
        summary: dict[str, Any],
        usage_prefix: str,
    ) -> AgentRunResult:
        if not isinstance(raw, dict):
            logger.error(
                "Literature tool returned an unexpected result type",
                event_type="literature_tool_bad_result",
                component="LiteratureService._normalize",
                tool=name,
                result_type=type(raw).__name__,
            )
            return self._failed(
                name,
                f"{name} returned an unexpected result type "
                f"({type(raw).__name__}).",
                summary,
                usage_prefix,
            )

        try:
            citations = (
                self._paperclip_citations(raw)
                if name == "paperclip"
                else self._pubtator_citations(raw)
            )
            return AgentRunResult(
                status="completed",
                answer=raw.get("final_answer"),
                citations=citations,
                warnings=list(raw.get("warnings") or []),
                usage=self._tool_usage(summary, usage_prefix),
            )
        except Exception as error:
            logger.error(
                "Literature tool result normalization failed",
                event_type="literature_tool_normalization_failed",
                component="LiteratureService._normalize",
                tool=name,
                error_type=type(error).__name__,
                error=str(error),
                exc_info=error,
            )
            return self._failed(
                name,
                f"{name} returned a result this server could not read "
                f"({type(error).__name__}).",
                summary,
                usage_prefix,
            )
