"""Structured outputs the orchestrator's own LLM calls must return."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AgentRoute(BaseModel):
    agent: str = Field(description="Id of a selected agent, exactly as listed.")
    reason: str = Field(description="One sentence on what this agent contributes.")


class RoutingOutput(BaseModel):
    standalone_question: str = Field(
        description=(
            "The question rewritten to be understandable without the "
            "conversation history; the original question verbatim if it "
            "already stands alone."
        )
    )
    agents: list[AgentRoute] = Field(
        description="The agents that should work on the question."
    )
    rationale: str = Field(description="One or two sentences explaining the plan.")


class ContradictionOutput(BaseModel):
    topic: str = Field(description="What the agents disagree about.")
    agents: list[str] = Field(
        description="Source tags of the agents involved, e.g. ['KG', 'Paperclip']."
    )
    resolution: str = Field(
        description="How the conflict was resolved, or why it could not be."
    )


class SynthesisOutput(BaseModel):
    answer: str = Field(description="The final Markdown answer for the user.")
    contradictions: list[ContradictionOutput] = Field(
        default_factory=list,
        description="Every conflict found between the reports. Empty if none.",
    )


__all__ = [
    "AgentRoute",
    "ContradictionOutput",
    "RoutingOutput",
    "SynthesisOutput",
]
