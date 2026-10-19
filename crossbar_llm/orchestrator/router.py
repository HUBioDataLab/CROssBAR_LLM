"""Build deterministic agent plans and rewrite conversational follow-ups."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)

from crossbar_llm.agent_tools.logging_config import get_logger
from crossbar_llm.orchestrator.llm import ainvoke_structured
from crossbar_llm.orchestrator.prompts import (
    REWRITER_HUMAN_TEMPLATE,
    REWRITER_JSON_INSTRUCTION,
    REWRITER_SYSTEM_TEMPLATE,
)
from crossbar_llm.orchestrator.registry import AgentId
from crossbar_llm.orchestrator.schemas import QuestionRewriteOutput

logger = get_logger(__name__)

REWRITER_NODE_NAME = "orchestrator.rewriter"


@dataclass(frozen=True)
class ConversationTurn:
    question: str
    answer: str


@dataclass(frozen=True)
class AgentPlan:
    selected: tuple[AgentId, ...]
    rationale: str
    standalone_question: str
    strategy: Literal["user_selected"] = "user_selected"
    reasons: dict[AgentId, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _format_history(history: Sequence[ConversationTurn]) -> str:
    return "\n".join(
        f"User: {turn.question}\nAssistant: {turn.answer}" for turn in history
    )


def _prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(REWRITER_SYSTEM_TEMPLATE),
            HumanMessagePromptTemplate.from_template(REWRITER_HUMAN_TEMPLATE),
        ]
    )


async def rewrite_question(
    *,
    chat_model: BaseChatModel,
    question: str,
    history: Sequence[ConversationTurn],
) -> tuple[str, tuple[str, ...]]:
    """Rewrite a follow-up as a standalone question.

    Failure is non-fatal: literature agents receive the original question and
    the warning is exposed in orchestration metadata.
    """
    if not history:
        return question, ()

    try:
        output = await ainvoke_structured(
            chat_model=chat_model,
            prompt=_prompt(),
            schema=QuestionRewriteOutput,
            values={"history": _format_history(history), "question": question},
            json_instruction=REWRITER_JSON_INSTRUCTION,
            node_name=REWRITER_NODE_NAME,
        )
        standalone = output.standalone_question.strip()
        if not standalone:
            raise ValueError("question rewrite returned an empty question")
    except Exception as error:
        logger.error(
            "Question rewriting failed; using the original question",
            event_type="question_rewrite_failed",
            component="orchestrator.rewrite_question",
            error_type=type(error).__name__,
            error=str(error),
            exc_info=error,
        )
        return question, (
            "Question rewriting failed, so literature agents received the original question.",
        )

    logger.info(
        "Rewrote follow-up question",
        event_type="question_rewritten",
        component="orchestrator.rewrite_question",
    )
    return standalone, ()


__all__ = [
    "REWRITER_NODE_NAME",
    "AgentPlan",
    "ConversationTurn",
    "rewrite_question",
]
