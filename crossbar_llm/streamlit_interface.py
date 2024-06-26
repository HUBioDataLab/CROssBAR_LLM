import streamlit as st
import streamlit.components.v1 as components
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

model_choices = ["gpt-3.5-turbo-0125", "gemini-1.5-pro-latest", "claude-3-opus-20240229"]
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

# Get autocomplete words from all text files under folder query_db
autocomplete_words = []
for root, dirs, files in os.walk("query_db"):
    for file in files:
        if file.endswith(".txt"):
            with open(os.path.join(root, file), "r") as f:
                autocomplete_words.extend(f.read().splitlines())

# Input form
with st.form("query_form"):

    # Placeholder for the JavaScript code
    components.html(
        f"""
        <script src="https://cdn.jsdelivr.net/npm/fuse.js@6.4.6"></script>
        <script>
        const suggestions = {autocomplete_words};
        const fuse = new Fuse(suggestions, {{
          includeScore: true,
          threshold: 0.3
        }});

        function debounce(func, wait) {{
          let timeout;
          return function(...args) {{
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
          }};
        }}

        function updateHiddenInput(value) {{
            const hiddenInput = window.parent.document.querySelector('input[type="password"]');
            if (hiddenInput) {{
                hiddenInput.value = value;
                hiddenInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }}

        function autocomplete(inp) {{
          let currentFocus;
          inp.addEventListener("input", debounce(function(e) {{
              let a, b, i, val = this.value.split(" ").pop();
              if (val.length < 3) {{
                closeAllLists();
                return false;
              }}
              closeAllLists();
              if (!val) {{ return false; }}
              currentFocus = -1;
              a = document.createElement("DIV");
              a.setAttribute("id", this.id + "autocomplete-list");
              a.setAttribute("class", "autocomplete-items");
              this.parentNode.appendChild(a);
              const results = fuse.search(val).slice(0, 10); // Limit results to 10 items
              for (i = 0; i < results.length; i++) {{
                if (results[i].score <= 0.3) {{
                  b = document.createElement("DIV");
                  b.innerHTML = "<strong>" + results[i].item.substr(0, val.length) + "</strong>";
                  b.innerHTML += results[i].item.substr(val.length);
                  b.innerHTML += "<input type='hidden' value='" + results[i].item + "'>";
                  b.addEventListener("click", function(e) {{
                      let words = inp.value.split(" ");
                      words.pop();
                      words.push(this.getElementsByTagName("input")[0].value);
                      inp.value = words.join(" ");
                      closeAllLists();
                  }});
                  a.appendChild(b);
                }}
              }}
              updateHiddenInput(this.value);
          }}, 300)); // Debounce with a delay of 300ms

          inp.addEventListener("keydown", function(e) {{
              let x = document.getElementById(this.id + "autocomplete-list");
              if (x) x = x.getElementsByTagName("div");
              if (e.keyCode == 40) {{
                currentFocus++;
                addActive(x);
              }} else if (e.keyCode == 38) {{
                currentFocus--;
                addActive(x);
              }} else if (e.keyCode == 13) {{
                e.preventDefault();
                if (currentFocus > -1) {{
                  if (x) x[currentFocus].click();
                }}
              }}
              updateHiddenInput(this.value);
          }});

          function addActive(x) {{
            if (!x) return false;
            removeActive(x);
            if (currentFocus >= x.length) currentFocus = 0;
            if (currentFocus < 0) currentFocus = (x.length - 1);
            x[currentFocus].classList.add("autocomplete-active");
          }}

          function removeActive(x) {{
            for (let i = 0; i < x.length; i++) {{
              x[i].classList.remove("autocomplete-active");
            }}
          }}

          function closeAllLists(elmnt) {{
            const x = document.getElementsByClassName("autocomplete-items");
            for (let i = 0; i < x.length; i++) {{
              if (elmnt != x[i] && elmnt != inp) {{
                x[i].parentNode.removeChild(x[i]);
              }}
            }}
          }}

          document.addEventListener("click", function (e) {{
              closeAllLists(e.target);
          }});
        }}
        </script>
        <style>
        .autocomplete {{
          position: relative;
          display: inline-block;
          width: 100%;
        }}
        .autocomplete input {{
          width: 100%;
          padding: 10px;
          font-size: 16px;
          border: 1px solid #ccc;
          border-radius: 4px;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
          box-sizing: border-box;
        }}
        .autocomplete-items {{
          position: absolute;
          border: 1px solid #d4d4d4;
          border-bottom: none;
          border-top: none;
          z-index: 99;
          top: 100%;
          left: 0;
          right: 0;
          overflow-x: hidden;
          background-color: #fff;
        }}
        .autocomplete-items div {{
          padding: 10px;
          cursor: pointer;
          background-color: #fff;
          border-bottom: 1px solid #d4d4d4;
        }}
        .autocomplete-items div:hover {{
          background-color: #e9e9e9;
        }}
        .autocomplete-active {{
          background-color: DodgerBlue !important;
          color: #ffffff;
        }}
        </style>
        <div class="autocomplete">
          <input id="question_input" type="text" name="question" placeholder="Enter your natural language query here using clear and plain English">
        </div>
        <script>
        autocomplete(document.getElementById("question_input"));
        </script>
        """,
        height=200,
    )
    question = st.text_input("Hidden Question Input", key="hidden_question", type="password")


    query_llm_type = st.selectbox("LLM for Query Generation*", 
                                ["gpt-3.5-turbo-0125", "gemini-1.5-pro-latest", "claude-3-opus-20240229", "llama3-70b-8192", "mixtral-8x7b-32768"], 
                                index=st.session_state.example_model_index, 
                                help="Choose the LLM to generate the Cypher query. *Required field."
                                )
    llm_api_key = st.text_input("API Key for LLM", type="password", help="Enter your API key if you choose paid model.")
    verbose_mode = st.checkbox("Enable Verbose Mode", help="Show detailed logs and intermediate steps.")
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
    question = st.session_state.hidden_question
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
    question = st.session_state.hidden_question
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
    question = st.session_state.hidden_question
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