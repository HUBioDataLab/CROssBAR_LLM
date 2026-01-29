import asyncio
import json
import logging
import os
import queue
import threading
import time
import traceback
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from typing import Any, Dict, List, Optional

import neo4j
import numpy as np
import pandas as pd

# Import configuration
from config import (
    IS_DEVELOPMENT,
    IS_PRODUCTION,
    get_provider_env_var,
    get_provider_for_model,
    get_setting,
)
from config import get_api_keys_status as get_api_keys_status_from_config
from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_csrf_protect import CsrfProtect
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from tools.langchain_llm_qa_trial import RunPipeline, configure_logging
from tools.utils import Logger
from tools.structured_logger import (
    get_structured_logger,
    create_query_log,
    finalize_query_log,
    log_error,
    QueryLogEntry,
)
from tools.conversation_store import get_conversation_store, ConversationTurn
from models_config import get_all_models

# Load environment variables
load_dotenv()

origins = [
    "http://localhost:3000",  # React dev server
    "http://127.0.0.1:3000",
    "http://localhost:8501",
    "http://127.0.0.1:8501",
    f"https://crossbarv2.hubiodatalab.com{os.getenv('REACT_APP_CROSSBAR_LLM_ROOT_PATH')}",
]

app = FastAPI()


# Global exception handler middleware for comprehensive error logging
@app.middleware("http")
async def log_requests_and_errors(request: Request, call_next):
    """
    Middleware to log all requests and catch unhandled exceptions.
    
    Provides comprehensive error logging with:
    - Full request details
    - Complete stack traces
    - Request timing
    - Error context
    """
    request_id = str(time.time())  # Simple request ID for middleware-level logging
    request_start_time = time.time()
    
    # Get client IP
    client_ip = "unknown"
    try:
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            client_ip = x_forwarded_for.split(",")[0].strip()
        elif hasattr(request, "client") and hasattr(request.client, "host"):
            client_ip = request.client.host
    except:
        pass
    
    Logger.debug(
        f"[MIDDLEWARE] Request started",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": str(request.url.path),
            "client_ip": client_ip
        }
    )
    
    try:
        response = await call_next(request)
        
        request_duration_ms = (time.time() - request_start_time) * 1000
        
        Logger.debug(
            f"[MIDDLEWARE] Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": str(request.url.path),
                "status_code": response.status_code,
                "duration_ms": request_duration_ms
            }
        )
        
        return response
        
    except Exception as e:
        request_duration_ms = (time.time() - request_start_time) * 1000
        error_traceback = traceback.format_exc()
        
        Logger.error(
            f"[MIDDLEWARE] Unhandled exception",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": str(request.url.path),
                "client_ip": client_ip,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "duration_ms": request_duration_ms
            }
        )
        
        Logger.debug(
            f"[MIDDLEWARE] Exception traceback",
            extra={
                "request_id": request_id,
                "traceback": error_traceback
            }
        )
        
        # Log to structured logger
        log_error(e, step="middleware", context={
            "method": request.method,
            "path": str(request.url.path),
            "client_ip": client_ip
        })
        
        # Re-raise to let FastAPI handle it
        raise


# Global exception handler for HTTPException
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with detailed logging."""
    Logger.error(
        f"[HTTP_EXCEPTION] {exc.status_code}",
        extra={
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": str(request.url.path),
            "method": request.method
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# Global exception handler for unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with comprehensive logging."""
    error_traceback = traceback.format_exc()
    
    Logger.error(
        f"[GLOBAL_EXCEPTION] Unhandled exception",
        extra={
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "path": str(request.url.path),
            "method": request.method
        }
    )
    
    Logger.debug(
        f"[GLOBAL_EXCEPTION] Full traceback",
        extra={"traceback": error_traceback}
    )
    
    # Log to structured logger
    log_error(exc, step="global_exception_handler", context={
        "path": str(request.url.path),
        "method": request.method
    })
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "message": "An unexpected error occurred. Please try again."
            }
        }
    )


