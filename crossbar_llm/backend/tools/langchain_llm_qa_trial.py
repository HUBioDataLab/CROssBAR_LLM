import json
import logging
import os
import sys
import traceback
from datetime import datetime
from time import time

from dotenv import load_dotenv
from wrapt_timeout_decorator import *

# Import path
current_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# Import required modules for Neo4J connection and schema extraction
from typing import Any, Dict, Literal, Optional, Union

import numpy as np
import pandas as pd
from .neo4j_query_corrector import correct_query
from .neo4j_query_executor_extractor import Neo4jGraphHelper
from .qa_templates import (
    CYPHER_GENERATION_PROMPT,
    CYPHER_OUTPUT_PARSER_PROMPT,
    VECTOR_SEARCH_CYPHER_GENERATION_PROMPT,
    FOLLOW_UP_QUESTIONS_PROMPT,
    FOLLOW_UP_QUESTIONS_SEMANTIC_PROMPT,
    CYPHER_ERROR_CORRECTION_PROMPT,
    CYPHER_EMPTY_RESULT_REGEN_PROMPT,
)
from .utils import Logger, timed_block, detailed_timer
from .structured_logger import (
    get_structured_logger,
    get_current_query_log,
    LLMCallLog,
    TokenUsage,
    timed_step,
    timed_operation,
)
from .llm_callback_handler import create_llm_callback, DetailedLLMCallback

from langchain_core.output_parsers import StrOutputParser
from langchain_anthropic import ChatAnthropic
from langchain_community.llms import Ollama, Replicate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_nvidia_ai_endpoints import ChatNVIDIA

# Import the Language Model wrappers
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, validate_call


def configure_logging(verbose=False, log_filename=None):
    """
    Configure logging for the application based on verbosity level.
    
    Note: File logging is handled by structured_logger.py, so we only set up
    console logging here. The log_filename parameter is ignored (kept for backward compatibility).
    
    Args:
        verbose (bool): Whether to show detailed debug logs
        log_filename (str): Deprecated - kept for backward compatibility
    """
    # Set up handlers based on verbosity
    handlers = []
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        handlers.append(console_handler)
    
    # Configure root logger (no file handler - structured_logger handles file logging)
    logging.basicConfig(
        handlers=handlers if handlers else None,
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True  # Override any existing configuration
    )
    
    # Log configuration completed
    log_level = "DEBUG" if verbose else "INFO"
    logging.info(f"Logging initialized with level: {log_level}")


class Config(BaseModel):
    """
    Config class for handling environment variables.
    It loads the variables from a .env file and makes them available as attributes.
    """

    load_dotenv()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "default")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY") or "default"
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "default")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "default")
    replicate_api_key: str = os.getenv("REPLICATE_API_KEY", "default")
    nvidia_api_key: str = os.getenv("NVIDIA_API_KEY", "default")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "default")
    neo4j_usr: str = os.getenv("NEO4J_USERNAME")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD")
    neo4j_db_name: str = os.getenv("NEO4J_DATABASE_NAME")
    neo4j_uri: str = os.getenv("NEO4J_URI")


class Neo4JConnection:
    """
    Neo4JConnection class to handle interactions with a Neo4J database.
    It encapsulates the connection details and provides methods to interact with the database.
    """

    def __init__(
        self,
        user: str,
        password: str,
        db_name: str,
        uri: str,
        reset_schema: bool = False,
        create_vector_indexes: bool = False,
    ):

        self.graph_helper = Neo4jGraphHelper(
            URI=uri,
            user=user,
            password=password,
            db_name=db_name,
            reset_schema=reset_schema,
            create_vector_indexes=create_vector_indexes,
        )

        self.schema = self.graph_helper.create_graph_schema_variables()

    @validate_call
    def execute_query(self, query: str, top_k: int = 6) -> list:
        """
        Method to execute a given Cypher query against the Neo4J database.
        It returns the top k results.
        """
        return self.graph_helper.execute(query, top_k)


class OpenAILanguageModel:
    """
    OpenAILanguageModel class for interacting with OpenAI's language models.
    It initializes the model with given API key and specified parameters.
    """

    def __init__(
        self, api_key: str, model_name: str = None, temperature: float | int = None
    ):
        self.model_name = model_name or "gpt-3.5-turbo-instruct"
        self.temperature = temperature or 0
        
        # Models that don't support temperature parameter
        no_temp_models = [
            "gpt-5.1",
            "gpt-5",
            "gpt-5-nano",
            "gpt-5-mini",
            "gpt-4.1",
            "o4-mini",
            "o3",
            "o3-mini",
            "o1",
            "o1-mini",
            "o1-pro",
        ]
        
        if self.model_name in no_temp_models:
            self.llm = ChatOpenAI(
                api_key=api_key,
                model_name=self.model_name,
                request_timeout=600,
                temperature=1,
            )
        else:
            self.llm = ChatOpenAI(
                api_key=api_key,
                model_name=self.model_name,
                temperature=self.temperature,
                request_timeout=600,
            )


class GoogleGenerativeLanguageModel:
    """
    GoogleGenerativeLanguageModel class for interacting with Google's Generative AI models.
    It initializes the model with given API key and specified parameters.
    """

    def __init__(
        self, api_key: str, model_name: str = None, temperature: float | int = None
    ):
        self.model_name = model_name or "gemini-1.5-pro-latest"
        self.temperature = temperature or 0
        self.llm = ChatGoogleGenerativeAI(
            api_key=api_key,
            model=self.model_name,
            temperature=self.temperature,
            request_timeout=600,
        )


class AnthropicLanguageModel:
    """
    AnthropicLanguageModel class for interacting with Anthropic's language models.
    It initializes the model with given API key and specified parameters.
    """

    def __init__(
        self, api_key: str, model_name: str = None, temperature: float | int = None
    ):
        self.model_name = model_name or "claude-3-opus-20240229"
        self.temperature = temperature or 0
        self.llm = ChatAnthropic(
            anthropic_api_key=api_key,
            model_name=self.model_name,
            temperature=self.temperature,
        )


