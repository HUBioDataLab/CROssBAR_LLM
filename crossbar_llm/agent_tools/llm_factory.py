from typing import Optional, Sequence, Callable
from pathlib import Path

from langchain.chat_models import init_chat_model, BaseChatModel
from langchain_core.tools import BaseTool 

from .config import APIKeyConfig, LLMConfig, ModelsConfig, AgentConfig

from pydantic import BaseModel, Field, FilePath, field_validator, validate_call

import yaml

from .logging_config import get_logger

logger = get_logger(__name__)


class CypherStrategy(BaseModel):
    """
    In our application, this wil be used for LLMs responsible for generating/correcting Cypher queries based on user questions.
    """
    cypher_query: str = Field(description="Generated Cypher query to be executed against the Neo4j database.")

class OutputParserStrategy(BaseModel):
    """
    In our application, this will be used for LLM responsible for parsing the raw results from Neo4j execution.
    """
    final_answer: str = Field(description="Final answer to be returned to the user after executing the Cypher query and processing the results.")


# FOR ENTITY RESOLUTION
class ResolvedEntity(BaseModel):
    entity_string: str = Field(
        description="Exact entity mention extracted from the user question."
    )

    node_type: str = Field(
        description="Node type of the resolved entity in the graph database."
    )

    resolved_name: Optional[str] = Field(
        default=None,
        description="Canonical entity name returned by the database. None if no candidate was found."
    )

    resolved_name_score: Optional[float] = Field(
        default=None,
        description="Full-text search score of the resolved entity."
    )

    resolved_name_order: Optional[int] = Field(
        default=None,
        description="Rank position of the resolved entity in the search results."
    )

    @field_validator("resolved_name", mode="before")
    @classmethod
    def normalize_resolved_name(cls, value: str) -> str | None:
        if isinstance(value, str) and value.strip().lower() in {"none", "null", ""}:
            return None
        return value


class EntityResolutionStrategy(BaseModel):
    entities: list[ResolvedEntity] = Field(
        default_factory=list,
        description="List of resolved entities extracted from the user question."
    )


class FollowUpQuestionStrategy(BaseModel):
    question_1: str = Field(description="First follow-up question")
    question_2: str = Field(description="Second follow-up question")
    question_3: str = Field(description="Third follow-up question")

    def to_list(self) -> list[str]:
        return list(self.model_dump().values())
    
class BiologicalRelevanceValidatorStrategy(BaseModel):
    relevant: bool = Field(description="Whether the user's question is biologically relevant based on the content of the question.")
    reason: Optional[str] = Field(description="Explanation of why the question is or isn't biologically relevant.")

"""
There are some specific implementations for providers:
https://docs.langchain.com/oss/python/integrations/chat/openrouter

"""

