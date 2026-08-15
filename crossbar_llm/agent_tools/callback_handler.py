from typing import Optional, Union, Any
from uuid import UUID
from dataclasses import dataclass, field, asdict

from threading import Lock

from langchain_core.callbacks import BaseCallbackHandler
from langchain.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class UsageCounter:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    reasoning: int = 0

    def add_usage(self, usage: dict[str, int]) -> None:
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        self.total_tokens += usage.get("total_tokens", 0)
        self.cache_read += usage.get("cache_read", 0)
        self.cache_write += usage.get("cache_write", 0)
        self.reasoning += usage.get("reasoning", 0)

    def __add__(self, other: "UsageCounter") -> "UsageCounter":
        return UsageCounter(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cache_read=self.cache_read + other.cache_read,
            cache_write=self.cache_write + other.cache_write,
            reasoning=self.reasoning + other.reasoning
        )

    def __iadd__(self, other: "UsageCounter") -> "UsageCounter":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.cache_read += other.cache_read
        self.cache_write += other.cache_write
        self.reasoning += other.reasoning
        return self
    
    def to_dict(self) -> dict[str, int]:
        return asdict(self)

@dataclass
class UsageRecord(UsageCounter):
    model: str | None = None
    call_count: int = 0

    def register_call(self, usage: dict[str, int], model_name: str | None = None) -> None:
        if self.model is None:
            self.model = model_name
        
        self.add_usage(usage)
        self.call_count += 1
    
    def to_dict(self) -> dict[str, Union[int, str]]:
        return asdict(self)
    
@dataclass
class AggregatedUsage:
    totals: UsageCounter = field(default_factory=UsageCounter)
    models_by_node: dict[str, list[str]] = field(default_factory=dict)

    def register_model(self, node_name: str, model_name: str) -> None:
        if node_name is None or model_name is None:
            raise ValueError("node_name and model_name cannot be None")
        
        if node_name not in self.models_by_node:
            self.models_by_node[node_name] = []
        
        if model_name not in self.models_by_node[node_name]:
            self.models_by_node[node_name].append(model_name)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "totals": self.totals.to_dict(),
            "models_by_node": self.models_by_node
        }