class GroqLanguageModel:
    """
    GroqLanguageModel class for interacting with Groq's language models.
    It initializes the model with given API key and specified parameters.
    """

    def __init__(
        self, api_key: str, model_name: str = None, temperature: float | int = None
    ):
        self.model_name = model_name or "llama3-70b-8192"
        self.temperature = temperature or 0
        self.llm = ChatGroq(
            groq_api_key=api_key,
            model_name=self.model_name,
            temperature=self.temperature,
        )


class ReplicateLanguageModel:
    """
    ReplicateLanguageModel class for interacting with Replicate's language models.
    It initializes the model with given API key and specified parameters.
    """

    def __init__(
        self, api_key: str, model_name: str = None, temperature: float | int = None
    ):
        self.model_name = model_name or "replicate-1.0"
        self.temperature = temperature or 0
        self.llm = Replicate(
            replicate_api_key=api_key,
            model_name=self.model_name,
            temperature=self.temperature,
        )


class OllamaLanguageModel:
    """
    OllamaLanguageModel class for interacting with Ollama's language models.
    """

    def __init__(self, model_name: str = None, temperature: float | int = None):
        self.model_name = model_name or "codestral:latest"
        self.temperature = temperature or 0
        self.llm = Ollama(
            model=self.model_name, temperature=self.temperature, timeout=300
        )


class NVIDIALanguageModel:
    """
    NVIDIALanguageModel class for interacting with NVIDIA's language models.
    It initializes the model with given API key and specified parameters.
    """

    def __init__(
        self, api_key: str, model_name: str = None, temperature: float | int = None
    ):
        self.model_name = model_name or "meta/llama-3.1-405b-instruct"
        self.temperature = temperature or 0
        self.llm = ChatNVIDIA(
            api_key=api_key, model=self.model_name, temperature=self.temperature
        )


class OpenRouterLanguageModel:
    """
    OpenRouterLanguageModel class for interacting with OpenRouter's language models.
    It initializes the model with given API key and specified parameters.
    """

    def __init__(
        self, api_key: str, model_name: str = None, temperature: float | int = None,
        base_url: str = "https://openrouter.ai/api/v1"
    ):
        self.model_name = model_name or "deepseek/deepseek-r1"
        self.temperature = temperature or 0
        self.llm = ChatOpenAI(
            api_key=api_key, model_name=self.model_name, temperature=self.temperature, request_timeout=600, base_url=base_url
        )


