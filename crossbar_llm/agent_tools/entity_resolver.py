import yaml


from .neo4j_client import Neo4jClient
from .config import Neo4jConfig, FullTextIndexMappings, EntityResolverConfig

from langchain_core.messages import ToolMessage, BaseMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain.tools import tool

from pydantic import validate_call, FilePath, BaseModel, Field

from pathlib import Path
from typing import Optional, Literal, Union, Annotated, Callable


from .logging_config import get_logger, log_execution_time
logger = get_logger(__name__)


# FOR TOOL CALL
class ToolCandidate(BaseModel):
    name: str
    score: float
    rank: int

class ToolSearchResult(BaseModel):
    kind: Literal["search_result"] = "search_result"
    entity_name: str
    node_type: str
    candidates: list[ToolCandidate] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.candidates) == 0

class ToolErrorResult(BaseModel):
    kind: Literal["error"] = "error"
    entity_name: str
    node_type: str
    error: str

# This creates a discriminated union. 
# ToolOutcome can be either ToolSearchResult or ToolErrorResult; Pydantic uses "kind" to decide which one to validate.
ToolOutcome = Annotated[
    Union[ToolSearchResult, ToolErrorResult],
    Field(discriminator="kind"),
]

class EntityToolExecution(BaseModel):
    tool_args: dict
    tool_call_id: str
    tool_response: ToolOutcome
    was_corrected: bool = False
    correction_attempts: int = 0
    final_entity_name: Optional[str] = None
    final_node_type: Optional[str] = None
    message_history: list[BaseMessage] = Field(default_factory=list)


    @property
    def as_tool_message(self) -> ToolMessage:
        return ToolMessage(
            content=self.tool_response.model_dump(),
            tool_call_id=self.tool_call_id
        )