# Helper function to get real client IP address when behind a reverse proxy
def get_client_ip(request: Request, x_forwarded_for: Optional[str] = Header(None)):
    # Print debug information
    Logger.debug(f"x_forwarded_for type: {type(x_forwarded_for)}")
    Logger.debug(f"x_forwarded_for value: {x_forwarded_for}")

    # First try X-Forwarded-For header which is standard for proxies
    if x_forwarded_for and isinstance(x_forwarded_for, str):
        # Ensure x_forwarded_for is treated as a string
        x_forwarded_for_str = str(x_forwarded_for)
        # X-Forwarded-For can contain multiple IPs - the first one is the client
        client_ip = x_forwarded_for_str.split(",")[0].strip()
        Logger.debug(f"Using X-Forwarded-For IP: {client_ip}")
        return client_ip

    # Try getting X-Forwarded-For from the request headers directly
    x_forwarded_for_header = request.headers.get("x-forwarded-for")
    if x_forwarded_for_header:
        client_ip = x_forwarded_for_header.split(",")[0].strip()
        Logger.debug(f"Using X-Forwarded-For from request headers: {client_ip}")
        return client_ip

    # Try X-Real-IP header (used by some proxies)
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        Logger.debug(f"Using X-Real-IP: {x_real_ip}")
        return x_real_ip

    # Try custom header (if client is sending it)
    client_ip_header = request.headers.get("x-client-ip")
    if client_ip_header:
        Logger.debug(f"Using X-Client-IP header: {client_ip_header}")
        return client_ip_header

    # Try to get from request body if provided
    try:
        body = request.scope.get("_body")
        if body:
            body_json = json.loads(body.decode("utf-8"))
            if "client_ip" in body_json:
                Logger.debug(
                    f"Using client_ip from request body: {body_json['client_ip']}"
                )
                return body_json["client_ip"]
    except:
        pass

    # Try to get from form data for multipart/form-data requests
    try:
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            form_data = request._form
            if form_data and "client_ip" in form_data:
                client_ip = form_data.get("client_ip")
                Logger.debug(f"Using client_ip from form data: {client_ip}")
                return client_ip
    except:
        pass

    # Fall back to the direct client IP (the proxy server most likely)
    if hasattr(request, "client") and hasattr(request.client, "host"):
        Logger.debug(f"Falling back to direct client IP: {request.client.host}")
        return request.client.host

    # Ultimate fallback
    Logger.warning("Could not determine client IP, using default")
    return "127.0.0.1"


# Rate limiting implementation
class RateLimiter:
    def __init__(self):
        self.request_records: Dict[
            str, List[datetime]
        ] = {}  # IP -> list of request timestamps
        # Get rate limits from configuration
        self.minute_limit = get_setting("rate_limits", {}).get("minute", 6)
        self.hour_limit = get_setting("rate_limits", {}).get("hour", 20)
        self.day_limit = get_setting("rate_limits", {}).get("day", 50)
        self.enabled = get_setting("rate_limiting_enabled", True)

        # Log with readable rate limit values
        if not self.enabled:
            Logger.info("Rate limiting is disabled (development mode)")
        else:
            # Consider very high limits as effectively unlimited for display purposes
            minute_display = (
                "unlimited" if self.minute_limit >= 1000000 else self.minute_limit
            )
            hour_display = (
                "unlimited" if self.hour_limit >= 1000000 else self.hour_limit
            )
            day_display = "unlimited" if self.day_limit >= 1000000 else self.day_limit
            Logger.info(
                f"Rate limiting is enabled with limits: {minute_display}/min, {hour_display}/hr, {day_display}/day"
            )

    def is_rate_limited(self, ip: str) -> tuple[bool, str, int]:
        # If rate limiting is disabled, immediately return not limited
        if not self.enabled:
            return False, "", 0

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

        # Check minute limit - skip check if limit is effectively unlimited
        if self.minute_limit < 1000000:  # Threshold for "unlimited"
            minute_ago = current_time - timedelta(minutes=1)
            minute_requests = [
                ts for ts in self.request_records[ip_str] if ts > minute_ago
            ]
            if len(minute_requests) > self.minute_limit:
                # Keep only requests from the last day for storage efficiency
                self.request_records[ip_str] = [
                    ts
                    for ts in self.request_records[ip_str]
                    if ts > (current_time - timedelta(days=1))
                ]
                return True, "minute", 60

        # Check hour limit - skip check if limit is effectively unlimited
        if self.hour_limit < 1000000:  # Threshold for "unlimited"
            hour_ago = current_time - timedelta(hours=1)
            hour_requests = [ts for ts in self.request_records[ip_str] if ts > hour_ago]
            if len(hour_requests) > self.hour_limit:
                # Keep only requests from the last day for storage efficiency
                self.request_records[ip_str] = [
                    ts
                    for ts in self.request_records[ip_str]
                    if ts > (current_time - timedelta(days=1))
                ]
                return True, "hour", 3600

        # Check day limit - skip check if limit is effectively unlimited
        if self.day_limit < 1000000:  # Threshold for "unlimited"
            day_ago = current_time - timedelta(days=1)
            day_requests = [ts for ts in self.request_records[ip_str] if ts > day_ago]
            if len(day_requests) > self.day_limit:
                # Keep last 30 days of requests
                self.request_records[ip_str] = [
                    ts
                    for ts in self.request_records[ip_str]
                    if ts > (current_time - timedelta(days=30))
                ]
                return True, "day", 86400

        # No rate limit exceeded
        return False, "", 0


# Create rate limiter instance
rate_limiter = RateLimiter()


