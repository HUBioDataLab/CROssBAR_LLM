from typing_extensions import Self
from typing import Literal
from pydantic import BaseModel, Field, model_validator, field_validator

from fastapi import Form

from crossbar_llm.agent_tools.config import VectorMappings
from crossbar_llm.api.schemas.common import ExecutionControl, SearchMode


class ModelConfigRequest(BaseModel):
    provider: str
    model: str
    top_k: int = Field(default=10, ge=1, le=100)
    reasoning_enabled: bool = Field(default=False)
    reasoning_effort: Literal["low", "medium", "high"] = None

    @model_validator(mode="after")
    def validate_reasoning(self) -> Self:
        if self.reasoning_enabled and self.reasoning_effort is None:
            raise ValueError("Reasoning effort must be set when reasoning is enabled")
        return self


class ChatRequestBase(ModelConfigRequest):
    question: str = Field(..., min_length=4, max_length=4000)
    execution_mode: ExecutionControl

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Question cannot be empty or whitespace")
        return value
    

class DbSearchRequest(ChatRequestBase):
    search_mode: Literal[SearchMode.DB_SEARCH] = SearchMode.DB_SEARCH
    execution_mode: Literal[ExecutionControl.GENERATE_AND_RUN, ExecutionControl.GENERATE] = ExecutionControl.GENERATE_AND_RUN

class VectorSearchRequest(ChatRequestBase):
    search_mode: Literal[SearchMode.VECTOR_SEARCH] = SearchMode.VECTOR_SEARCH
    execution_mode: Literal[ExecutionControl.GENERATE_AND_RUN, ExecutionControl.GENERATE] = ExecutionControl.GENERATE_AND_RUN
    vector_category: str
    embedding_type: str

    @property
    def vector_index(self) -> str:
        print(f"Getting vector index for category: {self.vector_category}, embedding type: {self.embedding_type}")
        return VectorMappings().get_vector_index_name(self.vector_category, self.embedding_type)
    

class UploadVectorSearchRequest(VectorSearchRequest):

    @classmethod
    def as_form(
        cls,
        question: str = Form(...),
        execution_mode: Literal[ExecutionControl.GENERATE_AND_RUN, ExecutionControl.GENERATE] = Form(ExecutionControl.GENERATE_AND_RUN),
        provider: str = Form(...),
        model: str = Form(...),
        top_k: int = Form(10),
        reasoning_enabled: bool = Form(False),
        reasoning_effort: Literal["low", "medium", "high"] | None = Form(None),
        vector_category: str = Form(...),
        embedding_type: str = Form(...),
    ) -> Self:
        return cls(
            question=question,
            execution_mode=execution_mode,
            provider=provider,
            model=model,
            top_k=top_k,
            reasoning_enabled=reasoning_enabled,
            reasoning_effort=reasoning_effort,
            vector_category=vector_category,
            embedding_type=embedding_type,
        )

    


class ResumeRequest(ModelConfigRequest):
    search_mode: SearchMode
    execution_mode: Literal[ExecutionControl.RESUME] = ExecutionControl.RESUME
    action: Literal["approve", "edit"]
    edited_cypher: str

    @field_validator("edited_cypher")
    @classmethod
    def validate_edited_cypher(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Edited Cypher cannot be empty or whitespace")
        return value




