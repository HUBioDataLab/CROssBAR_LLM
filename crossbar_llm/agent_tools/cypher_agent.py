from typing import TypedDict, Optional, Annotated, Literal, Union
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, RemoveMessage
from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)


from langgraph.graph.message import add_messages, REMOVE_ALL_MESSAGES
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt


from .config import LLMConfig, Neo4jConfig, AgentConfig, VectorMappings
from .llm_factory import LLMFactory
from .prompt import (
    CYPHER_GENERATION_TEMPLATE,
    VECTOR_SEARCH_CYPHER_GENERATION_TEMPLATE,
    ERROR_CORRECTION_TEMPLATE,
    CYPHER_OUTPUT_PARSER_TEMPLATE,
    WEB_SEARCH_TEMPLATE,
    ENTITY_RESOLUTION_TEMPLATE,
    FOLLOW_UP_QUESTIONS_TEMPLATE,
    VECTOR_SEARCH_FOLLOW_UP_QUESTIONS_TEMPLATE,
    BIOLOGICAL_RELEVANCE_VALIDATION_TEMPLATE
)
from .neo4j_client import Neo4jClient
from .validators import validate_and_correct_query
from.entity_resolver import EntityResolver, EntityToolExecution


import numpy as np

from .logging_config import get_logger, log_execution_time

logger = get_logger(__name__)


class CypherAttempt(TypedDict):
    attempt_number: int
    cypher_query: str
    is_valid: bool # is_valid indicates whether the cypher query passed all validations
    syntax_valid: bool
    schema_valid: bool
    property_valid: bool
    syntax_errors: Optional[list[str]]
    schema_errors: Optional[list[str]]
    property_errors: Optional[list[str]]

    # execution
    execution_ok: bool # execution_ok specifically indicates whether the query executed successfully against the database.
    execution_error: Optional[str]

    attempt_source: Optional[Literal["generation", "error_correction", "web_search"]] = "generation" # This field indicates the source of the cypher attempt, whether it was from the generation, an error correction step, or a web search.
    # This can be useful for analysis and debugging to understand which steps are contributing to successful queries and which might be leading to errors.



class CypherAgentState(TypedDict):
    # user input
    question: str

    # resolution results
    # We can store the resolved entities and their types here after the entity resolution step, which
    # can then be used to condition the cypher generation step. This can help the LLM generate more accurate 
    # cypher queries by providing it with explicit information about the entities involved in the user's question.
    resolved_entities: Optional[Union[
         list[dict[str, str]], # This structure allows for multiple resolved entities, each with a mapping from the entity name in the user question to the resolved entity name in the database.
         str # In cases where the resolution process determines that no entities could be resolved, we can use a simple string message to indicate that, rather than an empty list or dict which might be ambiguous.
    ]] = None

    # agent state
    current_cypher: str
    retry_count: int
    cypher_mode: Literal["db_search", "vector_search"] = "db_search" # Flag for whether to use traditional database search or vector search. This can be used in routing decisions and prompt conditioning.
    # vector search specific variables
    vector_index: Optional[str] = None
    embedding: Optional[list[float]] = None
    
    # validation/execution results
    is_ok: bool # Both validation and execution results contribute to this overall status. It primarily reflects whether the current state is considered successful for generating an answer.
    cypher_attempts: list[CypherAttempt]

    no_valid_schema_path: bool = False # This flag can be set to True when the agent determines that the user's question cannot be satisfied by any valid path in the schema, which can then be used to route the agent towards providing an informative response to the user rather than attempting to generate or correct a Cypher query that would ultimately fail validation.

    cypher_source: Literal["generation", "error_correction", "web_search", "human_edit"] # This field indicates the source of the current cypher query.

    execution_result: Optional[list] # CHECK THE EXECUTION OUPUT TO MAKE SURE

    # final answer
    final_answer: Optional[str]

    # web search
    web_search_used: bool = False
    web_search_result: Optional[str]

    # follow-up questions
    follow_up_questions: Optional[list[str]]

    # Human-in-the-loop control
    execution_mode: Literal["generate_and_run", "generate"] = "generate_and_run"
    human_review_action: Literal["approve", "edit"]

    # biological relevance validation
    biological_relevance: bool # This field can store the result of biological relevance validation, which can be used to determine whether to proceed with the agent's processing or to halt and inform the user that their question is outside the relevant domain.

    # messages for LLM conversation
    messages: Annotated[list[BaseMessage], add_messages]
    # CAREFULLY CHECK THIS BEFORE DECIDING TO USE IT

    # benchmark mode
    benchmark_mode: Optional[bool] = False # This flag can be used to indicate whether the agent is running in benchmark mode, which does not create answers, only generates cypher queries and executes them.


