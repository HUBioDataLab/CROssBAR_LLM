"""Chat model construction, via the project's shared LLM factory.

The agent graph takes an already-built `chat_model` rather than building one
itself: that keeps the graph independent of how the model is configured, and
is the seam the tests inject fakes at. This helper is the convenience path for
callers who just want the project's configured model.
"""
from __future__ import annotations

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel

from crossbar_llm.agent_tools.config import LLMConfig, ReasoningConfig
from crossbar_llm.agent_tools.llm_factory import LLMFactory


def build_chat_model(
    *,
    model: str,
    provider: str | None = None,
    temperature: float = 0.0,
    callbacks: list[BaseCallbackHandler] | None = None,
    reasoning: ReasoningConfig | None = None,
) -> BaseChatModel:
    """Build a chat model for this agent.

    `provider` may be omitted — the factory infers it from the model name.
    Temperature defaults to 0.0 because routing and synthesis both want
    reproducible output, where the factory's own default is 1.0.
    """
    config = LLMConfig(
        model=model,
        provider=provider,
        temperature=temperature,
        callbacks=callbacks or [],
        reasoning=reasoning or ReasoningConfig(),
    )
    return LLMFactory(config).get_base_model()


__all__ = ["build_chat_model"]
