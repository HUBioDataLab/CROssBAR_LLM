import os, sys
import logging
from dotenv import load_dotenv
from datetime import datetime

# Import path
current_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# Import required modules for Neo4J connection and schema extraction
from crossbar_llm.neo4j_query_executor_extractor import Neo4jGraphHelper

# Import the Language Model wrappers
from langchain_community.chat_models import ChatOpenAI
from langchain_google_genai import GoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq
from langchain_community.llms import Replicate

# Import LLMChain for handling the sequence of language model operations
from langchain.chains import LLMChain
from crossbar_llm.neo4j_query_corrector import correct_query
from crossbar_llm.qa_templates import CYPHER_GENERATION_PROMPT, CYPHER_OUTPUT_PARSER_PROMPT

from pydantic import BaseModel, validate_call

from typing import Literal, Union

import pandas as pd
import numpy as np


def configure_logging(verbose=False, log_filename="query_log.log"):
    log_handlers = [logging.FileHandler(log_filename)]
    if verbose:
        log_handlers.append(logging.StreamHandler())
    
    logging.basicConfig(handlers=log_handlers, level=logging.INFO, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class Config(BaseModel):
    """
    Config class for handling environment variables.
    It loads the variables from a .env file and makes them available as attributes.
    """
    load_dotenv()
    openai_api_key: str = os.getenv("MY_OPENAI_API_KEY")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY")
    groq_api_key: str = os.getenv("GROQ_API_KEY")
    replicate_api_key: str = os.getenv("REPLICATE_API_KEY")
    neo4j_usr: str = os.getenv("NEO4J_USER")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD")
    neo4j_db_name: str = os.getenv("NEO4J_DB_NAME")
    neo4j_uri: str = os.getenv("NEO4J_URI")

class Neo4JConnection:
    """
    Neo4JConnection class to handle interactions with a Neo4J database.
    It encapsulates the connection details and provides methods to interact with the database.
    """
    def __init__(self, user: str, password: str, db_name: str, uri: str):
        self.graph_helper = Neo4jGraphHelper(uri, user, password, db_name)
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
    def __init__(self, api_key: str, model_name: str = None, temperature: float | int = None):
        self.model_name = model_name or "gpt-3.5-turbo-instruct"
        self.temperature = temperature or 0
        self.llm = ChatOpenAI(api_key=api_key, model_name=self.model_name, temperature=self.temperature, request_timeout=600)

class GoogleGenerativeLanguageModel:
    """
    GoogleGenerativeLanguageModel class for interacting with Google's Generative AI models.
    It initializes the model with given API key and specified parameters.
    """
    def __init__(self, api_key: str, model_name: str = None, temperature: float | int = None):
        self.model_name = model_name or "gemini-pro"
        self.temperature = temperature or 0
        self.llm = GoogleGenerativeAI(google_api_key = api_key, model = self.model_name, temparature = self.temperature)

class AnthropicLanguageModel:
    """
    AnthropicLanguageModel class for interacting with Anthropic's language models.
    It initializes the model with given API key and specified parameters.
    """
    def __init__(self, api_key: str, model_name: str = None, temperature: float | int = None):
        self.model_name = model_name or "claude-3-opus-20240229"
        self.temperature = temperature or 0
        self.llm = ChatAnthropic(anthropic_api_key=api_key, model_name=self.model_name, temperature=self.temperature)

class GroqLanguageModel:
    """
    GroqLanguageModel class for interacting with Groq's language models.
    It initializes the model with given API key and specified parameters.
    """
    def __init__(self, api_key: str, model_name: str = None, temperature: float | int = None):
        self.model_name = model_name or "llama3-70b-8192"
        self.temperature = temperature or 0
        self.llm = ChatGroq(groq_api_key=api_key, model_name=self.model_name, temperature=self.temperature)

class ReplicateLanguageModel:
    """
    ReplicateLanguageModel class for interacting with Replicate's language models.
    It initializes the model with given API key and specified parameters.
    """
    def __init__(self, api_key: str, model_name: str = None, temperature: float | int = None):
        self.model_name = model_name or "replicate-1.0"
        self.temperature = temperature or 0
        self.llm = Replicate(replicate_api_key=api_key, model_name=self.model_name, temperature=self.temperature)
class QueryChain:
    """
    QueryChain class to handle the generation, correction, and parsing of Cypher queries using language models.
    It encapsulates the entire process as a single chain of operations.
    """
    def __init__(self, 
                 cypher_llm: Union[OpenAILanguageModel, GoogleGenerativeLanguageModel, AnthropicLanguageModel, GroqLanguageModel, ReplicateLanguageModel],
                 qa_llm: Union[OpenAILanguageModel, GoogleGenerativeLanguageModel, AnthropicLanguageModel, GroqLanguageModel, ReplicateLanguageModel],
                 schema: dict, 
                 verbose: bool = False):
        self.cypher_chain = LLMChain(llm=cypher_llm, prompt=CYPHER_GENERATION_PROMPT, verbose = verbose)
        self.qa_chain = LLMChain(llm=qa_llm, prompt=CYPHER_OUTPUT_PARSER_PROMPT, verbose = verbose)
        self.schema = schema
        self.verbose = verbose

    @validate_call
    def run_cypher_chain(self, question: str) -> str:
        """
        Executes the query chain: generates a query, corrects it, and returns the corrected query.
        """
        self.generated_query = self.cypher_chain.run(node_types=self.schema["nodes"], 
                                                node_properties=self.schema["node_properties"], 
                                                edge_properties=self.schema["edge_properties"],
                                                edges=self.schema["edges"], 
                                                question=question).strip().strip("\n").replace("cypher","").strip("`")
        

        corrected_query = correct_query(query=self.generated_query, edge_schema=self.schema["edges"])

        # Logging generated and corrected queries
        logging.info(f"Generated Query: {self.generated_query}")
        logging.info(f"Corrected Query: {corrected_query}")

        return corrected_query
    

class RunPipeline:

    def __init__(self,
                 model_name = Union[str, list[str], dict[Literal["cypher_llm_model", "qa_llm_model"], str]],
                 verbose: bool = False,
                 top_k: int = 5,):
        
        self.verbose = verbose
        self.top_k = top_k
        self.config: Config = Config()
        self.neo4j_connection: Neo4JConnection = Neo4JConnection(self.config.neo4j_usr, 
                                                                 self.config.neo4j_password, 
                                                                 self.config.neo4j_db_name,
                                                                 self.config.neo4j_uri)
        
        # define llm type(s)
        self.define_llm(model_name)

        # define outputs list
        self.outputs = []

    def define_llm(self, model_name):

        google_llm_models = [
            "gemini-pro",
            "gemini-1.5-pro-latest"
            ]            
        openai_llm_models = [
                "gpt-3.5-turbo-instruct",
                "gpt-3.5-turbo-1106",
                "gpt-3.5-turbo",
                "gpt-3.5-turbo-0125",
                "gpt-4-0125-preview",
                "gpt-4-turbo-preview",
                "gpt-4-1106-preview",
                "gpt-4-32k-0613",
                "gpt-4-0613",
                "gpt-3.5-turbo-16k"
            ]
        antrophic_llm_models = [
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307",
                "claude-2.1",
                "claude-2.0",
                "claude-instant-1.2",
            ]
        groq_llm_models = [
                "llama3-8b-8192",
                "llama3-70b-8192",
                "mixtral-8x7b-32768",
                "gemma-7b-it",
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
                        self.llm["cypher_llm"] = OpenAILanguageModel(self.config.openai_api_key, model_name=model_name["cypher_llm_model"]).llm
                    elif model_name in google_llm_models:
                        self.llm["cypher_llm"] = GoogleGenerativeLanguageModel(self.config.gemini_api_key, model_name=model_name["cypher_llm_model"]).llm
                    elif model_name in antrophic_llm_models:
                        self.llm["cypher_llm"] = AnthropicLanguageModel(self.config.anthropic_api_key, model_name=model_name["cypher_llm_model"]).llm
                    elif model_name in groq_llm_models:
                        self.llm["cypher_llm"] = GroqLanguageModel(self.config.groq_api_key, model_name=model_name["cypher_llm_model"]).llm
                    else:
                        raise ValueError("Unsupported Language Model Name")
                elif model_name in openai_llm_models:
                    self.llm["qa_llm"] = OpenAILanguageModel(self.config.openai_api_key, model_name=model_name["qa_llm_model"]).llm
                elif model_name in google_llm_models:
                    self.llm["qa_llm"] = GoogleGenerativeLanguageModel(self.config.gemini_api_key, model_name=model_name["qa_llm_model"]).llm
                elif model_name in antrophic_llm_models:
                    self.llm["qa_llm"] = AnthropicLanguageModel(self.config.anthropic_api_key, model_name=model_name["qa_llm_model"]).llm
                elif model_name in groq_llm_models:
                    self.llm["qa_llm"] = GroqLanguageModel(self.config.groq_api_key, model_name=model_name["qa_llm_model"]).llm
                else:
                    raise ValueError("Unsupported Language Model Name")

        elif model_name in google_llm_models:
            self.llm = GoogleGenerativeLanguageModel(self.config.gemini_api_key, model_name=model_name).llm
        elif model_name in openai_llm_models:
            self.llm = OpenAILanguageModel(self.config.openai_api_key, model_name=model_name).llm
        elif model_name in antrophic_llm_models:
            self.llm = AnthropicLanguageModel(self.config.anthropic_api_key, model_name=model_name).llm
        elif model_name in groq_llm_models:
            self.llm = GroqLanguageModel(self.config.groq_api_key, model_name=model_name).llm
        else:
            raise ValueError("Unsupported Language Model Name")
        
    @validate_call
    def run_for_query(self, 
            question: str, 
            reset_llm_type: bool = False,
            model_name: Union[str, list[str], dict[Literal["cypher_llm_model", "qa_llm_model"], str]] = None,
            api_key: str = None) -> str:
        
        if api_key:
            self.config.openai_api_key = api_key
            self.config.gemini_api_key = api_key
            self.config.anthropic_api_key = api_key
            self.config.groq_api_key = api_key
            self.config.replicate_api_key = api_key

        else:
            self.config = Config()

        if reset_llm_type:
            self.define_llm(model_name=model_name)   

        logging.info(
            f"Selected Language Model(s): {list(self.llm.values()) if isinstance(self.llm, dict) else self.llm}"
        )
        logging.info(f"Question: {question}")

        if isinstance(self.llm, dict):
            query_chain: QueryChain = QueryChain(cypher_llm=self.llm["cypher_llm"], qa_llm=self.llm["qa_llm"], schema = self.neo4j_connection.schema)
        else:
            query_chain: QueryChain = QueryChain(cypher_llm=self.llm, qa_llm=self.llm, schema = self.neo4j_connection.schema)

        corrected_query = query_chain.run_cypher_chain(question)

        return corrected_query
    
    def execute_query(self, query: str, question: str, model_name, reset_llm_type, api_key: str = None) -> str:
        result = self.neo4j_connection.execute_query(query, top_k=self.top_k)

        if api_key:
            self.config.openai_api_key = api_key
            self.config.gemini_api_key = api_key
            self.config.anthropic_api_key = api_key
            self.config.groq_api_key = api_key
            self.config.replicate_api_key = api_key
        else:
            self.config = Config()

        if reset_llm_type:
            self.define_llm(model_name=model_name)

        logging.info(f"Query Result: {result}")

        if isinstance(self.llm, dict):
            query_chain: QueryChain = QueryChain(cypher_llm=self.llm["cypher_llm"], qa_llm=self.llm["qa_llm"], schema = self.neo4j_connection.schema)
        else:
            query_chain: QueryChain = QueryChain(cypher_llm=self.llm, qa_llm=self.llm, schema = self.neo4j_connection.schema)

        final_output = query_chain.qa_chain.run(output=result, input_question=question).strip("\n")

        logging.info(f"{final_output}")

        return final_output, result
        

    @validate_call
    def run_without_errors(self,
                           question: str, 
                           reset_llm_type: bool = False,
                           model_name: Union[str, list[str], dict[Literal["cypher_llm_model", "qa_llm_model"], str]] = None) -> str:
        
        if reset_llm_type:
            self.define_llm(model_name=model_name)

        logging.info(
            f"Selected Language Model(s): {list(self.llm.values()) if isinstance(self.llm, dict) else self.llm}"
        )
        logging.info(f"Question: {question}")

        if isinstance(self.llm, dict):
            query_chain: QueryChain = QueryChain(cypher_llm=self.llm["cypher_llm"], qa_llm=self.llm["qa_llm"], schema = self.neo4j_connection.schema)
        else:
            query_chain: QueryChain = QueryChain(cypher_llm=self.llm, qa_llm=self.llm, schema = self.neo4j_connection.schema)

        corrected_query = query_chain.run_cypher_chain(question)

        if not corrected_query:
            self.outputs.append((query_chain.generated_query, "", "", ""))
            return None

        try:
            result = self.neo4j_connection.execute_query(corrected_query, top_k=self.top_k)
            logging.info(f"Query Result: {result}")
        except Exception as e:
            logging.info(f"An error occurred trying to execute the query: {e}")
            self.outputs.append((query_chain.generated_query, corrected_query, "", ""))
            return None

        final_output = query_chain.qa_chain.run(output=result, input_question=question).strip("\n")

        logging.info(f"{final_output}")

        # add outputs of all steps to a list
        self.outputs.append((query_chain.generated_query, 
                          corrected_query,
                          result,
                          final_output))
        
        return final_output
    
    def create_dataframe_from_outputs(self) -> pd.DataFrame:
        df = pd.DataFrame(self.outputs, columns=["Generated Query", "Corrected Query",
                                            "Query Result", "Natural Language Answer"])

        return df.replace("", np.nan)


def main():
    """
    Main function to execute the flow of operations.
    It initializes all necessary classes and executes the query generation, execution, and parsing process.
    """

    current_date = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
    log_filename = f"query_log_{current_date}.log"

    verbose_input = input("Enable verbose mode? (yes/no):\n").lower() == 'yes'
    configure_logging(verbose=verbose_input, log_filename=log_filename)
    
    logging.info("Starting the pipeline...")

    try:
        pipeline = RunPipeline(verbose=verbose_input, model_name="gpt-3.5-turbo-instruct")

        question = str(input("Enter a question:\n"))

        final_output = pipeline.run(question=question)

        print(final_output)

        logging.info("Pipeline finished successfully.")
    
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e
    

if __name__ == "__main__":
    main()
