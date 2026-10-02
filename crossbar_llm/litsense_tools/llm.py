"""Provider-agnostic chat model factory.

Build order step 4. The only module in the package allowed to import LangChain's model
machinery; the provider is a config string, not an import (ADR-004).

The rest of the package sees a `Synthesizer`: an async callable from messages to a validated
`SynthesisOutput`. Tests substitute a plain async function; nothing downstream can tell.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from crossbar_llm.litsense_tools.config import Settings
from crossbar_llm.litsense_tools.models import DepthVerdict, RelevanceVerdict, SynthesisOutput, TokenUsage
from crossbar_llm.litsense_tools.prompts import Message


def load_provider_env() -> None:
    """Make `.env`-declared provider credentials visible to the provider SDK.

    Provider credentials are the SDK's concern, not `Settings`' (ADR-004) — but SDKs read
    the *process environment*, and pydantic-settings only lifts `LITSENSE_`-prefixed
    variables out of `.env`. This bridges the gap right before a model is built: existing
    environment variables always win, and a missing `.env` is a no-op. (python-dotenv is
    already a pydantic-settings dependency — no new requirement.)
    """
    load_dotenv()


Synthesizer = Callable[[Sequence[Message]], Awaitable[SynthesisOutput]]


def reasoning_request(effort: str | None) -> dict[str, Any] | None:
    """`Settings.reasoning_effort` → OpenRouter's unified ``reasoning`` object (ADR-010).

    None: send nothing, the provider's default applies. ``"none"``: switch reasoning off
    explicitly (``{"enabled": false}`` — the documented universal off switch; some models
    reason by default). Any other level: ``{"effort": level}``.
    """
    if effort is None:
        return None
    if effort == "none":
        return {"enabled": False}
    return {"effort": effort}


def chat_model_kwargs(settings: Settings) -> dict[str, Any]:
    """Provider keyword arguments derived from `Settings`, beyond the model string.

    The only provider-specific knowledge in the package (ADR-004 keeps it in this module):
    the reasoning request travels as ``extra_body`` on the OpenAI-compatible provider,
    which is how OpenRouter is reached. Asking for a reasoning level on any other provider
    is refused rather than silently ignored — a "reasoning" run that did not reason would
    poison a comparison.
    """
    extra_body: dict[str, Any] = {}
    reasoning = reasoning_request(settings.reasoning_effort)
    if reasoning is not None:
        extra_body["reasoning"] = reasoning
    if settings.provider_order:
        extra_body["provider"] = {
            "order": [p.strip() for p in settings.provider_order.split(",") if p.strip()],
            "allow_fallbacks": True,
        }
    if not extra_body:
        return {}
    provider = settings.model.split(":", 1)[0] if ":" in settings.model else ""
    if provider != "openai":
        raise ValueError(
            "reasoning_effort / provider_order are wired for the OpenAI-compatible provider "
            f"only (OpenRouter); model {settings.model!r} uses provider {provider or 'default'!r}"
        )
    # Only route to upstream providers that support everything in the request (the
    # reasoning object, the JSON-schema response format): a provider that would silently
    # ignore one of them is worse than an error.
    extra_body.setdefault("provider", {})["require_parameters"] = True
    return {"extra_body": extra_body}


def structured_output_kwargs(settings: Settings) -> dict[str, Any]:
    """`with_structured_output` keyword arguments from `Settings` (none = LangChain default)."""
    if settings.structured_output_method is None:
        return {}
    return {"method": settings.structured_output_method}


def build_chat_model(settings: Settings) -> Any:  # noqa: ANN401 — LangChain's BaseChatModel
    """The configured chat model, with credentials loaded and the reasoning request applied.

    `settings.model` is a provider-qualified string ('anthropic:claude-sonnet-4-6'); the
    provider package is resolved and imported by LangChain at this point, not before.
    """
    load_provider_env()
    return init_chat_model(settings.model, **chat_model_kwargs(settings))


class UsageCollector(AsyncCallbackHandler):
    """Sums the token usage of every chat-model call made under one runnable config.

    The agent attaches a fresh collector to each `run()` as a LangChain callback; LangGraph
    propagates it to the model calls inside the nodes, so usage is captured **without
    touching the seams** — a `Synthesizer` built by `build_synthesizer` reports it, a fake
    one in tests simply reports nothing. Reads the provider-normalized `usage_metadata`
    only (LangChain's own `UsageMetadataCallbackHandler` additionally requires a model name
    in the response metadata and silently drops usage without one).
    """

    def __init__(self) -> None:
        super().__init__()
        self.usage = TokenUsage()

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:  # noqa: ANN401
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                if isinstance(generation, ChatGeneration) and isinstance(message, AIMessage):
                    call = TokenUsage.from_usage_metadata(message.usage_metadata)
                    call.calls = 1  # a call happened even if the provider reported nothing
                    self.usage = self.usage + call


#: The relevance gate's seam (ADR-008): same shape as `Synthesizer`, different output model.
#: The team's own LLM plugs in behind this exactly the way it will behind `Synthesizer`.
RelevanceChecker = Callable[[Sequence[Message]], Awaitable[RelevanceVerdict]]

#: The depth evaluator's seam (ADR-009): same shape again. Judges whether the synthesized
#: answer has enough scientific depth; an insufficient verdict triggers the one full-text
#: refinement pass.
DepthEvaluator = Callable[[Sequence[Message]], Awaitable[DepthVerdict]]


def build_synthesizer(settings: Settings) -> Synthesizer:
    """A structured-output synthesis callable for the configured model.

    The model's output is re-validated through `SynthesisOutput` so a provider returning
    a bare dict and one returning a model instance look the same to callers.
    """
    structured = build_chat_model(settings).with_structured_output(
        SynthesisOutput, **structured_output_kwargs(settings)
    )

    async def synthesize(messages: Sequence[Message]) -> SynthesisOutput:
        output = await structured.ainvoke(list(messages))
        return SynthesisOutput.model_validate(output)

    return synthesize


def build_relevance_checker(settings: Settings) -> RelevanceChecker:
    """A structured-output relevance-gate callable for the configured model (ADR-008)."""
    structured = build_chat_model(settings).with_structured_output(
        RelevanceVerdict, **structured_output_kwargs(settings)
    )

    async def check(messages: Sequence[Message]) -> RelevanceVerdict:
        output = await structured.ainvoke(list(messages))
        return RelevanceVerdict.model_validate(output)

    return check


def build_depth_evaluator(settings: Settings) -> DepthEvaluator:
    """A structured-output depth-evaluator callable for the configured model (ADR-009)."""
    structured = build_chat_model(settings).with_structured_output(
        DepthVerdict, **structured_output_kwargs(settings)
    )

    async def evaluate(messages: Sequence[Message]) -> DepthVerdict:
        output = await structured.ainvoke(list(messages))
        return DepthVerdict.model_validate(output)

    return evaluate


#: What the dry-run synthesizer answers in place of a model.
DRY_RUN_TEXT = (
    "[dry run] No model is connected. The messages above are exactly what a connected model "
    "would have received."
)


def build_dry_run_synthesizer() -> Synthesizer:
    """A `Synthesizer` that consults no model at all.

    The synthesis role is ultimately going to the project team's own LLM; until that module
    is approved and wired in, this stub keeps the connection point open and lets the rest of
    the pipeline run end to end. Whatever the team ships needs to satisfy the same one-line
    contract: async, messages in, `SynthesisOutput` out.
    """

    async def synthesize(messages: Sequence[Message]) -> SynthesisOutput:
        return SynthesisOutput(text=DRY_RUN_TEXT)

    return synthesize


def build_dry_run_relevance_checker() -> RelevanceChecker:
    """A `RelevanceChecker` that consults no model and lets every question through.

    The dry-run counterpart of `build_dry_run_synthesizer`: with it, the gated pipeline
    still runs retrieval end to end without a model or an API key.
    """

    async def check(messages: Sequence[Message]) -> RelevanceVerdict:
        return RelevanceVerdict(relevant=True, reason="dry run: no model consulted")

    return check


def build_dry_run_depth_evaluator() -> DepthEvaluator:
    """A `DepthEvaluator` that consults no model and always accepts the first answer.

    The dry-run counterpart for ADR-009 — with it, the refinement loop never fires and the
    graph stays effectively linear, which is also what benchmarks want when measuring the
    first-pass answer (the reference harness's `_always_sufficient_evaluator`).
    """

    async def evaluate(messages: Sequence[Message]) -> DepthVerdict:
        return DepthVerdict(sufficient=True, missing="")

    return evaluate
