import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from wrapt_timeout_decorator import *

# Import path
current_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# Import required modules for Neo4J connection and schema extraction
from typing import Literal, Union

import numpy as np
import pandas as pd
from .neo4j_query_corrector import correct_query
from .neo4j_query_executor_extractor import Neo4jGraphHelper
from .qa_templates import (
    CYPHER_GENERATION_PROMPT,
    CYPHER_OUTPUT_PARSER_PROMPT,
    VECTOR_SEARCH_CYPHER_GENERATION_PROMPT,
)
from langchain.chains import LLMChain
from langchain_anthropic import ChatAnthropic
from langchain_community.llms import Ollama, Replicate
from langchain_google_genai import GoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_nvidia_ai_endpoints import ChatNVIDIA

# Import the Language Model wrappers
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, validate_call


def configure_logging(verbose=False, log_filename="query_log.log"):
    """
    Configure logging for the application based on verbosity level.
    
    Args:
        verbose (bool): Whether to show detailed debug logs
        log_filename (str): Name of the log file to write logs to
    """
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(parent_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_filename)
    
    # Set up file handler for all logs
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # Set up handlers based on verbosity
    handlers = [file_handler]
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        handlers.append(console_handler)
    
    # Configure root logger
    logging.basicConfig(
        handlers=handlers,
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Log configuration completed
    log_level = "DEBUG" if verbose else "INFO"
    logging.info(f"Logging initialized with level: {log_level}, output to: {log_path}")


class Config(BaseModel):
    """
    Config class for handling environment variables.
    It loads the variables from a .env file and makes them available as attributes.
    """

    load_dotenv()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "default")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "default")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "default")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "default")
    replicate_api_key: str = os.getenv("REPLICATE_API_KEY", "default")
    nvidia_api_key: str = os.getenv("NVIDIA_API_KEY", "default")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "default")
    neo4j_usr: str = os.getenv("NEO4J_USERNAME")
    neo4j_password: str = os.getenv("MY_NEO4J_PASSWORD")
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
            "gpt-4.1-2025-04-14",
            "o4-mini-2025-04-16",
            "o3-2025-04-16",
            "o3-mini-2025-01-31",
            "o1-2024-12-17",
            "o1-mini-2024-09-12",
            "o1-pro-2025-03-19",
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
        self.llm = GoogleGenerativeAI(
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
    ):

        if search_type == "db_search":
            self.cypher_chain = LLMChain(
                llm=cypher_llm, prompt=CYPHER_GENERATION_PROMPT, verbose=verbose
            )
        else:
            self.cypher_chain = LLMChain(
                llm=cypher_llm,
                prompt=VECTOR_SEARCH_CYPHER_GENERATION_PROMPT,
                verbose=verbose,
            )

        self.qa_chain = LLMChain(
            llm=qa_llm, prompt=CYPHER_OUTPUT_PARSER_PROMPT, verbose=verbose
        )
        self.schema = schema
        self.verbose = verbose
        self.search_type = search_type

        self.generated_queries = []

    @timeout(180)
    @validate_call
    def run_cypher_chain(
        self,
        question: str,
        vector_index: str = None,
        embedding: Union[list[float], None] = None,
    ) -> str:
        """
        Executes the query chain: generates a query, corrects it, and returns the corrected query.
        """

        if self.search_type == "db_search":
            self.generated_query = (
                self.cypher_chain.run(
                    node_types=self.schema["nodes"],
                    node_properties=self.schema["node_properties"],
                    edge_properties=self.schema["edge_properties"],
                    edges=self.schema["edges"],
                    question=question,
                )
                .strip()
                .strip("\n")
                .replace("cypher", "")
                .strip("`")
                .replace("''", "'")
                .replace('""', '"')
            )

        elif self.search_type == "vector_search" and embedding is None:
            self.generated_query = (
                self.cypher_chain.run(
                    node_types=self.schema["nodes"],
                    node_properties=self.schema["node_properties"],
                    edge_properties=self.schema["edge_properties"],
                    edges=self.schema["edges"],
                    question=question,
                    vector_index=vector_index,
                )
                .strip()
                .strip("\n")
                .replace("cypher", "")
                .strip("`")
                .replace("''", "'")
                .replace('""', '"')
            )

        elif self.search_type == "vector_search" and embedding is not None:

            self.generated_query = (
                self.cypher_chain.run(
                    node_types=self.schema["nodes"],
                    node_properties=self.schema["node_properties"],
                    edge_properties=self.schema["edge_properties"],
                    edges=self.schema["edges"],
                    question=question,
                    vector_index=vector_index,
                )
                .strip()
                .strip("\n")
                .replace("cypher", "")
                .strip("`")
                .replace("''", "'")
                .replace('""', '"')
            )

            self.generated_query = self.generated_query.format(user_input=embedding)

        corrected_query = correct_query(
            query=self.generated_query, edge_schema=self.schema["edges"]
        )

        self.generated_queries.append(corrected_query)

        # Logging generated and corrected queries
        logging.info(f"Generated Query: {self.generated_query}")
        logging.info(f"Corrected Query: {corrected_query}")

        return corrected_query


