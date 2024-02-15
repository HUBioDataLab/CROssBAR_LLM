import gradio as gr
import sys, os, logging
from datetime import datetime

# Import path
current_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from CROssBARLLM.langchain_llm_qa_trial import RunPipeline

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


with gr.Blocks() as interface:
    with gr.Column():

        question = gr.Textbox(label="Question")
        llm_type = gr.Dropdown(["gpt-3.5-turbo-instruct", "gemini-pro"], label="LLM Type", value="gpt-3.5-turbo-instruct")
        openai_api_key = gr.Textbox(label="OpenAI API Key", placeholder="Enter your OpenAI API Key here")

    with gr.Row():
        run_query_button = gr.Button("Generate Query", variant="secondary")
        generate_and_run_button = gr.Button("Generate and Run Query", variant="primary")
        clear_question = gr.ClearButton(question, value="Clear Question")
        
    with gr.Column():    
        query_textbox = gr.Textbox(label="Generted Query", interactive=True)
        verbose_mode = gr.Checkbox(label="Enable verbose mode")

    with gr.Row():
        run_natural_button = gr.Button("Get Natural Language Answer", variant="primary")
        clear_query = gr.ClearButton(query_textbox, value="Clear Query")

    natural = gr.Textbox(label="Natural Language Answer")
    verbose_output = gr.Textbox(label="Verbose Output", visible=True)
    query_output = gr.Textbox(label="Query Output")


    run_query_button.click(run_query, inputs=[question, llm_type, openai_api_key], outputs=[query_textbox])
    run_natural_button.click(run_natural, inputs=[query_textbox, question, llm_type, verbose_mode, openai_api_key], outputs=[natural, verbose_output, query_output])
    generate_and_run_button.click(generate_and_run, inputs=[question, llm_type, verbose_mode, openai_api_key], outputs=[natural, verbose_output, query_output, query_textbox])

interface.launch()

