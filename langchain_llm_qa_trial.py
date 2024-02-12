import os
import logging
from dotenv import load_dotenv
from datetime import datetime

# Import required modules for Neo4J connection and schema extraction
from neo4j_query_executor_extractor import Neo4jGraphHelper

# Import the Language Model wrappers for OpenAI and Google Generative AI
from langchain.llms import OpenAI
from langchain_google_genai import GoogleGenerativeAI

# Import LLMChain for handling the sequence of language model operations
from langchain.chains import LLMChain
from neo4j_query_corrector import correct_query
from qa_templates import CYPHER_GENERATION_PROMPT, CYPHER_OUTPUT_PARSER_PROMPT

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
    neo4j_usr: str = os.getenv("NEO4J_USER")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD")
    neo4j_db_name: str = os.getenv("NEO4J_DB_NAME")

class Neo4JConnection:
    """
    Neo4JConnection class to handle interactions with a Neo4J database.
    It encapsulates the connection details and provides methods to interact with the database.
    """
    def __init__(self, user: str, password: str, db_name: str):
        self.graph_helper = Neo4jGraphHelper("neo4j://localhost:7687", user, password, db_name)
        self.schema = self.graph_helper.create_graph_schema_variables()

    @validate_call
    def execute_query(self, query: str, top_k: int = 5) -> list:
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
        self.llm = OpenAI(openai_api_key=api_key, model_name=self.model_name, temperature=self.temperature)

class GoogleGenerativeLanguageModel:
    """
    GoogleGenerativeLanguageModel class for interacting with Google's Generative AI models.
    It initializes the model with given API key and specified parameters.
    """
    def __init__(self, api_key: str, model_name: str = None, temperature: float | int = None):
        self.model_name = model_name or "gemini-pro"
        self.temperature = temperature or 0
        self.llm = GoogleGenerativeAI(google_api_key = api_key, model = self.model_name, temparature = self.temperature)

class QueryChain:
    """
    QueryChain class to handle the generation, correction, and parsing of Cypher queries using language models.
    It encapsulates the entire process as a single chain of operations.
    """
    def __init__(self, llm: Union[OpenAILanguageModel, GoogleGenerativeLanguageModel], schema, verbose: bool = False):
        self.cypher_chain = LLMChain(llm=llm, prompt=CYPHER_GENERATION_PROMPT, verbose = verbose)
        self.qa_chain = LLMChain(llm=llm, prompt=CYPHER_OUTPUT_PARSER_PROMPT, verbose = verbose)
        self.schema = schema
        self.verbose = verbose

    @validate_call
    def run_chain(self, question: str) -> str:
        """
        Executes the query chain: generates a query, corrects it, and returns the corrected query.
        """
        self.generated_query = self.cypher_chain.run(node_types=self.schema["nodes"], 
                                                node_properties=self.schema["node_properties"], 
                                                edge_properties=self.schema["edge_properties"],
                                                edges=self.schema["edges"], 
                                                question=question)
        

        corrected_query = correct_query(query=self.generated_query, edge_schema=self.schema["edges"])

        # Logging generated and corrected queries
        logging.info(f"Generated Query: {self.generated_query}")
        logging.info(f"Corrected Query: {corrected_query}")

        return corrected_query
    

class RunPipeline:

    def __init__(self, llm_type: Literal["openai", "gemini"] = None, verbose: bool = False):
        
        self.verbose = verbose
        self.config: Config = Config()
        self.neo4j_connection: Neo4JConnection = Neo4JConnection(self.config.neo4j_usr, 
                                                                 self.config.neo4j_password, 
                                                                 self.config.neo4j_db_name)
        
        llm_type = llm_type or str(input("Which model (openai / gemini):\n"))
        
        if llm_type == "openai":
            self.llm = OpenAILanguageModel(self.config.openai_api_key).llm
        elif llm_type == "gemini":
            self.llm = GoogleGenerativeLanguageModel(self.config.gemini_api_key).llm
        else:
            raise ValueError("Unsupported Language Model Type")
        
        # define outputs list
        self.outputs = []
        
    @validate_call
    def run(self, 
            question: str, 
            reset_llm_type: bool = False,
            llm_type: Literal["openai", "gemini"] = None) -> str:

        if reset_llm_type:
            self.reset_llm_type(llm_type=llm_type)   

        logging.info(f"Selected Language Model: {self.llm.model_name}")
        logging.info(f"Question: {question}")

        query_chain: QueryChain = QueryChain(llm=self.llm, schema = self.neo4j_connection.schema)

        corrected_query = query_chain.run_chain(question)

        result = self.neo4j_connection.execute_query(corrected_query)

        logging.info(f"Query Result: {result}")

        final_output = query_chain.qa_chain.run(output=result, input_question=question)

        logging.info(f"Natural Language Answer: {final_output}")

        # add outputs of all steps to a list
        self.outputs.append((query_chain.generated_query, 
                          corrected_query,
                          result,
                          final_output))
        
        return final_output
    @validate_call
    def run_without_errors(self,
                           question: str, 
                           reset_llm_type: bool = False,
                           llm_type: Literal["openai", "gemini"] = None) -> str:
        
        if reset_llm_type:
            self.reset_llm_type(llm_type=llm_type)

        logging.info(f"Selected Language Model: {self.llm.model_name}")
        logging.info(f"Question: {question}")

        query_chain: QueryChain = QueryChain(llm=self.llm, schema = self.neo4j_connection.schema)

        corrected_query = query_chain.run_chain(question)

        if not corrected_query:
            self.outputs.append((query_chain.generated_query, "", "", ""))
            return None

        try:
            result = self.neo4j_connection.execute_query(corrected_query)
            logging.info(f"Query Result: {result}")
        except Exception as e:
            logging.info(f"An error occurred trying to execute the query: {e}")
            self.outputs.append((query_chain.generated_query, corrected_query, "", ""))
            return None

        final_output = query_chain.qa_chain.run(output=result, input_question=question)

        logging.info(f"Natural Language Answer: {final_output}")

        # add outputs of all steps to a list
        self.outputs.append((query_chain.generated_query, 
                          corrected_query,
                          result,
                          final_output))
        
        return final_output

        
    
    def create_dataframe_from_outputs(self) -> pd.DataFrame:
        df = pd.DataFrame(self.outputs, columns=["Generated Query", "Corrected Query",
                                            "Query Result", "Natural Language Answer"])
        df.replace("", np.nan, inplace=True)

        return df
    
    @validate_call
    def reset_llm_type(self, llm_type: Literal["openai", "gemini"] = None) -> None:
        if llm_type == "openai":
            self.llm = OpenAILanguageModel(self.config.openai_api_key).llm
        elif llm_type == "gemini":
            self.llm = GoogleGenerativeLanguageModel(self.config.gemini_api_key).llm
        else:
            raise ValueError("Unsupported Language Model Type")


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
        pipeline = RunPipeline(verbose=verbose_input)

        question = str(input("Enter a question:\n"))

        final_output = pipeline.run(question=question)

        print(final_output)

        logging.info("Pipeline finished successfully.")
    
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e
    

if __name__ == "__main__":
    main()