class QueryChain:
    """
    QueryChain class to handle the generation, correction, and parsing of Cypher queries using language models.
    It encapsulates the entire process as a single chain of operations.
    
    Enhanced with detailed logging for all LLM interactions.
    """

    def __init__(
        self,
        cypher_llm: Union[
            OpenAILanguageModel,
            GoogleGenerativeLanguageModel,
            AnthropicLanguageModel,
            GroqLanguageModel,
            ReplicateLanguageModel,
            OllamaLanguageModel,
            NVIDIALanguageModel,
            OpenRouterLanguageModel,
        ],
        qa_llm: Union[
            OpenAILanguageModel,
            GoogleGenerativeLanguageModel,
            AnthropicLanguageModel,
            GroqLanguageModel,
            ReplicateLanguageModel,
            OllamaLanguageModel,
            NVIDIALanguageModel,
            OpenRouterLanguageModel,
        ],
        schema: dict,
        verbose: bool = False,
        search_type: Literal["vector_search", "db_search"] = "db_search",
        model_name: str = "",
        provider: str = "",
    ):
        self.model_name = model_name
        self.provider = provider
        
        Logger.info(
            f"Initializing QueryChain",
            extra={
                "search_type": search_type,
                "model_name": model_name,
                "provider": provider,
                "verbose": verbose
            }
        )

        # Use LCEL (LangChain Expression Language) pattern for chains
        if search_type == "db_search":
            self.cypher_chain = CYPHER_GENERATION_PROMPT | cypher_llm | StrOutputParser()
            self.prompt_template = CYPHER_GENERATION_PROMPT
        else:
            self.cypher_chain = VECTOR_SEARCH_CYPHER_GENERATION_PROMPT | cypher_llm | StrOutputParser()
            self.prompt_template = VECTOR_SEARCH_CYPHER_GENERATION_PROMPT

        self.qa_chain = CYPHER_OUTPUT_PARSER_PROMPT | qa_llm | StrOutputParser()
        self.qa_prompt_template = CYPHER_OUTPUT_PARSER_PROMPT
        self.cypher_llm = cypher_llm  # Store the LLM for error correction
        self.qa_llm = qa_llm  # Store the LLM for follow-up generation
        self.schema = schema
        self.verbose = verbose
        self.search_type = search_type

        self.generated_queries = []
        
        # Log schema summary
        schema_summary = {
            "node_types_count": len(schema.get("nodes", [])),
            "edge_types_count": len(schema.get("edges", [])),
            "node_properties_count": len(schema.get("node_properties", [])),
            "edge_properties_count": len(schema.get("edge_properties", []))
        }
        Logger.debug(f"Schema loaded", extra=schema_summary)

    def _get_schema_context_for_logging(self) -> Dict[str, Any]:
        """Get a summary of schema context for logging."""
        return {
            "nodes": self.schema.get("nodes", [])[:5],  # First 5 node types
            "edges_count": len(self.schema.get("edges", [])),
            "node_properties_sample": self.schema.get("node_properties", [])[:3]
        }

    @timeout(300)
    @validate_call
    def run_cypher_chain(
        self,
        question: str,
        vector_index: str = None,
        embedding: Union[list[float], None] = None,
        conversation_context: str = "",
    ) -> str:
        """
        Executes the query chain: generates a query, corrects it, and returns the corrected query.
        
        Includes detailed logging of:
        - Prompt variables and template
        - Raw LLM response
        - Query cleaning steps
        - Timing information
        
        Args:
            question: The user's natural language question
            vector_index: Optional vector index for similarity search
            embedding: Optional embedding for vector search
            conversation_context: Optional context from previous conversation turns
        """
        structured_logger = get_structured_logger()
        step = structured_logger.start_step("cypher_generation", {
            "question": question,
            "search_type": self.search_type,
            "vector_index": vector_index,
            "has_embedding": embedding is not None,
            "has_conversation_context": bool(conversation_context)
        })
        
        llm_start_time = time()
        raw_response = ""
        
        try:
            # Prepare prompt variables for logging
            prompt_variables = {
                "node_types": str(self.schema["nodes"])[:500],
                "node_properties": str(self.schema["node_properties"])[:500],
                "edge_properties": str(self.schema["edge_properties"])[:500],
                "edges": str(self.schema["edges"])[:500],
                "question": question,
            }
            if vector_index:
                prompt_variables["vector_index"] = vector_index
            
            Logger.debug(
                f"[CYPHER_GEN] Starting query generation",
                extra={
                    "question": question,
                    "search_type": self.search_type,
                    "model": self.model_name,
                    "provider": self.provider
                }
            )
            
            # Create callback handler for this LLM call
            callback = create_llm_callback(
                call_type="cypher_generation",
                model_name=self.model_name,
                provider=self.provider
            )

            # Format conversation context for cypher generation (only include last 2-3 for token efficiency)
            cypher_context = ""
            if conversation_context:
                cypher_context = f"\nPrevious conversation context (use for understanding follow-up questions):\n{conversation_context}\n"

            if self.search_type == "db_search":
                Logger.debug("[CYPHER_GEN] Executing db_search query generation")
                raw_response = self.cypher_chain.invoke(
                    {
                        "node_types": self.schema["nodes"],
                        "node_properties": self.schema["node_properties"],
                        "edge_properties": self.schema["edge_properties"],
                        "edges": self.schema["edges"],
                        "question": question,
                        "conversation_context": cypher_context,
                    },
                    config={"callbacks": [callback]}
                )
                
            elif self.search_type == "vector_search" and embedding is None:
                Logger.debug("[CYPHER_GEN] Executing vector_search query generation (no embedding)")
                raw_response = self.cypher_chain.invoke(
                    {
                        "node_types": self.schema["nodes"],
                        "node_properties": self.schema["node_properties"],
                        "edge_properties": self.schema["edge_properties"],
                        "edges": self.schema["edges"],
                        "question": question,
                        "vector_index": vector_index,
                        "conversation_context": cypher_context,
                    },
                    config={"callbacks": [callback]}
                )

            elif self.search_type == "vector_search" and embedding is not None:
                Logger.debug("[CYPHER_GEN] Executing vector_search query generation (with embedding)")
                raw_response = self.cypher_chain.invoke(
                    {
                        "node_types": self.schema["nodes"],
                        "node_properties": self.schema["node_properties"],
                        "edge_properties": self.schema["edge_properties"],
                        "edges": self.schema["edges"],
                        "question": question,
                        "vector_index": vector_index,
                        "conversation_context": cypher_context,
                    },
                    config={"callbacks": [callback]}
                )
            
            llm_duration_ms = (time() - llm_start_time) * 1000
            
            # Log raw response
            Logger.debug(
                f"[CYPHER_GEN] Raw LLM response received",
                extra={
                    "raw_response_length": len(raw_response),
                    "raw_response_preview": raw_response[:500] if raw_response else "",
                    "duration_ms": llm_duration_ms
                }
            )
            
            # Clean the response step by step (with logging)
            Logger.debug("[CYPHER_GEN] Cleaning raw response")
            cleaned = raw_response.strip()
            cleaned = cleaned.strip("\n")
            cleaned = cleaned.replace("cypher", "")
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("''", "'")
            cleaned = cleaned.replace('""', '"')
            
            self.generated_query = cleaned
            
            # Handle embedding substitution for vector search
            if self.search_type == "vector_search" and embedding is not None:
                Logger.debug("[CYPHER_GEN] Substituting embedding into query")
                self.generated_query = self.generated_query.format(user_input=embedding)
            
            Logger.info(
                f"[CYPHER_GEN] Query generated successfully",
                extra={
                    "generated_query": self.generated_query[:500],
                    "query_length": len(self.generated_query),
                    "llm_duration_ms": llm_duration_ms
                }
            )
            
            # Correct the query
            Logger.debug("[CYPHER_GEN] Starting query correction")
            correction_start_time = time()
            
            corrected_query = correct_query(
                query=self.generated_query, edge_schema=self.schema["edges"]
            )
            
            correction_duration_ms = (time() - correction_start_time) * 1000
            
            self.generated_queries.append(corrected_query)
            
            # Detailed logging of correction results
            query_changed = corrected_query != self.generated_query
            Logger.info(
                f"[CYPHER_GEN] Query correction completed",
                extra={
                    "original_query": self.generated_query[:300],
                    "corrected_query": corrected_query[:300] if corrected_query else "EMPTY",
                    "query_changed": query_changed,
                    "correction_success": bool(corrected_query),
                    "correction_duration_ms": correction_duration_ms
                }
            )
            
            # Log to structured logger
            structured_logger.end_step(step, "completed")
            
            # Update current query log if exists
            current_log = get_current_query_log()
            if current_log:
                current_log.generated_query = self.generated_query
                current_log.final_query = corrected_query
            
            return corrected_query
            
        except Exception as e:
            llm_duration_ms = (time() - llm_start_time) * 1000
            
            Logger.exception(
                f"[CYPHER_GEN] Error during query generation",
                exc=e,
                context={
                    "question": question,
                    "search_type": self.search_type,
                    "raw_response_preview": raw_response[:200] if raw_response else "",
                    "duration_ms": llm_duration_ms
                }
            )
            
            structured_logger.end_step(step, "failed", e)
            raise

    @timeout(180)
    def regenerate_query_with_error(
        self,
        question: str,
        failed_query: str,
        error_message: str,
        conversation_context: str = "",
    ) -> str:
        """
        Regenerate a Cypher query using error feedback from a failed execution.
        
        This method is used when a generated query fails during execution.
        It passes the error message to the LLM so it can learn from the mistake
        and generate a corrected query.
        
        Args:
            question: The user's original question
            failed_query: The Cypher query that failed
            error_message: The error message from the failed execution
            conversation_context: Optional context from previous conversation turns
            
        Returns:
            A corrected Cypher query
        """
        structured_logger = get_structured_logger()
        step = structured_logger.start_step("cypher_error_correction", {
            "question": question,
            "failed_query": failed_query[:300],
            "error_message": error_message[:500],
            "has_conversation_context": bool(conversation_context)
        })
        
        llm_start_time = time()
        raw_response = ""
        
        try:
            Logger.info(
                "[CYPHER_ERROR_CORRECTION] Starting query regeneration with error feedback",
                extra={
                    "question": question,
                    "failed_query": failed_query[:300],
                    "error_message": error_message[:300],
                    "model": self.model_name,
                    "provider": self.provider
                }
            )
            
            # Create the error correction chain using the stored cypher LLM
            error_correction_chain = CYPHER_ERROR_CORRECTION_PROMPT | self.cypher_llm | StrOutputParser()
            
            # Format conversation context
            cypher_context = ""
            if conversation_context:
                cypher_context = f"\nPrevious conversation context:\n{conversation_context}\n"
            
            # Create callback handler for this LLM call
            callback = create_llm_callback(
                call_type="cypher_error_correction",
                model_name=self.model_name,
                provider=self.provider
            )
            
            raw_response = error_correction_chain.invoke(
                {
                    "question": question,
                    "failed_query": failed_query,
                    "error_message": error_message,
                    "node_types": self.schema["nodes"],
                    "node_properties": self.schema["node_properties"],
                    "edges": self.schema["edges"],
                    "edge_properties": self.schema["edge_properties"],
                    "conversation_context": cypher_context,
                },
                config={"callbacks": [callback]}
            )
            
            llm_duration_ms = (time() - llm_start_time) * 1000
            
            Logger.debug(
                "[CYPHER_ERROR_CORRECTION] Raw LLM response received",
                extra={
                    "raw_response_length": len(raw_response),
                    "raw_response_preview": raw_response[:500] if raw_response else "",
                    "duration_ms": llm_duration_ms
                }
            )
            
            # Clean the response
            cleaned = raw_response.strip()
            cleaned = cleaned.strip("\n")
            cleaned = cleaned.replace("cypher", "")
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("''", "'")
            cleaned = cleaned.replace('""', '"')
            
            # Correct the query
            corrected_query = correct_query(
                query=cleaned, edge_schema=self.schema["edges"]
            )
            
            Logger.info(
                "[CYPHER_ERROR_CORRECTION] Query regenerated successfully",
                extra={
                    "corrected_query": corrected_query[:500],
                    "query_length": len(corrected_query),
                    "llm_duration_ms": llm_duration_ms
                }
            )
            
            structured_logger.end_step(step, "completed")
            
            return corrected_query
            
        except Exception as e:
            llm_duration_ms = (time() - llm_start_time) * 1000
            
            Logger.exception(
                "[CYPHER_ERROR_CORRECTION] Error during query regeneration",
                exc=e,
                context={
                    "question": question,
                    "failed_query": failed_query[:200],
                    "error_message": error_message[:200],
                    "raw_response_preview": raw_response[:200] if raw_response else "",
                    "duration_ms": llm_duration_ms
                }
            )
            
            structured_logger.end_step(step, "failed", e)
            raise

    @timeout(180)
    def regenerate_query_on_empty(
        self,
        question: str,
        failed_query: str,
        conversation_context: str = "",
    ) -> str:
        """
        Regenerate a Cypher query when the previous query returned no results.
        
        This method is used when a generated query executes successfully but returns
        an empty result set. It passes the failed query to the LLM so it can try
        a more general or alternative approach.
        
        Args:
            question: The user's original question
            failed_query: The Cypher query that returned no results
            conversation_context: Optional context from previous conversation turns
            
        Returns:
            A new Cypher query that may return results
        """
        structured_logger = get_structured_logger()
        step = structured_logger.start_step("cypher_empty_result_regen", {
            "question": question,
            "failed_query": failed_query[:300],
            "has_conversation_context": bool(conversation_context)
        })
        
        llm_start_time = time()
        raw_response = ""
        
        try:
            Logger.info(
                "[CYPHER_EMPTY_REGEN] Starting query regeneration after empty result",
                extra={
                    "question": question,
                    "failed_query": failed_query[:300],
                    "model": self.model_name,
                    "provider": self.provider
                }
            )
            
            # Create the empty result regeneration chain using the stored cypher LLM
            empty_regen_chain = CYPHER_EMPTY_RESULT_REGEN_PROMPT | self.cypher_llm | StrOutputParser()
            
            # Format conversation context
            cypher_context = ""
            if conversation_context:
                cypher_context = f"\nPrevious conversation context:\n{conversation_context}\n"
            
            # Create callback handler for this LLM call
            callback = create_llm_callback(
                call_type="cypher_empty_result_regen",
                model_name=self.model_name,
                provider=self.provider
            )
            
            raw_response = empty_regen_chain.invoke(
                {
                    "question": question,
                    "failed_query": failed_query,
                    "node_types": self.schema["nodes"],
                    "node_properties": self.schema["node_properties"],
                    "edges": self.schema["edges"],
                    "edge_properties": self.schema["edge_properties"],
                    "conversation_context": cypher_context,
                },
                config={"callbacks": [callback]}
            )
            
            llm_duration_ms = (time() - llm_start_time) * 1000
            
            Logger.debug(
                "[CYPHER_EMPTY_REGEN] Raw LLM response received",
                extra={
                    "raw_response_length": len(raw_response),
                    "raw_response_preview": raw_response[:500] if raw_response else "",
                    "duration_ms": llm_duration_ms
                }
            )
            
            # Clean the response
            cleaned = raw_response.strip()
            cleaned = cleaned.strip("\n")
            cleaned = cleaned.replace("cypher", "")
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("''", "'")
            cleaned = cleaned.replace('""', '"')
            
            # Correct the query
            corrected_query = correct_query(
                query=cleaned, edge_schema=self.schema["edges"]
            )
            
            Logger.info(
                "[CYPHER_EMPTY_REGEN] Query regenerated successfully",
                extra={
                    "corrected_query": corrected_query[:500],
                    "query_length": len(corrected_query),
                    "llm_duration_ms": llm_duration_ms
                }
            )
            
            structured_logger.end_step(step, "completed")
            
            return corrected_query
            
        except Exception as e:
            llm_duration_ms = (time() - llm_start_time) * 1000
            
            Logger.exception(
                "[CYPHER_EMPTY_REGEN] Error during query regeneration",
                exc=e,
                context={
                    "question": question,
                    "failed_query": failed_query[:200],
                    "raw_response_preview": raw_response[:200] if raw_response else "",
                    "duration_ms": llm_duration_ms
                }
            )
            
            structured_logger.end_step(step, "failed", e)
            raise

    def run_qa_chain(
        self,
        output: Any,
        input_question: str,
        conversation_context: str = "",
    ) -> str:
        """
        Run the QA chain to generate a natural language response.
        
        Includes detailed logging of the QA process.
        
        Args:
            output: The Cypher query output to parse
            input_question: The user's original question
            conversation_context: Optional context from previous conversation turns
        """
        structured_logger = get_structured_logger()
        step = structured_logger.start_step("qa_response_generation", {
            "question": input_question,
            "output_type": type(output).__name__,
            "output_length": len(str(output)) if output else 0,
            "has_conversation_context": bool(conversation_context)
        })
        
        qa_start_time = time()
        
        try:
            Logger.debug(
                f"[QA_CHAIN] Starting QA response generation",
                extra={
                    "question": input_question,
                    "output_preview": str(output)[:300] if output else "",
                    "model": self.model_name,
                    "provider": self.provider,
                    "has_conversation_context": bool(conversation_context)
                }
            )
            
            # Format conversation context for QA response
            qa_context = ""
            if conversation_context:
                qa_context = f"\nPrevious conversation for context:\n{conversation_context}\n"
            
            # Create callback handler for QA chain
            callback = create_llm_callback(
                call_type="qa_response",
                model_name=self.model_name,
                provider=self.provider
            )
            
            raw_response = self.qa_chain.invoke(
                {
                    "output": output,
                    "input_question": input_question,
                    "conversation_context": qa_context,
                },
                config={"callbacks": [callback]}
            )
            
            qa_duration_ms = (time() - qa_start_time) * 1000
            
            final_response = raw_response.strip("\n")
            
            Logger.info(
                f"[QA_CHAIN] QA response generated successfully",
                extra={
                    "response_preview": final_response[:300],
                    "response_length": len(final_response),
                    "duration_ms": qa_duration_ms
                }
            )
            
            structured_logger.end_step(step, "completed")
            
            return final_response
            
        except Exception as e:
            qa_duration_ms = (time() - qa_start_time) * 1000
            
            Logger.exception(
                f"[QA_CHAIN] Error during QA response generation",
                exc=e,
                context={
                    "question": input_question,
                    "duration_ms": qa_duration_ms
                }
            )
            
            structured_logger.end_step(step, "failed", e)
            raise

    def generate_follow_up_questions(
        self,
        question: str,
        answer: str,
        is_semantic_search: bool = False,
        vector_category: str = None,
    ) -> list[str]:
        """
        Generate follow-up question suggestions based on the Q&A.
        
        Args:
            question: The user's original question
            answer: The assistant's response
            is_semantic_search: Whether semantic/vector search is active
            vector_category: The vector category used (e.g., "Protein", "Drug")
            
        Returns:
            List of suggested follow-up questions (up to 3)
        """
        try:
            Logger.debug(
                f"[FOLLOW_UP] Generating follow-up questions",
                extra={
                    "question_preview": question[:100],
                    "answer_preview": answer[:200],
                    "is_semantic_search": is_semantic_search,
                    "vector_category": vector_category
                }
            )
            
            # Choose the appropriate template based on semantic search status
            if is_semantic_search and vector_category:
                follow_up_chain = FOLLOW_UP_QUESTIONS_SEMANTIC_PROMPT | self.qa_llm | StrOutputParser()
                invoke_params = {
                    "question": question,
                    "answer": answer,
                    "vector_category": vector_category,
                }
            else:
                follow_up_chain = FOLLOW_UP_QUESTIONS_PROMPT | self.qa_llm | StrOutputParser()
                invoke_params = {
                    "question": question,
                    "answer": answer,
                }
            
            callback = create_llm_callback(
                call_type="follow_up_generation",
                model_name=self.model_name,
                provider=self.provider
            )
            
            raw_response = follow_up_chain.invoke(
                invoke_params,
                config={"callbacks": [callback]}
            )
            
            # Parse the JSON array from response
            import json
            try:
                # Try to extract JSON array from response
                response_text = raw_response.strip()
                # Find the JSON array in the response
                start_idx = response_text.find('[')
                end_idx = response_text.rfind(']') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    follow_ups = json.loads(json_str)
                    if isinstance(follow_ups, list):
                        # Return up to 3 questions
                        return [str(q).strip() for q in follow_ups[:3] if q]
            except json.JSONDecodeError:
                Logger.warning(
                    "[FOLLOW_UP] Failed to parse follow-up questions as JSON",
                    extra={"raw_response": raw_response[:300]}
                )
            
            return []
            
        except Exception as e:
            Logger.warning(
                f"[FOLLOW_UP] Error generating follow-up questions",
                extra={"error": str(e)}
            )
            return []


