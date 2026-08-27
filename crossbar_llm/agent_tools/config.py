from pydantic import BaseModel, ConfigDict, SecretStr, PositiveInt, Field, model_validator, validate_call, field_validator, field_serializer
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    YamlConfigSettingsSource
)
from typing import Optional, Literal, Union, Any
from typing_extensions import Self
from langchain_core.callbacks import BaseCallbackHandler

from pathlib import Path
from httpx import Timeout
from .logging_config import get_logger

logger = get_logger(__name__)

class ConfigPaths:
    BASE_DIR = Path(__file__).resolve().parent
    METADATA_DIR = BASE_DIR / "metadata"

    ENV_FILE = BASE_DIR / ".env"
    MODELS_CONFIG_FILE = METADATA_DIR / "models_config.yaml"
    VECTOR_MAPPINGS_FILE = METADATA_DIR / "vector_mappings.yaml"
    FULLTEXT_INDEX_MAPPINGS_FILE = METADATA_DIR / "fulltext_index_mappings.yaml"


class APIKeyConfig(BaseSettings):
    """
    Application API key settings loaded from environment variables or 
    from a dotenv file.

    Environment variables:
    - OPENAI_API_KEY
    - GEMINI_API_KEY
    - ANTHROPIC_API_KEY
    - GROQ_API_KEY
    - OPENROUTER_API_KEY
    """

    model_config = SettingsConfigDict(
        env_file=ConfigPaths.ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    groq_api_key: SecretStr | None = Field(default=None, alias="GROQ_API_KEY")
    openrouter_api_key: SecretStr | None = Field(default=None, alias="OPENROUTER_API_KEY")

    @validate_call(validate_return=True)
    def get_api_key(self, provider_resolved_name: str, provider_to_api_key_attr: dict[str, str]) -> Optional[SecretStr]:

        api_key_attr = provider_to_api_key_attr.get(provider_resolved_name)
        if api_key_attr is None:
            logger.error(
                "API key attribute for provider not found in configuration",
                event_type="config_error",
                component="APIKeyConfig.get_api_key",
                provider_resolved_name=provider_resolved_name
            )
            raise ValueError(f"API key attribute for provider '{provider_resolved_name}' not found in configuration.")
        
        api_key = getattr(self, api_key_attr, None)
        if not api_key:
            logger.error(
                "API key for provider not found as an environment variable",
                event_type="config_error",
                component="APIKeyConfig.get_api_key",
                provider_resolved_name=provider_resolved_name
            )
            raise ValueError(f"API key for provider '{provider_resolved_name}' not found as an environment variable.")
        
        logger.debug(
            "Resolved API key for provider",
            event_type="config_resolved",
            component="APIKeyConfig.get_api_key",
            provider_resolved_name=provider_resolved_name,
            api_key_attr=api_key_attr
        )

        return api_key
  

class Neo4jConfig(BaseSettings):
    """
    Neo4j connection settings loaded from environment variables or
    from a dotenv file.

    Environment variables:
    - NEO4J_USER
    - NEO4J_PASSWORD
    - NEO4J_DB_NAME
    - NEO4J_URI
    """
    model_config = SettingsConfigDict(
        env_file=ConfigPaths.ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    neo4j_usr: str = Field(alias="NEO4J_USER")
    neo4j_password: str = Field(alias="NEO4J_PASSWORD")
    neo4j_db_name: str = Field(alias="NEO4J_DB_NAME")
    neo4j_uri: str = Field(alias="NEO4J_URI")

class ReasoningConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    effort: Optional[Literal["low", "medium", "high"]] = None

    # openai reasoning config parameters
    openai_reasoning_summary: Optional[Literal["auto", "detailed", "concise"]] = "auto"
    use_responses_api: Optional[bool] = True

    # anthropic reasoning config parameters
    anthropic_thinking_type: Optional[Literal["enabled", "adaptive"]] = "enabled" # adaptive for Opus 4.6+
    budget_tokens: Optional[PositiveInt] = Field(default=1024, lt=4_000)

    # google genai config parameters
    include_thoughts: Optional[bool] = True

    # groq config parameters
    include_reasoning : Optional[bool] = True

    @model_validator(mode="after")
    def validate_reasoning_config(self) -> Self:
        if self.enabled and self.effort is None:
            logger.error(
                "Effort level must be specified when reasoning is enabled.",
                event_type="config_error",
                component="ReasoningConfig.validate_reasoning_config",
                reasoning_config=self.model_dump(exclude={"model_config"})
            )
            raise ValueError("Effort level must be specified when reasoning is enabled.")
    
        return self

    def get_openai_reasoning_kwargs(self) -> dict[str, Any]:
        
        # CHECK: WHETHER THIS IS CORRECT?
        return {
            "use_responses_api": self.use_responses_api,
            "reasoning": {
                "effort": self.effort,
                "summary": self.openai_reasoning_summary,
            }
        }
    
    def get_anthropic_reasoning_kwargs(self) -> dict[str, Any]:

        return {
            "thinking": {
                "type": self.anthropic_thinking_type,
                "budget_tokens": self.budget_tokens,
            }
        }
    
    def get_google_genai_reasoning_kwargs(self) -> dict[str, Any]:
        
        return {
            "thinking_level": self.effort,
            "include_thoughts": self.include_thoughts,
        }
    
    def get_openrouter_reasoning_kwargs(self) -> dict[str, Any]:
        
        return {
            "reasoning": {
                "effort": self.effort,
            }
        }
    
    def get_groq_reasoning_kwargs(self) -> dict[str, Any]:
        
        return {
            "include_reasoning": self.include_reasoning,
        }
    
    def get_ollama_reasoning_kwargs(self) -> dict[str, Any]:
        raise NotImplementedError("Reasoning configuration for Ollama provider is not implemented yet.")
    

class LLMConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    model: str
    provider: Optional[Literal["openai", "anthropic", "google_genai", "groq", "openrouter", "ollama"]] = None
    temperature: float = 1.
    timeout: Union[float, int, Timeout] = 90.0
    max_retries: int = 2
    callbacks: list[BaseCallbackHandler] = Field(default_factory=list)
    reasoning: ReasoningConfig = Field(default_factory=ReasoningConfig)
    extra_kwargs: dict = Field(default_factory=dict)


    @field_validator("callbacks")
    def check_callbacks(cls, v: list[BaseCallbackHandler]) -> list[BaseCallbackHandler]:
        if not isinstance(v, list):
            logger.error(
                "Callbacks must be provided as a list.",
                event_type="config_error",
                component="LLMConfig.check_callbacks",
                callbacks=v
            )
            raise ValueError("Callbacks must be provided as a list.")
        
        for callback in v:
            if not issubclass(type(callback), BaseCallbackHandler):
                logger.error(
                    "All callbacks must be instances of BaseCallbackHandler.",
                    event_type="config_error",
                    component="LLMConfig.check_callbacks",
                    invalid_callback=callback
                )
                raise ValueError("All callbacks must be instances of BaseCallbackHandler.")
        
        return v
    
    @field_serializer("callbacks")
    def serialize_callbacks(self, v: list[BaseCallbackHandler]) -> list[str]:
        return [callback.__class__.__name__ for callback in v]
    

    @model_validator(mode="after")
    def split_provider_from_model(self) -> Self:
        """
        This validator checks if the model string contains a provider prefix (e.g., "openai:gpt-4") and splits it into separate 'provider' and 'model' fields if necessary. 
        If the provider is already specified or if the model string does not contain a provider prefix, it leaves the data unchanged.
        """
        
        model = self.model
        provider = self.provider

        if provider and ":" in model:
            logger.error(
                "Model string should not contain provider prefix when 'provider' field is already specified.",
                event_type="config_error",
                component="LLMConfig.split_provider_from_model",
                provider=provider,
                model=model
            )
            raise ValueError("Model string should not contain provider prefix when 'provider' field is already specified.")
        
        if model.count(":") > 1:
            logger.error(
                "Model string contains more than one ':' character, which is not allowed.",
                event_type="config_error",
                component="LLMConfig.split_provider_from_model",
                model=model
            )
            raise ValueError("Model string should not contain more than one ':'.")
        
        if provider or ":" not in model:
            return self
        
        
        provider_from_model, model_name = model.split(":")
        self.provider = provider_from_model
        self.model = model_name

        logger.debug(
            "Split provider from model string",
            event_type="config_parsing",
            component="LLMConfig.split_provider_from_model",
            original_model=model,
            resolved_provider=provider_from_model,
            resolved_model=model_name
        )
        
        return self
    
    @model_validator(mode="after")
    def validate_provider_and_model(self) -> Self:
        """
        This validator checks the consistency between the 'provider' and 'model' fields after the initial validation.
        """

        if self.provider is not None and ":" in self.model:
            logger.error(
                "Model string should not contain provider prefix when 'provider' field is already specified.",
                event_type="config_error",
                component="LLMConfig.validate_provider_and_model",
                provider=self.provider,
                model=self.model
            )
            raise ValueError("Model string should not contain provider prefix when 'provider' field is already specified.")
        
        return self

    
    @model_validator(mode="after")
    def normalize_timeout_for_provider(self) -> Self:
        """
        Normalize the `timeout` field for providers whose LangChain integrations use
        different timeout semantics.

        This validator runs after `split_provider_from_model`, so provider inference
        from model strings such as `"openai:gpt-5"` or `"openrouter:qwen/..."`
        has already happened before timeout normalization is applied.

        Provider-specific behavior:
        - `openai`:
          If `timeout` is given as a numeric value, convert it to `httpx.Timeout`
          so timeout handling becomes fine-grained across connection,
          read, write, and pool phases. This is important because for OpenAI-based
          integrations, a simple float timeout such as `timeout=30` primarily sets
          the read timeout, not the connection timeout. As a result, requests to
          unreachable endpoints may not time out as expected unless an
          `httpx.Timeout` object is used. If `timeout` is already an `httpx.Timeout`
          instance, keep it unchanged.

        - `openrouter`:
          If `timeout` is given as a numeric value, interpret it as seconds at the
          config layer and convert it to milliseconds. This is necessary because the installed
          `langchain_openrouter` integration expects `timeout` in milliseconds.

        - other providers:
          Leave `timeout` unchanged.

        Returns:
            Self: The validated configuration with provider-appropriate timeout
            normalization applied.
        """

        if self.provider not in {"openai", "openrouter"}:
            return self
        
        if self.provider == "openrouter":
            if isinstance(self.timeout, Timeout):
                logger.error(
                    "OpenRouter timeout should be provided as a numeric value in seconds, not as an httpx.Timeout instance.",
                    event_type="config_error",
                    component="LLMConfig.normalize_timeout_for_provider",
                    provider=self.provider,
                    timeout=self.timeout
                )

                raise ValueError(
                    "OpenRouter timeout must be numeric in seconds at config level; "
                    "httpx.Timeout is only supported for the OpenAI models."
                )

            # self.timeout = ... trigger validate_assignment and they will loop infinitely.
            # so either we need to use self.__dict__ to bypass validation or we should assign validate_assignment to False
            self.__dict__["timeout"] = int(float(self.timeout) * 1000)
            
            return self
        
        if isinstance(self.timeout, Timeout):
            logger.debug(
                "Timeout is already an httpx.Timeout instance, no normalization needed for OpenAI provider.",
                event_type="config_validated",
                component="LLMConfig.normalize_timeout_for_provider",
                provider=self.provider,
                timeout=self.timeout
            )
            return self
        
        self.__dict__["timeout"] = Timeout(
                connect=90.0,
                read=float(self.timeout),
                write=90.0,
                pool=90.0,
            )
            
        logger.debug(
            "Normalized timeout for OpenAI provider.",
            event_type="config_validated",
            component="LLMConfig.normalize_timeout_for_provider",
            provider=self.provider,
            timeout=self.timeout
        )

        return self
        
class AgentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_iterations: int = Field(default=3, description="Maximum number of iterations for the agent to attempt generating valid and executable Cypher query.")
    enable_web_search: bool = Field(default=False, description="Enable web search agent")
    enable_entity_resolution: bool = Field(default=True, description="Enable entity resolution agent")
    web_search_model: Literal["gpt-5.1", "gemini-3-pro-preview"] = Field(default="gpt-5.1", description="Model to be used for web search tool. Options are 'gpt-5.1' and 'gemini-3-pro-preview'.")
    biological_relevance_validation_model: str = Field(default="gpt-5.4-nano", description="Model to be used for biological relevance validation.")
    keep_last_n_messages: int = Field(default=24, description="Number of recent messages to keep in memory")

# Entity Resolver Configurations
class EntityResolverConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_attempts: int = Field(default=3, description="Maximum number of attempts in error correction for entity resolution.")
    replace_chars: list[str] = Field(default=["/", "(+)", "[", "]", "^"], description="List of characters to replace in entity names to prevent errors during full text search query execution. These characters will be replaced with an empty string.")


# Vector Index Configurations
class VectorIndexConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    index_name: str
    property_name: str
    vector_size: int

class VectorMappings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid",
        frozen=True,
        yaml_file=ConfigPaths.VECTOR_MAPPINGS_FILE,
    )

    SmallMolecule: list[VectorIndexConfig]
    Protein: list[VectorIndexConfig]
    GOTerm: VectorIndexConfig
    Phenotype: VectorIndexConfig
    Disease: VectorIndexConfig
    ProteinDomain: VectorIndexConfig
    EcNumber: VectorIndexConfig
    Pathway: VectorIndexConfig
    Gene: VectorIndexConfig

    @classmethod
    def settings_customise_sources(cls, *args, **kwargs):
        return (YamlConfigSettingsSource(cls),)
    
    @validate_call(validate_return=True)
    def index_name_to_vector_size(self) -> dict[str, int]:
        result = {}
        for config in self.model_dump(exclude_none=True).values():
            if isinstance(config, list):
                for v in config:
                    result[v["index_name"]] = v["vector_size"]
            else:
                result[config["index_name"]] = config["vector_size"]

        logger.debug(
            "Generated index name to vector size mapping",
            event_type="config_accessed",
            component="VectorMappings.index_name_to_vector_size",
            mapping=result
        )
        return result
    
    def get_vector_index_name(self, vector_category: str, embedding_type: str) -> str:
        config = self.model_dump(exclude_none=True).get(vector_category)
        if config is None:
            logger.error(
                "Vector category not found in vector mappings.",
                event_type="config_error",
                component="VectorMappings.get_vector_index_name",
                vector_category=vector_category,
                embedding_type=embedding_type
            )
            raise ValueError(f"Vector category '{vector_category}' not found in vector mappings.")
        
        index_name = None
        if isinstance(config, list):
            for v in config:
                if v["index_name"].replace("Embeddings", "") == embedding_type:
                    index_name = v["index_name"]
                    break
        elif config["index_name"].replace("Embeddings", "") == embedding_type:
            index_name = config["index_name"]
        
        if index_name is None:
            logger.error(
                "Embedding type not found for the given vector category in vector mappings.",
                event_type="config_error",
                component="VectorMappings.get_vector_index_name",
                vector_category=vector_category,
                embedding_type=embedding_type
            )
            raise ValueError(f"Embedding type '{embedding_type}' not found for vector category '{vector_category}' in vector mappings.")
        
        logger.debug(
            "Retrieved vector index name for the given vector category and embedding type.",
            event_type="config_accessed",
            component="VectorMappings.get_vector_index_name",
            vector_category=vector_category,
            embedding_type=embedding_type,
            index_name=index_name
        )
        return index_name


# Full Text Index Configurations
class FullTextIndexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    index_name: str
    property_name: str
    fulltext_analyzer: str

class FullTextIndexMappings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid",
        frozen=True,
        yaml_file=ConfigPaths.FULLTEXT_INDEX_MAPPINGS_FILE,
    )
    GOTerm: FullTextIndexConfig
    ProteinDomain: FullTextIndexConfig
    SideEffect: FullTextIndexConfig
    SmallMolecule: FullTextIndexConfig
    Gene: FullTextIndexConfig
    Pathway: FullTextIndexConfig
    Protein: FullTextIndexConfig
    Phenotype: FullTextIndexConfig
    OrganismTaxon: FullTextIndexConfig
    Disease: FullTextIndexConfig
    EcNumber: FullTextIndexConfig

    @classmethod
    def settings_customise_sources(cls, *args, **kwargs):
        return (YamlConfigSettingsSource(cls),)

    def get_node_types(self) -> set[str]:
        node_types = set(self.model_dump(exclude_none=True).keys())
        logger.debug(
            "Retrieved node types from full text index mappings",
            event_type="config_accessed",
            component="FullTextIndexMappings.get_node_types",
            node_type_count=len(node_types),
            node_types=sorted(node_types)
        )
        return node_types
    
    @validate_call(validate_return=True)
    def get_index_name_by_node_type(self, node_type: str) -> str:
        config = self.model_dump(exclude_none=True).get(node_type)
        if config is None:
            logger.error(
                "Node type not found in fulltext index mappings.",
                event_type="config_error",
                component="FullTextIndexMappings.get_index_name_by_node_type",
                node_type=node_type
            )
            raise ValueError(f"Node type '{node_type}' not found in fulltext index mappings.")
        
        logger.debug(
            "Retrieved index name for node type from full text index mappings",
            event_type="config_accessed",
            component="FullTextIndexMappings.get_index_name_by_node_type",
            node_type=node_type,
            index_name=config["index_name"]
        )
        return config["index_name"]

    @validate_call(validate_return=True)
    def get_property_name_by_node_type(self, node_type: str) -> str:
        config = self.model_dump(exclude_none=True).get(node_type)
        if config is None:
            logger.error(
                "Node type not found in fulltext index mappings.",
                event_type="config_error",
                component="FullTextIndexMappings.get_property_name_by_node_type",
                node_type=node_type
            )
            raise ValueError(f"Node type '{node_type}' not found in fulltext index mappings.")
        
        logger.debug(
            "Retrieved property name for node type from full text index mappings",
            event_type="config_accessed",
            component="FullTextIndexMappings.get_property_name_by_node_type",
            node_type=node_type,
            property_name=config["property_name"]
        )
        return config["property_name"]