class CypherAgent:
    def __init__(self,
                llm_config: LLMConfig,
                neo4j_config: Neo4jConfig,
                top_k: int = 10,
                debug_mode: bool = False,
                benchmark_mode: bool = False,
                disable_limit: bool = False
            ):

        self.llm_factory = LLMFactory(llm_config)
        self.cypher_llm = self.llm_factory.create_cypher_llm() # For both cypher generation and error correction, we can use the same LLM with different prompts. Uses CypherStrategy from llm_factory.py for structured output.
        self.output_parser_llm = self.llm_factory.create_output_parser_llm() # For only output parsing. Uses OutputParserStrategy from llm_factory.py for structured output.
        

        self.neo4j_client = Neo4jClient(neo4j_config)
        self.graph_schema = self.neo4j_client.create_graph_schema_variables()
        self.top_k = top_k
        self.debug_mode = debug_mode
        self.benchmark_mode = benchmark_mode
        self.disable_limit = disable_limit

        if self.benchmark_mode is False and self.disable_limit is True:
            logger.error(
                "disable_limit can only be True when benchmark_mode is True. In normal operation, limit should not be disabled to prevent excessive data retrieval.",
                event_type="invalid_initialization_configuration",
                component="CypherAgent.__init__",
                disable_limit=disable_limit,
                benchmark_mode=benchmark_mode
            )
            raise ValueError("disable_limit can only be True when benchmark_mode is True. In normal operation, limit should not be disabled to prevent excessive data retrieval.")

        self.entity_resolver = EntityResolver(neo4j_client=self.neo4j_client)

        self.index_name_to_vector_size = VectorMappings().index_name_to_vector_size()
        logger.debug(
            "Loaded vector index configuration",
            event_type="vector_index_config_loaded",
            index_name_to_vector_size=self.index_name_to_vector_size
        )
        
        logger.info(
            "CypherAgent initialized",
            event_type="cypher_agent_initialized",
            component="CypherAgent.__init__",
            llm_config=llm_config.model_dump(),
            neo4j_config={
                "uri": neo4j_config.neo4j_uri,
                "database": neo4j_config.neo4j_db_name,
            },
            top_k=top_k,
            debug_mode=debug_mode,
            benchmark_mode=benchmark_mode
        )

    def trim_messages(self, state: CypherAgentState, new_messages: list[BaseMessage]) -> list[BaseMessage | RemoveMessage]:
        """
        Keep only the last N messages (configured by AgentConfig.keep_last_n_messages)
        using RemoveMessage so the add_messages reducer can prune old history.
        """
        existing_messages = list(state.get("messages") or [])
        if len(existing_messages) + len(new_messages) <= AgentConfig().keep_last_n_messages:
            return existing_messages + new_messages
        
        combined_messages = existing_messages + new_messages

        logger.debug(
            "Trimming message history",
            event_type="trimming_message_history",
            component="CypherAgent.trim_messages",
            existing_message_count=len(existing_messages),
            new_message_count=len(new_messages),
            combined_message_count=len(combined_messages),
            retained_message_count=AgentConfig().keep_last_n_messages
        )

        # Always rewrite the bounded window to avoid relying on merge behavior
        # when the list is still below the limit.
        return [RemoveMessage(id=REMOVE_ALL_MESSAGES), *combined_messages[-AgentConfig().keep_last_n_messages:]]
    
    @log_execution_time(logger, component="CypherAgent.initialize_state")
    def biological_relevance_validation_node(self, state: CypherAgentState):

        logger.info(
            "Starting biological relevance validation",
            event_type="biological_relevance_validation_started",
            component="CypherAgent.biological_relevance_validation_node",
            question=state["question"]
        )

        prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(
                    BIOLOGICAL_RELEVANCE_VALIDATION_TEMPLATE
                ),
                HumanMessagePromptTemplate.from_template("{question}")
            ])
        
        verdict_llm = self.llm_factory.create_biological_relevance_validator_llm()

        messages = prompt.format_messages(question=state["question"])

        verdict = verdict_llm.invoke(
            messages,
            config={
                "metadata": {
                    "node_name": "biological_relevance_validation",
                }
            }
        )

        logger.info(
            "Completed biological relevance validation",
            event_type="biological_relevance_validation_completed",
            component="CypherAgent.biological_relevance_validation_node",
            question=state["question"],
            verdict=verdict["parsed"].relevant,
            reason=verdict["parsed"].reason
        )
        return {
            "biological_relevance": verdict["parsed"].relevant,
            "final_answer": f"Your question is outside the biological/biomedical domain.\nReason: {verdict['parsed'].reason}" if verdict["parsed"].relevant is False else None,
        }        
    
    def route_after_biological_relevance_validation(self, state: CypherAgentState) -> Literal["entity_resolution", "generate_cypher", "end"]:
        if state["biological_relevance"] is False:
            logger.info(
                "Routing to end because question is outside biology/biomedical domain",
                event_type="route_selected",
                component="CypherAgent.route_after_biological_relevance_validation",
                route="end"
            )
            return "end"
        
        elif AgentConfig().enable_entity_resolution:
            logger.info(
                "Routing to entity resolution",
                event_type="route_selected",
                component="CypherAgent.route_after_biological_relevance_validation",
                route="entity_resolution"
            )
            return "entity_resolution"
        
        logger.info(
            "Routing to cypher generation",
            event_type="route_selected",
            component="CypherAgent.route_after_biological_relevance_validation",
            route="generate_cypher"
        )
        return "generate_cypher"
    
    @log_execution_time(logger, component="CypherAgent.entity_resolution_node")
    def entity_resolution_node(self, state: CypherAgentState):

        logger.info(
            "Starting entity resolution",
            event_type="entity_resolution_started",
            component="CypherAgent.entity_resolution_node",
            question=state["question"]
        )
        
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(ENTITY_RESOLUTION_TEMPLATE),
                HumanMessagePromptTemplate.from_template("User Question: {question}"),
            ]
        )

        entity_resolution_structured_llm = self.llm_factory.create_entity_resolution_llm()
        entity_resolution_llm_with_tools = self.llm_factory.create_entity_resolution_llm_with_tools(
            tools=[
                self.entity_resolver.entity_search_tool
            ]
        )

        # Extraction mode
        extracted_entities = self.entity_resolver.run_entity_llm_stage(
            mode="extraction",
            question=state["question"],
            llm=entity_resolution_structured_llm,
            prompt=prompt
        )

        logger.debug(
            "Completed entity extraction stage",
            event_type="entity_extraction_completed",
            component="CypherAgent.entity_resolution_node",
            question=state["question"],
            extracted_entities=extracted_entities.model_dump() if extracted_entities else "No entities extracted"
        )

        if not extracted_entities or not hasattr(extracted_entities, "entities") or not extracted_entities.entities:
            logger.warning(
                "No entities extracted from the question",
                event_type="entity_extraction_warning",
                component="CypherAgent.entity_resolution_node",
                question=state["question"]
            )
            return {"resolved_entities": "No entities extracted"}
            
        
        # Tool call mode
        tool_plan = self.entity_resolver.run_entity_llm_stage(
            mode="tool call",
            question=state["question"],
            llm=entity_resolution_llm_with_tools,
            prompt=prompt,
            extracted_entities=extracted_entities.model_dump_json()
        )
       
        if len(tool_plan.tool_calls) != len(extracted_entities.entities):

            # This means the number of tool calls planned by the LLM does not match the number of entities extracted, which is an error. 
            logger.warning(
                "Mismatch between planned tool calls and extracted entities",
                event_type="entity_resolution_failed",
                component="CypherAgent.entity_resolution_node",
                question=state["question"],
                planned_tool_call_count=len(tool_plan.tool_calls),
                extracted_entity_count=len(extracted_entities.entities),
                planned_tool_calls=tool_plan.tool_calls,
                extracted_entities=extracted_entities.entities
            )
            return {"resolved_entities": (
                f"Length of tool calls ({len(tool_plan.tool_calls)}) does not match length of extracted entities ({len(extracted_entities.entities)})."
                 " This indicates a mismatch between the LLM's planned tool calls and the initially extracted entities, which may lead to incorrect processing."    
            )}
        

        tool_call_results: list[EntityToolExecution] = []
        for tool_call in tool_plan.tool_calls:
            single_tool_request = AIMessage(
                content=tool_plan.content if isinstance(tool_plan.content, str) else "",
                tool_calls=[tool_call],
            )

            result = self.entity_resolver.run_single_entity_tool_call_with_retry(
                tool_call=tool_call,
                question=state["question"],
                llm=entity_resolution_llm_with_tools,
                prompt=prompt,
                prior_messages=[single_tool_request],
            )
            tool_call_results.append(result)

        resolution_messages: list[BaseMessage] = []
        for call_result in tool_call_results:
            resolution_messages.extend(call_result.message_history)

        logger.debug(
            "Completed entity tool calls",
            event_type="entity_tool_calls_completed",
            component="CypherAgent.entity_resolution_node",
            question=state["question"],
            tool_call_count=len(tool_call_results),
            tool_call_results=tool_call_results
        )

        # Resolution mode
        resolution_result = self.entity_resolver.run_entity_llm_stage(
            mode="resolution",
            question=state["question"],
            llm=entity_resolution_structured_llm,
            prompt=prompt,
            extracted_entities=extracted_entities.model_dump_json(),
            prior_messages=resolution_messages
        )

        if resolution_result:
            resolved_entities_list = [
                    {
                    "entity_name_in_user_question": entity.entity_string,
                    "resolved_entity_name_in_db": entity.resolved_name
                    }
                for entity in resolution_result.entities
                if entity.resolved_name
            ]

        if not resolution_result or not resolved_entities_list:
            logger.warning(
                "No entities resolved after tool calls",
                event_type="entity_resolution_warning",
                component="CypherAgent.entity_resolution_node",
                question=state["question"],
                tool_call_results=tool_call_results,
                resolution_result=resolution_result.model_dump()
             )
        
        logger.info(
            "Completed entity resolution",
            event_type="entity_resolution_completed",
            component="CypherAgent.entity_resolution_node",
            question=state["question"],
            resolved_entities=resolved_entities_list
        )
        
        return {
            "resolved_entities": resolved_entities_list if resolved_entities_list else "No entities resolved"
        }

    @log_execution_time(logger, component="CypherAgent.generate_cypher_node")
    def generate_cypher_node(self, state: CypherAgentState):

        logger.info(
            "Starting cypher generation",
            event_type="cypher_generation_started",
            component="CypherAgent.generate_cypher_node",
            question=state["question"],
            has_resolved_entities=bool(state.get("resolved_entities")) and not isinstance(state.get("resolved_entities"), str),
            resolved_entities=state.get("resolved_entities")
         )

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(CYPHER_GENERATION_TEMPLATE if state["cypher_mode"] == "db_search" else VECTOR_SEARCH_CYPHER_GENERATION_TEMPLATE),
                MessagesPlaceholder("chat_history"),
                HumanMessagePromptTemplate.from_template("User Question: {question}"),
            ]
        )

        resolved_entities = state.get("resolved_entities")
        # condition the prompt based on the cypher_mode. If it's db_search, we provide the graph schema information. If it's vector_search, we provide the relevant vector index information along with the graph schema.
        if state["cypher_mode"] == "db_search":
            messages = prompt.format_messages(
                node_types=self.graph_schema["nodes"],
                node_properties=self.graph_schema["node_properties"],
                edge_properties=self.graph_schema["edge_properties"],
                edges=self.graph_schema["edges"],
                chat_history=state["messages"],
                question=state["question"],
                resolved_entities="Null" if not resolved_entities or isinstance(resolved_entities, str) else resolved_entities
            )

            logger.debug(
                "Formatted cypher generation prompt for db search",
                event_type="cypher_generation_prompt_formatted",
                component="CypherAgent.generate_cypher_node",
                question=state["question"],
                resolved_entities=resolved_entities,
            )
        else:
            messages = prompt.format_messages(
                vector_index=state["vector_index"],
                node_types=self.graph_schema["nodes"],
                node_properties=self.graph_schema["node_properties"],
                edge_properties=self.graph_schema["edge_properties"],
                edges=self.graph_schema["edges"],
                chat_history=state["messages"],
                question=state["question"],
                resolved_entities="Null" if not resolved_entities or isinstance(resolved_entities, str) else resolved_entities
            )

            logger.debug(
                "Formatted cypher generation prompt for vector search",
                event_type="cypher_generation_prompt_formatted",
                component="CypherAgent.generate_cypher_node",
                question=state["question"],
                vector_index=state["vector_index"],
                resolved_entities=resolved_entities,
            )

        # invoke LLM to get cypher query
        response = self.cypher_llm.invoke(
            messages,
            config={
                "metadata": {
                    "node_name": "generate_cypher",
                }
            }
        )

        if state["cypher_mode"] == "vector_search" and state["embedding"] is not None and state["vector_index"] is not None:

            raw_cypher = response["parsed"].cypher_query
            if "{user_input}" not in raw_cypher:
                raise ValueError(
                    "Vector upload flow requires a query template containing {user_input}, "
                    "but the model generated a node-based vector query instead."
                )
            # If it's a vector search with user given embedding, we need to add it to generated cypher query by replacing the placeholder with the actual embedding values.
            # This is because the LLM generates a cypher query with a placeholder for the embedding, and we need to fill in that placeholder with the actual embedding values provided by the user.
            cypher_query = raw_cypher.format(
                user_input=handle_embedding(
                    embedding=np.array(state["embedding"]),
                    vector_index=state["vector_index"],
                    index_name_to_vector_size=self.index_name_to_vector_size,
                )
            )

            logger.debug(
                "Formatted cypher query with user embedding for vector search",
                event_type="cypher_query_formatted_with_embedding",
                component="CypherAgent.generate_cypher_node",
                question=state["question"],
                vector_index=state["vector_index"],
                embedding_shape=np.array(state["embedding"]).shape,
                formatted_cypher_query=cypher_query
            )
        else:
            cypher_query = response["parsed"].cypher_query

        
        logger.info(
            "Completed cypher generation",
            event_type="cypher_generation_completed",
            component="CypherAgent.generate_cypher_node",
            question=state["question"],
            generated_cypher=cypher_query
        )

        return {
            "current_cypher": cypher_query,
            "retry_count": 0,
            "cypher_source": "generation",
        }

    @log_execution_time(logger, component="CypherAgent.validate_cypher_node")
    def validate_cypher_node(self, state: CypherAgentState):

        query = state["current_cypher"]
        if (query == "NO_VALID_SCHEMA_PATH" and state.get("no_valid_schema_path", False) is False) or (state.get("no_valid_schema_path", False) is True and query != "NO_VALID_SCHEMA_PATH"):
            logger.error(
                "Inconsistent state detected between current_cypher and no_valid_schema_path flag. If `no_valid_schema_path` is True, then `current_cypher` should be `NO_VALID_SCHEMA_PATH`, and if `no_valid_schema_path` is False, then `current_cypher` should not be `NO_VALID_SCHEMA_PATH`. This inconsistency indicates a logical error in the state management of the agent.",
                event_type="inconsistent_state_error",
                component="CypherAgent.validate_cypher_node",
                current_cypher=query,
                no_valid_schema_path_flag=state.get("no_valid_schema_path", False)
            )

            raise ValueError(
                f"Inconsistent state: current_cypher is '{query}' but no_valid_schema_path flag is {state.get('no_valid_schema_path', False)}. These should be consistent with each other."
            )
        
        if state.get("no_valid_schema_path", False):
            logger.info(
                "Skipping cypher validation because no_valid_schema_path flag is set to True, indicating that the agent has determined that the user's question cannot be satisfied by any valid path in the schema.",
                event_type="cypher_validation_skipped",
                component="CypherAgent.validate_cypher_node",
                current_cypher=query,
                no_valid_schema_path_flag=state.get("no_valid_schema_path", False)
            )
            return {
                "is_ok": False
            }


        logger.info(
            "Starting cypher validation",
            event_type="cypher_validation_started",
            component="CypherAgent.validate_cypher_node",
            current_cypher=query,
            retry_count=state.get("retry_count", 0)
        )

        correction_result = validate_and_correct_query(
            query=query,
            cfg=Neo4jConfig(),
            edge_schema=self.graph_schema["edges"],
            cypher_mode=state["cypher_mode"],
        )

        is_valid = correction_result["ok"]
        checks = correction_result["checks"]

        # if status is valid and corrected query is provided, something is wrong. Should be checked.
        if is_valid is False and correction_result.get("corrected_query") is not None:
            logger.error(
                "Validation failed but corrected query is provided, which should not happen. Please check the validation logic.",
                event_type="cypher_validation_failed",
                component="CypherAgent.validate_cypher_node",
                correction_result=correction_result
            )

            raise ValueError(
                "Corrected query should not be provided when the original query is invalid."
            )

        attempt = CypherAttempt(
            attempt_number=state.get("retry_count", 0) + 1,
            cypher_query=query,
            is_valid=is_valid,
            syntax_valid=checks["syntax"]["ok"],
            schema_valid=checks["schema"]["ok"],
            property_valid=checks["properties"]["ok"],
            syntax_errors=checks["syntax"]["message"] if not checks["syntax"]["ok"] else None,
            schema_errors=checks["schema"]["message"] if not checks["schema"]["ok"] else None,
            property_errors=checks["properties"]["message"] if not checks["properties"]["ok"] else None,
            execution_ok=False,
            execution_error=None,
            attempt_source=state.get("cypher_source"),
        )

        attempts = list(state.get("cypher_attempts") or [])
        attempts.append(attempt)

        updated_state = {
            "cypher_attempts": attempts,
        }

        logger.info(
            "Completed cypher validation",
            event_type="cypher_validation_completed",
            component="CypherAgent.validate_cypher_node",
            current_cypher=query,
            is_valid=is_valid,
            syntax_valid=attempt["syntax_valid"],
            schema_valid=attempt["schema_valid"],
            property_valid=attempt["property_valid"],
            attempt_source=attempt["attempt_source"],
            attempt_number=attempt["attempt_number"],
            total_attempts=len(attempts)
        )

        if is_valid and correction_result.get("corrected_query"):
            updated_state["current_cypher"] = correction_result["corrected_query"]
            logger.debug(
                "Applied corrected cypher query from validation step",
                event_type="cypher_validation_corrected",
                component="CypherAgent.validate_cypher_node",
                original_query=query,
                corrected_query=correction_result["corrected_query"]
            )

        return updated_state

    def route_after_validate(self, state: CypherAgentState) -> Literal["execute_cypher", "retry", "web_search", "fail", "human_review"]:
        if state.get("no_valid_schema_path", False):
            logger.info(
                "Routing to fail because no valid schema path exists for the user's question.",
                event_type="route_selected",
                component="CypherAgent.route_after_validate",
                route="fail",
            )
            return "fail"
        
        if state["cypher_attempts"][-1].get("is_valid", False):
            
            if not self.benchmark_mode and state.get("execution_mode", "generate_and_run") == "generate":
                logger.info(
                    "Routing to human review because execution mode is set to generate",
                    event_type="route_selected",
                    component="CypherAgent.route_after_validate",
                    route="human_review",
                    execution_mode=state.get("execution_mode")
                )
                return "human_review"
            
            logger.info(
                "Routing to execute cypher",
                event_type="route_selected",
                component="CypherAgent.route_after_validate",
                route="execute_cypher",
                execution_mode=state.get("execution_mode"),
                last_cypher_attempt=state["cypher_attempts"][-1]
            )

            return "execute_cypher"

        if state.get("retry_count", 0) < AgentConfig().max_iterations:
            logger.warning(
                "Routing to error correction after failed validation",
                event_type="route_selected",
                component="CypherAgent.route_after_validate",
                route="retry",
                retry_count=state.get("retry_count", 0),
                max_iterations=AgentConfig().max_iterations,
                last_cypher_attempt=state["cypher_attempts"][-1]
            )
            return "retry"

        if AgentConfig().enable_web_search and not state.get("web_search_used", False):
            logger.warning(
                "Routing to web search after exhausted validation fallbacks",
                event_type="route_selected",
                component="CypherAgent.route_after_validate",
                route="web_search",
                retry_count=state.get("retry_count", 0),
                max_iterations=AgentConfig().max_iterations,
                last_cypher_attempt=state["cypher_attempts"][-1],
                web_search_enabled=AgentConfig().enable_web_search,
                web_search_used=state.get("web_search_used", False)
            )
            return "web_search"
        
        logger.warning(
            "Routing to fail",
            event_type="route_selected",
            component="CypherAgent.route_after_validate",
            route="fail",
            retry_count=state.get("retry_count", 0),
            max_iterations=AgentConfig().max_iterations,
            last_cypher_attempt=state["cypher_attempts"][-1],
            web_search_enabled=AgentConfig().enable_web_search,
            web_search_used=state.get("web_search_used", False)
        )

        return "fail"
    
    @log_execution_time(logger, component="CypherAgent.human_review_node")
    def human_review_node(self, state: CypherAgentState):

        logger.info(
            "Starting human review",
            event_type="human_review_started",
            component="CypherAgent.human_review_node",
            question=state["question"],
            current_cypher=state["current_cypher"]
        )
        review = interrupt({
            "question": state["question"],
            "current_cypher": state["current_cypher"],
        })

        action = review.get("action")
        if action == "approve":
            logger.info(
                "Human review approved",
                event_type="human_review_approved",
                component="CypherAgent.human_review_node",
                action=action,
            )
            return {
                "human_review_action": "approve"
            }
        
        elif action == "edit":
            edited_cypher = review.get("edited_cypher")
            if not edited_cypher:
                logger.error(
                    "Edited cypher is missing in human review edit action",
                    event_type="human_review_failed",
                    component="CypherAgent.human_review_node",
                    action=action,
                    edited_cypher=edited_cypher
                )

                raise ValueError("Edited Cypher must be a non-empty string.")
            
            logger.info(
                "Human edit provided",
                event_type="human_review_edited",
                component="CypherAgent.human_review_node",
                payload=review,
            )

            return {
                "human_review_action": "edit",
                "current_cypher": edited_cypher,
                "cypher_source": "human_edit"
            }
        
        logger.error(
            "Invalid action in human review",
            event_type="human_review_failed",
            component="CypherAgent.human_review_node",
            payload=review
        )
        
        raise ValueError("Review payload must contain action='approve' or action='edit'.")

    @log_execution_time(logger, component="CypherAgent.execute_cypher_node")
    def execute_cypher_node(self, state: CypherAgentState):
        logger.info(
            "Starting cypher execution",
            event_type="cypher_execution_started",
            component="CypherAgent.execute_cypher_node",
            current_cypher=state["current_cypher"],
            retry_count=state.get("retry_count", 0)
        )

        query = state["current_cypher"]
        if self.disable_limit:
            logger.warning(
                "Executing cypher query with limit disabled. This may result in large data retrieval.",
                event_type="cypher_execution_limit_disabled",
                component="CypherAgent.execute_cypher_node",
                current_cypher=query
            )
            result = self.neo4j_client.execute_query(query, disable_limit=True)
        else:
            result = self.neo4j_client.execute_query(query, top_k=self.top_k)
            
        attempts = list(state.get("cypher_attempts") or [])
        if not attempts:
            logger.error(
                "No cypher attempts found for execution",
                event_type="cypher_execution_failed",
                component="CypherAgent.execute_cypher_node",
                current_cypher=query,
                retry_count=state.get("retry_count", 0)
            )

            raise ValueError("No cypher attempt found for execution.")

        last_attempt = attempts[-1].copy()

        if isinstance(result, str):
            # An error occurred during execution
            last_attempt["execution_ok"] = False
            last_attempt["execution_error"] = result
            last_attempt["is_valid"] = False
            attempts[-1] = last_attempt

            logger.warning(
                "Cypher execution failed",
                event_type="cypher_execution_failed",
                component="CypherAgent.execute_cypher_node",
                current_cypher=query,
                error=result
            )

            return {
                "cypher_attempts": attempts,
                "is_ok": False,
                "execution_result": None,
            }
        elif result == []:
            # No results found, but execution was successful
            last_attempt["execution_ok"] = False
            last_attempt["execution_error"] = "Query executed successfully but returned no results."
            last_attempt["is_valid"] = False
            attempts[-1] = last_attempt

            logger.warning(
                "Cypher execution returned no results",
                event_type="cypher_execution_no_results",
                component="CypherAgent.execute_cypher_node",
                current_cypher=query
            )

            return {
                "cypher_attempts": attempts,
                "is_ok": False,
                "execution_result": None,
            }
        else:
            # Successful execution
            last_attempt["execution_ok"] = True
            last_attempt["execution_error"] = None
            last_attempt["is_valid"] = True
            attempts[-1] = last_attempt

            logger.info(
                "Cypher execution successful",
                event_type="cypher_execution_successful",
                component="CypherAgent.execute_cypher_node",
                current_cypher=query,
                result_count=len(result) if isinstance(result, list) else "unknown",
                execution_result=result
            )

            return {
                "cypher_attempts": attempts,
                "is_ok": True,
                "execution_result": result,
            }

    def route_after_execution(self, state: CypherAgentState) -> Literal["answer", "retry", "web_search", "fail", "end"]:
        if state.get("is_ok", False):
            if self.benchmark_mode is True:
                logger.info(
                    "Routing to end in benchmark mode after successful execution",
                    event_type="route_selected",
                    component="CypherAgent.route_after_execution",
                    route="end",
                    current_cypher=state["current_cypher"],
                    benchmark_mode=self.benchmark_mode
                )
                return "end"
            
            logger.info(
                "Routing to answer generation after successful execution",
                event_type="route_selected",
                component="CypherAgent.route_after_execution",
                route="answer",
                current_cypher=state["current_cypher"],
            )
            return "answer"

        if state.get("retry_count", 0) < AgentConfig().max_iterations:
            logger.warning(
                "Routing to error correction after failed execution",
                event_type="route_selected",
                component="CypherAgent.route_after_execution",
                route="retry",
                retry_count=state.get("retry_count", 0),
                execution_result=state.get("execution_result"),
            )
            return "retry"

        if AgentConfig().enable_web_search and not state.get("web_search_used", False):
            logger.warning(
                "Routing to web search after exhausted execution retries",
                event_type="route_selected",
                component="CypherAgent.route_after_execution",
                route="web_search",
                retry_count=state.get("retry_count", 0),
                max_iterations=AgentConfig().max_iterations,
                execution_result=state.get("execution_result"),
                web_search_enabled=AgentConfig().enable_web_search,
                web_search_used=state.get("web_search_used", False)
            )
            return "web_search"

        logger.warning(
            "Routing to fail after exhausted execution fallbacks",
            event_type="route_selected",
            component="CypherAgent.route_after_execution",
            route="fail"
        )

        return "fail"

    @log_execution_time(logger, component="CypherAgent.error_correction_node")
    def error_correction_node(self, state: CypherAgentState):
        # -------------------------------------------------
        # Should I add entity resolution results to this LLM's prompt?
        # -------------------------------------------------

        logger.info(
            "Starting error correction",
            event_type="error_correction_started",
            component="CypherAgent.error_correction_node",
            question=state["question"],
            current_cypher=state["current_cypher"],
            retry_count=state.get("retry_count", 0),
            attempt_count=len(state.get("cypher_attempts") or []),
            no_valid_schema_path_flag=state.get("no_valid_schema_path", False)
         )
        attempts = state.get("cypher_attempts") or []
        if not attempts:
            logger.error(
                "Error correction called without attempts",
                event_type="error_correction_failed",
                component="CypherAgent.error_correction_node",
                question=state["question"],
                current_cypher=state["current_cypher"],
                retry_count=state.get("retry_count", 0)
            )
            raise ValueError("No cypher attempts available for error correction.")

        if all(attempts[-1][key] for key in ["is_valid", "execution_ok"]):
            raise ValueError("The last cypher attempt is already valid and executed successfully. Error correction should not be triggered.")

        last_attempt = attempts[-1].copy()

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(ERROR_CORRECTION_TEMPLATE),
                HumanMessagePromptTemplate.from_template("User Question: {question}"),
            ]
        )

        errors = "Errors in the last attempt:\n"
        for key, value in last_attempt.items():
            if key in ["syntax_errors", "schema_errors", "property_errors", "execution_error"] and value:
                errors += f"{key}: {value}\n"

        cypher_history = "\n".join(
            [
                f"attempt {idx}: {attempt.get('cypher_query')}"
                for idx, attempt in enumerate(attempts, start=1)
            ]
        )

        messages = prompt.format_messages(
            last_cypher=state["current_cypher"],
            cypher_history=cypher_history,
            attempt_n=last_attempt["attempt_number"],
            vector_index=state.get("vector_index", "None"),
            errors=errors,
            node_types=self.graph_schema["nodes"],
            node_properties=self.graph_schema["node_properties"],
            edge_properties=self.graph_schema["edge_properties"],
            edges=self.graph_schema["edges"],
            question=state["question"],
        )

        response = self.cypher_llm.invoke(
            messages,
            config={
                "metadata": {
                    "node_name": "error_correction",
                }
            }
        )

        corrected_cypher = response["parsed"].cypher_query
        if corrected_cypher == "NO_VALID_SCHEMA_PATH":
            logger.info(
                "Error correction determined that no valid schema path exists",
                event_type="error_correction_no_valid_schema_path",
                component="CypherAgent.error_correction_node",
                question=state["question"],
                current_cypher=state["current_cypher"],
                retry_count=state.get("retry_count", 0),
                no_valid_schema_path_flag=True
            )
            return {
                "no_valid_schema_path": True,
                "final_answer": (
                    "I could not answer this question from the knowledge graph because "
                    "no valid schema path exists for the requested relation or node."
                ),
            }

        
        logger.info(
            "Completed error correction",
            event_type="error_correction_completed",
            component="CypherAgent.error_correction_node",
            question=state["question"],
            corrected_cypher=corrected_cypher,
            retry_count=state.get("retry_count", 0) + 1,
            cypher_source="error_correction",
            no_valid_schema_path_flag=False
        )
        return {
            "current_cypher": corrected_cypher,
            "retry_count": state.get("retry_count", 0) + 1,
            "cypher_source": "error_correction",
            "no_valid_schema_path": False,  # reset this flag in case it was set in the previous attempt
        }
    
    @log_execution_time(logger, component="CypherAgent.generate_answer_node")
    def generate_answer_node(self, state: CypherAgentState):

        if state.get("execution_result") is None:
            raise ValueError("Execution result is empty. Somehow we reached answer generation without a successful execution. This should not happen.")

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(CYPHER_OUTPUT_PARSER_TEMPLATE),
                MessagesPlaceholder("chat_history"),
                HumanMessagePromptTemplate.from_template("User Question: {question}"),
            ]
        )

        messages = prompt.format_messages(
            output=state["execution_result"],
            question=state["question"],
            chat_history=state["messages"],
        )

        response = self.output_parser_llm.invoke(
            messages,
            config={
                "metadata": {
                    "node_name": "generate_answer",
                }
            }
        )

        new_messages = [
            HumanMessage(content=f"User question: {state['question']}"),
            AIMessage(content=f"Generated cypher: {state['current_cypher']}"),
            AIMessage(content=f"Answer: {response['parsed'].final_answer}"),
        ]

        return {
            "final_answer": response["parsed"].final_answer,
            "messages": self.trim_messages(state, new_messages),
        }
    
    @log_execution_time(logger, component="CypherAgent.follow_up_question_node")
    def follow_up_question_node(self, state: CypherAgentState):

        if not state.get("final_answer"):
            raise ValueError("Final answer is empty. Cannot generate follow-up questions.")

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(FOLLOW_UP_QUESTIONS_TEMPLATE if state["cypher_mode"] == "db_search" else VECTOR_SEARCH_FOLLOW_UP_QUESTIONS_TEMPLATE),
                MessagesPlaceholder("chat_history"),
                HumanMessagePromptTemplate.from_template("User Question: {question}")
            ]
        )

        follow_up_question_llm = self.llm_factory.create_follow_up_question_llm()

        if state["cypher_mode"] == "db_search":
            messages = prompt.format_messages(
                question=state["question"],
                chat_history=state["messages"],
                answer=state["final_answer"]
            )
        else:
            messages = prompt.format_messages(
                question=state["question"],
                chat_history=state["messages"],
                answer=state["final_answer"],
                vector_category=state["vector_index"]
            )
        
        response = follow_up_question_llm.invoke(
            messages,
            config={
                "metadata": {
                    "node_name": "follow_up_questions",
                }
            }
        )

        return {
            "follow_up_questions": response["parsed"].to_list()
        }

    def _validate_web_search_preconditions(self, state: CypherAgentState) -> list[CypherAttempt]:
        attempts = state.get("cypher_attempts") or []

        checks = {
            "web_search_disabled": (
                not AgentConfig().enable_web_search,
                "Web search is not enabled in the agent configuration.",
            ),
            "final_answer_exists": (
                state.get("final_answer") is not None,
                f"Final answer is already generated. Web search node should not be triggered. Final answer: {state.get('final_answer')}",
            ),
            "retry_not_exhausted": (
                state.get("retry_count", 0) < AgentConfig().max_iterations,
                f"Retry count has not yet reached the maximum iterations. Current retry count: {state.get('retry_count', 0)}, Max iterations: {AgentConfig().max_iterations}",
            ),
            "web_search_already_used": (
                state.get("web_search_used", False),
                f"Web search has already been used. Web search used: {state.get('web_search_used', False)}",
            ),
            "no_attempts": (
                not attempts,
                "No cypher attempts available for web search.",
            ),
            "last_attempt_already_successful": (
                bool(attempts) and all(attempts[-1][key] for key in ["is_valid", "execution_ok"]),
                "The last cypher attempt is already valid and executed successfully. Web search should not be triggered.",
            ),
        }

        for _, (failed, message) in checks.items():
            if failed:
                raise ValueError(message)
        
        return attempts

    @log_execution_time(logger, component="CypherAgent.web_search_node")
    def web_search_node(self, state: CypherAgentState):

        attempts = self._validate_web_search_preconditions(state)      

        last_attempt = attempts[-1].copy()
        
        # Should I provide chat history in the web search prompt? 
        # Maybe not, to save tokens and because web search is more of a fallback when we are stuck, so the immediate context of the question and the failed attempts might be more relevant.
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(WEB_SEARCH_TEMPLATE),
                MessagesPlaceholder("chat_history"),
                HumanMessagePromptTemplate.from_template("User Question: {question}"),
            ]
        )

        # For web search. Uses CypherStrategy from llm_factory.py for structured output.
        web_search_llm = self.llm_factory.create_web_search_llm(AgentConfig().web_search_model) 


        errors = "Errors in the last attempt:\n"
        for key, value in last_attempt.items():
            if key in ["syntax_errors", "schema_errors", "property_errors", "execution_error"] and value:
                errors += f"{key}: {value}\n"

        cypher_history = "\n".join(
            [
                f"attempt {idx}: {attempt.get('cypher_query')}"
                for idx, attempt in enumerate(attempts, start=1)
            ]
        )

        messages = prompt.format_messages(
            last_cypher=state["current_cypher"],
            cypher_history=cypher_history,
            errors=errors,
            vector_index=state.get("vector_index", "None"),
            neo4j_version=self.neo4j_client.get_db_version(),
            node_types=self.graph_schema["nodes"],
            node_properties=self.graph_schema["node_properties"],
            edge_properties=self.graph_schema["edge_properties"],
            edges=self.graph_schema["edges"],
            question=state["question"],
            chat_history=state["messages"],
        )

        # use web search LLM
        response = web_search_llm.invoke(
            messages,
            config={
                "metadata": {
                    "node_name": "web_search",
                }
            }
        )

        return {
            "current_cypher": response["parsed"].cypher_query,
            "retry_count": state.get("retry_count", 0) + 1,
            "cypher_source": "web_search",
            "web_search_used": True,
        }


    def fail_node(self, state: CypherAgentState):
        if state.get("final_answer") is not None:
            return {
                "final_answer": state["final_answer"]
            }

        return {
            "final_answer": "I'm sorry, but I couldn't find an answer to your question after multiple attempts. Please try rephrasing your question or ask about something else.",
        }
    
    def build_benchmark_mode_graph(self, checkpointer):
        builder = StateGraph(CypherAgentState)
        if AgentConfig().enable_entity_resolution:
            builder.add_node("entity_resolution", self.entity_resolution_node)
            builder.add_edge(START, "entity_resolution")
            builder.add_edge("entity_resolution", "generate_cypher")
        else:
            builder.add_edge(START, "generate_cypher")

        builder.add_node("generate_cypher", self.generate_cypher_node)
        builder.add_node("validate_cypher", self.validate_cypher_node)
        builder.add_node("execute_cypher", self.execute_cypher_node)
        builder.add_node("web_search", self.web_search_node)
        builder.add_node("fail", self.fail_node)
        builder.add_node("error_correction", self.error_correction_node)

        
        
        builder.add_edge("generate_cypher", "validate_cypher")

        builder.add_conditional_edges(
            "validate_cypher",
            self.route_after_validate,
            {
                "execute_cypher": "execute_cypher",
                "retry": "error_correction",
                "web_search": "web_search",
                "fail": "fail",
            },
        )

        builder.add_conditional_edges(
            "execute_cypher",
            self.route_after_execution,
            {
                "end": END, # In benchmark mode, we end after successful execution
                "retry": "error_correction",
                "web_search": "web_search",
                "fail": "fail",
            },
        )

        builder.add_edge("error_correction", "validate_cypher")
        builder.add_edge("web_search", "validate_cypher")
        builder.add_edge("fail", END)
        
        return builder.compile(checkpointer=checkpointer, debug=self.debug_mode)


    def build_graph(self, checkpointer):
        # In benchmark mode, we want to skip the nodes that are not relevant for evaluating the core cypher generation and execution capabilities.
        if self.benchmark_mode:
            return self.build_benchmark_mode_graph(checkpointer)
        

        builder = StateGraph(CypherAgentState)

        builder.add_node("biological_relevance_validation", self.biological_relevance_validation_node)
        builder.add_node("entity_resolution", self.entity_resolution_node)
        builder.add_node("generate_cypher", self.generate_cypher_node)
        builder.add_node("validate_cypher", self.validate_cypher_node)
        builder.add_node("human_review", self.human_review_node)
        builder.add_node("execute_cypher", self.execute_cypher_node)
        builder.add_node("web_search", self.web_search_node)
        builder.add_node("fail", self.fail_node)
        builder.add_node("answer", self.generate_answer_node)
        builder.add_node("error_correction", self.error_correction_node)
        builder.add_node("follow_up_questions", self.follow_up_question_node)

        

        builder.add_conditional_edges(
            "biological_relevance_validation",
            self.route_after_biological_relevance_validation,
            {
                "entity_resolution": "entity_resolution",
                "generate_cypher": "generate_cypher",
                "end": END,
            },
        )
        builder.add_conditional_edges(
            "validate_cypher",
            self.route_after_validate,
            {
                "execute_cypher": "execute_cypher",
                "retry": "error_correction",
                "web_search": "web_search",
                "fail": "fail",
                "human_review": "human_review",
            },
        )
        builder.add_conditional_edges(
            "execute_cypher",
            self.route_after_execution,
            {
                "answer": "answer",
                "retry": "error_correction",
                "web_search": "web_search",
                "fail": "fail",
            },
        )

        builder.add_edge(START, "biological_relevance_validation")
        builder.add_edge("entity_resolution", "generate_cypher")
        builder.add_edge("generate_cypher", "validate_cypher")
        builder.add_edge("error_correction", "validate_cypher")
        builder.add_edge("web_search", "validate_cypher")
        builder.add_edge("answer", "follow_up_questions")
        builder.add_edge("follow_up_questions", END)
        builder.add_edge("fail", END)
        builder.add_edge("human_review", "execute_cypher")
        
        return builder.compile(checkpointer=checkpointer, debug=self.debug_mode)


def handle_embedding(embedding: np.ndarray, vector_index: str, index_name_to_vector_size: dict[str, int]) -> list[float]:
    if np.isnan(embedding).any():
        raise ValueError("NaN value found in provided embedding")
    
    if np.isinf(embedding).any():
        raise ValueError("Infinite value found in provided embedding")
    
    if not np.issubdtype(embedding.dtype, np.floating):
        raise ValueError("Input embedding must be a float array")
    
    if len(embedding.shape) > 1:
        raise ValueError("Input embedding must be a 1D array")
    
    if embedding.shape[0] != index_name_to_vector_size[vector_index]:
        raise ValueError(
                f"Invalid embedding vector shape provided. Expected {index_name_to_vector_size[vector_index]}, got {embedding.shape[0]}"
            )
    
    return embedding.tolist()
