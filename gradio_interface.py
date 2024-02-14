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

def run_pipeline(question: str, verbose_mode: bool, llm_type) -> str:
    logging.info("Processing question...")

    # Run the pipeline
    try:
        response = rp.run(question, model_name=llm_type, reset_llm_type=True)
    except Exception as e:
        logging.error(f"Error in pipeline: {e}")
        raise e

    # Read the log file content if verbose mode is on
    verbose_output = ""
    if verbose_mode:
        with open(log_filename, 'r') as file:
            verbose_output = file.read()

    return response, verbose_output

# Gradio Interface
iface = gr.Interface(
    fn=run_pipeline,

    inputs=[gr.Textbox(label="Question"), gr.Checkbox(label="Enable verbose mode"), gr.Dropdown(["gpt-3.5-turbo-instruct", "gemini-pro"], label="LLM Type")],
    outputs=[gr.Textbox(label="Answer"), gr.Textbox(label="Verbose Output", visible=True)]
)

iface.launch()