# Helper function for conditional CSRF validation
async def validate_csrf_if_enabled(
    request: Request, csrf_token: CsrfProtect = Depends()
):
    if get_setting("csrf_enabled", True):
        try:
            await csrf_token.validate_csrf(request, cookie_key="fastapi-csrf-token")
        except ValueError as e:
            Logger.error(f"CSRF validation failed: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    else:
        Logger.debug("CSRF validation skipped (development mode)")
    return True


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
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    cookie_httponly: bool = True
    # Set a longer expiration time (24 hours)
    cookie_max_age: int = 86400  # 24 hours in seconds


@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()


@app.get("/csrf-token/")
def get_csrf_token(csrf_protect: CsrfProtect = Depends()):
    Logger.debug("Getting CSRF token")

    # If CSRF is disabled (development mode), return a dummy token
    if not get_setting("csrf_enabled", True):
        Logger.info(
            "CSRF protection is disabled (development mode), returning dummy token"
        )
        return JSONResponse(
            {
                "detail": "CSRF protection is disabled in development mode",
                "csrf_token": "development-mode-no-csrf-required",
                "environment": "development",
            }
        )

    # Production mode - generate real CSRF token
    csrf_token, signed_token = csrf_protect.generate_csrf_tokens()
    response = JSONResponse(
        {
            "detail": "CSRF cookie set",
            "csrf_token": csrf_token,
            "environment": "production",
        }
    )
    csrf_protect.set_csrf_cookie(signed_token, response)
    Logger.info("CSRF token generated and set in cookie")
    return response


# Neo4j connection details
neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
neo4j_uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
neo4j_password = os.getenv("MY_NEO4J_PASSWORD", "password")
neo4j_db_name = os.getenv("NEO4J_DATABASE_NAME", "neo4j")

# Initialize RunPipeline instances cache
pipeline_instances = {}


# Helper function to check rate limits and return appropriate error
def check_rate_limit(request: Request):
    # Skip rate limiting check if disabled in config
    if not get_setting("rate_limiting_enabled", True):
        return

    # Get actual client IP from headers or fallback to direct client IP (without Header dependency)
    # Try getting X-Forwarded-For from the request headers directly
    client_ip = None

    # Try to get from headers
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(",")[0].strip()
        Logger.debug(f"Using X-Forwarded-For from request headers: {client_ip}")

    # Try X-Real-IP header
    elif request.headers.get("x-real-ip"):
        client_ip = request.headers.get("x-real-ip")
        Logger.debug(f"Using X-Real-IP: {client_ip}")

    # Try custom header
    elif request.headers.get("x-client-ip"):
        client_ip = request.headers.get("x-client-ip")
        Logger.debug(f"Using X-Client-IP header: {client_ip}")

    # Fall back to direct client IP
    elif hasattr(request, "client") and hasattr(request.client, "host"):
        client_ip = request.client.host
        Logger.debug(f"Using direct client IP: {client_ip}")

    # Default
    else:
        client_ip = "127.0.0.1"
        Logger.warning("Could not determine client IP, using default")

    # Ensure client_ip is a string
    client_ip_str = str(client_ip)
    Logger.debug(f"Client IP for rate limiting: {client_ip_str}")

    is_limited, limit_type, retry_seconds = rate_limiter.is_rate_limited(client_ip_str)

    if is_limited:
        Logger.warning(
            f"Rate limit exceeded for IP: {client_ip_str} ({limit_type} limit)"
        )

        # Get current limits from rate limiter
        minute_limit = rate_limiter.minute_limit
        hour_limit = rate_limiter.hour_limit
        day_limit = rate_limiter.day_limit

        # Format limit values for display (consider very large numbers as "unlimited")
        minute_display = "unlimited" if minute_limit >= 1000000 else minute_limit
        hour_display = "unlimited" if hour_limit >= 1000000 else hour_limit
        day_display = "unlimited" if day_limit >= 1000000 else day_limit

        # Create appropriate error message based on limit type
        if limit_type == "minute":
            detail_message = (
                f"Minute rate limit exceeded ({minute_display} requests per minute)."
            )
        elif limit_type == "hour":
            detail_message = (
                f"Hour rate limit exceeded ({hour_display} requests per hour)."
            )
        elif limit_type == "day":
            detail_message = (
                f"Daily rate limit exceeded ({day_display} requests per day)."
            )
        else:
            detail_message = "Rate limit exceeded."

        raise HTTPException(
            status_code=429,
            detail={
                "error": detail_message,
                "retry_after": retry_seconds,
                "limit_type": limit_type,
            },
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
        if not getattr(self, "running", True):
            return
        log_entry = self.format(record)
        # Add to the thread-safe queue
        self.log_messages.put(log_entry)

    def _worker(self):
        """Worker thread that transfers messages from the thread-safe queue to the asyncio queue."""
        # Use getattr with default to avoid AttributeError
        while getattr(self, "running", True):
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
        if hasattr(self, "worker_thread") and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
        super().close()


# Modify the existing logging setup
def setup_logging(verbose=False):
    # File logging is handled by structured_logger.py
    configure_logging(verbose=verbose)

    # Add async queue handler for streaming logs to frontend
    logger = logging.getLogger()

    # Check if AsyncQueueHandler already exists in handlers
    has_queue_handler = any(isinstance(h, AsyncQueueHandler) for h in logger.handlers)

    if not has_queue_handler:
        queue_handler = AsyncQueueHandler()
        queue_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
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
                yield {"event": "log", "data": json.dumps({"log": log_entry})}
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
    vector_category: Optional[str] = None
    provider: Optional[str] = None
    session_id: Optional[str] = None  # For conversation memory


class RunQueryRequest(BaseModel):
    query: str
    question: str
    llm_type: str
    top_k: int = 5
    api_key: str
    verbose: bool = False
    provider: Optional[str] = None
    session_id: Optional[str] = None  # For conversation memory
    is_semantic_search: bool = False  # Whether semantic/vector search is active
    vector_category: Optional[str] = None  # Category used for semantic search


class GenerateQueryResponse(BaseModel):
    """Response model for query generation with conversation support."""
    query: str
    session_id: Optional[str] = None
    conversation_turn_count: int = 0


class RunQueryResponse(BaseModel):
    """Response model for query execution with conversation support."""
    response: str
    result: List[Any]
    query: str
    follow_up_questions: List[str] = []
    session_id: Optional[str] = None
    conversation_turn_count: int = 0


@app.post("/generate_query/")
async def generate_query(
    request: Request,
    generate_query_request: GenerateQueryRequest,
    csrf_token: CsrfProtect = Depends(),
    _: bool = Depends(validate_csrf_if_enabled),
):
    """
    Generate a Cypher query from a natural language question.
    
    Includes comprehensive structured logging for all steps.
    """
    request_start_time = time.time()
    
    # Apply rate limiting
    check_rate_limit(request)

    setup_logging(generate_query_request.verbose)
    
    # Get client IP for logging
    client_ip = ""
    try:
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            client_ip = x_forwarded_for.split(",")[0].strip()
        elif hasattr(request, "client") and hasattr(request.client, "host"):
            client_ip = request.client.host
    except:
        client_ip = "unknown"

    # Determine provider
    provider = (
        (generate_query_request.provider or "").strip().lower()
        if generate_query_request.provider
        else get_provider_for_model(generate_query_request.llm_type) or ""
    )
    
    # Determine search type
    search_type = "db_search"
    if generate_query_request.embedding is not None or (
        generate_query_request.vector_index and generate_query_request.vector_category
    ):
        search_type = "vector_search"
    
    # Create structured query log
    structured_logger = get_structured_logger()
    query_log = structured_logger.create_query_log(
        question=generate_query_request.question,
        provider=provider,
        model_name=generate_query_request.llm_type,
        top_k=generate_query_request.top_k,
        search_type=search_type,
        vector_index=generate_query_request.vector_index,
        embedding_provided=generate_query_request.embedding is not None,
        verbose=generate_query_request.verbose,
        client_ip=client_ip
    )

    Logger.info(
        f"[API] /generate_query/ - Starting request",
        extra={
            "request_id": query_log.request_id,
            "question": generate_query_request.question[:100],
            "model": generate_query_request.llm_type,
            "provider": provider,
            "top_k": generate_query_request.top_k,
            "search_type": search_type,
            "client_ip": client_ip
        }
    )

    # Handle "env" API key by using the API key from .env
    api_key = generate_query_request.api_key
    if api_key == "env":
        if not provider:
            Logger.error(
                "[API] /generate_query/ - Provider required for env API key",
                extra={"request_id": query_log.request_id}
            )
            finalize_query_log(status="failed")
            raise HTTPException(
                status_code=400,
                detail="Provider is required when using 'env' api_key. Supply 'provider' or pass an explicit API key.",
            )
        env_var = get_provider_env_var(provider)
        if not env_var:
            Logger.error(
                f"[API] /generate_query/ - Unknown provider: {provider}",
                extra={"request_id": query_log.request_id}
            )
            finalize_query_log(status="failed")
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider '{provider}'.",
            )
        api_key = os.getenv(env_var)
        if not api_key:
            Logger.error(
                f"[API] /generate_query/ - API key not configured: {env_var}",
                extra={"request_id": query_log.request_id}
            )
            finalize_query_log(status="failed")
            raise HTTPException(
                status_code=400,
                detail=f"API key for provider '{provider}' is not configured in environment ({env_var}).",
            )
        Logger.info(
            f"[API] /generate_query/ - Using env API key",
            extra={
                "request_id": query_log.request_id,
                "provider": provider,
                "env_var": env_var
            }
        )

    key = f"{generate_query_request.llm_type}_{api_key}"

    # Get conversation context if session_id is provided
    conversation_context = ""
    conversation_turn_count = 0
    if generate_query_request.session_id:
        try:
            conversation_store = get_conversation_store()
            # For cypher generation, use only last 2-3 turns to save tokens (schema takes most space)
            conversation_context = conversation_store.get_context_string(
                generate_query_request.session_id,
                max_turns=3,
                include_cypher=True  # Include cypher for context in query generation
            )
            conversation_turn_count = len(conversation_store.get_history(generate_query_request.session_id))
            if conversation_context:
                Logger.info(
                    f"[API] /generate_query/ - Using conversation context",
                    extra={
                        "request_id": query_log.request_id,
                        "session_id": generate_query_request.session_id[:8] + "...",
                        "turn_count": conversation_turn_count,
                        "context_length": len(conversation_context)
                    }
                )
        except Exception as e:
            Logger.warning(
                f"[API] /generate_query/ - Failed to get conversation context",
                extra={
                    "request_id": query_log.request_id,
                    "error": str(e)
                }
            )

    # Initialize or reuse RunPipeline instance
    if key not in pipeline_instances:
        Logger.info(
            f"[API] /generate_query/ - Creating new pipeline instance",
            extra={
                "request_id": query_log.request_id,
                "model": generate_query_request.llm_type
            }
        )
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

    query = ""
    
    try:
        if generate_query_request.embedding is not None:
            Logger.info(
                "[API] /generate_query/ - Processing vector search with embedding",
                extra={
                    "request_id": query_log.request_id,
                    "vector_index": generate_query_request.vector_index
                }
            )

            generate_query_request.embedding = (
                generate_query_request.embedding.replace('{"vector_data":', "")
                .replace("}", "")
                .replace("[", "")
                .replace("]", "")
            )
            embedding = [float(x) for x in generate_query_request.embedding.split(",")]
            embedding = np.array(embedding)
            
            Logger.debug(
                f"[API] /generate_query/ - Embedding parsed",
                extra={
                    "request_id": query_log.request_id,
                    "embedding_shape": embedding.shape,
                    "embedding_dtype": str(embedding.dtype)
                }
            )

            vector_index = f"{generate_query_request.vector_index}Embeddings"
            rp.search_type = "vector_search"
            rp.top_k = generate_query_request.top_k

            query = rp.run_for_query(
                question=generate_query_request.question,
                model_name=generate_query_request.llm_type,
                api_key=api_key,
                vector_index=vector_index,
                embedding=embedding,
                reset_llm_type=True,
                conversation_context=conversation_context,
            )

        elif (
            generate_query_request.vector_index
            and generate_query_request.vector_category
        ):
            Logger.info(
                "[API] /generate_query/ - Processing category-based vector search",
                extra={
                    "request_id": query_log.request_id,
                    "vector_index": generate_query_request.vector_index,
                    "vector_category": generate_query_request.vector_category
                }
            )

            vector_index = f"{generate_query_request.vector_index}Embeddings"
            rp.search_type = "vector_search"
            rp.top_k = generate_query_request.top_k

            query = rp.run_for_query(
                question=generate_query_request.question,
                model_name=generate_query_request.llm_type,
                api_key=api_key,
                vector_index=vector_index,
                embedding=None,
                reset_llm_type=True,
                conversation_context=conversation_context,
            )

        else:
            Logger.info(
                "[API] /generate_query/ - Processing standard database search",
                extra={"request_id": query_log.request_id}
            )
            rp.search_type = "db_search"
            rp.top_k = generate_query_request.top_k

            query = rp.run_for_query(
                question=generate_query_request.question,
                model_name=generate_query_request.llm_type,
                api_key=api_key,
                reset_llm_type=True,
                conversation_context=conversation_context,
            )

        request_duration_ms = (time.time() - request_start_time) * 1000
        
        Logger.info(
            "[API] /generate_query/ - Query generation successful",
            extra={
                "request_id": query_log.request_id,
                "query_preview": query[:200] if query else "",
                "query_length": len(query) if query else 0,
                "duration_ms": request_duration_ms
            }
        )
        
        # Finalize the structured log
        finalize_query_log(
            generated_query=query,
            final_query=query,
            status="completed"
        )

    except Exception as e:
        request_duration_ms = (time.time() - request_start_time) * 1000
        error_traceback = traceback.format_exc()
        
        Logger.error(
            f"[API] /generate_query/ - Error generating query",
            extra={
                "request_id": query_log.request_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "duration_ms": request_duration_ms
            }
        )
        Logger.debug(
            f"[API] /generate_query/ - Error traceback",
            extra={
                "request_id": query_log.request_id,
                "traceback": error_traceback
            }
        )
        
        # Log error to structured logger
        log_error(e, step="generate_query", context={
            "question": generate_query_request.question,
            "model": generate_query_request.llm_type
        })
        
        finalize_query_log(status="failed")
        
        logs = log_stream.getvalue()
        logger.removeHandler(handler)
        raise HTTPException(
            status_code=500, 
            detail={
                "error": str(e),
                "error_type": type(e).__name__,
                "request_id": query_log.request_id,
                "logs": logs
            }
        )

    finally:
        logger.removeHandler(handler)

    logs = log_stream.getvalue()

    response = JSONResponse({
        "query": query, 
        "logs": logs,
        "request_id": query_log.request_id,
        "session_id": generate_query_request.session_id,
        "conversation_turn_count": conversation_turn_count
    })
    return response


@app.post("/run_query/")
async def run_query(
    request: Request,
    run_query_request: RunQueryRequest,
    csrf_token: CsrfProtect = Depends(),
    _: bool = Depends(validate_csrf_if_enabled),
):
    """
    Execute a Cypher query and generate a natural language response.
    
    Includes comprehensive structured logging for all steps.
    """
    request_start_time = time.time()
    
    # Apply rate limiting
    check_rate_limit(request)

    setup_logging(run_query_request.verbose)
    
    # Get client IP for logging
    client_ip = ""
    try:
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            client_ip = x_forwarded_for.split(",")[0].strip()
        elif hasattr(request, "client") and hasattr(request.client, "host"):
            client_ip = request.client.host
    except:
        client_ip = "unknown"

    # Determine provider
    provider = (
        (run_query_request.provider or "").strip().lower()
        if run_query_request.provider
        else get_provider_for_model(run_query_request.llm_type) or ""
    )
    
    # Create structured query log
    structured_logger = get_structured_logger()
    query_log = structured_logger.create_query_log(
        question=run_query_request.question,
        provider=provider,
        model_name=run_query_request.llm_type,
        top_k=run_query_request.top_k,
        search_type="query_execution",
        verbose=run_query_request.verbose,
        client_ip=client_ip
    )
    
    # Store the query being executed
    query_log.final_query = run_query_request.query

    Logger.info(
        f"[API] /run_query/ - Starting request",
        extra={
            "request_id": query_log.request_id,
            "question": run_query_request.question[:100],
            "query_preview": run_query_request.query[:200],
            "model": run_query_request.llm_type,
            "provider": provider,
            "top_k": run_query_request.top_k,
            "client_ip": client_ip
        }
    )

    # Handle "env" API key by using the API key from .env
    api_key = run_query_request.api_key
    if api_key == "env":
        if not provider:
            Logger.error(
                "[API] /run_query/ - Provider required for env API key",
                extra={"request_id": query_log.request_id}
            )
            finalize_query_log(status="failed")
            raise HTTPException(
                status_code=400,
                detail="Provider is required when using 'env' api_key. Supply 'provider' or pass an explicit API key.",
            )
        env_var = get_provider_env_var(provider)
        if not env_var:
            Logger.error(
                f"[API] /run_query/ - Unknown provider: {provider}",
                extra={"request_id": query_log.request_id}
            )
            finalize_query_log(status="failed")
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider '{provider}'.",
            )
        api_key = os.getenv(env_var)
        if not api_key:
            Logger.error(
                f"[API] /run_query/ - API key not configured: {env_var}",
                extra={"request_id": query_log.request_id}
            )
            finalize_query_log(status="failed")
            raise HTTPException(
                status_code=400,
                detail=f"API key for provider '{provider}' is not configured in environment ({env_var}).",
            )
        Logger.info(
            f"[API] /run_query/ - Using env API key",
            extra={
                "request_id": query_log.request_id,
                "provider": provider,
                "env_var": env_var
            }
        )

    key = f"{run_query_request.llm_type}_{api_key}"

    # Get conversation context if session_id is provided
    conversation_context = ""
    conversation_turn_count = 0
    conversation_store = None
    if run_query_request.session_id:
        try:
            conversation_store = get_conversation_store()
        except Exception as e:
            Logger.warning(
                f"[API] /run_query/ - Failed to initialize conversation store",
                extra={
                    "request_id": query_log.request_id,
                    "error": str(e)
                }
            )
        
        if conversation_store:
            try:
                # For QA response, use more context (full 10 turns)
                conversation_context = conversation_store.get_context_string(
                    run_query_request.session_id,
                    max_turns=10,
                    include_cypher=False  # No need for cypher in QA response
                )
                conversation_turn_count = len(conversation_store.get_history(run_query_request.session_id))
                if conversation_context:
                    Logger.info(
                        f"[API] /run_query/ - Using conversation context",
                        extra={
                            "request_id": query_log.request_id,
                            "session_id": run_query_request.session_id[:8] + "...",
                            "turn_count": conversation_turn_count,
                            "context_length": len(conversation_context)
                        }
                    )
            except Exception as e:
                Logger.warning(
                    f"[API] /run_query/ - Failed to get conversation context",
                    extra={
                        "request_id": query_log.request_id,
                        "error": str(e)
                    }
                )

    if key not in pipeline_instances:
        Logger.info(
            f"[API] /run_query/ - Creating new pipeline instance",
            extra={
                "request_id": query_log.request_id,
                "model": run_query_request.llm_type
            }
        )
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

    nl_response = ""
    result = []
    
    try:
        Logger.info(
            "[API] /run_query/ - Executing query against database",
            extra={
                "request_id": query_log.request_id,
                "query_preview": run_query_request.query[:200]
            }
        )
        
        nl_response, result = rp.execute_query(
            query=run_query_request.query,
            question=run_query_request.question,
            model_name=run_query_request.llm_type,
            api_key=api_key,
            reset_llm_type=True,
            conversation_context=conversation_context,
        )

        request_duration_ms = (time.time() - request_start_time) * 1000
        result_count = len(result) if isinstance(result, list) else 1
        
        Logger.info(
            "[API] /run_query/ - Query executed successfully",
            extra={
                "request_id": query_log.request_id,
                "result_count": result_count,
                "response_preview": nl_response[:200] if nl_response else "",
                "response_length": len(nl_response) if nl_response else 0,
                "duration_ms": request_duration_ms
            }
        )
        
        # Store the conversation turn if session_id is provided
        follow_up_questions = []
        if run_query_request.session_id and conversation_store and nl_response:
            try:
                # Store the turn
                conversation_store.add_turn(
                    session_id=run_query_request.session_id,
                    question=run_query_request.question,
                    cypher_query=run_query_request.query,
                    answer=nl_response
                )
                conversation_turn_count += 1
                
                Logger.info(
                    f"[API] /run_query/ - Stored conversation turn",
                    extra={
                        "request_id": query_log.request_id,
                        "session_id": run_query_request.session_id[:8] + "...",
                        "turn_count": conversation_turn_count
                    }
                )
                
                # Generate follow-up questions
                try:
                    # Get the QueryChain to generate follow-ups
                    from tools.langchain_llm_qa_trial import QueryChain
                    if isinstance(rp.llm, dict):
                        query_chain = QueryChain(
                            cypher_llm=rp.llm["cypher_llm"],
                            qa_llm=rp.llm["qa_llm"],
                            schema=rp.neo4j_connection.schema,
                            model_name=rp.current_model_name,
                            provider=rp.current_provider,
                        )
                    else:
                        query_chain = QueryChain(
                            cypher_llm=rp.llm,
                            qa_llm=rp.llm,
                            schema=rp.neo4j_connection.schema,
                            model_name=rp.current_model_name,
                            provider=rp.current_provider,
                        )
                    
                    follow_up_questions = query_chain.generate_follow_up_questions(
                        question=run_query_request.question,
                        answer=nl_response,
                        is_semantic_search=run_query_request.is_semantic_search,
                        vector_category=run_query_request.vector_category
                    )
                    
                    Logger.info(
                        f"[API] /run_query/ - Generated follow-up questions",
                        extra={
                            "request_id": query_log.request_id,
                            "follow_up_count": len(follow_up_questions)
                        }
                    )
                except Exception as e:
                    Logger.warning(
                        f"[API] /run_query/ - Failed to generate follow-up questions",
                        extra={
                            "request_id": query_log.request_id,
                            "error": str(e)
                        }
                    )
            except Exception as e:
                Logger.warning(
                    f"[API] /run_query/ - Failed to store conversation turn",
                    extra={
                        "request_id": query_log.request_id,
                        "error": str(e)
                    }
                )
        
        # Finalize the structured log
        finalize_query_log(
            final_query=run_query_request.query,
            natural_language_response=nl_response,
            status="completed"
        )

    except Exception as e:
        request_duration_ms = (time.time() - request_start_time) * 1000
        error_traceback = traceback.format_exc()
        
        Logger.error(
            f"[API] /run_query/ - Error executing query",
            extra={
                "request_id": query_log.request_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "duration_ms": request_duration_ms
            }
        )
        Logger.debug(
            f"[API] /run_query/ - Error traceback",
            extra={
                "request_id": query_log.request_id,
                "traceback": error_traceback
            }
        )
        
        # Log error to structured logger
        log_error(e, step="run_query", context={
            "question": run_query_request.question,
            "query": run_query_request.query[:200],
            "model": run_query_request.llm_type
        })
        
        finalize_query_log(status="failed")
        
        logs = log_stream.getvalue()
        logger.removeHandler(handler)
        raise HTTPException(
            status_code=500, 
            detail={
                "error": str(e),
                "error_type": type(e).__name__,
                "request_id": query_log.request_id,
                "logs": logs
            }
        )
        
    finally:
        logger.removeHandler(handler)

    logs = log_stream.getvalue()

    response = JSONResponse({
        "response": nl_response, 
        "result": result, 
        "logs": logs,
        "request_id": query_log.request_id,
        "session_id": run_query_request.session_id,
        "conversation_turn_count": conversation_turn_count,
        "follow_up_questions": follow_up_questions
    })

    return response


