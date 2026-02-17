import asyncio
import hashlib
import hmac
import json
import logging
import os
import queue
import secrets
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
    is_env_model_allowed,
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


def get_free_models_for_environment() -> List[str]:
    """
    Return model names that can be used with server-managed (`api_key='env'`) keys.
    Development: all models.
    Production: only explicitly allowed free models with configured provider keys.
    """
    all_models = get_all_models()
    all_model_names = [model for provider_models in all_models.values() for model in provider_models]

    # A model can only be "free" if its provider key is actually configured.
    configured_models: List[str] = []
    for model_name in all_model_names:
        provider_id = get_provider_for_model(model_name)
        env_var = get_provider_env_var(provider_id or "")
        if not env_var:
            continue
        env_value = os.getenv(env_var, "")
        if env_value and env_value != "default":
            configured_models.append(model_name)

    if IS_DEVELOPMENT:
        # In development, expose all configured-provider models as free.
        return configured_models

    free_models: List[str] = []
    for model_name in configured_models:
        if is_env_model_allowed(model_name):
            free_models.append(model_name)
    return free_models

# Load environment variables
load_dotenv()

_IP_HASH_SECRET: bytes = os.getenv("IP_HASH_SECRET", "").encode("utf-8") or secrets.token_bytes(32)


def anonymize_ip(raw_ip: str) -> str:
    """
    Return a GDPR-compliant anonymized client identifier derived from a raw IP.

    Uses HMAC-SHA256 keyed with a server secret so the mapping is:
      • deterministic  – same IP ➜ same ID  (rate-limiting works)
      • irreversible   – cannot recover the IP from the ID
      • collision-safe – 16 hex chars = 64 bits of entropy

    The returned string has the form ``anon_<16-hex-chars>`` so it is
    immediately recognisable as an anonymized value in logs.
    """
    if not raw_ip or raw_ip in ("unknown", ""):
        return "anon_unknown"
    digest = hmac.new(_IP_HASH_SECRET, raw_ip.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"anon_{digest[:16]}"


def extract_client_ip(request: Request) -> str:
    """
    Extract the real client IP from a request and return its **anonymized**
    form.  Checks common proxy headers in priority order.

    This is the single source of truth for client identification — every
    place that needs a client identifier should call this function instead
    of re-implementing header inspection.
    """
    raw_ip: str | None = None

    # 1. X-Forwarded-For (standard reverse-proxy header, first entry = client)
    xff = request.headers.get("x-forwarded-for")
    if xff:
        raw_ip = xff.split(",")[0].strip()
    # 2. X-Real-IP (nginx convention)
    elif request.headers.get("x-real-ip"):
        raw_ip = request.headers.get("x-real-ip")
    # 3. X-Client-IP (custom header)
    elif request.headers.get("x-client-ip"):
        raw_ip = request.headers.get("x-client-ip")
    # 4. Direct connection (usually the proxy itself)
    elif hasattr(request, "client") and request.client and hasattr(request.client, "host"):
        raw_ip = request.client.host
    # 5. Fallback
    else:
        raw_ip = "127.0.0.1"

    return anonymize_ip(raw_ip)


origins = [
    "http://localhost:3000",  # React dev server
    "http://127.0.0.1:3000",
    "http://localhost:3001",  # Log dashboard dev server
    "http://127.0.0.1:3001",
    "http://localhost:8501",
    "http://127.0.0.1:8501",
    f"https://crossbarv2.hubiodatalab.com{os.getenv('REACT_APP_CROSSBAR_LLM_ROOT_PATH')}",
]

app = FastAPI()

# Mount the dashboard API router
from dashboard_api import router as dashboard_router
app.include_router(dashboard_router)


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

    # Get anonymized client identifier
    client_id = extract_client_ip(request)

    Logger.debug(
        f"[MIDDLEWARE] Request started",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": str(request.url.path),
            "client_id": client_id
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
                "client_id": client_id,
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
            "client_id": client_id
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


# Helper function to get anonymized client identifier when behind a reverse proxy.
# Returns a GDPR-compliant hashed identifier — never a raw IP address.
def get_client_ip(request: Request, x_forwarded_for: Optional[str] = Header(None)):
    """Return an anonymized client identifier derived from the real IP.

    Kept as a FastAPI dependency (``Depends(get_client_ip)``) for backward
    compatibility.  Internally delegates to :func:`extract_client_ip` which
    hashes the IP via HMAC-SHA256.
    """
    return extract_client_ip(request)


# Rate limiting implementation
class RateLimiter:
    def __init__(self):
        self.request_records: Dict[
            str, List[datetime]
        ] = {}  # anonymized client ID -> list of request timestamps
        # Get rate limits from configuration
        self.minute_limit = get_setting("rate_limits", {}).get("minute", 6)
        self.hour_limit = get_setting("rate_limits", {}).get("hour", 20)
        self.day_limit = get_setting("rate_limits", {}).get("day", 50)
        self.enabled = get_setting("rate_limiting_enabled", True)

        # Log with readable rate limit values
        if not self.enabled:
            Logger.info("Rate limiting is disabled")
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

    def is_rate_limited(self, client_id: str) -> tuple[bool, str, int]:
        # If rate limiting is disabled, immediately return not limited
        if not self.enabled:
            return False, "", 0

        current_time = datetime.now()

        # Ensure client_id is a string
        id_str = str(client_id)
        Logger.debug(f"Checking rate limit for client: {id_str}")

        # If client not in records, add it
        if id_str not in self.request_records:
            self.request_records[id_str] = [current_time]
            return False, "", 0

        # Add current timestamp to tracking
        self.request_records[id_str].append(current_time)

        # Check minute limit - skip check if limit is effectively unlimited
        if self.minute_limit < 1000000:  # Threshold for "unlimited"
            minute_ago = current_time - timedelta(minutes=1)
            minute_requests = [
                ts for ts in self.request_records[id_str] if ts > minute_ago
            ]
            if len(minute_requests) > self.minute_limit:
                # Keep only requests from the last day for storage efficiency
                self.request_records[id_str] = [
                    ts
                    for ts in self.request_records[id_str]
                    if ts > (current_time - timedelta(days=1))
                ]
                return True, "minute", 60

        # Check hour limit - skip check if limit is effectively unlimited
        if self.hour_limit < 1000000:  # Threshold for "unlimited"
            hour_ago = current_time - timedelta(hours=1)
            hour_requests = [ts for ts in self.request_records[id_str] if ts > hour_ago]
            if len(hour_requests) > self.hour_limit:
                # Keep only requests from the last day for storage efficiency
                self.request_records[id_str] = [
                    ts
                    for ts in self.request_records[id_str]
                    if ts > (current_time - timedelta(days=1))
                ]
                return True, "hour", 3600

        # Check day limit - skip check if limit is effectively unlimited
        if self.day_limit < 1000000:  # Threshold for "unlimited"
            day_ago = current_time - timedelta(days=1)
            day_requests = [ts for ts in self.request_records[id_str] if ts > day_ago]
            if len(day_requests) > self.day_limit:
                # Keep last 30 days of requests
                self.request_records[id_str] = [
                    ts
                    for ts in self.request_records[id_str]
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

    # Get anonymized client identifier (GDPR-compliant)
    client_id = extract_client_ip(request)
    Logger.debug(f"Client ID for rate limiting: {client_id}")

    is_limited, limit_type, retry_seconds = rate_limiter.is_rate_limited(client_id)

    if is_limited:
        Logger.warning(
            f"Rate limit exceeded for client: {client_id} ({limit_type} limit)"
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
    request_id: Optional[str] = None  # For continuing an existing log from generate_query


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


class RunQueryWithRetryRequest(BaseModel):
    """Request model for query execution with automatic retry on error."""
    query: str
    question: str
    llm_type: str
    top_k: int = 5
    api_key: str
    verbose: bool = False
    provider: Optional[str] = None
    session_id: Optional[str] = None
    is_semantic_search: bool = False
    vector_category: Optional[str] = None
    max_retries: int = 3  # Maximum number of retry attempts
    request_id: Optional[str] = None  # For continuing an existing log from generate_query


class RetryAttempt(BaseModel):
    """Model for a single retry attempt."""
    attempt: int
    query: str
    error: Optional[str] = None
    error_type: Optional[str] = None
    success: bool = False


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

    # Get anonymized client identifier (GDPR-compliant)
    client_id = extract_client_ip(request)

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
        client_id=client_id
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
            "client_id": client_id
        }
    )

    # Handle "env" API key by using the API key from .env
    api_key = generate_query_request.api_key
    if api_key == "env":
        if not is_env_model_allowed(generate_query_request.llm_type):
            Logger.warning(
                "[API] /generate_query/ - Model not allowed for env API key",
                extra={
                    "request_id": query_log.request_id,
                    "model": generate_query_request.llm_type,
                    "environment": "production" if IS_PRODUCTION else "development",
                },
            )
            finalize_query_log(status="failed")
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Model '{generate_query_request.llm_type}' is not available "
                    "with server-managed API keys in this environment."
                ),
            )
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

    # Get anonymized client identifier (GDPR-compliant)
    client_id = extract_client_ip(request)

    # Determine provider
    provider = (
        (run_query_request.provider or "").strip().lower()
        if run_query_request.provider
        else get_provider_for_model(run_query_request.llm_type) or ""
    )

    # Create or continue structured query log
    structured_logger = get_structured_logger()
    
    # If request_id is provided, try to continue existing log; otherwise create new one
    if run_query_request.request_id:
        # Try to get existing log
        existing_log = structured_logger.get_current_log()
        if existing_log and existing_log.request_id == run_query_request.request_id:
            query_log = existing_log
            Logger.info(
                f"[API] /run_query/ - Continuing existing log",
                extra={
                    "request_id": query_log.request_id,
                    "existing_steps": len(query_log.steps)
                }
            )
        else:
            # Log not found in current context, create with provided request_id
            query_log = structured_logger.create_query_log(
                question=run_query_request.question,
                provider=provider,
                model_name=run_query_request.llm_type,
                top_k=run_query_request.top_k,
                search_type="query_execution",
                verbose=run_query_request.verbose,
                client_id=client_id,
                request_id=run_query_request.request_id
            )
            Logger.info(
                f"[API] /run_query/ - Created log with provided request_id",
                extra={"request_id": query_log.request_id}
            )
    else:
        # No request_id provided, create new log
        query_log = structured_logger.create_query_log(
            question=run_query_request.question,
            provider=provider,
            model_name=run_query_request.llm_type,
            top_k=run_query_request.top_k,
            search_type="query_execution",
            verbose=run_query_request.verbose,
            client_id=client_id
        )
        Logger.info(
            f"[API] /run_query/ - Created new log",
            extra={"request_id": query_log.request_id}
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
            "client_id": client_id
        }
    )

    # Handle "env" API key by using the API key from .env
    api_key = run_query_request.api_key
    if api_key == "env":
        if not is_env_model_allowed(run_query_request.llm_type):
            Logger.warning(
                "[API] /run_query/ - Model not allowed for env API key",
                extra={
                    "request_id": query_log.request_id,
                    "model": run_query_request.llm_type,
                    "environment": "production" if IS_PRODUCTION else "development",
                },
            )
            finalize_query_log(status="failed")
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Model '{run_query_request.llm_type}' is not available "
                    "with server-managed API keys in this environment."
                ),
            )
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


