from pydantic import BaseModel, Field
from typing import Literal, Any

from crossbar_llm.api.schemas.common import SearchMode


class SessionCreateResponse(BaseModel):
    session_id: str


class LiteratureToolResult(BaseModel):
    status: Literal["completed", "failed", "skipped"]
    answer: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)


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
    literature: dict[str, LiteratureToolResult] | None = None

class PendingResumeResponse(BaseModel):
    # Declared, not just passed: the service has always handed a `status` to
    # this model, but without a field for it pydantic dropped it silently, so
    # the one response that most needs to say what it is said nothing.
    status: Literal["awaiting_human_review"] = "awaiting_human_review"
    session_id: str
    question: str
    mode: SearchMode
    generated_cypher: str | None = None


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
