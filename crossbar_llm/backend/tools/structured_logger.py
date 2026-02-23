"""
Structured Logging System for CROssBAR LLM

This module provides ultra-detailed structured logging for query processing,
LLM interactions, and error tracking. All logs are stored in JSON format
for easy parsing and analysis.
"""

import json
import logging
import os
import threading
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from time import time
from typing import Any, Dict, List, Optional, Union


current_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(current_dir)
LOGS_DIR = os.path.join(parent_dir, "logs")
STRUCTURED_LOGS_DIR = os.path.join(LOGS_DIR, "structured_logs")
DETAILED_LOGS_DIR = os.path.join(LOGS_DIR, "detailed_logs")


def ensure_log_directories():
    """Ensure all log directories exist."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(STRUCTURED_LOGS_DIR, exist_ok=True)
    os.makedirs(DETAILED_LOGS_DIR, exist_ok=True)


@dataclass
class TokenUsage:
    """Track token usage from LLM calls."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMCallLog:
    """Log entry for a single LLM call."""
    call_type: str = ""  # "cypher_generation", "qa_response", etc.
    model_name: str = ""
    provider: str = ""
    prompt: str = ""
    prompt_template: str = ""
    prompt_variables: Dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""
    parsed_response: str = ""
    thinking_content: str = ""  # For models with chain-of-thought
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    duration_ms: float = 0.0
    start_time: str = ""
    end_time: str = ""
    error: Optional[str] = None
    error_traceback: Optional[str] = None


@dataclass
class QueryCorrectionLog:
    """Log entry for query correction steps."""
    original_query: str = ""
    corrections: List[Dict[str, Any]] = field(default_factory=list)
    final_query: str = ""
    success: bool = True
    failure_reason: Optional[str] = None
    schemas_checked: int = 0
    duration_ms: float = 0.0


@dataclass
class Neo4jExecutionLog:
    """Log entry for Neo4j query execution."""
    query: str = ""
    query_with_limit: str = ""
    top_k: int = 0
    execution_time_ms: float = 0.0
    result_count: int = 0
    result_sample: List[Dict[str, Any]] = field(default_factory=list)
    full_results: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    connection_status: str = "unknown"


@dataclass
class StepLog:
    """Generic step log entry."""
    step_name: str = ""
    step_number: int = 0
    duration_ms: float = 0.0
    start_time: str = ""
    end_time: str = ""
    status: str = "pending"  # pending, in_progress, completed, failed
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_traceback: Optional[str] = None


@dataclass
class QueryLogEntry:
    """
    Complete log entry for a single query request.
    Contains all information from request to response.
    """
    # Request identification
    request_id: str = ""
    timestamp: str = ""
    client_id: str = ""

    # Request parameters
    question: str = ""
    provider: str = ""
    model_name: str = ""
    top_k: int = 5
    search_type: str = "db_search"
    vector_index: Optional[str] = None
    embedding_provided: bool = False
    verbose: bool = False

    # Pipeline steps
    steps: List[StepLog] = field(default_factory=list)

    # LLM calls
    llm_calls: List[LLMCallLog] = field(default_factory=list)

    # Query processing
    generated_query: str = ""
    query_correction: Optional[QueryCorrectionLog] = None
    final_query: str = ""

    # Neo4j execution
    neo4j_execution: Optional[Neo4jExecutionLog] = None

    # Response
    natural_language_response: str = ""

    # Timing
    total_duration_ms: float = 0.0
    start_time: str = ""
    end_time: str = ""

    # Status and errors
    status: str = "pending"  # pending, in_progress, completed, failed
    error: Optional[str] = None
    error_type: Optional[str] = None
    error_traceback: Optional[str] = None
    error_step: Optional[str] = None

    # Metadata
    schema_summary: Dict[str, Any] = field(default_factory=dict)
    additional_metadata: Dict[str, Any] = field(default_factory=dict)


