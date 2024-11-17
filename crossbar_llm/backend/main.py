import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional, List
from tools.langchain_llm_qa_trial import RunPipeline
import numpy as np
import pandas as pd
import neo4j
from io import BytesIO

import logging
from io import StringIO

# Load environment variables
load_dotenv()

origins = [
    "http://localhost:3000",  # React app running on localhost
    "http://127.0.0.1:3000",
]

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Neo4j connection details
neo4j_user = os.getenv("NEO4J_USER", "neo4j")
neo4j_uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
neo4j_password = os.getenv("MY_NEO4J_PASSWORD", "password")
neo4j_db_name = os.getenv("NEO4J_DB_NAME", "neo4j")

# Initialize RunPipeline instances cache
pipeline_instances = {}

class GenerateQueryRequest(BaseModel):
    question: str
    llm_type: str
    top_k: int = 5
    api_key: str
    verbose: bool = False
    vector_index: Optional[str] = None
    embedding: Optional[str] = None

class RunQueryRequest(BaseModel):
    query: str
    question: str
    llm_type: str
    top_k: int = 5
    api_key: str
    verbose: bool = False

@app.post("/generate_query/")
async def generate_query(request: GenerateQueryRequest):
    key = f"{request.llm_type}_{request.api_key}"

    # Initialize or reuse RunPipeline instance
    if key not in pipeline_instances:
        pipeline_instances[key] = RunPipeline(
            model_name=request.llm_type,
            verbose=request.verbose,
        )

    rp = pipeline_instances[key]

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG if request.verbose else logging.INFO)
    logger = logging.getLogger()
    logger.addHandler(handler)
    
    try:
        embedding = None
        if request.embedding is not None:
            request.embedding = request.embedding.replace('{"vector_data":', '').replace('}', '').replace('[', '').replace(']', '')
            embedding = [float(x) for x in request.embedding.split(",")]
            embedding = np.array(embedding)

            vector_index = f"{request.vector_index}Embeddings"

            rp.search_type = "vector_search"
        else:
            rp.search_type = "db_search"

        print(f"Embedding for {request.vector_index}:", embedding)
        print(f"Vector index for {request.vector_index}:", vector_index)
            

        query = rp.run_for_query(
            question=request.question,
            model_name=request.llm_type,
            top_k=request.top_k,
            api_key=request.api_key,
            vector_index=vector_index,
            embedding = embedding,
            reset_llm_type=True
        )
    finally:
        logger.removeHandler(handler)

    logs = log_stream.getvalue()

    return {"query": query, "logs": logs}

@app.post("/run_query/")
async def run_query(request: RunQueryRequest):
    key = f"{request.llm_type}_{request.api_key}"

    if key not in pipeline_instances:
        pipeline_instances[key] = RunPipeline(
            model_name=request.llm_type,
            verbose=request.verbose,
        )

    rp = pipeline_instances[key]

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG if request.verbose else logging.INFO)
    logger = logging.getLogger()
    logger.addHandler(handler)

    try:
        response, result = rp.execute_query(
            query=request.query,
            question=request.question,
            model_name=request.llm_type,
            api_key=request.api_key,
            reset_llm_type=True
        )
    finally:
        logger.removeHandler(handler)
    
    logs = log_stream.getvalue()

    return {"response": response, "result": result, "logs": logs}

@app.post("/upload_vector/")
async def upload_vector(
    vector_category: str = Form(...),
    embedding_type: Optional[str] = Form(None),
    file: UploadFile = File(...)
):
    try:
        contents = await file.read()
        filename = file.filename
        file_extension = filename.split('.')[-1]

        # Convert the file content to vector
        if file_extension == 'csv':
            df = pd.read_csv(BytesIO(contents))
            if df.shape[1] > 1:
                raise ValueError(
                    "The CSV file should contain only one column (one array). Multiple columns detected."
                )
            vector_data = df.to_numpy().flatten()
        elif file_extension == 'npy':
            arr = np.load(BytesIO(contents), allow_pickle=True)
            if arr.ndim > 1:
                raise ValueError(
                    "The NPY file should contain only one array. Multiple arrays or a multi-dimensional array detected."
                )
            vector_data = arr.flatten()
        else:
            raise ValueError("Unsupported file format. Please upload a CSV or NPY file.")

        print(f"Vector data for {filename}:", vector_data)

        return {"vector_data": vector_data.tolist()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Utility functions

def get_neo4j_statistics():
    driver = neo4j.GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    with driver.session() as session:
        # Get top 5 node labels and their counts
        top_labels_query = """
        MATCH (n)
        UNWIND labels(n) AS label
        RETURN label, COUNT(*) AS count
        ORDER BY count DESC
        LIMIT 5
        """
        top_labels_result = session.run(top_labels_query)
        top_5_labels = {record["label"]: record["count"] for record in top_labels_result}

        # Get counts of node label combinations
        node_counts_query = """
        MATCH (n)
        WITH labels(n) AS labels_list, COUNT(*) AS count
        RETURN labels_list, count
        ORDER BY count DESC
        """
        node_counts_result = session.run(node_counts_query)
        # Convert labels list to a string to make it JSON-serializable
        node_counts = {", ".join(record["labels_list"]): record["count"] for record in node_counts_result}

        # Get top 5 relationship types and their counts
        relationship_counts_query = """
        MATCH ()-[r]->()
        RETURN TYPE(r) AS type, COUNT(*) AS count
        ORDER BY count DESC
        LIMIT 5
        """
        relationship_counts_result = session.run(relationship_counts_query)
        relationship_counts = {record["type"]: record["count"] for record in relationship_counts_result}

    driver.close()

    statistics = {
        "top_5_labels": top_5_labels,
        "node_counts": node_counts,
        "relationship_counts": relationship_counts
    }

    return statistics