class EntityResolver:
    def __init__(
            self,
            neo4j_client: Neo4jClient,
            fulltext_index_config_path: FilePath = Path(__file__).resolve().parent / "metadata" / "fulltext_index_mappings.yaml",
            entity_resolver_config: EntityResolverConfig = EntityResolverConfig()
        ):
        
        self.neo4j_client = neo4j_client
        self.entity_search_tool = self.build_entity_search_tool()
        self.entity_resolver_config = entity_resolver_config
        with open(fulltext_index_config_path, "r") as f:
            raw_mappings = yaml.safe_load(f)
            self.fulltext_index_mappings = FullTextIndexMappings.model_validate(raw_mappings)
            logger.debug(
                "Full-text index mappings loaded successfully",
                event_type="config_load",
                component="EntityResolver.__init__",
                fulltext_index_mappings=self.fulltext_index_mappings.model_dump()
            )

        
        logger.info(
            "Entity resolver initialized successfully",
            event_type="initialization",
            component="EntityResolver.__init__",
            fulltext_index_config_path=fulltext_index_config_path,
            entity_resolver_config=self.entity_resolver_config.model_dump()
        )


    def build_entity_search_tool(self) -> Callable[[str, str], dict[str, Union[str, list, None]]]:
        # There is also ToolNode in LangGraph. Maybe you can use that instead of this standalone tool function.
        # But for now, let's keep it simple and just use a tool function here.
        @tool
        def entity_search_tool(node_type: str, entity_name: str) -> dict[str, Union[str, list, None]]:
            """
            Search for an entity in the Neo4j graph database using fulltext index.
            Args:
                node_type (str): The type of the node to search for.
                entity_name (str): The name of the entity to search for.
            """

            logger.debug(
                "Starting entity fulltext search tool execution",
                event_type="tool_execution",
                component="EntityResolver.build_entity_search_tool",
                node_type=node_type,
                entity_name=entity_name
            )

            results = self.neo4j_client.fulltext_search(node_type, entity_name)
            
            payload = {
                "candidates": None if isinstance(results, str) else results,
                "error": results if isinstance(results, str) else None
            }

            logger.debug(
                "Entity fulltext search tool execution completed",
                event_type="tool_execution_completed",
                component="EntityResolver.build_entity_search_tool",
                node_type=node_type,
                entity_name=entity_name,
                has_error=payload["error"] is not None,
                num_candidates=len(payload["candidates"]) if payload["candidates"] is not None else 0,
                candidates=payload["candidates"]
            )
            
            return payload
        
        return entity_search_tool
    
    @log_execution_time(logger, component="EntityResolver.run_entity_search")
    def run_entity_search(self, node_type: str, entity_name: str) -> ToolOutcome:

        logger.debug(
            "Running entity search",
            event_type="entity_search_started",
            component="EntityResolver.run_entity_search",
            node_type=node_type,
            entity_name=entity_name
        )

        tool_response = self.entity_search_tool.invoke({"node_type": node_type, "entity_name": entity_name})
        if isinstance(tool_response, str):
            # This means an error occurred and the response is an error message
            logger.warning(
                "Entity search tool returned an error",
                event_type="entity_search_failed",
                component="EntityResolver.run_entity_search",
                node_type=node_type,
                entity_name=entity_name,
                error_message=tool_response
            )
            return ToolErrorResult(entity_name=entity_name, node_type=node_type, error=tool_response)
        
        if tool_response.get("error"):
            logger.warning(
                "Entity search tool returned an error in payload",
                event_type="entity_search_failed",
                component="EntityResolver.run_entity_search",
                node_type=node_type,
                entity_name=entity_name,
                error_message=tool_response["error"]
            )
            return ToolErrorResult(entity_name=entity_name, node_type=node_type, error=tool_response["error"])
        
        candidates = [
                ToolCandidate(
                    name=c["name"],
                    score=c["score"],
                    rank=c["rank"]
                )
                for c in tool_response.get("candidates", [])
        ]

        logger.info(
            "Entity search completed successfully",
            event_type="entity_search_completed",
            component="EntityResolver.run_entity_search",
            node_type=node_type,
            entity_name=entity_name,
            num_candidates=len(candidates),
            candidates=candidates
        )
        
        return ToolSearchResult(
            entity_name=entity_name,
            node_type=node_type,
            candidates=candidates
        )
    
    @log_execution_time(logger, component="EntityResolver.run_entity_llm_stage")
    def run_entity_llm_stage(
            self,
            *,
            mode: Literal["extraction", "tool call", "resolution", "error correction"],
            question: str,
            extracted_entities: Optional[str] = None,
            prior_messages: Optional[list[BaseMessage]] = None,
            llm: BaseChatModel,
            prompt: ChatPromptTemplate,
        ):

        logger.debug(
            "Running entity resolver LLM stage",
            event_type="entity_llm_stage_started",
            component="EntityResolver.run_entity_llm_stage",
            mode=mode,
            question=question,
            has_extracted_entities=extracted_entities is not None,
            prior_messages_count=len(prior_messages) if prior_messages else 0
        )

        
        messages = prompt.format_messages(
            node_types=self.fulltext_index_mappings.get_node_types(),
            question=question,
            extracted_entities=extracted_entities,
            mode = mode
        )

        logger.debug(
            "Prompt formatted for entity LLM stage",
            event_type="llm_stage_prompt_formatted",
            component="EntityResolver.run_entity_llm_stage",
            mode=mode,
            question=question,
            num_messages=len(messages)
        )

        if prior_messages:
            messages.extend(prior_messages)

        
        if mode in {"extraction", "tool call", "resolution", "error correction"}:
            response = llm.invoke(
                messages,
                config={
                    "metadata": {
                        "node_name": f"entity_resolution_mode_{mode.replace(' ', '_')}", # maybe just use entity_resolution and pass the mode as a separate metadata field?
                    }
                }
            )
            logger.debug(
                "LLM stage completed",
                event_type="entity_llm_stage_completed",
                component="EntityResolver.run_entity_llm_stage",
                mode=mode,
                has_tool_calls=bool(getattr(response, "tool_calls", None)),
            )
            return response
        else:
            logger.error(
                "Invalid mode specified for entity LLM stage",
                event_type="entity_llm_stage_failed",
                component="EntityResolver.run_entity_llm_stage",
                mode=mode
            )
            raise ValueError(f"Invalid mode '{mode}' specified for LLM stage. Must be one of 'extraction', 'tool call', 'resolution', or 'error correction'.")
    

    @log_execution_time(logger, component="EntityResolver.run_single_entity_tool_call_with_retry")
    def run_single_entity_tool_call_with_retry(
        self,
        *,
        tool_call: dict,
        question: str,
        llm: BaseChatModel,
        prompt: ChatPromptTemplate,
        prior_messages: Optional[list[BaseMessage]] = None
    ):
        
        original_tool_args = tool_call["args"]
        final_tool_args = original_tool_args.copy()
        tool_call_id = tool_call["id"]
        was_corrected = False
        corrected_entity_name = None
        corrected_node_type = None
        correction_attempts = 0
        tool_messages = []

        logger.info(
            "Starting single entity tool call with retry",
            event_type="single_entity_tool_call_started",
            component="EntityResolver.run_single_entity_tool_call_with_retry",
            tool_call_id=tool_call_id,
            original_tool_args=original_tool_args,
            max_attempts=self.entity_resolver_config.max_attempts,
        )

        conversation: list[BaseMessage] = list(prior_messages or [])

        original_entity_name = final_tool_args["entity_name"]
        for char in self.entity_resolver_config.replace_chars:
            final_tool_args["entity_name"] = final_tool_args["entity_name"].replace(char, "")
        
        if original_entity_name != final_tool_args["entity_name"]:
            logger.debug(
                "Sanitized entity name for entity search tool call",
                event_type="entity_name_sanitized",
                component="EntityResolver.run_single_entity_tool_call_with_retry",
                tool_call_id=tool_call_id,
                original_entity_name=original_entity_name,
                sanitized_entity_name=final_tool_args["entity_name"]
            )

        # Use sanitized args on the first call too
        tool_response = self.run_entity_search(**final_tool_args)
        conversation.append(
            ToolMessage(
                content=tool_response.model_dump(),
                tool_call_id=tool_call_id,
            )
        )

        logger.debug(
            "Initial entity search completed",
            event_type="entity_search_completed",
            component="EntityResolver.run_single_entity_tool_call_with_retry",
            tool_call_id=tool_call_id,
            response_kind=tool_response.kind,
            tool_args=final_tool_args,
            tool_response=tool_response
        )

        for _ in range(self.entity_resolver_config.max_attempts):
            if isinstance(tool_response, ToolSearchResult):
                # ------------------------
                # What if ToolSearchResult is empty?
                # ------------------------
                was_corrected = True
                corrected_entity_name = final_tool_args["entity_name"]
                corrected_node_type = final_tool_args["node_type"]

                logger.info(
                    "Entity search successful",
                    event_type="entity_search_successful",
                    component="EntityResolver.run_single_entity_tool_call_with_retry",
                    tool_call_id=tool_call_id,
                    correction_attempts=correction_attempts,
                    final_entity_name=corrected_entity_name,
                    final_node_type=corrected_node_type,
                    candidates=tool_response.candidates
                )
                break
            
            logger.warning(
                "Entity search failed, attempting error correction",
                event_type="entity_search_tool_retry_attempt",
                component="EntityResolver.run_single_entity_tool_call_with_retry",
                tool_call_id=tool_call_id,
                correction_attempts=correction_attempts,
                error=tool_response.error,
                current_entity_name=final_tool_args["entity_name"],
                current_node_type=final_tool_args["node_type"]
            )

            repair_res = self.run_entity_llm_stage(
                mode="error correction",
                question=question,
                extracted_entities=tool_response.model_dump_json(),
                llm=llm,
                prompt=prompt,
                prior_messages=conversation
            )

            if not repair_res.tool_calls:
                logger.warning(
                    "No tool calls generated in error correction mode. Stopping attempts.",
                    event_type="no_tool_calls_generated",
                    component="EntityResolver.run_single_entity_tool_call_with_retry",
                    tool_call_id=tool_call_id,
                    correction_attempts=correction_attempts
                )
                break

            conversation.append(repair_res)
            repaired_tool_call = repair_res.tool_calls[0]
            tool_call_id = repaired_tool_call["id"]
            final_tool_args = repaired_tool_call["args"]
            correction_attempts += 1
            
            tool_response = self.run_entity_search(**final_tool_args)
            conversation.append(
            ToolMessage(
                content=tool_response.model_dump(),
                tool_call_id=tool_call_id,
                )
            )

            logger.debug(
                "Error correction attempt completed",
                event_type="error_correction_attempt_completed",
                component="EntityResolver.run_single_entity_tool_call_with_retry",
                tool_call_id=tool_call_id,
                correction_attempts=correction_attempts,
                repaired_tool_args=final_tool_args
            )

        logger.info(
            "Finished single entity tool call with retry",
            event_type="single_entity_tool_call_completed",
            component="EntityResolver.run_single_entity_tool_call_with_retry",
            tool_call_id=tool_call_id,
            correction_attempts=correction_attempts,
            was_successful=isinstance(tool_response, ToolSearchResult),
            final_entity_name=corrected_entity_name,
            final_node_type=corrected_node_type,
            response_kind=tool_response.kind
        )

        return EntityToolExecution(
            tool_args=final_tool_args,
            tool_call_id=tool_call_id,
            tool_response=tool_response,
            was_corrected=correction_attempts > 0 and was_corrected,
            final_entity_name=corrected_entity_name,
            final_node_type=corrected_node_type,
            correction_attempts=correction_attempts,
            message_history=conversation
        )