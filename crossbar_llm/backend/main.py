import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_csrf_protect import CsrfProtect
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional, List
from tools.langchain_llm_qa_trial import RunPipeline, configure_logging
from tools.utils import Logger
import numpy as np
import pandas as pd
import neo4j
from io import BytesIO, StringIO

from sse_starlette.sse import EventSourceResponse
import asyncio
import queue
import threading
import json
import logging
import time

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
    Logger.debug("Getting CSRF token")
    csrf_token, signed_token = csrf_protect.generate_csrf_tokens()
    response = JSONResponse({"detail": "CSRF cookie set" ,"csrf_token": csrf_token})
    csrf_protect.set_csrf_cookie(signed_token, response)
    Logger.info("CSRF token generated and set in cookie")
    return response

# Neo4j connection details
neo4j_user = os.getenv("NEO4J_USER", "neo4j")
neo4j_uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
neo4j_password = os.getenv("MY_NEO4J_PASSWORD", "password")
neo4j_db_name = os.getenv("NEO4J_DB_NAME", "neo4j")

# Initialize RunPipeline instances cache
pipeline_instances = {}


log_queue = asyncio.Queue()

# Create a custom logging handler
class AsyncQueueHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        # Use asyncio.create_task to avoid blocking
        asyncio.create_task(log_queue.put(log_entry))

# Modify the existing logging setup
def setup_logging(verbose=False):
    current_time = time.strftime("%Y-%m-%d-%H:%M:%S")
    log_filename = f"query_log_{current_time}.log"
    configure_logging(verbose=verbose, log_filename=log_filename)
    
    # Add async queue handler for streaming logs to frontend
    logger = logging.getLogger()
    
    # Check if AsyncQueueHandler already exists in handlers
    has_queue_handler = any(isinstance(h, AsyncQueueHandler) for h in logger.handlers)
    
    if not has_queue_handler:
        queue_handler = AsyncQueueHandler()
        queue_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(queue_handler)
    
    # Log setup complete
    Logger.info(f"Backend logging initialized with verbose={verbose}")

