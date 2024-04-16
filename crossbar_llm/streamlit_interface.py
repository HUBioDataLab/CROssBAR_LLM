import streamlit as st
import sys, os, logging
from datetime import datetime

# Import path
current_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from crossbar_llm.langchain_llm_qa_trial import RunPipeline

# Initialize logging
current_date = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
log_filename = f"query_log_{current_date}.log"
logging.basicConfig(filename=log_filename, level=logging.INFO, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Initialize the pipeline once
rp = RunPipeline(verbose=False, model_name="gpt-3.5-turbo")  # Assuming default verbose is False

def run_query(question: str, llm_type, api_key=None) -> str:
    logging.info("Processing question...")

    # Run the pipeline
    try:
        response = rp.run_for_query(question, model_name=llm_type, reset_llm_type=True, api_key=api_key)
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e

    return response


def run_natural(query: str, question: str, llm_type, verbose_mode: bool, api_key=None) -> str:
    logging.info("Processing question...")

    # Run the pipeline
    try:
        response, result = rp.execute_query(query=query, question=question, model_name=llm_type, reset_llm_type=True, api_key=api_key)
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e
    
    verbose_output = ""
    if verbose_mode:
        with open(log_filename, 'r') as file:
            verbose_output = file.read()

    return response, verbose_output, result


def generate_and_run(question: str, llm_type, verbose_mode: bool, api_key=None) -> str:
    logging.info("Processing question...")

    # Run the pipeline
    try:
        query = rp.run_for_query(question, model_name=llm_type, reset_llm_type=True, api_key=api_key)
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e

    # Run the pipeline
    try:
        response, result = rp.execute_query(query=query, question=question, model_name=llm_type, reset_llm_type=True, api_key=api_key)
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e
    
    verbose_output = ""
    if verbose_mode:
        with open(log_filename, 'r') as file:
            verbose_output = file.read()

    return response, verbose_output, result, query

st.title("CROssBAR LLM Query Interface")
st.markdown("### Ask a natural language question here (check below for examples)")

with st.form("query_form"):
    question = st.text_input("Question (Please enter your natural language query here using clear and plain English)", "")
    query_llm_type = st.selectbox("LLM choice (Select the large language model to be utilized for processing your query from the dropdown menu)", ["gpt-3.5-turbo-0125", "gemini-pro", "claude-3-opus-20240229"])
    openai_api_key = st.text_input("OpenAI API key (If you choose any of the GPT models, you are required to enter your key to run the query)", "")
    verbose_mode = st.checkbox("Enable verbose mode (Check this box to obtain detailed information about the LLM and DB runs including error logs, context for the query and the response)")
    generate_button = st.form_submit_button("Generate and Run Cypher Query")

if generate_button:
    response, verbose_output, result, query = generate_and_run(question, query_llm_type, verbose_mode, openai_api_key)
    st.text_area("Generated DB Query", query, height=100)
    st.text_area("Natural language answer", response, height=100)
    if verbose_mode:
        st.text_area("Verbose output", verbose_output, height=100)