# Model Configurations
class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    models: set[str]
    free_models: set[str] = Field(default_factory=set)


class ModelsConfig(BaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid",
        frozen=True,
        yaml_file=ConfigPaths.MODELS_CONFIG_FILE,
    )
    OpenAI: ProviderConfig
    Anthropic: ProviderConfig
    Google: ProviderConfig
    Groq: ProviderConfig
    OpenRouter: ProviderConfig
    Ollama: ProviderConfig
    provider_aliases: dict[str, str]
    provider_to_api_key_attr: dict[str, str]
    supported_models_for_search: set[str]

    @classmethod
    def settings_customise_sources(cls, *args, **kwargs):
        return (YamlConfigSettingsSource(cls),)

    @validate_call(validate_return=True)
    def get_all_model_names(self) -> list[str]:
        all_models = []

        for field_name, field_info in self.__class__.model_fields.items():
            if issubclass(field_info.annotation, ProviderConfig):
                all_models.extend(getattr(self, field_name).models)
        
        logger.debug(
            "Retrieved all model names from provider configurations",
            event_type="config_accessed",
            component="ModelsConfig.get_all_model_names",
            model_count=len(all_models),
            models=sorted(all_models)
        )
        return all_models

    @validate_call(validate_return=True)
    def get_free_model_names(self) -> list[str]:
        free_models = []
        for field_name, field_info in self.__class__.model_fields.items():
            if issubclass(field_info.annotation, ProviderConfig):
                free_models.extend(getattr(self, field_name).free_models)
        
        logger.debug(
            "Retrieved free model names from provider configurations",
            event_type="config_accessed",
            component="ModelsConfig.get_free_model_names",
            model_count=len(free_models),
            models=sorted(free_models)
        )
        return free_models
    
    @validate_call(validate_return=True)
    def get_providers(self) -> set[str]:
        provider = set(
            field_name 
            for field_name, field_info in self.__class__.model_fields.items() 
            if issubclass(field_info.annotation, ProviderConfig)
        )
        logger.debug(
            "Retrieved provider names from configuration",
            event_type="config_accessed",
            component="ModelsConfig.get_providers",
            provider_count=len(provider),
            providers=sorted(provider)
        )
        return provider

    @validate_call(validate_return=True)
    def get_models_by_provider(self, provider_name: str) -> set[str]:
        provider_config = getattr(self, provider_name, None)
        if provider_config is not None and isinstance(provider_config, ProviderConfig):
            logger.debug(
                "Retrieved models for provider from configuration",
                event_type="config_accessed",
                component="ModelsConfig.get_models_by_provider",
                provider_name=provider_name,
                model_count=len(provider_config.models),
                models=sorted(provider_config.models)
            )
            return provider_config.models

        logger.error(
            "Provider not found in configuration",
            event_type="config_error",
            component="ModelsConfig.get_models_by_provider", 
            provider_name=provider_name
        )
        raise ValueError(f"Provider '{provider_name}' not found in configuration.")
    
    @validate_call(validate_return=True)
    def get_provider_by_model(self, model_name: str) -> str:
        """
        Get the runtime provider name for a given model name.
        WARNING: It does not return provider aliases. For example, it will return "google_genai" or "openai" not "Google" or "OpenAI".
        """
        for field_name, field_info in self.__class__.model_fields.items():
            if issubclass(field_info.annotation, ProviderConfig) and model_name in getattr(self, field_name).models:
                for runtime_name, resolved_name in self.provider_aliases.items():
                    if resolved_name == field_name:
                        logger.debug(
                            "Resolved provider name for model",
                            event_type="config_resolved",
                            component="ModelsConfig.get_provider_by_model",
                            model_name=model_name,
                            provider_runtime_name=runtime_name,
                            provider_config_name=field_name
                        )
                        return runtime_name
                
        logger.error(
            "Model not found in any provider configuration",
            event_type="config_error",
            component="ModelsConfig.get_provider_by_model",
            model_name=model_name
        )
        raise ValueError(f"Model '{model_name}' not found in any provider configuration.")

    @validate_call(validate_return=True)
    def validate_provider_model(self, resolved_provider_name: str, model_name: str, raise_on_error: bool = True) -> bool:
     
        provider_config = getattr(self, resolved_provider_name, None)

        if provider_config is None or not isinstance(provider_config, ProviderConfig):
            if raise_on_error:
                logger.error(
                    "Provider not found in configuration",
                    event_type="config_error",
                    component="ModelsConfig.validate_provider_model",
                    provider_name=resolved_provider_name
                )
                raise ValueError(
                    f"Provider '{resolved_provider_name}' not found. Available providers: {', '.join(sorted(self.__class__.model_fields.keys()))}"
                )
            return False

        if model_name not in provider_config.models:
            if raise_on_error:
                logger.error(
                    "Model not found under provider",
                    event_type="config_error",
                    component="ModelsConfig.validate_provider_model",
                    model_name=model_name,
                    provider_name=resolved_provider_name
                )
                raise ValueError(
                    f"Model '{model_name}' not found under provider '{resolved_provider_name}'."
                )
            return False

        logger.debug(
            "Validated model under provider successfully",
            event_type="config_validated",
            component="ModelsConfig.validate_provider_model",
            model_name=model_name,
            provider_name=resolved_provider_name
        )
        return True
