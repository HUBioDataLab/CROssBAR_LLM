from pydantic import BaseModel, Field
from typing import Literal, Any

from crossbar_llm.api.schemas.common import SearchMode


class SessionCreateResponse(BaseModel):
    session_id: str

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

class PendingResumeResponse(BaseModel):
    session_id: str
    question: str
    mode: SearchMode
    generated_cypher: str | None = None
