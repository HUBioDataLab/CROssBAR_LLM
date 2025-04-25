import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_csrf_protect import CsrfProtect
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional, List, Dict
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
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

origins = [
    "http://localhost:8501",  # React app running on localhost
    "http://127.0.0.1:8501",
    f"https://crossbarv2.hubiodatalab.com{os.getenv('REACT_APP_CROSSBAR_LLM_ROOT_PATH')}",
]

app = FastAPI()

# Helper function to get real client IP address when behind a reverse proxy
def get_client_ip(request: Request, x_forwarded_for: Optional[str] = Header(None)):
    # First try X-Forwarded-For header which is standard for proxies
    if x_forwarded_for:
        # Ensure x_forwarded_for is treated as a string
        x_forwarded_for_str = str(x_forwarded_for)
        # X-Forwarded-For can contain multiple IPs - the first one is the client
        client_ip = x_forwarded_for_str.split(',')[0].strip()
        Logger.debug(f"Using X-Forwarded-For IP: {client_ip}")
        return client_ip
    
    # Try X-Real-IP header (used by some proxies)
    x_real_ip = request.headers.get('x-real-ip')
    if x_real_ip:
        Logger.debug(f"Using X-Real-IP: {x_real_ip}")
        return x_real_ip
    
    # Try custom header (if client is sending it)
    client_ip_header = request.headers.get('x-client-ip')
    if client_ip_header:
        Logger.debug(f"Using X-Client-IP header: {client_ip_header}")
        return client_ip_header
    
    # Try to get from request body if provided
    try:
        body = request.scope.get('_body')
        if body:
            body_json = json.loads(body.decode('utf-8'))
            if 'client_ip' in body_json:
                Logger.debug(f"Using client_ip from request body: {body_json['client_ip']}")
                return body_json['client_ip']
    except:
        pass
    
    # Try to get from form data for multipart/form-data requests
    try:
        if request.headers.get('content-type', '').startswith('multipart/form-data'):
            form_data = request._form
            if form_data and 'client_ip' in form_data:
                client_ip = form_data.get('client_ip')
                Logger.debug(f"Using client_ip from form data: {client_ip}")
                return client_ip
    except:
        pass
    
    # Fall back to the direct client IP (the proxy server most likely)
    Logger.debug(f"Falling back to direct client IP: {request.client.host}")
    return request.client.host

# Rate limiting implementation
class RateLimiter:
    def __init__(self):
        self.request_records: Dict[str, List[datetime]] = {}  # IP -> list of request timestamps
    
    def is_rate_limited(self, ip: str) -> tuple[bool, str, int]:
        current_time = datetime.now()

        # Ensure ip is a string
        ip_str = str(ip)
        Logger.debug(f"Checking rate limit for IP: {ip_str}")
        
        # If IP not in records, add it
        if ip_str not in self.request_records:
            self.request_records[ip_str] = [current_time]
            return False, "", 0
        
        # Add current timestamp to tracking
        self.request_records[ip_str].append(current_time)
        
        # Check minute limit (3 requests per minute)
        minute_ago = current_time - timedelta(minutes=1)
        minute_requests = [ts for ts in self.request_records[ip_str] if ts > minute_ago]
        if len(minute_requests) > 3:
            # Keep only requests from the last day for storage efficiency
            self.request_records[ip_str] = [
                ts for ts in self.request_records[ip_str] 
                if ts > (current_time - timedelta(days=1))
            ]
            return True, "minute", 60
        
        # Check hour limit (10 requests per hour)
        hour_ago = current_time - timedelta(hours=1)
        hour_requests = [ts for ts in self.request_records[ip_str] if ts > hour_ago]
        if len(hour_requests) > 10:
            # Keep only requests from the last day for storage efficiency
            self.request_records[ip_str] = [
                ts for ts in self.request_records[ip_str] 
                if ts > (current_time - timedelta(days=1))
            ]
            return True, "hour", 3600
            
        # Check day limit (25 requests per day)
        day_ago = current_time - timedelta(days=1)
        day_requests = [ts for ts in self.request_records[ip_str] if ts > day_ago]
        if len(day_requests) > 25:
            # Keep last 30 days of requests
            self.request_records[ip_str] = [
                ts for ts in self.request_records[ip_str] 
                if ts > (current_time - timedelta(days=30))
            ]
            return True, "day", 86400
            
        # No rate limit exceeded
        return False, "", 0

