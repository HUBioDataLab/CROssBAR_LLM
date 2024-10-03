import pathlib
import sys

sys.path.insert(0, pathlib.Path(__file__).parent().parent().absolute())

import io
import logging
import os
import pickle
from contextlib import redirect_stdout
from datetime import datetime
from logging.handlers import RotatingFileHandler

import neo4j
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from crossbar_llm.langchain_llm_qa_trial import RunPipeline

examples = [
    {
        "label": "Gene related to Psoriasis",
        "question": "Which Gene is related to Disease named psoriasis?",
        "model": "gpt-4o-mini",
        "verbose": False,
        "limit": 10,
    },
    {
        "label": "Targets of Caffeine",
        "question": "What proteins does the drug named Caffeine target?",
        "model": "gpt-4o-mini",
        "verbose": False,
        "limit": 10,
    },
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
    "gpt-4o-mini",
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
    "codestral:latest",
    "llama3:instruct",
    "tomasonjo/codestral-text2cypher:latest",
    "tomasonjo/llama3-text2cypher-demo:latest",
    "llama3.1:8b",
    "qwen2:7b-instruct",
    "gemma2:latest",
    "meta/llama-3.1-405b-instruct",
    "meta/llama-3.1-8b-instruct",
    "nv-mistralai/mistral-nemo-12b-instruct",
    "mistralai/mixtral-8x22b-instruct-v0.1",
    "mistralai/mistral-large-2-instruct",
    "nvidia/nemotron-4-340b-instruct",
]

node_label_to_vector_index_names = {
    "SmallMolecule": "[Selformer](https://iopscience.iop.org/article/10.1088/2632-2153/acdb30)",
    "Drug": "[Selformer](https://iopscience.iop.org/article/10.1088/2632-2153/acdb30)",
    "Compound": "[Selformer](https://iopscience.iop.org/article/10.1088/2632-2153/acdb30)",
    "Protein": [
        "[Prott5](https://arxiv.org/abs/2007.06225)",
        "[Esm2](https://www.biorxiv.org/content/10.1101/2022.07.20.500902v3)",
    ],
    "GOTerm": "[Anc2vec](https://academic.oup.com/bib/article/23/2/bbac003/6523148)",
    "CellularComponent": "[Anc2vec](https://academic.oup.com/bib/article/23/2/bbac003/6523148)",
    "BiologicalProcess": "[Anc2vec](https://academic.oup.com/bib/article/23/2/bbac003/6523148)",
    "MolecularFunction": "[Anc2vec](https://academic.oup.com/bib/article/23/2/bbac003/6523148)",
    "Phenotype": "[Cada](https://academic.oup.com/nargab/article/3/3/lqab078/6363753)",
    "Disease": "[Doc2vec](https://academic.oup.com/bioinformatics/article/37/2/236/5877941)",
    "ProteinDomain": "[Dom2vec](https://www.mdpi.com/1999-4893/14/1/28)",
    "EcNumber": "[Rxnfp](https://www.nature.com/articles/s42256-020-00284-w)",
    "Pathway": "[Biokeen](https://www.biorxiv.org/content/10.1101/631812v1)",
}

neo4j_user = os.getenv("NEO4J_USER", "neo4j")
neo4j_password = os.getenv("NEO4J_PASSWORD", "password")


def main():
    # Setup
    st.set_page_config(page_title="CROssBAR LLM Query Interface", layout="wide")
    current_dir = os.path.dirname(os.path.realpath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.append(parent_dir)

    initialize_logging()

    # Initialize RunPipeline
    if "rp" not in st.session_state:
        st.session_state.rp = RunPipeline(verbose=False, model_name="gpt-3.5-turbo")

    if "first_run" not in st.session_state:
        st.session_state.first_run = True

    # Streamlit UI
    st.title("CROssBAR LLM Query Interface")

    if "recent_queries" not in st.session_state:
        st.session_state.recent_queries = []

    tab1, tab2 = st.tabs(["LLM Query", "Vector File Upload"])

    with tab1:
        query_interface(file_upload=False)

    with tab2:
        query_interface(file_upload=True)

    st.sidebar.title("About CROssBAR LLM Query Interface")
    st.sidebar.write(
        """
    This tool allows you to generate and run Cypher queries for Neo4j using various LLM models. 
    You can analyze individual inputs or upload vector files for batch processing.

    Key Features:
    - Multiple LLM model support
    - Vector file upload and analysis
    - Cypher query generation and execution
    - Detailed output with natural language answers
    - Query statistics and recent query history

    Use this tool to interact with the CROssBAR knowledge graph database and explore the data in a user-friendly manner.
    """
    )


def setup_file_logging():
    # Make log file name based on current date
    log_file = f"{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    return file_handler


# Logging setup
def initialize_logging():
    if "log_stream" not in st.session_state:
        st.session_state.log_stream = io.StringIO()

        # Console handler (for verbose mode)
        console_handler = logging.StreamHandler(st.session_state.log_stream)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

        # File handler
        file_handler = setup_file_logging()

        # Root logger setup
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)