@app.get("/stream-logs")
async def stream_logs():
    Logger.debug("Stream logs endpoint accessed")
    async def event_generator():
        while True:
            try:
                # Wait for new log entries
                log_entry = await log_queue.get()
                Logger.debug(f"Sending log entry: {log_entry[:50]}...")
                yield {
                    "event": "log",
                    "data": json.dumps({"log": log_entry})
                }
            except Exception as e:
                Logger.error(f"Error in event generator: {e}")
                continue

    return EventSourceResponse(event_generator())

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
    setup_logging(generate_query_request.verbose)
    try:
        await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
    except ValueError as e:
        Logger.error(f"CSRF validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    Logger.info(f"Generating query for question: '{generate_query_request.question}'")
    Logger.debug(f"Using LLM: {generate_query_request.llm_type}, top_k: {generate_query_request.top_k}")
    
    key = f"{generate_query_request.llm_type}_{generate_query_request.api_key}"

    # Initialize or reuse RunPipeline instance
    if key not in pipeline_instances:
        Logger.info(f"Creating new pipeline instance for {generate_query_request.llm_type}")
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
            Logger.info("Processing vector search with embedding")
            Logger.debug(f"Vector index: {generate_query_request.vector_index}")
            
            generate_query_request.embedding = generate_query_request.embedding.replace('{"vector_data":', '').replace('}', '').replace('[', '').replace(']', '')
            embedding = [float(x) for x in generate_query_request.embedding.split(",")]
            embedding = np.array(embedding)
            Logger.debug(f"Embedding shape: {embedding.shape}")
            
            vector_index = f"{generate_query_request.vector_index}Embeddings"
            rp.search_type = "vector_search"
            rp.top_k = generate_query_request.top_k
            
            Logger.info("Generating query with vector embedding")
            query = rp.run_for_query(
                question=generate_query_request.question,
                model_name=generate_query_request.llm_type,
                api_key=generate_query_request.api_key,
                vector_index=vector_index,
                embedding=embedding,
                reset_llm_type=True
            )
            
        else:
            Logger.info("Processing standard database search")
            rp.search_type = "db_search"
            rp.top_k = generate_query_request.top_k
            
            query = rp.run_for_query(
                question=generate_query_request.question,
                model_name=generate_query_request.llm_type,
                api_key=generate_query_request.api_key,
                reset_llm_type=True
            )
            
        Logger.info("Query generation successful")
        Logger.debug(f"Generated query: {query}")
            
    except Exception as e:
        Logger.error(f"Error generating query: {str(e)}")
        logs = log_stream.getvalue()
        logger.removeHandler(handler)
        raise HTTPException(
            status_code=500, 
            detail={
                "error": str(e),
                "logs": logs
            }
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
    setup_logging(run_query_request.verbose)
    try:
        await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
    
    except ValueError as e:
        Logger.error(f"CSRF validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    Logger.info(f"Running query for question: '{run_query_request.question}'")
    Logger.debug(f"Query to execute: {run_query_request.query}")
    Logger.debug(f"Using LLM: {run_query_request.llm_type}, top_k: {run_query_request.top_k}")
    
    key = f"{run_query_request.llm_type}_{run_query_request.api_key}"

    if key not in pipeline_instances:
        Logger.info(f"Creating new pipeline instance for {run_query_request.llm_type}")
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
        Logger.info("Executing query against database")
        response, result = rp.execute_query(
            query=run_query_request.query,
            question=run_query_request.question,
            model_name=run_query_request.llm_type,
            api_key=run_query_request.api_key,
            reset_llm_type=True
        )
        
        Logger.info("Query executed successfully")
        Logger.debug(f"Result count: {len(result) if isinstance(result, list) else 'N/A'}")
        Logger.debug(f"Natural language response generated")
        
    except Exception as e:
        Logger.error(f"Error running query: {str(e)}")
        logs = log_stream.getvalue()
        logger.removeHandler(handler)
        raise HTTPException(
            status_code=500, 
            detail={
                "error": str(e),
                "logs": logs
            }
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
    Logger.info(f"Vector upload requested for category: {vector_category}")
    Logger.debug(f"Embedding type: {embedding_type}")
    Logger.debug(f"Filename: {file.filename}")
    
    try:
        await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
        
    except ValueError as e:
        Logger.error(f"CSRF validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    try:
        contents = await file.read()
        filename = file.filename
        file_extension = filename.split('.')[-1]
        Logger.debug(f"File extension: {file_extension}")
        
        # Convert the file content to vector
        if file_extension == 'csv':
            Logger.debug("Processing CSV file")
            df = pd.read_csv(BytesIO(contents))
            if df.shape[1] > 1:
                Logger.warning("CSV file contains multiple columns")
                raise ValueError(
                    "The CSV file should contain only one column (one array). Multiple columns detected."
                )
            vector_data = df.to_numpy().flatten()
        elif file_extension == 'npy':
            Logger.debug("Processing NPY file")
            arr = np.load(BytesIO(contents), allow_pickle=True)
            if arr.ndim > 1:
                Logger.warning("NPY file contains multi-dimensional array")
                raise ValueError(
                    "The NPY file should contain only one array. Multiple arrays or a multi-dimensional array detected."
                )
            vector_data = arr.flatten()
        else:
            Logger.error(f"Unsupported file format: {file_extension}")
            raise ValueError("Unsupported file format. Please upload a CSV or NPY file.")
        
        Logger.debug(f"Vector data shape: {vector_data.shape}")
        Logger.info("Vector data processed successfully")
        
        response = JSONResponse({"vector_data": vector_data.tolist()})
        return response
    except ValueError as e:
        Logger.error(f"Error processing vector data: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/database_stats/")
async def get_database_stats(request: Request, csrf_token: CsrfProtect = Depends()):
    Logger.info("Database stats requested")
    try:
        await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
    except ValueError as e:
        Logger.error(f"CSRF validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
        
    try:
        statistics = get_neo4j_statistics()
        Logger.info("Database stats retrieved successfully")
        Logger.debug(f"Database stats: {statistics}")
        return statistics
    except Exception as e:
        Logger.error(f"Error getting database stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Utility functions
def get_neo4j_statistics():
    Logger.debug(f"Connecting to Neo4j at {neo4j_uri}")
    driver = neo4j.GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    with driver.session() as session:
        # Get top 5 node labels and their counts
        Logger.debug("Executing query for top 5 node labels")
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
        Logger.debug("Executing query for node label combinations")
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
        Logger.debug("Executing query for relationship types")
        relationship_counts_query = """
        MATCH ()-[r]->()
        RETURN TYPE(r) AS type, COUNT(*) AS count
        ORDER BY count DESC
        LIMIT 5
        """
        relationship_counts_result = session.run(relationship_counts_query)
        relationship_counts = {record["type"]: record["count"] for record in relationship_counts_result}
    
    driver.close()
    Logger.debug("Neo4j connection closed")
    
    statistics = {
        "top_5_labels": top_5_labels,
        "node_counts": node_counts,
        "relationship_counts": relationship_counts
    }
    
    return statistics

# Initialize logging on startup
@app.on_event("startup")
async def startup_event():
    setup_logging(verbose=False)
    Logger.info("API server started")