import os
from dotenv import load_dotenv


class Config:
    """
    Config class for handling environment variables.
    It loads the variables from a .env file and makes them available as attributes.
    """
    def __init__(self):
        load_dotenv()
        self.openai_api_key = os.getenv("MY_OPENAI_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.neo4j_usr = os.getenv("NEO4J_USER")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD")
        self.neo4j_db_name = os.getenv("NEO4J_DB_NAME")


# Import required modules for Neo4J connection and schema extraction
from neo4j_schema_extractor import create_graph_schema_variables
from neo4j_query_executor import execute

class Neo4JConnection:
    """
    Neo4JConnection class to handle interactions with a Neo4J database.
    It encapsulates the connection details and provides methods to interact with the database.
    """
    def __init__(self, user, password, db_name):
        self.uri = "neo4j://localhost:7687"  # URI for Neo4J database
        self.user = user
        self.password = password
        self.db_name = db_name
        self.schema = self._create_schema()  # Automatically create the schema on initialization

    def _create_schema(self):
        """
        Private method to create the graph schema variables.
        This is done once during initialization.
        """
        return create_graph_schema_variables(URI=self.uri, user=self.user, password=self.password, db_name=self.db_name)

    def execute_query(self, query, top_k=5):
        """
        Method to execute a given Cypher query against the Neo4J database.
        It returns the top k results.
        """
        return execute(URI=self.uri, user=self.user, password=self.password, db_name=self.db_name, query=query, top_k=top_k)


# Import the Language Model wrappers for OpenAI and Google Generative AI
from langchain.llms import OpenAI
from langchain_google_genai import GoogleGenerativeAI

class OpenAILanguageModel:
    """
    OpenAILanguageModel class for interacting with OpenAI's language models.
    It initializes the model with given API key and specified parameters.
    """
    def __init__(self, api_key):
        self.llm = OpenAI(openai_api_key=api_key, model_name="gpt-3.5-turbo-instruct", temperature=0)

class GoogleGenerativeLanguageModel:
    """
    GoogleGenerativeLanguageModel class for interacting with Google's Generative AI models.
    It initializes the model with given API key and specified parameters.
    """
    def __init__(self, api_key):
        self.llm = GoogleGenerativeAI(google_api_key=api_key, model="gemini-pro", temparature=0)


# Import LLMChain for handling the sequence of language model operations
from langchain.chains import LLMChain
from neo4j_query_corrector import correct_query
from qa_templates import CYPHER_GENERATION_PROMPT, CYPHER_OUTPUT_PARSER_PROMPT

class QueryChain:
    """
    QueryChain class to handle the generation, correction, and parsing of Cypher queries using language models.
    It encapsulates the entire process as a single chain of operations.
    """
    def __init__(self, llm, schema):
        self.cypher_chain = LLMChain(llm=llm, prompt=CYPHER_GENERATION_PROMPT, verbose=False)
        self.qa_chain = LLMChain(llm=llm, prompt=CYPHER_OUTPUT_PARSER_PROMPT, verbose=False)
        self.schema = schema

    def run_chain(self, question):
        """
        Executes the query chain: generates a query, corrects it, and returns the corrected query.
        """
        generated_query = self.cypher_chain.run(node_types=self.schema["nodes"], 
                                                node_properties=self.schema["node_properties"], 
                                                edge_properties=self.schema["edge_properties"],
                                                edges=self.schema["edges"], 
                                                question=question)
        corrected_query = correct_query(query=generated_query, edge_schema=self.schema["edges"])
        return corrected_query
    

def main():
    """
    Main function to execute the flow of operations.
    It initializes all necessary classes and executes the query generation, execution, and parsing process.
    """
    # ANSI color codes for text formatting
    ANSI_CYAN = '\033[96m'
    ANSI_GREEN = '\033[92m'
    ANSI_YELLOW = '\033[93m'
    ANSI_RESET = '\033[0m'

    config = Config()
    neo4j_connection = Neo4JConnection(config.neo4j_usr, config.neo4j_password, config.neo4j_db_name)

    llm_type = input("Which model (openai / gemini):\n")
    llm = None
    if llm_type == "openai":
        llm = OpenAILanguageModel(config.openai_api_key).llm
    elif llm_type == "gemini":
        llm = GoogleGenerativeLanguageModel(config.gemini_api_key).llm
    else:
        raise ValueError("Unsupported Language Model Type")

    query_chain = QueryChain(llm, neo4j_connection.schema)
    question = "Which genes are related to disease named psoriasis?"
    corrected_query = query_chain.run_chain(question)
    
    # Print the generated query
    print(f"{ANSI_CYAN}Generated Query:{ANSI_RESET} {corrected_query}\n")
    
    result = neo4j_connection.execute_query(corrected_query)

    # Print the query result
    print(f"{ANSI_GREEN}Query Result:{ANSI_RESET} {result}\n")

    final_output = query_chain.qa_chain.run(output=result, input_question=question)

    # Print the final output in natural language
    print(f"{ANSI_YELLOW}Natural Language Answer:{ANSI_RESET} {final_output}\n")

if __name__ == "__main__":
    main()