class RunPipeline:
    """
    Main pipeline for running natural language to Cypher query conversion.
    
    Enhanced with comprehensive logging for all pipeline stages.
    """

    def __init__(
        self,
        model_name=Union[
            str, list[str], dict[Literal["cypher_llm_model", "qa_llm_model"], str]
        ],
        verbose: bool = False,
        top_k: int = 5,
        reset_schema: bool = False,
        search_type: Literal["vector_search", "db_search"] = "db_search",
    ):
        Logger.info(
            "[PIPELINE_INIT] Initializing RunPipeline",
            extra={
                "model_name": str(model_name),
                "verbose": verbose,
                "top_k": top_k,
                "search_type": search_type,
                "reset_schema": reset_schema
            }
        )

        self.verbose = verbose
        self.top_k = top_k
        self.config: Config = Config()
        
        # Store model info for logging
        self.current_model_name = model_name if isinstance(model_name, str) else str(model_name)
        self.current_provider = ""
        
        Logger.debug("[PIPELINE_INIT] Connecting to Neo4j")
        self.neo4j_connection: Neo4JConnection = Neo4JConnection(
            self.config.neo4j_usr,
            self.config.neo4j_password,
            self.config.neo4j_db_name,
            self.config.neo4j_uri,
            reset_schema=reset_schema,
            create_vector_indexes=False if search_type == "db_search" else True,
        )
        Logger.debug("[PIPELINE_INIT] Neo4j connection established")
        
        self.search_type = search_type

        # define llm type(s)
        self.define_llm(model_name)

        # define outputs list
        self.outputs = []
        
        Logger.info("[PIPELINE_INIT] Pipeline initialization complete")

    def define_llm(self, model_name):
        """Define LLM based on model name, with detailed logging."""
        from models_config import get_provider_for_model_name
        
        Logger.debug(f"[DEFINE_LLM] Defining LLM for model: {model_name}")
    
        provider_model_map = {
            "OpenAI": (OpenAILanguageModel, self.config.openai_api_key),
            "Google": (GoogleGenerativeLanguageModel, self.config.gemini_api_key),
            "Anthropic": (AnthropicLanguageModel, self.config.anthropic_api_key),
            "Groq": (GroqLanguageModel, self.config.groq_api_key),
            "Ollama": (OllamaLanguageModel, None),  # Ollama doesn't need an API key
            "Nvidia": (NVIDIALanguageModel, self.config.nvidia_api_key),
            "OpenRouter": (OpenRouterLanguageModel, self.config.openrouter_api_key),
        }
        
        def get_llm_for_model(model_name_str):
            """Helper function to get the appropriate LLM instance for a model name."""
            provider = get_provider_for_model_name(model_name_str)
            if not provider:
                Logger.error(f"[DEFINE_LLM] Unsupported model: {model_name_str}")
                raise ValueError(f"Unsupported Language Model Name: {model_name_str}")
            
            if provider not in provider_model_map:
                Logger.error(f"[DEFINE_LLM] Unsupported provider: {provider}")
                raise ValueError(f"Unsupported Provider: {provider}")
            
            model_class, api_key = provider_model_map[provider]
            
            Logger.info(
                f"[DEFINE_LLM] Creating LLM instance",
                extra={
                    "model": model_name_str,
                    "provider": provider,
                    "has_api_key": api_key is not None and api_key != "default"
                }
            )
            
            # Store provider info for logging
            self.current_provider = provider
            self.current_model_name = model_name_str
            
            # Ollama doesn't use an API key
            if provider == "Ollama":
                return model_class(model_name=model_name_str).llm, provider
            else:
                return model_class(api_key, model_name=model_name_str).llm, provider

        if isinstance(model_name, (dict, list)):

            if len(model_name) != 2:
                raise ValueError("Length of `model_name` must be 2")

            if isinstance(model_name, list):
                model_name = dict(zip(["cypher_llm_model", "qa_llm_model"], model_name))

            self.llm = {}
            self.llm_providers = {}
            for model_type, model_name_str in model_name.items():
                if model_type == "cypher_llm_model":
                    self.llm["cypher_llm"], provider = get_llm_for_model(model_name_str)
                    self.llm_providers["cypher_llm"] = provider
                elif model_type == "qa_llm_model":
                    self.llm["qa_llm"], provider = get_llm_for_model(model_name_str)
                    self.llm_providers["qa_llm"] = provider
                else:
                    raise ValueError(f"Unsupported model type: {model_type}")
            
            Logger.info(
                f"[DEFINE_LLM] Multiple LLMs configured",
                extra={"llm_providers": self.llm_providers}
            )

        else:
            self.llm, self.current_provider = get_llm_for_model(model_name)
            self.llm_providers = {"default": self.current_provider}

    @validate_call(config=ConfigDict(arbitrary_types_allowed=True))
    def run_for_query(
        self,
        question: str,
        vector_index: str = None,
        embedding: Union[np.array, None] = None,
        reset_llm_type: bool = False,
        model_name: Union[
            str, list[str], dict[Literal["cypher_llm_model", "qa_llm_model"], str]
        ] = None,
        api_key: str = None,
        conversation_context: str = "",
    ) -> str:
        """
        Run the query generation pipeline.
        
        Includes comprehensive logging of all steps.
        
        Args:
            question: The user's natural language question
            vector_index: Optional vector index for similarity search
            embedding: Optional embedding for vector search
            reset_llm_type: Whether to reset the LLM type
            model_name: Model name(s) to use
            api_key: API key for the LLM provider
            conversation_context: Optional context from previous conversation turns
        """
        pipeline_start_time = time()
        
        Logger.info(
            "[RUN_FOR_QUERY] Starting query generation pipeline",
            extra={
                "question": question,
                "search_type": self.search_type,
                "vector_index": vector_index,
                "has_embedding": embedding is not None,
                "model_name": model_name,
                "reset_llm_type": reset_llm_type,
                "has_conversation_context": bool(conversation_context)
            }
        )

        if api_key:
            Logger.debug("[RUN_FOR_QUERY] Setting custom API key for all providers")
            self.config.openai_api_key = api_key
            self.config.gemini_api_key = api_key
            self.config.anthropic_api_key = api_key
            self.config.groq_api_key = api_key
            self.config.replicate_api_key = api_key
            self.config.nvidia_api_key = api_key
            self.config.openrouter_api_key = api_key
        else:
            Logger.debug("[RUN_FOR_QUERY] Using default config from environment")
            self.config = Config()

        if reset_llm_type:
            Logger.debug(f"[RUN_FOR_QUERY] Resetting LLM type to: {model_name}")
            self.define_llm(model_name=model_name)

        # Log selected model(s)
        if isinstance(self.llm, dict):
            llm_info = {k: str(v) for k, v in self.llm.items()}
        else:
            llm_info = {"llm": str(self.llm)}
        
        Logger.info(
            "[RUN_FOR_QUERY] LLM configuration",
            extra={
                "llm_info": llm_info,
                "provider": self.current_provider,
                "model": self.current_model_name
            }
        )

        # Create QueryChain with model/provider info for logging
        if isinstance(self.llm, dict):
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm["cypher_llm"],
                qa_llm=self.llm["qa_llm"],
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
                model_name=self.current_model_name,
                provider=self.current_provider,
            )
        else:
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm,
                qa_llm=self.llm,
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
                model_name=self.current_model_name,
                provider=self.current_provider,
            )

        try:
            if self.search_type == "db_search":
                Logger.debug("[RUN_FOR_QUERY] Executing db_search pipeline")
                corrected_query = query_chain.run_cypher_chain(
                    question,
                    conversation_context=conversation_context
                )
            else:
                Logger.debug("[RUN_FOR_QUERY] Executing vector_search pipeline")
                processed_embedding = self.handle_embedding(
                    embedding=embedding, vector_index=vector_index
                )
                corrected_query = query_chain.run_cypher_chain(
                    question,
                    vector_index=vector_index,
                    embedding=processed_embedding,
                    conversation_context=conversation_context,
                )

            if not corrected_query and hasattr(query_chain, 'generated_query') and query_chain.generated_query:
                Logger.warning(
                    "[RUN_FOR_QUERY] Schema correction returned empty query, falling back to raw generated query",
                    extra={
                        "raw_generated_query": query_chain.generated_query[:300],
                        "question": question,
                    }
                )
                corrected_query = query_chain.generated_query

            pipeline_duration_ms = (time() - pipeline_start_time) * 1000
            
            Logger.info(
                "[RUN_FOR_QUERY] Query generation pipeline completed",
                extra={
                    "question": question,
                    "corrected_query": corrected_query[:300] if corrected_query else "EMPTY",
                    "query_success": bool(corrected_query),
                    "pipeline_duration_ms": pipeline_duration_ms
                }
            )

            return corrected_query
            
        except Exception as e:
            pipeline_duration_ms = (time() - pipeline_start_time) * 1000
            
            Logger.exception(
                "[RUN_FOR_QUERY] Pipeline failed",
                exc=e,
                context={
                    "question": question,
                    "search_type": self.search_type,
                    "duration_ms": pipeline_duration_ms
                }
            )
            raise

    def execute_query(
        self,
        query: str,
        question: str,
        model_name: str,
        reset_llm_type: bool = False,
        api_key: str = None,
        conversation_context: str = "",
    ) -> str:
        """
        Execute a Cypher query and generate a natural language response.
        
        Includes comprehensive logging of execution and response generation.
        
        Args:
            query: The Cypher query to execute
            question: The user's original question
            model_name: Model name to use
            reset_llm_type: Whether to reset the LLM type
            api_key: API key for the LLM provider
            conversation_context: Optional context from previous conversation turns
        """
        execution_start_time = time()
        
        Logger.info(
            "[EXECUTE_QUERY] Starting query execution",
            extra={
                "query": query[:300],
                "question": question,
                "top_k": self.top_k,
                "model_name": model_name,
                "has_conversation_context": bool(conversation_context)
            }
        )

        # Execute Neo4j query
        neo4j_start_time = time()
        try:
            result = self.neo4j_connection.execute_query(query, top_k=self.top_k)
            neo4j_duration_ms = (time() - neo4j_start_time) * 1000
            
            result_count = len(result) if isinstance(result, list) else 1
            Logger.info(
                "[EXECUTE_QUERY] Neo4j query executed",
                extra={
                    "result_count": result_count,
                    "result_preview": str(result)[:500] if result else "No results",
                    "neo4j_duration_ms": neo4j_duration_ms
                }
            )
        except Exception as e:
            neo4j_duration_ms = (time() - neo4j_start_time) * 1000
            Logger.exception(
                "[EXECUTE_QUERY] Neo4j query failed",
                exc=e,
                context={
                    "query": query,
                    "duration_ms": neo4j_duration_ms
                }
            )
            raise

        if api_key:
            Logger.debug("[EXECUTE_QUERY] Setting custom API key")
            self.config.openai_api_key = api_key
            self.config.gemini_api_key = api_key
            self.config.anthropic_api_key = api_key
            self.config.groq_api_key = api_key
            self.config.replicate_api_key = api_key
            self.config.nvidia_api_key = api_key
            self.config.openrouter_api_key = api_key
        else:
            self.config = Config()

        if reset_llm_type:
            Logger.debug(f"[EXECUTE_QUERY] Resetting LLM to: {model_name}")
            self.define_llm(model_name=model_name)

        # Create QueryChain for QA response
        if isinstance(self.llm, dict):
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm["cypher_llm"],
                qa_llm=self.llm["qa_llm"],
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
                model_name=self.current_model_name,
                provider=self.current_provider,
            )
        else:
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm,
                qa_llm=self.llm,
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
                model_name=self.current_model_name,
                provider=self.current_provider,
            )

        # Generate natural language response
        qa_start_time = time()
        try:
            final_output = query_chain.run_qa_chain(
                output=result,
                input_question=question,
                conversation_context=conversation_context
            )
            qa_duration_ms = (time() - qa_start_time) * 1000
            
            Logger.info(
                "[EXECUTE_QUERY] QA response generated",
                extra={
                    "response_preview": final_output[:300] if final_output else "",
                    "response_length": len(final_output) if final_output else 0,
                    "qa_duration_ms": qa_duration_ms
                }
            )
        except Exception as e:
            qa_duration_ms = (time() - qa_start_time) * 1000
            Logger.exception(
                "[EXECUTE_QUERY] QA response generation failed",
                exc=e,
                context={
                    "question": question,
                    "result_count": len(result) if isinstance(result, list) else 1,
                    "duration_ms": qa_duration_ms
                }
            )
            raise

        total_duration_ms = (time() - execution_start_time) * 1000
        
        Logger.info(
            "[EXECUTE_QUERY] Query execution completed",
            extra={
                "total_duration_ms": total_duration_ms,
                "neo4j_duration_ms": neo4j_duration_ms,
                "qa_duration_ms": qa_duration_ms,
                "result_count": len(result) if isinstance(result, list) else 1
            }
        )

        return final_output, result

    @validate_call(config=ConfigDict(arbitrary_types_allowed=True))
    def run_without_errors(
        self,
        question: str,
        vector_index: str = None,
        embedding: np.array = None,
        reset_llm_type: bool = False,
        model_name: Union[
            str, list[str], dict[Literal["cypher_llm_model", "qa_llm_model"], str]
        ] = None,
    ) -> str:
        """
        Run the full pipeline with error handling - errors don't propagate.
        
        Includes comprehensive logging of all steps and error states.
        """
        pipeline_start_time = time()
        
        Logger.info(
            "[RUN_WITHOUT_ERRORS] Starting error-tolerant pipeline",
            extra={
                "question": question,
                "search_type": self.search_type,
                "vector_index": vector_index,
                "has_embedding": embedding is not None
            }
        )

        if reset_llm_type:
            Logger.debug(f"[RUN_WITHOUT_ERRORS] Resetting LLM to: {model_name}")
            self.define_llm(model_name=model_name)

        Logger.info(
            "[RUN_WITHOUT_ERRORS] LLM configuration",
            extra={
                "llm": str(self.llm) if not isinstance(self.llm, dict) else {k: str(v) for k, v in self.llm.items()},
                "provider": self.current_provider,
                "model": self.current_model_name
            }
        )

        # Create QueryChain with model/provider info
        if isinstance(self.llm, dict):
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm["cypher_llm"],
                qa_llm=self.llm["qa_llm"],
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
                model_name=self.current_model_name,
                provider=self.current_provider,
            )
        else:
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm,
                qa_llm=self.llm,
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
                model_name=self.current_model_name,
                provider=self.current_provider,
            )

        # Generate query
        try:
            if self.search_type == "db_search":
                corrected_query = query_chain.run_cypher_chain(question)
            else:
                corrected_query = query_chain.run_cypher_chain(
                    question,
                    vector_index=vector_index,
                    embedding=self.handle_embedding(
                        embedding=embedding, vector_index=vector_index
                    ),
                )
        except Exception as e:
            Logger.exception(
                "[RUN_WITHOUT_ERRORS] Query generation failed",
                exc=e,
                context={"question": question}
            )
            self.outputs.append((question, "", "", "", ""))
            return None

        if not corrected_query:
            Logger.warning(
                "[RUN_WITHOUT_ERRORS] Query correction returned empty",
                extra={
                    "question": question,
                    "generated_query": query_chain.generated_query[:200] if hasattr(query_chain, 'generated_query') else ""
                }
            )
            self.outputs.append((question, query_chain.generated_query, "", "", ""))
            return None

        # Execute query
        try:
            neo4j_start_time = time()
            result = self.neo4j_connection.execute_query(
                corrected_query, top_k=self.top_k
            )
            neo4j_duration_ms = (time() - neo4j_start_time) * 1000
            
            Logger.info(
                "[RUN_WITHOUT_ERRORS] Neo4j query executed",
                extra={
                    "result_count": len(result) if isinstance(result, list) else 1,
                    "result_preview": str(result)[:300],
                    "duration_ms": neo4j_duration_ms
                }
            )
        except Exception as e:
            Logger.exception(
                "[RUN_WITHOUT_ERRORS] Neo4j query execution failed",
                exc=e,
                context={
                    "query": corrected_query,
                    "question": question
                }
            )
            self.outputs.append(
                (question, query_chain.generated_query, corrected_query, "", "")
            )
            return None

        # Generate natural language response
        try:
            qa_start_time = time()
            final_output = query_chain.run_qa_chain(
                output=result,
                input_question=question
            )
            qa_duration_ms = (time() - qa_start_time) * 1000
            
            Logger.info(
                "[RUN_WITHOUT_ERRORS] QA response generated",
                extra={
                    "response_preview": final_output[:200],
                    "duration_ms": qa_duration_ms
                }
            )
        except Exception as e:
            Logger.exception(
                "[RUN_WITHOUT_ERRORS] QA response generation failed",
                exc=e,
                context={"question": question}
            )
            self.outputs.append(
                (question, query_chain.generated_query, corrected_query, str(result), "")
            )
            return None

        pipeline_duration_ms = (time() - pipeline_start_time) * 1000

        # add outputs of all steps to a list
        self.outputs.append(
            (
                question,
                query_chain.generated_query,
                corrected_query,
                result,
                final_output,
            )
        )
        
        Logger.info(
            "[RUN_WITHOUT_ERRORS] Pipeline completed successfully",
            extra={
                "question": question,
                "total_duration_ms": pipeline_duration_ms,
                "has_response": bool(final_output)
            }
        )

        return final_output

    def create_dataframe_from_outputs(self) -> pd.DataFrame:
        df = pd.DataFrame(
            self.outputs,
            columns=[
                "Question",
                "Generated Query",
                "Corrected Query",
                "Query Result",
                "Natural Language Answer",
            ],
        )

        return df.replace("", np.nan)

    def handle_embedding(
        self, embedding: Union[np.array, None], vector_index: str
    ) -> Union[list[float], None]:
        if embedding is None:
            return None
        else:
            if np.isnan(embedding).any():
                raise ValueError("NaN value found in provided embedding")

            if np.isinf(embedding).any():
                raise ValueError("Infinite value found in provided embedding")

            if embedding.dtype != np.float64:
                raise ValueError("Input embedding must be a float array")

            if len(embedding.shape) > 1:
                raise ValueError("Input embedding must be a 1D array")

            vector_index_to_array_shape = {
                "SelformerEmbeddings": 768,
                "Prott5Embeddings": 1024,
                "Esm2Embeddings": 1280,
                "Anc2vecEmbeddings": 200,
                "CadaEmbeddings": 160,
                "Doc2vecEmbeddings": 100,
                "Dom2vecEmbeddings": 50,
                "RxnfpEmbeddings": 256,
                "BiokeenEmbeddings": 200,
            }

            if embedding.shape[0] != vector_index_to_array_shape[vector_index]:
                raise ValueError(
                    f"Invalid embedding vector shape provided. Expected {vector_index_to_array_shape[vector_index]}, got {embedding.shape[0]}"
                )

            return embedding.tolist()


def main():
    """
    Main function to execute the flow of operations.
    It initializes all necessary classes and executes the query generation, execution, and parsing process.
    """

    current_date = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
    log_filename = f"query_log_{current_date}.log"

    verbose_input = input("Enable verbose mode? (yes/no):\n").lower() == "yes"
    configure_logging(verbose=verbose_input, log_filename=log_filename)

    logging.info("Starting the pipeline...")

    try:
        pipeline = RunPipeline(
            verbose=verbose_input, model_name="gpt-3.5-turbo-instruct"
        )

        question = str(input("Enter a question:\n"))

        final_output = pipeline.run(question=question)

        print(final_output)

        logging.info("Pipeline finished successfully.")

    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e


if __name__ == "__main__":
    main()
