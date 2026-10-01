"""Model construction and structured calls for the orchestrator.

The structured call mirrors the literature packages: provider structured output
first, then a plain-JSON retry validated against the same schema, because some
providers answer in prose instead of making the schema tool call. Kept local
rather than imported from a tool package, following the project's rule that
packages do not reach into each other's internals.
"""
from __future__ import annotations

import json
from typing import Any, TypeVar

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from pydantic import BaseModel

from crossbar_llm.agent_tools.config import LLMConfig, ReasoningConfig
from crossbar_llm.agent_tools.llm_factory import LLMFactory

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def build_chat_model(
    *,
    model: str,
    provider: str | None = None,
    callbacks: list[BaseCallbackHandler] | None = None,
    reasoning: ReasoningConfig | None = None,
) -> BaseChatModel:
    """The user's model at temperature 0: routing and synthesis want stable output."""
    config = LLMConfig(
        model=model,
        provider=provider,
        temperature=0.0,
        callbacks=callbacks or [],
        reasoning=reasoning or ReasoningConfig(),
    )
    return LLMFactory(config).get_base_model()


def _content_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            item if isinstance(item, str) else str(item.get("text", ""))
            for item in content
            if isinstance(item, (str, dict))
        )
    return str(content)


def extract_json_object(text: str) -> dict[str, Any]:
    """The first JSON object in `text`, tolerating code fences and preamble."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("model response did not contain a JSON object")


async def ainvoke_structured(
    *,
    chat_model: BaseChatModel,
    prompt: ChatPromptTemplate,
    schema: type[StructuredModel],
    values: dict[str, Any],
    json_instruction: str,
    node_name: str,
) -> StructuredModel:
    config = {"metadata": {"node_name": node_name}}
    try:
        parsed = await (prompt | chat_model.with_structured_output(schema)).ainvoke(
            values, config=config
        )
        if parsed is not None:
            return parsed if isinstance(parsed, schema) else schema.model_validate(parsed)
        structured_error: Exception = ValueError("structured output returned None")
    except Exception as error:
        structured_error = error

    json_prompt = prompt + HumanMessagePromptTemplate.from_template(json_instruction)
    try:
        message = await (json_prompt | chat_model).ainvoke(values, config=config)
        return schema.model_validate(extract_json_object(_content_text(message)))
    except Exception as json_error:
        raise ValueError(
            "structured output failed and the JSON fallback failed: "
            f"{structured_error}; {json_error}"
        ) from json_error


__all__ = ["ainvoke_structured", "build_chat_model", "extract_json_object"]
