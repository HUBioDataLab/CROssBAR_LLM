from pydantic import BaseModel, Field
from typing import Literal, Any

from crossbar_llm.api.schemas.common import SearchMode
from crossbar_llm.orchestrator.registry import AgentId, AgentKind


class SessionCreateResponse(BaseModel):
    session_id: str


class AgentRunResult(BaseModel):
    """What one specialist agent produced for this question."""

    status: Literal["completed", "failed", "skipped"]
    answer: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    duration_seconds: float | None = None


class RoutingDecision(BaseModel):
    selected: list[AgentId] = Field(
        description="Agents the orchestrator asked, in the order it chose them."
    )
    reasons: dict[AgentId, str] = Field(
        default_factory=dict,
        description="Why each selected agent was asked, when the router said.",
    )
    skipped: dict[AgentId, str] = Field(
        default_factory=dict,
        description="Agents that were not asked, and why.",
    )
    rationale: str = ""
    standalone_question: str | None = None
    strategy: Literal["llm", "single_agent", "fallback"]


class Contradiction(BaseModel):
    topic: str
    agents: list[AgentId] = Field(default_factory=list)
    resolution: str


class OrchestrationResult(BaseModel):
    routing: RoutingDecision
    agents: dict[AgentId, AgentRunResult] = Field(default_factory=dict)
    contradictions: list[Contradiction] = Field(default_factory=list)
    synthesized: bool = Field(
        default=False,
        description=(
            "True when the final answer merges more than one agent's report; "
            "false when it is a single agent's answer passed through."
        ),
    )
    answer_sources: list[AgentId] = Field(
        default_factory=list,
        description="Agents whose reports the final answer is built from.",
    )
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, Any] = Field(
        default_factory=dict,
        description="The orchestrator's own LLM calls (relevance, routing, synthesis).",
    )


class ChatResponse(BaseModel):
    session_id: str
    status: Literal["completed", "failed", "awaiting_human_review"]

    question: str
    mode: SearchMode

    generated_cypher: str | None = None
    execution_result: list[Any] | None = None
    final_answer: str | None = None
    follow_up_questions: list[str] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    orchestration: OrchestrationResult | None = None

class PendingResumeResponse(BaseModel):
    # Declared, not just passed: the service has always handed a `status` to
    # this model, but without a field for it pydantic dropped it silently, so
    # the one response that most needs to say what it is said nothing.
    status: Literal["awaiting_human_review"] = "awaiting_human_review"
    session_id: str
    question: str
    mode: SearchMode
    generated_cypher: str | None = None
    # The plan the approval will carry out: which other agents run once the
    # Cypher is approved. `agents` is empty because none has run yet.
    orchestration: OrchestrationResult | None = None


class AgentInfo(BaseModel):
    id: AgentId
    name: str
    kind: AgentKind
    summary: str
    available: bool
    unavailable_reason: str | None = None
    supports_vector_search: bool


class AgentCatalogResponse(BaseModel):
    agents: list[AgentInfo]


class ProviderModels(BaseModel):
    models: list[str]
    free_models: list[str] = Field(default_factory=list)


class ModelsResponse(BaseModel):
    """Available LLM providers and models, keyed by runtime provider name.

    `default_provider` / `default_model` give a sensible seed for clients that
    have no preference (prefers a free model when one exists).
    """
    providers: dict[str, ProviderModels]
    default_provider: str
    default_model: str
    supported_models_for_search: list[str] = Field(default_factory=list)