class RunPipeline:

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

        self.verbose = verbose
        self.top_k = top_k
        self.config: Config = Config()
        self.neo4j_connection: Neo4JConnection = Neo4JConnection(
            self.config.neo4j_usr,
            self.config.neo4j_password,
            self.config.neo4j_db_name,
            self.config.neo4j_uri,
            reset_schema=reset_schema,
            create_vector_indexes=False if search_type == "db_search" else True,
        )
        self.search_type = search_type

        # define llm type(s)
        self.define_llm(model_name)

        # define outputs list
        self.outputs = []

    def define_llm(self, model_name):

        google_llm_models = [
            "gemini-2.0-flash-thinking-exp-01-21",
            "gemini-2.0-pro-exp-02-05",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-pro",
            "gemini-1.5-pro-latest",
            "gemini-1.5-flash-latest",
            "gemini-2.5-flash-preview-04-17",
            "gemini-2.5-pro-preview-03-25",
        ]
        openai_llm_models = [
            "gpt-4.1-2025-04-14",
            "o4-mini-2025-04-16",
            "o3-2025-04-16",
            "o3-mini-2025-01-31",
            "o1-2024-12-17",
            "o1-mini-2024-09-12",
            "o1-pro-2025-03-19",
            "gpt-3.5-turbo-instruct",
            "gpt-3.5-turbo-1106",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-0125",
            "gpt-4-0125-preview",
            "gpt-4-turbo",
            "gpt-4-turbo-preview",
            "gpt-4-1106-preview",
            "gpt-4-32k-0613",
            "gpt-4-0613",
            "gpt-3.5-turbo-16k",
            "gpt-4o",
            "gpt-4o-mini",
        ]
        antrophic_llm_models = [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-3-5-sonnet-latest",
            "claude-3-7-sonnet-latest",
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2",
        ]
        groq_llm_models = [
            "llama3-8b-8192",
            "llama3-70b-8192",
            "mixtral-8x7b-32768",
            "gemma-7b-it",
            "gemma2-9b-it",
        ]

        ollama_llm_models = [
            "codestral:latest",
            "llama3:instruct",
            "tomasonjo/codestral-text2cypher:latest",
            "tomasonjo/llama3-text2cypher-demo:latest",
            "llama3.1:8b",
            "qwen2:7b-instruct",
            "gemma2:latest",
        ]

        nvidia_llm_models = [
            "meta/llama-3.1-405b-instruct",
            "meta/llama-3.1-70b-instruct",
            "meta/llama-3.1-8b-instruct",
            "nv-mistralai/mistral-nemo-12b-instruct",
            "mistralai/mixtral-8x22b-instruct-v0.1",
            "mistralai/mistral-large-2-instruct",
            "nvidia/nemotron-4-340b-instruct",
        ]
        
        openrouter_llm_models = [
            "deepseek/deepseek-r1-distill-llama-70b",
            "deepseek/deepseek-r1:free",
            "deepseek/deepseek-r1",
            "deepseek/deepseek-r1:nitro",
            "deepseek/deepseek-chat",
        ] 

        if isinstance(model_name, (dict, list)):

            if len(model_name) != 2:
                raise ValueError("Length of `model_name` must be 2")

            if isinstance(model_name, list):
                model_name = dict(zip(["cypher_llm_model", "qa_llm_model"], model_name))

            self.llm = {}
            for model_type, model_name in model_name.items():
                if model_type == "cypher_llm_model":
                    if model_name in openai_llm_models:
                        self.llm["cypher_llm"] = OpenAILanguageModel(
                            self.config.openai_api_key,
                            model_name=model_name["cypher_llm_model"],
                        ).llm
                    elif model_name in google_llm_models:
                        self.llm["cypher_llm"] = GoogleGenerativeLanguageModel(
                            self.config.gemini_api_key,
                            model_name=model_name["cypher_llm_model"],
                        ).llm
                    elif model_name in antrophic_llm_models:
                        self.llm["cypher_llm"] = AnthropicLanguageModel(
                            self.config.anthropic_api_key,
                            model_name=model_name["cypher_llm_model"],
                        ).llm
                    elif model_name in groq_llm_models:
                        self.llm["cypher_llm"] = GroqLanguageModel(
                            self.config.groq_api_key,
                            model_name=model_name["cypher_llm_model"],
                        ).llm
                    elif model_name in ollama_llm_models:
                        self.llm["cypher_llm"] = OllamaLanguageModel(
                            model_name=model_name["cypher_llm_model"]
                        ).llm
                    elif model_name in nvidia_llm_models:
                        self.llm["cypher_llm"] = NVIDIALanguageModel(
                            self.config.nvidia_api_key,
                            model_name=model_name["cypher_llm_model"],
                        ).llm
                    if model_name in openrouter_llm_models:
                        self.llm["cypher_llm"] = OpenRouterLanguageModel(
                            self.config.openrouter_api_key,
                            model_name=model_name["cypher_llm_model"],
                        ).llm
                    else:
                        raise ValueError("Unsupported Language Model Name")
                elif model_name in openai_llm_models:
                    self.llm["qa_llm"] = OpenAILanguageModel(
                        self.config.openai_api_key,
                        model_name=model_name["qa_llm_model"],
                    ).llm
                elif model_name in google_llm_models:
                    self.llm["qa_llm"] = GoogleGenerativeLanguageModel(
                        self.config.gemini_api_key,
                        model_name=model_name["qa_llm_model"],
                    ).llm
                elif model_name in antrophic_llm_models:
                    self.llm["qa_llm"] = AnthropicLanguageModel(
                        self.config.anthropic_api_key,
                        model_name=model_name["qa_llm_model"],
                    ).llm
                elif model_name in groq_llm_models:
                    self.llm["qa_llm"] = GroqLanguageModel(
                        self.config.groq_api_key, model_name=model_name["qa_llm_model"]
                    ).llm
                elif model_name in ollama_llm_models:
                    self.llm["qa_llm"] = OllamaLanguageModel(
                        model_name=model_name["qa_llm_model"]
                    ).llm
                elif model_name in nvidia_llm_models:
                    self.llm["qa_llm"] = NVIDIALanguageModel(
                        self.config.nvidia_api_key,
                        model_name=model_name["qa_llm_model"],
                    ).llm
                elif model_name in openrouter_llm_models:
                    self.llm["qa_llm"] = OpenRouterLanguageModel(
                        self.config.openrouter_api_key,
                        model_name=model_name["qa_llm_model"],
                    ).llm
                else:
                    raise ValueError("Unsupported Language Model Name")

        elif model_name in google_llm_models:
            self.llm = GoogleGenerativeLanguageModel(
                self.config.gemini_api_key, model_name=model_name
            ).llm
        elif model_name in openai_llm_models:
            self.llm = OpenAILanguageModel(
                self.config.openai_api_key, model_name=model_name
            ).llm
        elif model_name in antrophic_llm_models:
            self.llm = AnthropicLanguageModel(
                self.config.anthropic_api_key, model_name=model_name
            ).llm
        elif model_name in groq_llm_models:
            self.llm = GroqLanguageModel(
                self.config.groq_api_key, model_name=model_name
            ).llm
        elif model_name in ollama_llm_models:
            self.llm = OllamaLanguageModel(model_name=model_name).llm
        elif model_name in nvidia_llm_models:
            self.llm = NVIDIALanguageModel(
                self.config.nvidia_api_key, model_name=model_name
            ).llm
        elif model_name in openrouter_llm_models:
            self.llm = OpenRouterLanguageModel(
                self.config.openrouter_api_key, model_name=model_name
            ).llm
        else:
            raise ValueError("Unsupported Language Model Name")

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
    ) -> str:

        if api_key:
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
            self.define_llm(model_name=model_name)

        logging.info(
            f"Selected Language Model(s): {list(self.llm.values()) if isinstance(self.llm, dict) else self.llm}"
        )
        logging.info(f"Question: {question}")

        if isinstance(self.llm, dict):
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm["cypher_llm"],
                qa_llm=self.llm["qa_llm"],
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
            )
        else:
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm,
                qa_llm=self.llm,
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
            )

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

        return corrected_query

    def execute_query(
        self,
        query: str,
        question: str,
        model_name: str,
        reset_llm_type: bool = False,
        api_key: str = None,
    ) -> str:

        result = self.neo4j_connection.execute_query(query, top_k=self.top_k)

        if api_key:
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
            self.define_llm(model_name=model_name)

        logging.info(f"Query Result: {result}")

        if isinstance(self.llm, dict):
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm["cypher_llm"],
                qa_llm=self.llm["qa_llm"],
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
            )
        else:
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm,
                qa_llm=self.llm,
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
            )

        final_output = query_chain.qa_chain.run(
            output=result, input_question=question
        ).strip("\n")

        logging.info(f"{final_output}")

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

        if reset_llm_type:
            self.define_llm(model_name=model_name)

        logging.info(
            f"Selected Language Model(s): {list(self.llm.values()) if isinstance(self.llm, dict) else self.llm}"
        )
        logging.info(f"Question: {question}")

        if isinstance(self.llm, dict):
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm["cypher_llm"],
                qa_llm=self.llm["qa_llm"],
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
            )
        else:
            query_chain: QueryChain = QueryChain(
                cypher_llm=self.llm,
                qa_llm=self.llm,
                schema=self.neo4j_connection.schema,
                search_type=self.search_type,
            )

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

        if not corrected_query:
            self.outputs.append((question, query_chain.generated_query, "", "", ""))
            return None

        try:
            result = self.neo4j_connection.execute_query(
                corrected_query, top_k=self.top_k
            )
            logging.info(f"Query Result: {result}")
        except Exception as e:
            logging.info(f"An error occurred trying to execute the query: {e}")
            self.outputs.append(
                (question, query_chain.generated_query, corrected_query, "", "")
            )
            return None

        final_output = query_chain.qa_chain.run(
            output=result, input_question=question
        ).strip("\n")

        logging.info(f"{final_output}")

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

            if embedding.dtype != np.float_:
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