class UsageMetricsCallback(BaseCallbackHandler):
    def __init__(self, session_id: str, strict: bool = True):
        super().__init__()
        self.raise_error = True
        # run_inline keeps it in the same thread so the raise actually stops the call
        self.run_inline = True

        self.session_id = session_id
        self.strict = strict
        self._lock = Lock()

        self.run_metadata: dict[str, dict[str, str]] = {}

        self.per_node_usage: dict[str, UsageRecord] = {}

        self.aggregated_usage: AggregatedUsage = AggregatedUsage()

        logger.info(
            "UsageMetricsCallback initialized successfully",
            event_type="initialization",
            component="UsageMetricsCallback.__init__",
            session_id=session_id,
            strict=strict,
        )

    def normalize_usage(
        self,
        usage_metadata: dict[str, Any],
    ) -> dict[str, int]:

        normalized = {
            "input_tokens": usage_metadata.get("input_tokens", 0),
            "output_tokens": usage_metadata.get("output_tokens", 0),
            "total_tokens": usage_metadata.get("total_tokens", 0),
            "cache_read": usage_metadata.get("input_token_details", {}).get("cache_read", 0),
            "cache_write": usage_metadata.get("output_token_details", {}).get("cache_write", 0), # this might be different for other models
            "reasoning": usage_metadata.get("output_token_details", {}).get("reasoning", 0), # this might be different for other models
        }

        logger.debug(
            "Normalized usage metadata successfully",
            event_type="usage_normalization",
            component="UsageMetricsCallback.normalize_usage",
            raw_usage=usage_metadata,
            session_id=self.session_id,
            normalized=normalized
        )

        return normalized

    def on_chat_model_start(self, 
                            serialized: dict[str, Any],
                            messages: list[list[Any]],
                            *, 
                            run_id: UUID, 
                            tags: Optional[list[str]] = None, 
                            invocation_params: Optional[dict[str, Any]] = None,
                            metadata: Optional[dict[str, Any]] = None, 
                            **kwargs: Any
                        ):
        metadata = metadata or {}
        invocation_params = invocation_params or {}

        node_name = metadata.get("node_name", "unknown_node")
        requested_model = (
            invocation_params.get("model")
            or invocation_params.get("model_name")
            or metadata.get("model")
            or serialized.get("kwargs", {}).get("model_name")
            or serialized.get("name")
            or "unknown_model"
        )

        with self._lock:
            self.run_metadata[str(run_id)] = {
                "node_name": node_name,
                "model": requested_model
            }
        
        logger.debug(
            "Registered chat model run metadata",
            event_type="run_metadata_registered",
            component="UsageMetricsCallback.on_chat_model_start",
            run_id=str(run_id),
            node_name=node_name,
            model_name=requested_model,
        )

    
    def on_llm_end(
            self, 
            response: Any, 
            *, 
            run_id: UUID, 
            **kwargs
        ):

        run_key = str(run_id)

        with self._lock:
            meta = self.run_metadata.pop(run_key, {"node_name": "unknown_node", "requested_model": "unknown_model"})
        
        try:
            usage_metadata = response.generations[0][0].message.usage_metadata
        except Exception:
            logger.error(
                "Failed to extract usage metadata from response",
                event_type="usage_metadata_extraction_failed",
                component="UsageMetricsCallback.on_llm_end",
                run_id=run_key,
                node_name=meta.get("node_name"),
                requested_model=meta.get("requested_model"),
                raw_response=response.generations if hasattr(response, "generations") else str(response),
            )
            if self.strict:
                raise ValueError(f"Failed to extract usage metadata from response for run_id: {run_key}")
            return # If not strict, just skip recording usage for this call

        # ---------------------
        # Currently, there is no fallback mechanism for normalizing usage metadata across different LLM providers.
        # Because, different LLM providers use different fields for usage metadata (I mean not primary one, but the fields like response_metadata or llm_output), 
        # it is not possible to have a single normalization function that works for all providers without provider-specific logic.
        # ----------------------

        normalized = self.normalize_usage(usage_metadata)
        # antropic does not provide reasoning tokens in the main usage metadata, but provides it in llm_output.
        if normalized["reasoning"] == 0 and hasattr(response, "llm_output"):
            llm_output = getattr(response, "llm_output", {}) or {}
            usage = llm_output.get("usage", {}) or {}
            output_tokens_details = usage.get("output_tokens_details", {}) or {}
            normalized["reasoning"] = output_tokens_details.get("thinking_tokens", 0)

        resolved_model_name = self._extract_resolved_model_name(response, fallback_model=meta.get("requested_model", "unknown_model"))
        node_name = meta["node_name"]

        with self._lock:

            if node_name not in self.per_node_usage:
                self.per_node_usage[node_name] = UsageRecord()
                logger.debug(
                    "Created per-node usage record",
                    event_type="usage_record_created",
                    component="UsageMetricsCallback.on_llm_end",
                    node_name=node_name,
                )
            
            node_record = self.per_node_usage[node_name]
            node_record.register_call(normalized, model_name=resolved_model_name)

            self.aggregated_usage.totals.add_usage(normalized)
            self.aggregated_usage.register_model(node_name, resolved_model_name)

        logger.info(
            "Recorded LLM usage successfully",
            event_type="usage_recorded",
            component="UsageMetricsCallback.on_llm_end",
            run_id=run_key,
            node_name=node_name,
            model_name=resolved_model_name,
            call_count=node_record.call_count,
            normalized_usage=normalized,
        )

        logger.debug(
            "Updated usage aggregation state",
            event_type="usage_state_updated",
            component="UsageMetricsCallback.on_llm_end",
            per_node_usage=self.get_usage_by_node(),
            aggregated_usage=self.aggregated_usage.to_dict(),
        )

    def _extract_resolved_model_name(self, response: Any, fallback_model: str = None) -> str:
        message = response.generations[0][0].message
        response_metadata = getattr(message, "response_metadata", {}) or {}
        llm_output = getattr(response, "llm_output", {}) or {}
        generation_info = response.generations[0][0].generation_info or {}

        resolved_model = (
            response_metadata.get("model_name") or
            response_metadata.get("model") or
            generation_info.get("model_name") or
            generation_info.get("model") or
            llm_output.get("model_name") or
            llm_output.get("model") or
            fallback_model
        )

        return resolved_model or "unknown_model"

    def get_usage_by_node(self) -> dict[str, dict[str, Union[int, str]]]:
        with self._lock:
            return {node: record.to_dict() for node, record in self.per_node_usage.items()}
    
    def get_total_usage(self) -> dict[str, int]:
        with self._lock:
            return self.aggregated_usage.totals.to_dict()
    
    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            summary = {
                "session_id": self.session_id,
                "per_node_usage": {node: record.to_dict() for node, record in self.per_node_usage.items()},
                "aggregated_usage": self.aggregated_usage.to_dict()
            }
            return summary
        
        logger.debug(
            "Retrieved usage metrics summary",
            event_type="usage_summary_retrieved",
            component="UsageMetricsCallback.get_summary",
            session_id=self.session_id,
            node_count=len(summary["per_node_usage"]),
        )
    
    def reset(self) -> None:
        with self._lock:
            self.run_metadata = {}
            self.per_node_usage = {}
            self.aggregated_usage = AggregatedUsage()
        
        logger.info(
            "Usage metrics callback state reset successfully",
            event_type="usage_state_reset",
            component="UsageMetricsCallback.reset",
            session_id=self.session_id,
        )