class StructuredLogger:
    """
    Centralized structured logging for the CROssBAR LLM application.

    Provides JSON-formatted logging with request tracking, timing,
    and detailed error capture.
    """

    # Thread-local storage for current query log
    _local = threading.local()

    # Class-level lock for file operations
    _file_lock = threading.Lock()

    def __init__(self):
        ensure_log_directories()
        self._setup_json_logger()

    def _setup_json_logger(self):
        """Set up the JSON file logger with rotation."""
        self.json_logger = logging.getLogger("structured_query_log")
        self.json_logger.setLevel(logging.INFO)

        # Prevent duplicate handlers
        if not self.json_logger.handlers:
            # Daily rotating log file
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_file = os.path.join(STRUCTURED_LOGS_DIR, f"query_log_{today}.jsonl")

            # Rotating file handler (10MB max, keep 30 backups)
            handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=30,
                encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.json_logger.addHandler(handler)
            self.json_logger.propagate = False

    @classmethod
    def generate_request_id(cls) -> str:
        """Generate a unique request ID."""
        return str(uuid.uuid4())

    @classmethod
    def get_current_log(cls) -> Optional[QueryLogEntry]:
        """Get the current query log from thread-local storage."""
        return getattr(cls._local, "current_log", None)

    @classmethod
    def set_current_log(cls, log_entry: QueryLogEntry):
        """Set the current query log in thread-local storage."""
        cls._local.current_log = log_entry

    @classmethod
    def clear_current_log(cls):
        """Clear the current query log from thread-local storage."""
        cls._local.current_log = None

    def create_query_log(
        self,
        question: str,
        provider: str,
        model_name: str,
        top_k: int = 5,
        search_type: str = "db_search",
        vector_index: Optional[str] = None,
        embedding_provided: bool = False,
        verbose: bool = False,
        client_id: str = "",
        request_id: Optional[str] = None
    ) -> QueryLogEntry:
        """
        Create a new query log entry and set it as the current log.

        Args:
            question: The user's question
            provider: LLM provider (openai, anthropic, etc.)
            model_name: Model name being used
            top_k: Number of results to return
            search_type: Type of search (db_search, vector_search)
            vector_index: Vector index name if applicable
            embedding_provided: Whether an embedding was provided
            verbose: Verbose logging flag
            client_id: GDPR-compliant anonymized client identifier
            request_id: Optional pre-generated request ID

        Returns:
            QueryLogEntry: The created log entry
        """
        now = datetime.now(timezone.utc)
        log_entry = QueryLogEntry(
            request_id=request_id or self.generate_request_id(),
            timestamp=now.isoformat(),
            start_time=now.isoformat(),
            client_id=client_id,
            question=question,
            provider=provider,
            model_name=model_name,
            top_k=top_k,
            search_type=search_type,
            vector_index=vector_index,
            embedding_provided=embedding_provided,
            verbose=verbose,
            status="in_progress"
        )

        self.set_current_log(log_entry)
        self._log_event("query_started", {
            "request_id": log_entry.request_id,
            "question": question,
            "provider": provider,
            "model": model_name,
            "search_type": search_type
        })

        return log_entry

    def start_step(self, step_name: str, details: Optional[Dict[str, Any]] = None) -> StepLog:
        """
        Start a new step in the current query log.

        Args:
            step_name: Name of the step
            details: Additional details about the step

        Returns:
            StepLog: The created step log
        """
        log = self.get_current_log()
        if not log:
            return StepLog()

        now = datetime.now(timezone.utc)
        step = StepLog(
            step_name=step_name,
            step_number=len(log.steps) + 1,
            start_time=now.isoformat(),
            status="in_progress",
            details=details or {}
        )
        log.steps.append(step)

        self._log_event("step_started", {
            "request_id": log.request_id,
            "step_name": step_name,
            "step_number": step.step_number
        })

        return step

    def end_step(self, step: StepLog, status: str = "completed", error: Optional[Exception] = None):
        """
        End a step and record its completion.

        Args:
            step: The step log to end
            status: Final status (completed, failed)
            error: Optional exception if failed
        """
        now = datetime.now(timezone.utc)
        step.end_time = now.isoformat()
        step.status = status

        if step.start_time:
            start = datetime.fromisoformat(step.start_time)
            step.duration_ms = (now - start).total_seconds() * 1000

        if error:
            step.error = str(error)
            step.error_traceback = traceback.format_exc()

        log = self.get_current_log()
        if log:
            self._log_event("step_ended", {
                "request_id": log.request_id,
                "step_name": step.step_name,
                "status": status,
                "duration_ms": step.duration_ms,
                "error": step.error
            })

    def log_llm_call(self, llm_call: LLMCallLog):
        """Add an LLM call log to the current query log."""
        log = self.get_current_log()
        if log:
            log.llm_calls.append(llm_call)
            self._log_event("llm_call", {
                "request_id": log.request_id,
                "call_type": llm_call.call_type,
                "model": llm_call.model_name,
                "provider": llm_call.provider,
                "duration_ms": llm_call.duration_ms,
                "tokens": asdict(llm_call.token_usage) if llm_call.token_usage else None,
                "error": llm_call.error
            })

    def log_query_correction(self, correction_log: QueryCorrectionLog):
        """Add query correction log to the current query log."""
        log = self.get_current_log()
        if log:
            log.query_correction = correction_log
            self._log_event("query_correction", {
                "request_id": log.request_id,
                "success": correction_log.success,
                "corrections_count": len(correction_log.corrections),
                "duration_ms": correction_log.duration_ms,
                "failure_reason": correction_log.failure_reason
            })

    def log_neo4j_execution(self, execution_log: Neo4jExecutionLog):
        """Add Neo4j execution log to the current query log."""
        log = self.get_current_log()
        if log:
            log.neo4j_execution = execution_log
            self._log_event("neo4j_execution", {
                "request_id": log.request_id,
                "execution_time_ms": execution_log.execution_time_ms,
                "result_count": execution_log.result_count,
                "error": execution_log.error
            })

    def log_error(
        self,
        error: Exception,
        step: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Log an error with full context.

        Args:
            error: The exception that occurred
            step: The step where the error occurred
            context: Additional context about the error
        """
        log = self.get_current_log()
        if log:
            log.error = str(error)
            log.error_type = type(error).__name__
            log.error_traceback = traceback.format_exc()
            log.error_step = step
            log.status = "failed"

        self._log_event("error", {
            "request_id": log.request_id if log else None,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "error_step": step,
            "traceback": traceback.format_exc(),
            "context": context
        })

    def finalize_query_log(
        self,
        generated_query: Optional[str] = None,
        final_query: Optional[str] = None,
        natural_language_response: Optional[str] = None,
        status: str = "completed"
    ) -> Optional[QueryLogEntry]:
        """
        Finalize the current query log and write it to file.

        Args:
            generated_query: The generated Cypher query
            final_query: The final corrected query
            natural_language_response: The NL response
            status: Final status

        Returns:
            The finalized QueryLogEntry
        """
        log = self.get_current_log()
        if not log:
            return None

        now = datetime.now(timezone.utc)
        log.end_time = now.isoformat()
        log.status = status

        if log.start_time:
            start = datetime.fromisoformat(log.start_time)
            log.total_duration_ms = (now - start).total_seconds() * 1000

        if generated_query:
            log.generated_query = generated_query
        if final_query:
            log.final_query = final_query
        if natural_language_response:
            log.natural_language_response = natural_language_response

        # Write to JSON log file
        self._write_log_entry(log)

        # Optionally write detailed log to separate file
        self._write_detailed_log(log)

        self._log_event("query_completed", {
            "request_id": log.request_id,
            "status": status,
            "total_duration_ms": log.total_duration_ms,
            "llm_calls_count": len(log.llm_calls),
            "steps_count": len(log.steps)
        })

        self.clear_current_log()
        return log

    def _write_log_entry(self, log: QueryLogEntry):
        """Write a log entry to the JSON Lines file."""
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_file = os.path.join(STRUCTURED_LOGS_DIR, f"query_log_{today}.jsonl")

            # Convert dataclass to dict, handling nested dataclasses
            log_dict = self._dataclass_to_dict(log)

            with self._file_lock:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_dict, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logging.error(f"Failed to write structured log: {e}")

    def _write_detailed_log(self, log: QueryLogEntry):
        """Write detailed log to individual file for debugging."""
        try:
            log_file = os.path.join(DETAILED_LOGS_DIR, f"{log.request_id}.json")
            log_dict = self._dataclass_to_dict(log)

            with self._file_lock:
                with open(log_file, "w", encoding="utf-8") as f:
                    json.dump(log_dict, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logging.error(f"Failed to write detailed log: {e}")

    # Fields to exclude from logs (large/redundant data)
    _EXCLUDED_FIELDS = {"prompt", "prompt_template", "prompt_variables"}

    def _dataclass_to_dict(self, obj: Any) -> Any:
        """Convert dataclass and nested dataclasses to dict.

        Excludes large fields like 'prompt' and 'prompt_variables' to keep logs concise.
        """
        if hasattr(obj, "__dataclass_fields__"):
            return {
                k: self._dataclass_to_dict(v)
                for k, v in asdict(obj).items()
                if k not in self._EXCLUDED_FIELDS
            }
        elif isinstance(obj, list):
            return [self._dataclass_to_dict(item) for item in obj]
        elif isinstance(obj, dict):
            # Also filter excluded fields from nested dicts (converted from nested dataclasses)
            return {
                k: self._dataclass_to_dict(v)
                for k, v in obj.items()
                if k not in self._EXCLUDED_FIELDS
            }
        return obj

    def _log_event(self, event_type: str, data: Dict[str, Any]):
        """Log an event to the standard logger as well."""
        log_message = json.dumps({
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data
        }, default=str)
        logging.info(f"[STRUCTURED_LOG] {log_message}")


# Context managers for timing
@contextmanager
def timed_step(logger: StructuredLogger, step_name: str, details: Optional[Dict[str, Any]] = None):
    """
    Context manager for timing a step.

    Usage:
        with timed_step(logger, "query_generation", {"model": "gpt-4"}):
            # do work
    """
    step = logger.start_step(step_name, details)
    try:
        yield step
        logger.end_step(step, "completed")
    except Exception as e:
        logger.end_step(step, "failed", e)
        raise


@contextmanager
def timed_operation(operation_name: str):
    """
    Simple context manager for timing operations.
    Returns timing info to caller.

    Usage:
        with timed_operation("llm_call") as timing:
            # do work
        print(f"Took {timing['duration_ms']}ms")
    """
    timing = {
        "operation": operation_name,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": None,
        "duration_ms": 0.0
    }
    start = time()
    try:
        yield timing
    finally:
        end = time()
        timing["end_time"] = datetime.now(timezone.utc).isoformat()
        timing["duration_ms"] = (end - start) * 1000


# Singleton instance
_structured_logger: Optional[StructuredLogger] = None


def get_structured_logger() -> StructuredLogger:
    """Get the singleton StructuredLogger instance."""
    global _structured_logger
    if _structured_logger is None:
        _structured_logger = StructuredLogger()
    return _structured_logger


# Convenience functions
def create_query_log(**kwargs) -> QueryLogEntry:
    """Create a new query log entry."""
    return get_structured_logger().create_query_log(**kwargs)


def get_current_query_log() -> Optional[QueryLogEntry]:
    """Get the current query log."""
    return StructuredLogger.get_current_log()


def log_llm_call(llm_call: LLMCallLog):
    """Log an LLM call."""
    get_structured_logger().log_llm_call(llm_call)


def log_query_correction(correction_log: QueryCorrectionLog):
    """Log query correction."""
    get_structured_logger().log_query_correction(correction_log)


def log_neo4j_execution(execution_log: Neo4jExecutionLog):
    """Log Neo4j execution."""
    get_structured_logger().log_neo4j_execution(execution_log)


def log_error(error: Exception, step: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
    """Log an error."""
    get_structured_logger().log_error(error, step, context)


def finalize_query_log(**kwargs) -> Optional[QueryLogEntry]:
    """Finalize the current query log."""
    return get_structured_logger().finalize_query_log(**kwargs)
