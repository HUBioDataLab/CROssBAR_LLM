"""Structured-output helpers shared by this agent's LLM-bound nodes.

Some providers return None instead of making the schema tool call when the
model answers in prose, so every structured call falls back to plain JSON and
validates locally against the same Pydantic schema.

Deliberately duplicated in each tool package rather than imported across them:
the two agents are developed independently and neither should break when the
other changes.
"""
from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from pydantic import BaseModel

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def _message_content_to_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _answer_text(message: Any) -> str:
    """The user-facing text of a model reply, and nothing else.

    Unlike `_message_content_to_text`, which keeps every block so a JSON payload
    can be recovered from it, this drops reasoning/thinking blocks: they are the
    model's private working, not part of the answer. Providers that return a
    list of content blocks (Anthropic with reasoning, some Gemini setups) would
    otherwise put that working, or a Python repr of the blocks, in front of the
    user.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif (
            isinstance(item, dict)
            and item.get("type", "text") == "text"
            and isinstance(item.get("text"), str)
        ):
            parts.append(item["text"])
    return "".join(parts)


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    decoder = json.JSONDecoder()
    for idx, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(stripped[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("model response did not contain a JSON object")


async def _ainvoke_structured_with_json_fallback(
    *,
    chat_model: BaseChatModel,
    prompt: ChatPromptTemplate,
    schema: type[StructuredModel],
    values: dict[str, Any],
    json_instruction: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[StructuredModel, bool]:
    """Use provider structured output first, then retry as plain JSON.

    Some providers expose weak tool-calling semantics: LangChain can return
    None when the model answers in prose instead of making the schema tool
    call. The JSON retry keeps those providers useful while still validating
    locally with the exact same Pydantic schema.
    """
    structured_error: Exception | None = None
    try:
        chain = prompt | chat_model.with_structured_output(schema)
        if metadata:
            parsed = await chain.ainvoke(values, config={"metadata": metadata})
        else:
            parsed = await chain.ainvoke(values)
        if parsed is not None:
            if isinstance(parsed, schema):
                return parsed, False
            return schema.model_validate(parsed), False
        structured_error = ValueError(
            "structured-output returned None (schema-coercion failed)"
        )
    except Exception as e:
        structured_error = e

    json_prompt = prompt + HumanMessagePromptTemplate.from_template(json_instruction)
    try:
        chain = json_prompt | chat_model
        if metadata:
            msg = await chain.ainvoke(values, config={"metadata": metadata})
        else:
            msg = await chain.ainvoke(values)
        data = _extract_json_object(_message_content_to_text(msg))
        return schema.model_validate(data), True
    except Exception as json_error:
        raise ValueError(
            "structured-output failed and JSON fallback failed: "
            f"{structured_error}; {json_error}"
        ) from json_error


def _salvage_answer_field(text: str) -> str | None:
    """The `answer` string from a JSON reply too broken to parse whole."""
    match = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    if match is None:
        return None
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return None


async def _ainvoke_structured_or_prose(
    *,
    chat_model: BaseChatModel,
    prompt: ChatPromptTemplate,
    schema: type[StructuredModel],
    values: dict[str, Any],
    json_instruction: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[StructuredModel | None, str | None, bool]:
    """Structured output for a call whose main payload is prose, e.g. an answer.

    Same two attempts as `_ainvoke_structured_with_json_fallback`, but when the
    JSON retry comes back as plain prose, that prose is still a usable answer,
    so it is returned instead of failing the run. Returns
    `(parsed, None, used_json_fallback)` or `(None, prose, True)`. Only a failed
    model call raises.
    """
    config = {"metadata": metadata} if metadata else None
    try:
        parsed = await (prompt | chat_model.with_structured_output(schema)).ainvoke(
            values, config=config
        )
        if parsed is not None:
            if not isinstance(parsed, schema):
                parsed = schema.model_validate(parsed)
            return parsed, None, False
    except Exception:
        pass

    json_prompt = prompt + HumanMessagePromptTemplate.from_template(json_instruction)
    msg = await (json_prompt | chat_model).ainvoke(values, config=config)
    try:
        data = _extract_json_object(_message_content_to_text(msg))
        return schema.model_validate(data), None, True
    except Exception:
        prose = _answer_text(msg)
        if prose.lstrip().startswith(("{", "```")):
            prose = _salvage_answer_field(prose) or prose
        return None, prose, True


__all__ = [
    "_ainvoke_structured_or_prose",
    "_ainvoke_structured_with_json_fallback",
    "_answer_text",
    "_extract_json_object",
    "_message_content_to_text",
]