@app.post("/run_query_with_retry/")
async def run_query_with_retry(
    request: Request,
    run_query_request: RunQueryWithRetryRequest,
    csrf_token: CsrfProtect = Depends(),
    _: bool = Depends(validate_csrf_if_enabled),
):
    """
    Execute a Cypher query with automatic retry on error or empty result.

    This endpoint uses Server-Sent Events (SSE) to stream progress back to the client.
    If the query fails with an error, it retries up to max_retries (default 3) times.
    If the query returns empty results, it retries up to 2 times with a different query.
    If all retries are exhausted, the LLM falls back to its internal knowledge to
    answer the user's question instead of returning an error.

    SSE Events:
    - attempt_started: Query execution attempt starting
    - attempt_failed: Query attempt failed with error
    - attempt_empty: Query returned empty results
    - query_regenerated: New query generated after error or empty result
    - fallback_started: Falling back to LLM internal knowledge
    - completed: Query executed successfully (or fallback response generated)
    - failed: All retry attempts and fallback exhausted (rare edge case)
    """
    check_rate_limit(request)

    request_start_time = time.time()

    # Get anonymized client identifier (GDPR-compliant)
    client_id = extract_client_ip(request)

    Logger.info(
        "[API] /run_query_with_retry/ - Starting request with retry support",
        extra={
            "question": run_query_request.question[:100],
            "query_preview": run_query_request.query[:200],
            "max_retries": run_query_request.max_retries,
            "client_id": client_id
        }
    )

    async def event_generator():
        """Generate SSE events for query execution with retry.

        Retry logic:
        - On query execution error: retry up to max_retries (default 3) times
          with error-corrected query regeneration.
        - On empty result: retry up to 2 times with empty-result-aware query
          regeneration.
        - If all retries are exhausted (for either error or empty), fall back
          to the LLM's internal knowledge instead of returning an error.
        """
        # Initialize or continue structured logging
        structured_logger = get_structured_logger()
        
        # If request_id is provided, try to continue existing log; otherwise create new one
        if run_query_request.request_id:
            # Try to get existing log
            existing_log = structured_logger.get_current_log()
            if existing_log and existing_log.request_id == run_query_request.request_id:
                query_log = existing_log
                Logger.info(
                    f"[API] /run_query_with_retry/ - Continuing existing log",
                    extra={
                        "request_id": query_log.request_id,
                        "existing_steps": len(query_log.steps)
                    }
                )
            else:
                # Determine provider
                provider = (
                    (run_query_request.provider or "").strip().lower()
                    if run_query_request.provider
                    else get_provider_for_model(run_query_request.llm_type) or ""
                )
                
                # Log not found in current context, create with provided request_id
                query_log = structured_logger.create_query_log(
                    question=run_query_request.question,
                    provider=provider,
                    model_name=run_query_request.llm_type,
                    top_k=run_query_request.top_k,
                    search_type="query_execution_with_retry",
                    verbose=run_query_request.verbose,
                    client_id=client_id,
                    request_id=run_query_request.request_id
                )
                Logger.info(
                    f"[API] /run_query_with_retry/ - Created log with provided request_id",
                    extra={"request_id": query_log.request_id}
                )
        else:
            # Determine provider
            provider = (
                (run_query_request.provider or "").strip().lower()
                if run_query_request.provider
                else get_provider_for_model(run_query_request.llm_type) or ""
            )
            
            # No request_id provided, create new log
            query_log = structured_logger.create_query_log(
                question=run_query_request.question,
                provider=provider,
                model_name=run_query_request.llm_type,
                top_k=run_query_request.top_k,
                search_type="query_execution_with_retry",
                verbose=run_query_request.verbose,
                client_id=client_id
            )
            Logger.info(
                f"[API] /run_query_with_retry/ - Created new log",
                extra={"request_id": query_log.request_id}
            )
        
        EMPTY_RESULT_STRING = "Given cypher query did not return any result"

        attempts = []
        current_query = run_query_request.query
        nl_response = ""
        result = []
        follow_up_questions = []
        conversation_turn_count = 0
        conversation_store = None

        # Get provider from query_log (already determined in structured logging initialization)
        provider = query_log.provider

        # Handle "env" API key
        api_key = run_query_request.api_key
        if api_key == "env":
            if not is_env_model_allowed(run_query_request.llm_type):
                yield {
                    "event": "failed",
                    "data": json.dumps({
                        "error": (
                            f"Model '{run_query_request.llm_type}' is not available "
                            "with server-managed API keys in this environment."
                        ),
                        "error_type": "ModelNotAllowed",
                        "attempts": attempts
                    })
                }
                return
            if not provider:
                yield {
                    "event": "failed",
                    "data": json.dumps({
                        "error": "Provider is required when using 'env' api_key",
                        "error_type": "ValidationError",
                        "attempts": attempts
                    })
                }
                return
            env_var = get_provider_env_var(provider)
            if env_var:
                api_key = os.getenv(env_var)

        # Get or create pipeline instance
        key = f"{run_query_request.llm_type}_{api_key}"
        if key not in pipeline_instances:
            pipeline_instances[key] = RunPipeline(
                model_name=run_query_request.llm_type,
                verbose=run_query_request.verbose,
            )
        rp = pipeline_instances[key]

        # Get conversation context
        conversation_context = ""
        if run_query_request.session_id:
            try:
                conversation_store = get_conversation_store()
                conversation_context = conversation_store.get_context_string(
                    run_query_request.session_id,
                    max_turns=5,
                    include_cypher=False
                )
                conversation_turn_count = len(conversation_store.get_history(run_query_request.session_id))
            except Exception as e:
                Logger.warning(
                    f"[API] /run_query_with_retry/ - Failed to get conversation context",
                    extra={"error": str(e)}
                )

        # Create QueryChain once for reuse across retries
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

        # Retry limits: errors get max_retries (default 3), empty results get 2
        max_error_retries = run_query_request.max_retries  # Default 3
        max_empty_retries = 2
        error_retries_used = 0
        empty_retries_used = 0
        attempt_num = 0
        should_fallback = False
        last_failure_type = None  # "error" or "empty"

        Logger.info(
            "[API] /run_query_with_retry/ - Starting retry loop",
            extra={
                "max_error_retries": max_error_retries,
                "max_empty_retries": max_empty_retries
            }
        )

        while True:
            attempt_num += 1
            attempt_info = {
                "attempt": attempt_num,
                "query": current_query,
                "error": None,
                "error_type": None,
                "empty_result": False,
                "success": False
            }

            # Notify client that attempt is starting
            yield {
                "event": "attempt_started",
                "data": json.dumps({
                    "attempt": attempt_num,
                    "query": current_query,
                    "error_retries_used": error_retries_used,
                    "empty_retries_used": empty_retries_used
                })
            }

            try:
                Logger.info(
                    f"[API] /run_query_with_retry/ - Attempt {attempt_num}",
                    extra={
                        "query_preview": current_query[:200],
                        "attempt": attempt_num,
                        "error_retries_used": error_retries_used,
                        "empty_retries_used": empty_retries_used
                    }
                )

                # Execute the query
                nl_response, result = rp.execute_query(
                    query=current_query,
                    question=run_query_request.question,
                    model_name=run_query_request.llm_type,
                    api_key=api_key,
                    reset_llm_type=True,
                    conversation_context=conversation_context,
                )

                # Check if the query returned empty results
                is_empty = (isinstance(result, str) and result == EMPTY_RESULT_STRING)

                if is_empty:
                    empty_retries_used += 1
                    attempt_info["empty_result"] = True
                    attempts.append(attempt_info)

                    Logger.warning(
                        f"[API] /run_query_with_retry/ - Attempt {attempt_num} returned empty results",
                        extra={
                            "empty_retries_used": empty_retries_used,
                            "max_empty_retries": max_empty_retries
                        }
                    )

                    # Notify client of empty result
                    yield {
                        "event": "attempt_empty",
                        "data": json.dumps({
                            "attempt": attempt_num,
                            "query": current_query,
                            "empty_retries_used": empty_retries_used,
                            "max_empty_retries": max_empty_retries
                        })
                    }

                    if empty_retries_used <= max_empty_retries:
                        # Can still retry for empty result
                        try:
                            Logger.info(
                                "[API] /run_query_with_retry/ - Regenerating query after empty result",
                                extra={"empty_retries_used": empty_retries_used}
                            )

                            new_query = query_chain.regenerate_query_on_empty(
                                question=run_query_request.question,
                                failed_query=current_query,
                                conversation_context=conversation_context,
                            )

                            Logger.info(
                                "[API] /run_query_with_retry/ - Query regenerated after empty result",
                                extra={"new_query_preview": new_query[:200]}
                            )

                            yield {
                                "event": "query_regenerated",
                                "data": json.dumps({
                                    "attempt": attempt_num + 1,
                                    "new_query": new_query,
                                    "reason": "empty_result"
                                })
                            }

                            current_query = new_query

                        except Exception as regen_error:
                            Logger.error(
                                "[API] /run_query_with_retry/ - Failed to regenerate query after empty result",
                                extra={"error": str(regen_error)}
                            )
                            # Continue with same query for next attempt

                        continue
                    else:
                        # Max empty retries reached - fall back to internal knowledge
                        # nl_response already contains the LLM's internal knowledge answer
                        # because execute_query passed the empty result through the QA chain
                        should_fallback = True
                        last_failure_type = "empty"
                        break

                # Query succeeded with actual data
                attempt_info["success"] = True
                attempts.append(attempt_info)

                Logger.info(
                    f"[API] /run_query_with_retry/ - Query succeeded on attempt {attempt_num}",
                    extra={
                        "result_count": len(result) if isinstance(result, list) else 1,
                        "response_preview": nl_response[:200] if nl_response else ""
                    }
                )

                # Store conversation turn if session_id is provided
                if run_query_request.session_id and conversation_store and nl_response:
                    try:
                        conversation_store.add_turn(
                            session_id=run_query_request.session_id,
                            question=run_query_request.question,
                            cypher_query=current_query,
                            answer=nl_response
                        )
                        conversation_turn_count += 1

                        # Generate follow-up questions
                        try:
                            follow_up_questions = query_chain.generate_follow_up_questions(
                                question=run_query_request.question,
                                answer=nl_response,
                                is_semantic_search=run_query_request.is_semantic_search,
                                vector_category=run_query_request.vector_category
                            )
                        except Exception as e:
                            Logger.warning(
                                f"[API] /run_query_with_retry/ - Failed to generate follow-up questions",
                                extra={"error": str(e)}
                            )
                    except Exception as e:
                        Logger.warning(
                            f"[API] /run_query_with_retry/ - Failed to store conversation turn",
                            extra={"error": str(e)}
                        )

                # Finalize the structured log
                finalize_query_log(
                    final_query=current_query,
                    natural_language_response=nl_response,
                    status="completed"
                )

                # Send completion event
                yield {
                    "event": "completed",
                    "data": json.dumps({
                        "response": nl_response,
                        "result": result,
                        "query": current_query,
                        "attempts": attempts,
                        "total_attempts": len(attempts),
                        "session_id": run_query_request.session_id,
                        "conversation_turn_count": conversation_turn_count,
                        "follow_up_questions": follow_up_questions
                    })
                }
                return

            except Exception as e:
                error_message = str(e)
                error_type = type(e).__name__
                error_retries_used += 1

                attempt_info["error"] = error_message
                attempt_info["error_type"] = error_type
                attempts.append(attempt_info)

                Logger.warning(
                    f"[API] /run_query_with_retry/ - Attempt {attempt_num} failed with error",
                    extra={
                        "error_type": error_type,
                        "error_message": error_message[:300],
                        "error_retries_used": error_retries_used,
                        "max_error_retries": max_error_retries
                    }
                )

                # Notify client of failure
                yield {
                    "event": "attempt_failed",
                    "data": json.dumps({
                        "attempt": attempt_num,
                        "error": error_message,
                        "error_type": error_type,
                        "query": current_query,
                        "error_retries_used": error_retries_used,
                        "max_error_retries": max_error_retries
                    })
                }

                if error_retries_used <= max_error_retries:
                    # Can still retry for error
                    try:
                        Logger.info(
                            "[API] /run_query_with_retry/ - Regenerating query with error feedback",
                            extra={"error_retries_used": error_retries_used}
                        )

                        new_query = query_chain.regenerate_query_with_error(
                            question=run_query_request.question,
                            failed_query=current_query,
                            error_message=error_message,
                            conversation_context=conversation_context,
                        )

                        Logger.info(
                            "[API] /run_query_with_retry/ - Query regenerated after error",
                            extra={"new_query_preview": new_query[:200]}
                        )

                        yield {
                            "event": "query_regenerated",
                            "data": json.dumps({
                                "attempt": attempt_num + 1,
                                "new_query": new_query,
                                "reason": "error",
                                "previous_error": error_message
                            })
                        }

                        current_query = new_query

                    except Exception as regen_error:
                        Logger.error(
                            "[API] /run_query_with_retry/ - Failed to regenerate query after error",
                            extra={"error": str(regen_error)}
                        )
                        # Continue with same query for next attempt

                    continue
                else:
                    # Max error retries reached - fall back to internal knowledge
                    should_fallback = True
                    last_failure_type = "error"
                    break

        # All retries exhausted - fall back to LLM internal knowledge
        if should_fallback:
            request_duration_ms = (time.time() - request_start_time) * 1000

            Logger.info(
                f"[API] /run_query_with_retry/ - Falling back to LLM internal knowledge",
                extra={
                    "last_failure_type": last_failure_type,
                    "error_retries_used": error_retries_used,
                    "empty_retries_used": empty_retries_used,
                    "total_attempts": len(attempts),
                    "duration_ms": request_duration_ms
                }
            )

            yield {
                "event": "fallback_started",
                "data": json.dumps({
                    "reason": last_failure_type,
                    "total_attempts": len(attempts)
                })
            }

            fallback_response = ""

            if last_failure_type == "empty":
                # nl_response already contains the LLM's internal knowledge answer
                # from the last execute_query call (QA chain saw the empty result)
                fallback_response = nl_response
            else:
                # Error case - need to explicitly get internal knowledge via QA chain
                try:
                    fallback_response = query_chain.run_qa_chain(
                        output=EMPTY_RESULT_STRING,
                        input_question=run_query_request.question,
                        conversation_context=conversation_context,
                    )
                except Exception as fallback_error:
                    Logger.error(
                        "[API] /run_query_with_retry/ - Failed to generate fallback response",
                        extra={"error": str(fallback_error)}
                    )
                    fallback_response = ""

            if fallback_response:
                Logger.info(
                    "[API] /run_query_with_retry/ - Fallback response generated successfully",
                    extra={
                        "response_preview": fallback_response[:200],
                        "last_failure_type": last_failure_type
                    }
                )

                # Store conversation turn for fallback response
                if run_query_request.session_id and conversation_store and fallback_response:
                    try:
                        conversation_store.add_turn(
                            session_id=run_query_request.session_id,
                            question=run_query_request.question,
                            cypher_query=current_query,
                            answer=fallback_response
                        )
                        conversation_turn_count += 1
                    except Exception as e:
                        Logger.warning(
                            "[API] /run_query_with_retry/ - Failed to store fallback conversation turn",
                            extra={"error": str(e)}
                        )

                # Generate follow-up questions for fallback response
                try:
                    follow_up_questions = query_chain.generate_follow_up_questions(
                        question=run_query_request.question,
                        answer=fallback_response,
                        is_semantic_search=run_query_request.is_semantic_search,
                        vector_category=run_query_request.vector_category
                    )
                except Exception as e:
                    Logger.warning(
                        "[API] /run_query_with_retry/ - Failed to generate follow-up questions for fallback",
                        extra={"error": str(e)}
                    )

                # Finalize the structured log for fallback success
                finalize_query_log(
                    final_query=current_query,
                    natural_language_response=fallback_response,
                    status="completed"
                )

                yield {
                    "event": "completed",
                    "data": json.dumps({
                        "response": fallback_response,
                        "result": [],
                        "query": current_query,
                        "attempts": attempts,
                        "total_attempts": len(attempts),
                        "session_id": run_query_request.session_id,
                        "conversation_turn_count": conversation_turn_count,
                        "follow_up_questions": follow_up_questions,
                        "used_internal_knowledge": True
                    })
                }
            else:
                # Last resort: could not even generate a fallback response
                Logger.error(
                    "[API] /run_query_with_retry/ - Failed to generate any response",
                    extra={
                        "total_attempts": len(attempts),
                        "duration_ms": request_duration_ms
                    }
                )

                # Finalize the structured log for failure
                finalize_query_log(status="failed")

                yield {
                    "event": "failed",
                    "data": json.dumps({
                        "error": "All retry attempts exhausted and fallback failed",
                        "error_type": "MaxRetriesExceeded",
                        "attempts": attempts,
                        "total_attempts": len(attempts)
                    })
                }

    return EventSourceResponse(event_generator())


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


@app.get("/free_models/")
def get_free_models():
    """
    Get models that are available without user API key (server-managed env keys).
    """
    Logger.info("Free models requested")
    free_models = get_free_models_for_environment()
    Logger.debug(f"Returning {len(free_models)} free models")
    return {"models": free_models}


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