# Utility functions
def fix_markdown(text: str) -> str:
    return text.replace(":", "\:")


# Main query functions
def run_query(
    question: str, llm_type, top_k, vector_index=None, embedding=None, api_key=None
) -> str:
    logger = logging.getLogger(__name__)
    st.session_state.log_stream.seek(0)
    st.session_state.log_stream.truncate()
    logger.info("Processing question...")
    try:
        st.session_state.rp.top_k = top_k
        if vector_index:
            st.session_state.rp.search_type = "vector_search"
            return st.session_state.rp.run_for_query(
                question,
                model_name=llm_type,
                reset_llm_type=True,
                api_key=api_key,
                vector_index=vector_index,
                embedding=embedding,
            )
        else:
            st.session_state.rp.search_type = "db_search"
            return st.session_state.rp.run_for_query(
                question, model_name=llm_type, reset_llm_type=True, api_key=api_key
            )

    except Exception as e:
        logger.error(f"Error in pipeline: {e}")
        raise e


def run_natural(
    query: str,
    question: str,
    llm_type,
    top_k,
    verbose_mode: bool,
    vector_index=None,
    embedding=None,
    api_key=None,
):
    logger = logging.getLogger(__name__)
    st.session_state.log_stream.seek(0)
    st.session_state.log_stream.truncate()
    logger.info("Processing question...")
    try:
        st.session_state.rp.top_k = top_k
        verbose_output = st.empty()

        def update_verbose():
            if verbose_mode:
                verbose_output.code(
                    st.session_state.log_stream.getvalue(), language="log"
                )

        with redirect_stdout(st.session_state.log_stream):
            response, result = st.session_state.rp.execute_query(
                query=query,
                question=question,
                model_name=llm_type,
                reset_llm_type=True,
                api_key=api_key,
            )
            update_verbose()

        return response, st.session_state.log_stream.getvalue(), result
    except Exception as e:
        logger.error(f"Error in pipeline: {e}")
        raise e


def generate_and_run(
    question: str,
    llm_type,
    top_k,
    verbose_mode: bool,
    vector_index=None,
    embedding=None,
    api_key=None,
):
    logger = logging.getLogger(__name__)
    st.session_state.log_stream.seek(0)
    st.session_state.log_stream.truncate()
    logger.info("Processing question...")
    try:
        st.session_state.rp.top_k = top_k
        verbose_output = st.empty()

        def update_verbose():
            if verbose_mode:
                verbose_output.code(
                    st.session_state.log_stream.getvalue(), language="log"
                )

        with redirect_stdout(st.session_state.log_stream):
            if vector_index:
                st.session_state.rp.search_type = "vector_search"
                query = st.session_state.rp.run_for_query(
                    question,
                    model_name=llm_type,
                    reset_llm_type=True,
                    api_key=api_key,
                    vector_index=vector_index,
                    embedding=embedding,
                )
            else:
                st.session_state.rp.search_type = "db_search"
                query = st.session_state.rp.run_for_query(
                    question, model_name=llm_type, reset_llm_type=True, api_key=api_key
                )
            update_verbose()

            response, result = st.session_state.rp.execute_query(
                query=query,
                question=question,
                model_name=llm_type,
                reset_llm_type=True,
                api_key=api_key,
            )
            update_verbose()

        return response, st.session_state.log_stream.getvalue(), result, query
    except Exception as e:
        logger.error(f"Error in pipeline: {e}")
        raise e