# Create rate limiter instance
rate_limiter = RateLimiter()

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

# Helper function to check rate limits and return appropriate error
def check_rate_limit(request: Request):
    # Get actual client IP from headers or fallback to direct client IP
    client_ip = get_client_ip(request)
    
    # Ensure client_ip is a string
    client_ip_str = str(client_ip)
    Logger.debug(f"Client IP for rate limiting: {client_ip_str}")
    
    is_limited, limit_type, retry_seconds = rate_limiter.is_rate_limited(client_ip_str)
    
    if is_limited:
        Logger.warning(f"Rate limit exceeded for IP: {client_ip_str} ({limit_type} limit)")
        
        # Create appropriate error message based on limit type
        if limit_type == "minute":
            detail_message = "Minute rate limit exceeded (3 requests per minute)."
        elif limit_type == "hour":
            detail_message = "Hour rate limit exceeded (10 requests per hour)."
        elif limit_type == "day":
            detail_message = "Daily rate limit exceeded (25 requests per day)."
        else:
            detail_message = "Rate limit exceeded."
            
        raise HTTPException(
            status_code=429, 
            detail={
                "error": detail_message,
                "retry_after": retry_seconds,
                "limit_type": limit_type
            }
        )

log_queue = asyncio.Queue()

# Create a custom logging handler
class AsyncQueueHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        # Create a thread-safe queue for log messages
        self.log_messages = queue.Queue()
        # Initialize running attribute before starting the thread
        self.running = True
        # Start a worker thread to process log messages
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        
    def emit(self, record):
        # Use getattr with default to avoid AttributeError
        if not getattr(self, 'running', True):
            return
        log_entry = self.format(record)
        # Add to the thread-safe queue
        self.log_messages.put(log_entry)
    
    def _worker(self):
        """Worker thread that transfers messages from the thread-safe queue to the asyncio queue."""
        # Use getattr with default to avoid AttributeError
        while getattr(self, 'running', True):
            try:
                # Get message from the thread-safe queue (blocking with timeout)
                log_entry = self.log_messages.get(timeout=0.5)
                
                # Try to transfer to the asyncio queue
                try:
                    # Check if we're in the main thread where an event loop might be running
                    if threading.current_thread() is threading.main_thread():
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                loop.create_task(log_queue.put(log_entry))
                            else:
                                # We're in the main thread but no loop is running
                                # Just store it for later retrieval
                                asyncio.run(log_queue.put(log_entry))
                        except RuntimeError:
                            # No event loop, just store the entry for later
                            pass
                    else:
                        # We're in a worker thread, can't directly interact with asyncio
                        # Store the entry for later retrieval by the main event loop
                        pass
                except Exception as e:
                    # If any asyncio error occurs, just continue
                    pass
                
                # Mark the task as done in the thread-safe queue
                self.log_messages.task_done()
                
            except queue.Empty:
                # Timeout on queue.get(), just continue the loop
                continue
            except Exception:
                # Any other error, just continue
                continue
    
    def close(self):
        # Set running to False
        self.running = False
        if hasattr(self, 'worker_thread') and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
        super().close()

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
    # Apply rate limiting
    check_rate_limit(request)
    
    setup_logging(generate_query_request.verbose)
    try:
        await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
    except ValueError as e:
        Logger.error(f"CSRF validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    Logger.info(f"Generating query for question: '{generate_query_request.question}'")
    Logger.debug(f"Using LLM: {generate_query_request.llm_type}, top_k: {generate_query_request.top_k}")
    
    # Handle "env" API key by using the API key from .env
    api_key = generate_query_request.api_key
    if api_key == "env":
        # Determine provider based on LLM type
        if generate_query_request.llm_type.startswith("gpt"):
            api_key = os.getenv("OPENAI_API_KEY")
            Logger.info("Using OpenAI API key from .env")
        elif generate_query_request.llm_type.startswith("claude"):
            api_key = os.getenv("ANTHROPIC_API_KEY")
            Logger.info("Using Anthropic API key from .env")
        elif generate_query_request.llm_type.startswith("gemini"):
            api_key = os.getenv("GEMINI_API_KEY")
            Logger.info("Using Google API key from .env")
        elif generate_query_request.llm_type.startswith("llama") or generate_query_request.llm_type.startswith("mixtral"):
            api_key = os.getenv("GROQ_API_KEY")
            Logger.info("Using Groq API key from .env")
        elif generate_query_request.llm_type.startswith("meta/llama") or generate_query_request.llm_type.startswith("mistralai"):
            api_key = os.getenv("NVIDIA_API_KEY")
            Logger.info("Using NVIDIA API key from .env")
        elif generate_query_request.llm_type.startswith("deepseek"):
            api_key = os.getenv("OPENROUTER_API_KEY")
            Logger.info("Using OpenRouter API key from .env")
        else:
            raise HTTPException(
                status_code=400,
                detail="Could not determine provider for LLM type. Please provide an API key directly."
            )
    
    key = f"{generate_query_request.llm_type}_{api_key}"

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
                api_key=api_key,
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
                api_key=api_key,
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
    # Apply rate limiting
    check_rate_limit(request)
    
    setup_logging(run_query_request.verbose)
    try:
        await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
    
    except ValueError as e:
        Logger.error(f"CSRF validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    Logger.info(f"Running query for question: '{run_query_request.question}'")
    Logger.debug(f"Query to execute: {run_query_request.query}")
    Logger.debug(f"Using LLM: {run_query_request.llm_type}, top_k: {run_query_request.top_k}")
    
    # Handle "env" API key by using the API key from .env
    api_key = run_query_request.api_key
    if api_key == "env":
        # Determine provider based on LLM type
        if run_query_request.llm_type.startswith("gpt"):
            api_key = os.getenv("OPENAI_API_KEY")
            Logger.info("Using OpenAI API key from .env")
        elif run_query_request.llm_type.startswith("claude"):
            api_key = os.getenv("ANTHROPIC_API_KEY")
            Logger.info("Using Anthropic API key from .env")
        elif run_query_request.llm_type.startswith("gemini"):
            api_key = os.getenv("GEMINI_API_KEY")
            Logger.info("Using Google API key from .env")
        elif run_query_request.llm_type.startswith("llama") or run_query_request.llm_type.startswith("mixtral"):
            api_key = os.getenv("GROQ_API_KEY")
            Logger.info("Using Groq API key from .env")
        elif run_query_request.llm_type.startswith("meta/llama") or run_query_request.llm_type.startswith("mistralai"):
            api_key = os.getenv("NVIDIA_API_KEY")
            Logger.info("Using NVIDIA API key from .env")
        elif run_query_request.llm_type.startswith("deepseek"):
            api_key = os.getenv("OPENROUTER_API_KEY")
            Logger.info("Using OpenRouter API key from .env")
        else:
            raise HTTPException(
                status_code=400,
                detail="Could not determine provider for LLM type. Please provide an API key directly."
            )
    
    key = f"{run_query_request.llm_type}_{api_key}"

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
            api_key=api_key,
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
    client_ip: Optional[str] = Form(None),
    file: UploadFile = File(...)
):
    # Apply rate limiting
    check_rate_limit(request)
    
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


@app.get("/api_keys_status/")
async def get_api_keys_status(request: Request):
    Logger.info("API keys status requested")
    
    # Load env variables to ensure we have the latest
    load_dotenv()
    
    # Check which API keys are available in the environment
    api_keys_status = {
        "OpenAI": os.getenv("OPENAI_API_KEY", "") != "" and os.getenv("OPENAI_API_KEY", "") != "default",
        "Anthropic": os.getenv("ANTHROPIC_API_KEY", "") != "" and os.getenv("ANTHROPIC_API_KEY", "") != "default",
        "Google": os.getenv("GEMINI_API_KEY", "") != "" and os.getenv("GEMINI_API_KEY", "") != "default",
        "Groq": os.getenv("GROQ_API_KEY", "") != "" and os.getenv("GROQ_API_KEY", "") != "default",
        "Nvidia": os.getenv("NVIDIA_API_KEY", "") != "" and os.getenv("NVIDIA_API_KEY", "") != "default",
        "OpenRouter": os.getenv("OPENROUTER_API_KEY", "") != "" and os.getenv("OPENROUTER_API_KEY", "") != "default",
    }
    
    Logger.debug(f"API keys status: {api_keys_status}")
    return api_keys_status

# Initialize logging on startup
@app.on_event("startup")
async def startup_event():
    setup_logging(verbose=False)
    # Initialize the event loop for threading usage
    asyncio.get_event_loop_policy().get_event_loop()
    Logger.info("API server started with rate limiting enabled")
    Logger.info("Rate limits: 3 requests per minute, 10 requests per hour, 25 requests per day")