@app.delete("/conversation/{session_id}")
async def clear_conversation(
    session_id: str,
    request: Request,
):
    """
    Clear the conversation history for a session.
    
    This allows users to start a fresh conversation.
    """
    try:
        conversation_store = get_conversation_store()
        cleared = conversation_store.clear_session(session_id)
        
        if cleared:
            Logger.info(
                f"[API] /conversation/ - Session cleared",
                extra={"session_id": session_id[:8] + "..."}
            )
            return JSONResponse({
                "success": True,
                "message": "Conversation cleared successfully"
            })
        else:
            return JSONResponse({
                "success": True,
                "message": "No conversation found for this session"
            })
    except Exception as e:
        Logger.error(
            f"[API] /conversation/ - Error clearing session",
            extra={"session_id": session_id[:8] + "...", "error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear conversation: {str(e)}"
        )


@app.get("/conversation/{session_id}")
async def get_conversation(
    session_id: str,
    request: Request,
):
    """
    Get the conversation history for a session.
    """
    try:
        conversation_store = get_conversation_store()
        history = conversation_store.get_history(session_id)
        session_info = conversation_store.get_session_info(session_id)
        
        return JSONResponse({
            "session_id": session_id,
            "turns": [
                {
                    "question": turn.question,
                    "cypher_query": turn.cypher_query,
                    "answer": turn.answer,
                    "timestamp": turn.timestamp.isoformat()
                }
                for turn in history
            ],
            "turn_count": len(history),
            "session_info": session_info
        })
    except Exception as e:
        Logger.error(
            f"[API] /conversation/ - Error getting conversation",
            extra={"session_id": session_id[:8] + "...", "error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get conversation: {str(e)}"
        )


@app.get("/conversation_stats/")
async def get_conversation_stats(request: Request):
    """
    Get overall statistics about the conversation store.
    """
    try:
        conversation_store = get_conversation_store()
        stats = conversation_store.get_stats()
        return JSONResponse(stats)
    except Exception as e:
        Logger.error(
            f"[API] /conversation_stats/ - Error getting stats",
            extra={"error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get conversation stats: {str(e)}"
        )


@app.post("/upload_vector/")
async def upload_vector(
    request: Request,
    csrf_token: CsrfProtect = Depends(),
    vector_category: str = Form(...),
    embedding_type: Optional[str] = Form(None),
    client_ip: Optional[str] = Form(None),
    file: UploadFile = File(...),
    _: bool = Depends(validate_csrf_if_enabled),
):
    # Apply rate limiting
    check_rate_limit(request)

    Logger.info(f"Vector upload requested for category: {vector_category}")
    Logger.debug(f"Embedding type: {embedding_type}")
    Logger.debug(f"Filename: {file.filename}")
    try:
        contents = await file.read()
        filename = file.filename
        file_extension = filename.split(".")[-1]
        Logger.debug(f"File extension: {file_extension}")

        # Convert the file content to vector
        if file_extension == "csv":
            Logger.debug("Processing CSV file")
            df = pd.read_csv(BytesIO(contents))
            if df.shape[1] > 1:
                Logger.warning("CSV file contains multiple columns")
                raise ValueError(
                    "The CSV file should contain only one column (one array). Multiple columns detected."
                )
            vector_data = df.to_numpy().flatten()
        elif file_extension == "npy":
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
            raise ValueError(
                "Unsupported file format. Please upload a CSV or NPY file."
            )

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

    # Check which API keys are available in the environment via centralized config
    api_keys_status = get_api_keys_status_from_config()

    Logger.debug(f"API keys status: {api_keys_status}")
    return api_keys_status


@app.get("/environment-info/")
def get_environment_info():
    """
    Get information about the current environment configuration.
    This is useful for debugging and development.
    """
    environment = "production" if IS_PRODUCTION else "development"

    # Get rate limits and convert very large numbers to "unlimited" for display
    rate_limits = get_setting("rate_limits", {})
    json_safe_rate_limits = {}

    for key, value in rate_limits.items():
        if value >= 1000000:  # Threshold for considering a limit as "unlimited"
            json_safe_rate_limits[key] = "unlimited"
        else:
            json_safe_rate_limits[key] = value

    return {
        "environment": environment,
        "isProduction": IS_PRODUCTION,
        "isDevelopment": IS_DEVELOPMENT,
        "settings": {
            "csrf_enabled": get_setting("csrf_enabled"),
            "rate_limiting_enabled": get_setting("rate_limiting_enabled"),
            "rate_limits": json_safe_rate_limits,
        },
    }


@app.get("/models/")
def get_available_models():
    """
    Get all available LLM models organized by provider.
    This provides a single source of truth for model choices in the frontend.
    """
    Logger.info("Available models requested")
    models = get_all_models()
    Logger.debug(f"Returning models configuration with {len(models)} providers")
    return models


# Initialize logging on startup
@app.on_event("startup")
async def startup_event():
    setup_logging(verbose=False)
    # Initialize the event loop for threading usage
    asyncio.get_event_loop_policy().get_event_loop()
    Logger.info("API server started with rate limiting enabled")
    Logger.info(
        "Rate limits: 3 requests per minute, 10 requests per hour, 25 requests per day"
    )