def add_recent_query(query, query_type):
    # Limit the recent queries list to the latest 5 entries
    if len(st.session_state.recent_queries) >= 5:
        st.session_state.recent_queries.pop(0)
    # Append the new query with its status and timestamp
    st.session_state.recent_queries.append(
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query": query,
            "type": query_type,
        }
    )


def convert_vector_file_to_np(file):
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
        if df.shape[1] > 1:
            raise ValueError(
                "The CSV file should contain only one column (one array). Multiple columns detected."
            )
        return df.to_numpy().flatten()
    elif file.name.endswith(".npy"):
        arr = np.load(file, allow_pickle=True)
        if arr.ndim > 1:
            raise ValueError(
                "The NPY file should contain only one array. Multiple arrays or a multi-dimensional array detected."
            )
        return arr.flatten()
    else:
        raise ValueError("Unsupported file format. Please upload a CSV or NPY file.")


def get_neo4j_statistics():
    pkl_file = "neo4j_statistics.pkl"

    # Check if the pickle file exists
    if os.path.exists(pkl_file):
        # Load statistics from the pickle file
        with open(pkl_file, "rb") as f:
            return pickle.load(f)

    # If the file doesn't exist, query Neo4j and create the file
    driver = neo4j.GraphDatabase.driver(
        "bolt://localhost:7687", auth=(neo4j_user, neo4j_password)
    )
    with driver.session() as session:
        # Get individual label counts
        result = session.run(
            """
        MATCH (n)
        UNWIND labels(n) AS label
        WITH label, count(n) AS count
        RETURN label, count
        ORDER BY count DESC
        LIMIT 5
        """
        )
        top_5_labels = {row["label"]: row["count"] for row in result}

        # Get label combination counts
        result = session.run(
            """
        MATCH (n)
        WITH labels(n) AS labels, count(n) AS count
        RETURN labels, count
        ORDER BY count DESC
        """
        )
        node_counts = {tuple(row["labels"]): row["count"] for row in result}

        # Get relationship counts
        result = session.run(
            """
        MATCH ()-[r]->()
        WITH type(r) AS type, count(r) AS count
        RETURN type, count
        ORDER BY count DESC
        LIMIT 5
        """
        )
        relationship_counts = {row["type"]: row["count"] for row in result}

    driver.close()

    # Store the results in a tuple
    statistics = (top_5_labels, node_counts, relationship_counts)

    # Save the statistics to a pickle file
    with open(pkl_file, "wb") as f:
        pickle.dump(statistics, f)

    return statistics


