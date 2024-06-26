import gradio as gr
import sys, os, logging
from datetime import datetime

# Import path
current_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

css = """
#question_box {
    font-size: 16px;
    background-color: #bfe3b4;
    border: 2px solid #EB6221;
    padding: 10px;
    border-radius: 5px;
}
#natural_answer_box {
    font-size: 16px;
    background-color: #ffae69;
    border: 2px solid #EB6221;
    padding: 10px;
    border-radius: 5px;
}
"""


from crossbar_llm.langchain_llm_qa_trial import RunPipeline

# Initialize logging
current_date = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
log_filename = f"query_log_{current_date}.log"
log_handlers = [logging.FileHandler(log_filename)]
logging.basicConfig(handlers=log_handlers, level=logging.INFO, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Initialize the pipeline once
rp = RunPipeline(verbose=False, model_name="gpt-3.5-turbo-instruct")  # Assuming default verbose is False


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


with gr.Blocks(css=css) as interface:
    with gr.Column():
        gr.Markdown("## CROssBAR LLM Query Interface")
        gr.Markdown("### Ask natural language question here (check below for examples)")
        question = gr.Textbox(label="Question (Please enter your natural language query here using clear and plain English)", elem_id="question_box")
        query_llm_type = gr.Dropdown(["gpt-3.5-turbo-instruct", "gemini-pro", "claude-3-opus-20240229", "gpt-3.5-turbo"], label="LLM choice (Select the large language model to be utilised for processing your query from the dropdown menu)", value="gpt-3.5-turbo")
        openai_api_key = gr.Textbox(label="OpenAI API key (If you choose any of the GPT models, you are required to enter your key to run the query)", placeholder="Enter your OpenAI API Key here")

    with gr.Row():
        generate_and_run_button = gr.Button("Generate and Run Cypher Query", variant="primary")
        run_query_button = gr.Button("Generate Cypher Query", variant="secondary")
        clear_question = gr.ClearButton(question, value="Clear Question")
        
    with gr.Column():    
        query_textbox = gr.Textbox(label="Generated DB Query (This is the graphDB query in Cypher generated by the LLM as an output to your question. You can inspect the query and modify it if necessary. Please hit \"Run Cypher Query\" after your modification. This option is added to fix potential LLM hallucinations)", interactive=True)
        verbose_mode = gr.Checkbox(label="Enable verbose mode (Check this box to obtain detailed information about the LLM and DB runs including error logs, context for the query and the response)")
        natural_llm_type = gr.Dropdown(["gpt-3.5-turbo-instruct", "gemini-pro", "claude-3-opus-20240229"], label="LLM choice (Select the large language model to be utilised for returning the natural language answer from the dropdown menu)", value="gpt-3.5-turbo-instruct")

    with gr.Row():
        run_natural_button = gr.Button("Run Cypher Query", variant="secondary")
        clear_query = gr.ClearButton(query_textbox, value="Clear Query")

    natural = gr.Textbox(label="Natural language answer (This field contains the answer to your question in English. This is the final output of the tool)", elem_id="natural_answer_box")
    query_output = gr.Textbox(label="Raw query output (This field contains the structured output of your query, directly obtained from the CROssBAR graphDB)")
    verbose_output = gr.Textbox(label="Verbose output (If verbose mode is enabled, this field will display extensive details about the query, including the intermediate steps. If you encountered an error, you may observe potential sources of it here)", visible=True)


    gr.Examples(
        [["Which Gene is related to Disease named psoriasis?", "gpt-3.5-turbo-instruct", False], ["What proteins does the drug named Caffeine target?", "gpt-3.5-turbo-instruct"]],
        [question, query_llm_type, verbose_mode],
        [natural, verbose_output, query_output, query_textbox]
    )
    
    run_query_button.click(run_query, inputs=[question, query_llm_type, openai_api_key], outputs=[query_textbox])
    run_natural_button.click(run_natural, inputs=[query_textbox, question, natural_llm_type, verbose_mode, openai_api_key], outputs=[natural, verbose_output, query_output])
    generate_and_run_button.click(generate_and_run, inputs=[question, query_llm_type, verbose_mode, openai_api_key], outputs=[natural, verbose_output, query_output, query_textbox])

interface.launch()