class LLMFactory:
    def __init__(
            self, 
            cfg: LLMConfig,
        ):

        self.cfg = cfg

        self.models_config = ModelsConfig()
        logger.debug("Loaded models configuration", event_type="config_load", component="LLMFactory.__init__")

        if self.cfg.provider is None:
            self.cfg.provider = self.models_config.get_provider_by_model(self.cfg.model)
            logger.debug("Inferred provider from model", event_type="config_inference", component="LLMFactory.__init__", params={"model": self.cfg.model, "inferred_provider": self.cfg.provider})


        self.models_config.validate_provider_model(self.models_config.provider_aliases[self.cfg.provider], self.cfg.model, raise_on_error=True)
        logger.debug("Validated model and provider configuration", event_type="config_validation", component="LLMFactory.__init__", params={"model": self.cfg.model, "provider": self.cfg.provider})
    
    @validate_call(validate_return=True)
    def get_base_model(self, model_override: str = None) -> BaseChatModel:
        provider_override = None
        if model_override:
            provider_override = self.models_config.get_provider_by_model(model_override)
            logger.debug("Overriding model and inferring provider", event_type="config_override", component="LLMFactory.get_base_model", params={"model_override": model_override, "inferred_provider": self.cfg.provider})
            self.models_config.validate_provider_model(self.models_config.provider_aliases[provider_override], model_override, raise_on_error=True)

        kwargs = {
            "model": model_override or self.cfg.model,
            "api_key": APIKeyConfig().get_api_key(
                self.models_config.provider_aliases[provider_override or self.cfg.provider],
                self.models_config.provider_to_api_key_attr
            ).get_secret_value(),
            "timeout": self.cfg.timeout,
            "max_retries": self.cfg.max_retries,
            "temperature": self.cfg.temperature,
            "callbacks": self.cfg.callbacks,
            **self.cfg.extra_kwargs
        }
        
        if provider_override:
            kwargs["model_provider"] = provider_override
        elif self.cfg.provider is not None:
            kwargs["model_provider"] = self.cfg.provider

        kwargs = self._apply_reasoning(kwargs["model_provider"], kwargs)

        logger.info(
            "Initializing base LLM", 
            event_type="llm_init", 
            component="LLMFactory.get_base_model", 
            params={k: v for k, v in kwargs.items() if k != "api_key"}
        ) 
        
        return init_chat_model(**kwargs)
    
    def create_cypher_llm(self) -> BaseChatModel:
        model = self.get_base_model()
        model = model.with_structured_output(CypherStrategy, include_raw=True)

        logger.debug("Created Cypher LLM with structured output", event_type="llm_creation", component="LLMFactory.create_cypher_llm")
        
        return model.with_retry(stop_after_attempt=self.cfg.max_retries)
    
    def create_output_parser_llm(self) -> BaseChatModel:
        model = self.get_base_model()
        model = model.with_structured_output(OutputParserStrategy, include_raw=True)
        
        logger.debug("Created OutputParser LLM with structured output", event_type="llm_creation", component="LLMFactory.create_output_parser_llm")
        
        return model.with_retry(stop_after_attempt=self.cfg.max_retries)
    
    @validate_call
    def create_web_search_llm(self, model_name: str = AgentConfig().web_search_model) -> BaseChatModel:
        if model_name not in self.models_config.supported_models_for_search:
            logger.error("Model not supported for web search", event_type="llm_error", component="LLMFactory.create_web_search_llm", params={"model": model_name, "supported_models": self.models_config.supported_models_for_search})
            raise ValueError(f"Given model '{model_name}' is not supported for web search. Please update the LLMConfig with a supported model.")
        
        model = self.get_base_model(model_override=model_name)
        if self.models_config.get_provider_by_model(model_name) == "openai":
            model_with_search = model.bind_tools(
                tools=[
                    {"type": "web_search"}
                ],
                response_format=CypherStrategy,
                strict=True
            )
            model_with_search = model_with_search.with_structured_output(CypherStrategy, include_raw=True)
                    
        elif self.models_config.get_provider_by_model(model_name) == "google_genai":
            model_with_search = model.bind(
                tools=[
                    {"google_search": {}}
                ],
                response_mime_type="application/json",
                response_schema=CypherStrategy.model_json_schema(),
            )

            model_with_search = model_with_search.with_structured_output(CypherStrategy, include_raw=True)
        
        logger.debug("Created Web Search LLM with structured output", event_type="llm_creation", component="LLMFactory.create_web_search_llm", params={"model": model.model, "provider": self.models_config.get_provider_by_model(model_name)})
        return model_with_search.with_retry(stop_after_attempt=self.cfg.max_retries)
        
    def create_entity_resolution_llm(self) -> BaseChatModel:
        model = self.get_base_model()
        model = model.with_structured_output(EntityResolutionStrategy, method="function_calling")
        
        logger.debug("Created Entity Resolution LLM with structured output", event_type="llm_creation", component="LLMFactory.create_entity_resolution_llm")
        return model.with_retry(stop_after_attempt=self.cfg.max_retries)
    
    @validate_call
    def create_entity_resolution_llm_with_tools(self, tools: Sequence[BaseTool | Callable]) -> BaseChatModel:
        model = self.get_base_model()
        model = model.bind_tools(tools=tools)
        logger.debug(
            "Created Entity Resolution LLM with tools", 
            event_type="llm_creation", 
            component="LLMFactory.create_entity_resolution_llm_with_tools",
            tool_count=len(tools),
            tool_names=[
            getattr(tool, "name", None) or getattr(tool, "__name__", str(tool))
            for tool in tools
            ],
        )
        return model.with_retry(stop_after_attempt=self.cfg.max_retries)
    
    def create_follow_up_question_llm(self) -> BaseChatModel:
        model = self.get_base_model()
        model = model.with_structured_output(FollowUpQuestionStrategy, include_raw=True)
        
        logger.debug("Created Follow Up Question LLM with structured output", event_type="llm_creation", component="LLMFactory.create_follow_up_question_llm")
        return model.with_retry(stop_after_attempt=self.cfg.max_retries)
    
    @validate_call
    def create_biological_relevance_validator_llm(self, model_name: str = AgentConfig().biological_relevance_validation_model) -> BaseChatModel:
        model = self.get_base_model(model_override=model_name)
        model = model.with_structured_output(BiologicalRelevanceValidatorStrategy, include_raw=True)
        
        logger.debug("Created Biological Relevance Validator LLM with structured output", event_type="llm_creation", component="LLMFactory.create_biological_relevance_validator_llm")
        return model.with_retry(stop_after_attempt=self.cfg.max_retries)
    
    @validate_call
    def _apply_reasoning(self, provider: str, kwargs: dict) -> dict:
        reasoning_cfg = self.cfg.reasoning
        if not reasoning_cfg.enabled:
            return kwargs
        
        kwargs = kwargs.copy()  # To avoid mutating the original kwargs

        method_name = f"get_{provider}_reasoning_kwargs"
        provider_fn = getattr(reasoning_cfg, method_name, None)

        if not provider_fn:
            supported_providers = sorted(
                p for p in self.models_config.provider_aliases
                if hasattr(reasoning_cfg, f"get_{p}_reasoning_kwargs")
            )
            logger.error(
                "Provider not supported",
                event_type="reasoning_application_error",
                component="LLMFactory._apply_reasoning",
                params={"provider": provider, "supported_providers": supported_providers}
            )

            raise ValueError(f"Provider '{provider}' is not supported. Supported providers are: {', '.join(supported_providers)}")
        
        reasoning_kwargs = provider_fn()
        kwargs.update(reasoning_kwargs)
        logger.debug(
            f"Applied reasoning configuration for {provider}",
            event_type="reasoning_application",
            component="LLMFactory._apply_reasoning",
            params={"provider": provider, "reasoning_kwargs": reasoning_kwargs}
        )

        return kwargs