def query_interface(file_upload=False):
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Query Input")
        example_labels = ["Select an example - or Write Your Own Query"] + [
            ex["label"] for ex in examples
        ]
        selected_example = st.selectbox(
            "Choose an example question",
            options=example_labels,
            key=f"example{'_file' if file_upload else ''}",
        )

        question_params = {
            "label": "Enter you question here",
            "value": "",
            "placeholder": None,
            "key": f"question{'_file' if file_upload else ''}",
        }

        query_llm_type_params = {
            "label": "LLM for Query Generation*",
            "options": model_choices,
            "index": 0,
            "key": f"llm_type{'_file' if file_upload else ''}",
            "help": "Choose the LLM to generate the Cypher query. *Required field.",
        }

        limit_options = [1, 3, 5, 10, 15, 20, 50, 100]
        limit_query_return_params = {
            "label": "Limit query return",
            "options": limit_options,
            "index": 3,
            "key": f"limit_return{'_file' if file_upload else ''}",
            "help": "Select the number of elements to limit the query return. Attention: Query execution uses Depth First Search (DFS) traversal, so some nodes may not be reached.",
        }

        verbose_mode_params = {
            "label": "Enable Verbose Mode",
            "value": False,
            "key": f"verbose{'_file' if file_upload else ''}",
            "help": "Show detailed logs and intermediate steps.",
        }

        if selected_example != "Select an example - or Write Your Own Query":
            example = next(ex for ex in examples if ex["label"] == selected_example)

            question_params.update(
                {
                    "value": example["question"],
                    "placeholder": example["question"],
                    "key": f"question_unchange{'_file' if file_upload else ''}",
                }
            )

            query_llm_type_params.update(
                {"index": model_choices.index(example["model"])}
            )

            limit_query_return_params.update(
                {
                    "index": limit_options.index(example["limit"]),
                }
            )

            verbose_mode_params.update(
                {
                    "value": example["verbose"],
                }
            )

        question = st.text_input(**question_params)
        query_llm_type = st.selectbox(**query_llm_type_params)
        limit_query_return = st.selectbox(**limit_query_return_params)
        verbose_mode = st.checkbox(**verbose_mode_params)

        llm_api_key = st.text_input(
            "API Key for LLM",
            type="password",
            key=f"api_key{'_file' if file_upload else ''}",
            help="Enter your API key if you choose a paid model.",
        )

        if file_upload:
            vector_file = st.file_uploader(
                "Upload Vector File",
                type=["csv", "npy"],
                help="Upload your vector file here.",
            )
            vector_category = st.selectbox(
                "Select Vector Category",
                options=list(node_label_to_vector_index_names.keys()),
                key="vector_category",
                help="Choose the category of the uploaded vector.",
            )

            if vector_category:
                embedding_options = node_label_to_vector_index_names[vector_category]
                if isinstance(embedding_options, list):
                    embedding_type = st.selectbox(
                        "Select Embedding Type",
                        options=[
                            option.split("]")[0][1:] for option in embedding_options
                        ],
                        key="embedding_type",
                        help="Choose the specific embedding type for this category.",
                    )
                    st.markdown(
                        f"Article of the Embedding Methodology: {[option for option in embedding_options if embedding_type in option][0]}"
                    )
                else:
                    embedding_type = embedding_options.split("]")[0][1:]
                    st.markdown(f"Embedding Type: {embedding_options}")

            if vector_file:
                try:
                    vector_data = convert_vector_file_to_np(vector_file)
                    st.write(f"Vector data shape: {vector_data.shape}")
                except ValueError as e:
                    st.error(f"Error processing vector file: {str(e)}")

        col1_1, col1_2, col1_3 = st.columns(3)

        if "error_occurred" not in st.session_state:
            st.session_state.error_occurred = False

        with col1_1:
            if st.button(
                "Generate & Run Query",
                key=f"gen_run{'_file' if file_upload else ''}",
                help="Click to process your query and get results.",
                type="primary",
            ):
                add_recent_query(question, "Generate & Run")
                st.session_state.generate_and_run_submitted = True
                st.session_state.error_occurred = False
        with col1_2:
            if st.button(
                "Generate Cypher Query",
                key=f"gen_cypher{'_file' if file_upload else ''}",
                help="Click to generate the Cypher query only.",
            ):
                add_recent_query(question, "Generate Query")
                st.session_state.generate_query_submitted = True
                st.session_state.error_occurred = False
        with col1_3:
            if st.button(
                "Run Generated Query",
                key=f"run_generated{'_file' if file_upload else ''}",
                help="Click to run the generated Cypher query.",
            ):
                st.session_state.run_query_submitted = True
                st.session_state.error_occurred = False

    with col2:
        st.subheader("Database Statistics")
        if st.session_state.first_run:
            top_5_labels, node_counts, relationship_counts = get_neo4j_statistics()
            st.session_state.first_run = False
            st.session_state.latest_values = {
                "top_5_labels": top_5_labels,
                "node_counts": node_counts,
                "relationship_counts": relationship_counts,
            }

        if not st.session_state.first_run:
            top_5_labels = st.session_state.latest_values["top_5_labels"]
            node_counts = st.session_state.latest_values["node_counts"]
            relationship_counts = st.session_state.latest_values["relationship_counts"]

        with st.expander("Top 5 Node Labels", expanded=True):
            fig1 = px.pie(
                values=list(top_5_labels.values()), names=list(top_5_labels.keys())
            )
            st.plotly_chart(fig1, use_container_width=True)

        with st.expander("Top 5 Relationship Types", expanded=True):
            fig2 = px.pie(
                values=list(relationship_counts.values()),
                names=list(relationship_counts.keys()),
            )
            st.plotly_chart(fig2, use_container_width=True)

        with st.expander("Node and Relationship Counts", expanded=True):
            total_nodes = sum(node_counts.values())
            total_relationships = sum(relationship_counts.values())

            st.metric("Total Nodes", f"{total_nodes:,}")
            st.metric("Total Relationships", f"{total_relationships:,}")

            st.subheader("Detailed Node Statistics")
            node_df = pd.DataFrame(
                [(", ".join(labels), count) for labels, count in node_counts.items()],
                columns=["Labels", "Count"],
            )
            node_df = node_df.sort_values("Count", ascending=False)
            st.dataframe(node_df)

    if st.session_state.get("generate_and_run_submitted", False):
        if question and query_llm_type:
            if not st.session_state.error_occurred:
                try:
                    with st.spinner("Generating and Running Query..."):
                        if file_upload and vector_file and vector_category:
                            vector_index = f"{embedding_type}Embeddings"
                            response, verbose_output, result, query = generate_and_run(
                                question,
                                query_llm_type,
                                limit_query_return,
                                verbose_mode,
                                api_key=llm_api_key,
                                vector_index=vector_index,
                                embedding=vector_data,
                            )
                        else:
                            response, verbose_output, result, query = generate_and_run(
                                question,
                                query_llm_type,
                                limit_query_return,
                                verbose_mode,
                                api_key=llm_api_key,
                            )

                    st.subheader("Generated Cypher Query:")
                    st.code(query, language="cypher")

                    st.subheader("Raw Query Output:")
                    st.code(str(result))

                    st.subheader("Natural Language Answer:")
                    st.write(fix_markdown(response))
                except Exception as e:
                    st.error(f"Error processing query: {str(e)}")
                    st.session_state.error_occurred = True
                    st.stop()
            else:
                st.warning("An error occured, please click the run button again.")

        else:
            st.warning(
                "Please make sure to fill in all the required fields before submitting the form."
            )
        st.session_state.generate_and_run_submitted = False

    if st.session_state.get("generate_query_submitted", False):
        if question and query_llm_type:
            if not st.session_state.error_occurred:
                with st.spinner("Generating Cypher Query..."):
                    if file_upload and vector_file and vector_category:
                        vector_index = f"{embedding_type}Embeddings"
                        generated_query = run_query(
                            question,
                            query_llm_type,
                            limit_query_return,
                            vector_index=vector_index,
                            embedding=vector_data,
                            api_key=llm_api_key,
                        )
                    else:
                        generated_query = run_query(
                            question,
                            query_llm_type,
                            limit_query_return,
                            api_key=llm_api_key,
                        )

                st.subheader("Generated Cypher Query:")
                st.text_area(
                    "You can edit the generated query below:",
                    value=generated_query,
                    key="edited_query",
                    height=150,
                )
            else:
                st.warning("An error occured, please click the run button again.")
        else:
            st.warning(
                "Please make sure to fill in all the required fields before generating the query."
            )
        st.session_state.generate_query_submitted = False

    if st.session_state.get("run_query_submitted", False):
        if "edited_query" in st.session_state and st.session_state.edited_query:
            if not st.session_state.error_occurred:
                with st.spinner("Running Cypher Query..."):
                    if file_upload and vector_file and vector_category:
                        vector_index = f"{embedding_type}Embeddings"
                        response, verbose_output, result = run_natural(
                            st.session_state.edited_query,
                            question,
                            query_llm_type,
                            limit_query_return,
                            verbose_mode,
                            vector_index=vector_index,
                            embedding=vector_data,
                            api_key=llm_api_key,
                        )
                    else:
                        response, verbose_output, result = run_natural(
                            st.session_state.edited_query,
                            question,
                            query_llm_type,
                            limit_query_return,
                            verbose_mode,
                            api_key=llm_api_key,
                        )

                st.subheader("Raw Query Output:")
                st.code(str(result))

                st.subheader("Natural Language Answer:")
                st.write(fix_markdown(response))
            else:
                st.warning("An error occured, please click the run button again.")

        else:
            st.warning("Please generate a Cypher query first before running it.")
        st.session_state.run_query_submitted = False

    st.subheader("Recent Queries")
    recent_queries = st.session_state.recent_queries
    st.table(pd.DataFrame(recent_queries))


if __name__ == "__main__":
    main()
