import streamlit as st
from code_editor import code_editor
from streamlit_ace import st_ace
import sys, os, logging
from datetime import datetime

# Import path
current_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from crossbar_llm.langchain_llm_qa_trial import RunPipeline


def initialize_logging():
    if 'log_filename' not in st.session_state:
        current_date = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
        st.session_state.log_filename = f"query_log_{current_date}.log"
        logging.basicConfig(filename=st.session_state.log_filename, level=logging.INFO,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

initialize_logging()


def fix_markdown(text: str) -> str:
    return text.replace(":", "\:")

# Initialize the pipeline once
if 'rp' not in st.session_state:
    st.session_state.rp = RunPipeline(verbose=False, model_name="gpt-3.5-turbo")

def run_query(question: str, llm_type, api_key=None) -> str:
    logging.info("Processing question...")

    # Run the pipeline
    try:
        response = st.session_state.rp.run_for_query(question, model_name=llm_type, reset_llm_type=True, api_key=api_key)
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e

    return response


def run_natural(query: str, question: str, llm_type, verbose_mode: bool, api_key=None) -> str:
    logging.info("Processing question...")

    # Run the pipeline
    try:
        response, result = st.session_state.rp.execute_query(query=query, question=question, model_name=llm_type, reset_llm_type=True, api_key=api_key)
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e
    
    verbose_output = ""
    if verbose_mode:
        with open(st.session_state.log_filename, 'r') as file:
            verbose_output = file.read()

    return response, verbose_output, result


def generate_and_run(question: str, llm_type, verbose_mode: bool, api_key=None) -> str:
    logging.info("Processing question...")

    # Run the pipeline
    try:
        query = st.session_state.rp.run_for_query(question, model_name=llm_type, reset_llm_type=True, api_key=api_key)
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e

    # Run the pipeline
    try:
        response, result = st.session_state.rp.execute_query(query=query, question=question, model_name=llm_type, reset_llm_type=True, api_key=api_key)
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e
    
    verbose_output = ""
    if verbose_mode:
        with open(st.session_state.log_filename, 'r') as file:
            verbose_output = file.read()

    return response, verbose_output, result, query

st.title("CROssBAR LLM Query Interface")

examples = [
    {"label": "Gene related to Psoriasis", "question": "Which Gene is related to Disease named psoriasis?", "model": "gemini-1.5-pro-latest", "verbose": False},
    {"label": "Targets of Caffeine", "question": "What proteins does the drug named Caffeine target?", "model": "gemini-1.5-pro-latest", "verbose": False}
]

model_choices = [
    "gemini-pro",
    "gemini-1.5-pro-latest",
    "gemini-1.5-flash-latest",
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
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    "claude-3-5-sonnet-20240620",
    "claude-2.1",
    "claude-2.0",
    "claude-instant-1.2",
    "llama3-8b-8192",
    "llama3-70b-8192",
    "mixtral-8x7b-32768",
    "gemma-7b-it",
    "gemma2-9b-it",
]
st.session_state.selected_example = st.selectbox("Choose an example to run:", 
                                                options=[ex['label'] for ex in examples],
                                                index=None)

if st.session_state.selected_example:
    example = next(ex for ex in examples if ex['label'] == st.session_state.selected_example)
    st.session_state.example_question = example['question']
    st.session_state.example_model_index = model_choices.index(example['model'])
    
else:
    st.session_state.example_question = None
    st.session_state.example_model_index = None

tab1, tab2 = st.tabs(["LLM Query", "Vector File Upload"])


def query_interface(file_upload=False):
    form_name = ""
    if file_upload:
        form_name = "query_form_file"
    else:
        form_name = "query_form"
    # Input form
    with st.form(form_name):

        question = st.text_area("Question*",
                                st.session_state.example_question,
                                placeholder="Enter your natural language query here using clear and plain English", 
                                height=100, 
                                help="Please be as specific as possible for better results. *Required field.")
        query_llm_type = st.selectbox("LLM for Query Generation*", 
                                    model_choices, 
                                    index=st.session_state.example_model_index, 
                                    help="Choose the LLM to generate the Cypher query. *Required field."
                                    )
        llm_api_key = st.text_input("API Key for LLM", type="password", help="Enter your API key if you choose paid model.")
        limit_query_return = st.selectbox("Limit query return", options=[1, 3, 5, 10, 15, 20, 50, 100], help="Select the number of elements to limit the query return.", index=2)
        verbose_mode = st.checkbox("Enable Verbose Mode", help="Show detailed logs and intermediate steps.")
        
        if file_upload:
            vector_file = st.file_uploader("Upload Vector File", type=["csv", "json", "parquet", "txt"], help="Upload your vector file here.")

        # Button container
        button_container = st.container()
        col1, col2, col3 = button_container.columns(3)

        if 'generate_and_run_submitted' not in st.session_state:
            st.session_state.generate_and_run_submitted = False
        if 'generate_query_submitted' not in st.session_state:
            st.session_state.generate_query_submitted = False
        if 'run_query_submitted' not in st.session_state:
            st.session_state.run_query_submitted = False
        if "generated_query" not in st.session_state:
            st.session_state.generated_query = None
        
        with col1:
            if st.form_submit_button("Generate & Run Query", help="Click to process your query and get results.", type="primary"):
                st.session_state.generate_and_run_submitted = True
                st.session_state.generate_query_submitted = False
                st.session_state.run_query_submitted = False
        with col2:
            if st.form_submit_button("Generate Cypher Query", help="Click to generate the Cypher query only."):
                st.session_state.generate_query_submitted = True
                st.session_state.generate_and_run_submitted = False
                st.session_state.run_query_submitted = False
        with col3:
            if st.form_submit_button("Run Generated Query", help="Click to run the generated Cypher query."):
                st.session_state.run_query_submitted = True
                st.session_state.generate_query_submitted = False
                st.session_state.generate_and_run_submitted = False

    if st.session_state.generate_and_run_submitted:
        if question and query_llm_type:
            with st.spinner('Generating and Running Query...'):
                response, verbose_output, result, query = generate_and_run(question, 
                                                                        query_llm_type, 
                                                                        verbose_mode, 
                                                                        llm_api_key)
            
            # Output areas with styling
            st.subheader("Generated Cypher Query:")
            st.code(query, language="cypher")

            st.subheader("Raw Query Output:")
            st.code(str(result))
            
            st.subheader("Natural Language Answer:")
            st.write(fix_markdown(response))
            
            if verbose_mode:
                st.subheader("Verbose Output:")
                st.code(verbose_output, language="log")
            
        else:
            st.warning("Please make sure to fill in all the required fields before submitting the form.")
        st.session_state.generate_and_run_submitted = False
    
    if st.session_state.generate_query_submitted:
      if question and query_llm_type:
          with st.spinner('Generating Cypher Query..'):
              generated_query = run_query(question, 
                              query_llm_type, 
                              llm_api_key)

          # Display the generated query with the code editor
          st.subheader("Generated Cypher Query:")
          st.text_area("You can edit the generated query below:", value=generated_query, key="edited_query")
          # edited_query = code_editor(st.session_state.generated_query, lang="cypher", key="cypher_editor")
          # st.code(str(edited_query))
      else:
          st.warning("Please make sure to fill in all the required fields before submitting the form.")
      st.session_state.generate_query_submitted = False

    if st.session_state.run_query_submitted:
        if st.session_state.edited_query: 
            with st.spinner('Running Cypher Query...'):
                    response, verbose_output, result = run_natural(st.session_state.edited_query, 
                                                                question, 
                                                                query_llm_type, 
                                                                verbose_mode, 
                                                                llm_api_key)
                    
                    st.subheader("Generated Cypher Query:")
                    st.code(st.session_state.generated_query, language="cypher")

                    st.subheader("Raw Query Output:")
                    st.code(str(result))

                    st.subheader("Natural Language Answer:")
                    st.write(response)
                    
                    if verbose_mode:
                        st.subheader("Verbose Output:")
                        st.code(verbose_output, language="log")
        else:
            st.warning("Please make sure the Cypher query is generated using 'Generate Cypher Query' button before running it.")
        st.session_state.run_query_submitted = False
        st.session_state.edited_query = None
      
with tab1:
    query_interface(file_upload=False)

with tab2:
    query_interface(file_upload=True)