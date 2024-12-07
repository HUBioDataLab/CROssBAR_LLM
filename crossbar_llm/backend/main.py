import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_csrf_protect import CsrfProtect
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
    "http://localhost:8501",  # React app running on localhost
    "http://127.0.0.1:8501",
    "https://crossbarv2.hubiodatalab.com/llm",
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

class CsrfSettings(BaseModel):
    secret_key: str = os.getenv("CSRF_SECRET_KEY")
    

@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()

@app.get("/csrf-token/")
def get_csrf_token(csrf_protect: CsrfProtect = Depends()):
    csrf_token, signed_token = csrf_protect.generate_csrf_tokens()
    response = JSONResponse({"detail": "CSRF cookie set" ,"csrf_token": csrf_token})
    csrf_protect.set_csrf_cookie(signed_token, response)
    return response

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
async def generate_query(
    request: Request,
    generate_query_request: GenerateQueryRequest,
    csrf_token: CsrfProtect = Depends()
    ):
    await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
    
    key = f"{generate_query_request.llm_type}_{generate_query_request.api_key}"

    # Initialize or reuse RunPipeline instance
    if key not in pipeline_instances:
        pipeline_instances[key] = RunPipeline(
            model_name=generate_query_request.llm_type,
            verbose=generate_query_request.verbose,
        )

    rp = pipeline_instances[key]

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG if generate_query_request.verbose else logging.INFO)
    logger = logging.getLogger()
    logger.addHandler(handler)
    
    try:
        if generate_query_request.embedding is not None:
            
            
            print("Embedding:", generate_query_request.vector_index)
            generate_query_request.embedding = generate_query_request.embedding.replace('{"vector_data":', '').replace('}', '').replace('[', '').replace(']', '')
            embedding = [float(x) for x in generate_query_request.embedding.split(",")]
            embedding = np.array(embedding)

            vector_index = f"{generate_query_request.vector_index}Embeddings"

            rp.search_type = "vector_search"
            rp.top_k = generate_query_request.top_k
            
            query = rp.run_for_query(
                question=generate_query_request.question,
                model_name=generate_query_request.llm_type,
                api_key=generate_query_request.api_key,
                vector_index=vector_index,
                embedding = embedding,
                reset_llm_type=True
            )
            
        else:
            rp.search_type = "db_search"
            rp.top_k = generate_query_request.top_k
            
            query = rp.run_for_query(
                question=generate_query_request.question,
                model_name=generate_query_request.llm_type,
                api_key=generate_query_request.api_key,
                reset_llm_type=True
            )

    finally:
        logger.removeHandler(handler)

    logs = log_stream.getvalue()
    
    response = JSONResponse({"query": query, "logs": logs})

    return response

@app.post("/run_query/")
async def run_query(
    request: Request,
    run_query_request: RunQueryRequest,
    csrf_token: CsrfProtect = Depends()
    ):
    await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
    
    key = f"{run_query_request.llm_type}_{run_query_request.api_key}"

    if key not in pipeline_instances:
        pipeline_instances[key] = RunPipeline(
            model_name=run_query_request.llm_type,
            verbose=run_query_request.verbose,
        )

    rp = pipeline_instances[key]

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG if run_query_request.verbose else logging.INFO)
    logger = logging.getLogger()
    logger.addHandler(handler)

    try:
        response, result = rp.execute_query(
            query=run_query_request.query,
            question=run_query_request.question,
            model_name=run_query_request.llm_type,
            api_key=run_query_request.api_key,
            reset_llm_type=True
        )
    finally:
        logger.removeHandler(handler)
    
    logs = log_stream.getvalue()
    
    response = JSONResponse({"response": response, "result": result, "logs": logs})
    
    return response

@app.post("/upload_vector/")
async def upload_vector(
    request: Request,
    csrf_token: CsrfProtect = Depends(),
    vector_category: str = Form(...),
    embedding_type: Optional[str] = Form(None),
    file: UploadFile = File(...)
):
    await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
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
        
        response = JSONResponse({"vector_data": vector_data.tolist()})
        csrf_token.set_csrf_cookie(csrf_token.generate_csrf_tokens(), response)

        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/database_stats/")
async def get_database_stats(request: Request, csrf_token: CsrfProtect = Depends()):
    await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
    statistics = get_neo4j_statistics()
    return statistics

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