# ---------------------------------------------------------------
# CHECK:
# WHAT HAPPEN WITH DIFFERENT LLM PROVIDERS OTHER THAN OPENAI?
# DOES FALLBACKS HAVE `cache_write` EQUIVALENT?
# ADD:
# LOGGING
# PYTEST TESTS
# --------------------------------------------------------------


# Currently not used, but can be used to validate if a question is biologically relevant before allowing the LLM call to proceed.
class BiologicalRelevanceValidatorCallback(BaseCallbackHandler):
    def __init__(
            self,
            relevance_llm: BaseChatModel,
            prompt_template: Optional[ChatPromptTemplate] = None
        ):
        super().__init__()
        self.relevance_llm = relevance_llm
        self.raise_error = True
        # run_inline keeps it in the same thread so the raise actually stops the call
        self.run_inline = True
        
        if prompt_template is None:
            self.prompt_template = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(
                    """
                    "You are an expert content classifier specializing in biological and biomedical sciences. 
                    Your task is to determine whether user questions fall within the biological/biomedical domain.
                    """.strip()
                ),
                HumanMessagePromptTemplate.from_template("{question}")
            ])

    def on_chat_model_start(self, serialized, messages, **kwargs):
        flat = [m for batch in messages for m in batch]
        print("LLM started with messages:", messages)
        user_messages = "\n".join([m.content for m in flat if isinstance(m, HumanMessage)])
        if not user_messages:
            return
        
        messages = self.prompt_template.format_prompt(question=user_messages).to_messages()
        verdict = self.relevance_llm.invoke(messages, config={"callbacks": []})
        print("Biological relevance validation response:\n", verdict)

        if verdict["parsed"].relevant is False:
            raise NonBiologicalQueryError(f"The question is outside the biological/biomedical domain.\nReason: {verdict['parsed'].reason}")

class NonBiologicalQueryError(ValueError):
    pass
