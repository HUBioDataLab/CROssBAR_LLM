"""Merge several agents' reports into one answer, resolving their conflicts."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)

from crossbar_llm.orchestrator.llm import ainvoke_structured
from crossbar_llm.orchestrator.prompts import (
    SYNTHESIS_HUMAN_TEMPLATE,
    SYNTHESIS_JSON_INSTRUCTION,
    SYNTHESIS_SYSTEM_TEMPLATE,
)
from crossbar_llm.orchestrator.registry import AGENT_SPECS, AgentId, resolve_agent
from crossbar_llm.orchestrator.schemas import SynthesisOutput

SYNTHESIZER_NODE_NAME = "orchestrator.synthesizer"

# Bounds on what one report may put in the prompt. A knowledge-graph result can
# run to hundreds of rows; the answer agent already summarised them, and the
# rows are only there so the synthesizer can check that summary.
MAX_RECORD_ROWS = 25
MAX_REPORT_CHARS = 8000


@dataclass(frozen=True)
class AgentReport:
    agent: AgentId
    status: str
    answer: str | None
    citations: Sequence[dict[str, Any]] = field(default_factory=tuple)
    records: Sequence[Any] | None = None
    warnings: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class Contradiction:
    topic: str
    agents: tuple[AgentId, ...]
    resolution: str


@dataclass(frozen=True)
class Synthesis:
    answer: str
    contradictions: tuple[Contradiction, ...]


def _citation_line(index: int, citation: dict[str, Any]) -> str:
    label = (
        citation.get("title")
        or citation.get("pmid")
        or citation.get("doc_id")
        or "Publication"
    )
    pmid = f" (PMID {citation['pmid']})" if citation.get("pmid") else ""
    url = f" {citation['url']}" if citation.get("url") else ""
    return f"[{index}] {label}{pmid}{url}"


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]}\n... (truncated)"


def format_report(report: AgentReport) -> str:
    spec = AGENT_SPECS[report.agent]
    parts = [f"### [{spec.tag}] {spec.name} (status: {report.status})"]
    parts.append(f"Answer:\n{report.answer or '(no answer)'}")
    if report.records:
        rows = list(report.records)[:MAX_RECORD_ROWS]
        shown = f"first {len(rows)} of {len(report.records)}"
        parts.append(
            f"Graph records ({shown}):\n{json.dumps(rows, default=str, ensure_ascii=False)}"
        )
    if report.citations:
        parts.append(
            "Sources:\n"
            + "\n".join(
                _citation_line(index, citation)
                for index, citation in enumerate(report.citations, start=1)
            )
        )
    if report.warnings:
        parts.append("Warnings: " + " ".join(report.warnings))
    return _truncate("\n\n".join(parts), MAX_REPORT_CHARS)


def _prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(SYNTHESIS_SYSTEM_TEMPLATE),
            HumanMessagePromptTemplate.from_template(SYNTHESIS_HUMAN_TEMPLATE),
        ]
    )


def _contradictions(output: SynthesisOutput) -> tuple[Contradiction, ...]:
    contradictions = []
    for item in output.contradictions:
        agents = tuple(
            dict.fromkeys(
                agent_id
                for reference in item.agents
                if (agent_id := resolve_agent(reference)) is not None
            )
        )
        contradictions.append(
            Contradiction(
                topic=item.topic.strip(),
                agents=agents,
                resolution=item.resolution.strip(),
            )
        )
    return tuple(contradictions)


async def synthesize_reports(
    *,
    chat_model: BaseChatModel,
    question: str,
    reports: Sequence[AgentReport],
) -> Synthesis:
    """One answer from several reports. Raises if the model call fails."""
    tags = ", ".join(f"[{AGENT_SPECS[report.agent].tag}]" for report in reports)
    output = await ainvoke_structured(
        chat_model=chat_model,
        prompt=_prompt(),
        schema=SynthesisOutput,
        values={
            "tags": tags,
            "reports": "\n\n".join(format_report(report) for report in reports),
            "question": question,
        },
        json_instruction=SYNTHESIS_JSON_INSTRUCTION,
        node_name=SYNTHESIZER_NODE_NAME,
    )
    answer = output.answer.strip()
    if not answer:
        raise ValueError("synthesis returned an empty answer")
    return Synthesis(answer=answer, contradictions=_contradictions(output))


def fallback_answer(reports: Sequence[AgentReport]) -> str:
    """Each report under its own heading, for when synthesis itself fails."""
    return "\n\n".join(
        f"**{AGENT_SPECS[report.agent].name}**\n\n{report.answer}"
        for report in reports
        if report.answer
    )


__all__ = [
    "SYNTHESIZER_NODE_NAME",
    "AgentReport",
    "Contradiction",
    "Synthesis",
    "fallback_answer",
    "format_report",
    "synthesize_reports",
]
