import os
from dotenv import load_dotenv

from qa_templates import CYPHER_GENERATION_PROMPT, CYPHER_OUTPUT_PARSER_PROMPT

from neo4j_schema_extractor import create_graph_schema_variables
from neo4j_query_corrector import correct_query
from neo4j_query_executor import execute

from langchain.chains import LLMChain
from langchain.llms import OpenAI
from langchain_google_genai import GoogleGenerativeAI

load_dotenv()

openai_api_key = os.getenv("MY_OPENAI_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")
neo4j_usr = os.getenv("NEO4J_USER")
neo4j_password = os.getenv("NEO4J_PASSWORD")
neo4j_db_name = os.getenv("NEO4J_DB_NAME")

llm_type = str(input("Which model:\n"))

if llm_type == "openai":
    # openai llms
    cypher_llm = OpenAI(openai_api_key=openai_api_key, model_name="gpt-3.5-turbo-instruct", temperature=0)
    qa_llm = OpenAI(openai_api_key=openai_api_key, model_name="gpt-3.5-turbo-instruct", temperature=0)

if llm_type == "gemini":
    # google llms
    cypher_llm = GoogleGenerativeAI(google_api_key=gemini_api_key, model="gemini-pro", temparature=0)
    qa_llm = GoogleGenerativeAI(google_api_key=gemini_api_key, model="gemini-pro", temparature=0)

cypher_chain = LLMChain(llm=cypher_llm, prompt=CYPHER_GENERATION_PROMPT, verbose=False)

# 32.360396s - without cache
# 17.121810s - with cache
schema = create_graph_schema_variables(URI="neo4j://localhost:7687", user=neo4j_usr, password=neo4j_password,
                                       db_name=neo4j_db_name)

question = "Tell me which genes are regulated by gene named ALX4."
out = cypher_chain.run(node_types=schema["nodes"], 
            node_properties=schema["node_properties"], 
            edge_properties=schema["edge_properties"],
            edges=schema["edges"], 
            question=question)


print(out)
print()

out = correct_query(query=out, edge_schema=schema["edges"])

print(out)
print()

result = execute(URI="neo4j://localhost:7687", 
                 user=neo4j_usr, 
                 password=neo4j_password,
                 db_name=neo4j_db_name,
                 query=out, 
                 top_k=5)

print(result)
print()

qa_chain = LLMChain(llm=qa_llm, prompt=CYPHER_OUTPUT_PARSER_PROMPT, verbose=False)

out = qa_chain.run(output=result, input_question=question)

print(out)







