"""
Utility functions and classes for CROssBAR LLM backend.

This module provides:
- Enhanced Logger class with JSON formatting support
- Timing decorators with detailed metrics
- Context managers for operation tracking
"""

import functools
import json
import logging
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from timeit import default_timer as timer
from typing import Any, Callable, Dict, Optional, TypeVar, Union

# Type variable for generic function decoration
F = TypeVar('F', bound=Callable[..., Any])


def timer_func(func: F) -> F:
    """
    Decorator that times function execution and logs the duration.
    
    Logs at DEBUG level when starting, INFO level when completed.
    Includes function arguments in debug output.
    
    Args:
        func: Function to wrap
        
    Returns:
        Wrapped function with timing
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        start_time = datetime.now(timezone.utc)
        t1 = timer()
        
        # Log start with limited args info
        args_info = f"args_count={len(args)}, kwargs_keys={list(kwargs.keys())}"
        logging.debug(f"[TIMER_START] {func_name}() starting | {args_info}")
        
        try:
            result = func(*args, **kwargs)
            t2 = timer()
            execution_time = t2 - t1
            
            logging.info(
                f"[TIMER_END] {func_name}() completed | "
                f"duration={execution_time:.6f}s ({execution_time*1000:.2f}ms)"
            )
            
            return result
            
        except Exception as e:
            t2 = timer()
            execution_time = t2 - t1
            
            logging.error(
                f"[TIMER_ERROR] {func_name}() failed | "
                f"duration={execution_time:.6f}s | error={type(e).__name__}: {str(e)}"
            )
            raise
    
    return wrapper


def detailed_timer(
    log_args: bool = False,
    log_result: bool = False,
    log_level: int = logging.INFO
) -> Callable[[F], F]:
    """
    Enhanced timing decorator with configurable logging.
    
    Args:
        log_args: Whether to log function arguments
        log_result: Whether to log the return value
        log_level: Logging level for completion message
        
    Returns:
        Decorator function
    
    Example:
        @detailed_timer(log_args=True, log_result=True)
        def my_function(x, y):
            return x + y
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            start_time = datetime.now(timezone.utc)
            t1 = timer()
            
            log_data = {
                "function": func_name,
                "start_time": start_time.isoformat(),
            }
            
            if log_args:
                # Safely stringify args
                try:
                    log_data["args"] = [_safe_repr(a) for a in args]
                    log_data["kwargs"] = {k: _safe_repr(v) for k, v in kwargs.items()}
                except Exception:
                    log_data["args"] = f"<{len(args)} args>"
                    log_data["kwargs"] = f"<{len(kwargs)} kwargs>"
            
            logging.debug(f"[DETAILED_TIMER_START] {json.dumps(log_data, default=str)}")
            
            try:
                result = func(*args, **kwargs)
                t2 = timer()
                execution_time = t2 - t1
                
                log_data["duration_s"] = round(execution_time, 6)
                log_data["duration_ms"] = round(execution_time * 1000, 2)
                log_data["status"] = "success"
                log_data["end_time"] = datetime.now(timezone.utc).isoformat()
                
                if log_result:
                    log_data["result"] = _safe_repr(result)
                
                logging.log(log_level, f"[DETAILED_TIMER_END] {json.dumps(log_data, default=str)}")
                
                return result
                
            except Exception as e:
                t2 = timer()
                execution_time = t2 - t1
                
                log_data["duration_s"] = round(execution_time, 6)
                log_data["duration_ms"] = round(execution_time * 1000, 2)
                log_data["status"] = "error"
                log_data["error_type"] = type(e).__name__
                log_data["error_message"] = str(e)
                log_data["traceback"] = traceback.format_exc()
                log_data["end_time"] = datetime.now(timezone.utc).isoformat()
                
                logging.error(f"[DETAILED_TIMER_ERROR] {json.dumps(log_data, default=str)}")
                raise
        
        return wrapper
    return decorator


def _safe_repr(obj: Any, max_length: int = 200) -> str:
    """
    Safely get a string representation of an object.
    
    Args:
        obj: Object to represent
        max_length: Maximum length of representation
        
    Returns:
        String representation, truncated if necessary
    """
    try:
        if isinstance(obj, (str, int, float, bool, type(None))):
            repr_str = str(obj)
        elif isinstance(obj, (list, tuple)):
            repr_str = f"<{type(obj).__name__} len={len(obj)}>"
        elif isinstance(obj, dict):
            repr_str = f"<dict keys={list(obj.keys())[:5]}...>" if len(obj) > 5 else f"<dict keys={list(obj.keys())}>"
        elif hasattr(obj, "__class__"):
            repr_str = f"<{obj.__class__.__name__}>"
        else:
            repr_str = str(type(obj))
        
        if len(repr_str) > max_length:
            return repr_str[:max_length] + "..."
        return repr_str
    except Exception:
        return "<unrepresentable>"


@contextmanager
def timed_block(block_name: str, log_level: int = logging.INFO):
    """
    Context manager for timing a block of code.
    
    Args:
        block_name: Name for the block being timed
        log_level: Logging level for messages
        
    Example:
        with timed_block("database_query"):
            # do work
    """
    start_time = datetime.now(timezone.utc)
    t1 = timer()
    
    logging.debug(f"[BLOCK_START] {block_name} | start_time={start_time.isoformat()}")
    
    try:
        yield
        t2 = timer()
        duration = t2 - t1
        logging.log(
            log_level,
            f"[BLOCK_END] {block_name} | duration={duration:.6f}s ({duration*1000:.2f}ms)"
        )
    except Exception as e:
        t2 = timer()
        duration = t2 - t1
        logging.error(
            f"[BLOCK_ERROR] {block_name} | duration={duration:.6f}s | "
            f"error={type(e).__name__}: {str(e)}"
        )
        raise


class Logger:
    """
    Enhanced logging class that provides consistent logging across the backend
    with different verbosity levels and JSON formatting support.
    
    Features:
    - Standard log levels (debug, info, warning, error, critical)
    - JSON-formatted logging for structured data
    - Exception logging with full traceback
    - Context-aware logging with extra data
    """
    
    @staticmethod
    def debug(message: str, *args, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Log detailed debugging information.
        
        Args:
            message: Log message
            extra: Optional extra data to include
        """
        if extra:
            message = f"{message} | extra={json.dumps(extra, default=str)}"
        logging.debug(message, *args, **kwargs)
    
    @staticmethod
    def info(message: str, *args, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Log general information about application progress.
        
        Args:
            message: Log message
            extra: Optional extra data to include
        """
        if extra:
            message = f"{message} | extra={json.dumps(extra, default=str)}"
        logging.info(message, *args, **kwargs)
    
    @staticmethod
    def warning(message: str, *args, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Log warnings that don't prevent the app from working.
        
        Args:
            message: Log message
            extra: Optional extra data to include
        """
        if extra:
            message = f"{message} | extra={json.dumps(extra, default=str)}"
        logging.warning(message, *args, **kwargs)
    
    @staticmethod
    def error(
        message: str,
        *args,
        exc_info: bool = False,
        extra: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Log errors that prevent functions from working properly.
        
        Args:
            message: Log message
            exc_info: Whether to include exception info
            extra: Optional extra data to include
        """
        if extra:
            message = f"{message} | extra={json.dumps(extra, default=str)}"
        logging.error(message, *args, exc_info=exc_info, **kwargs)
    
    @staticmethod
    def critical(
        message: str,
        *args,
        exc_info: bool = False,
        extra: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Log critical errors that prevent the app from working properly.
        
        Args:
            message: Log message
            exc_info: Whether to include exception info
            extra: Optional extra data to include
        """
        if extra:
            message = f"{message} | extra={json.dumps(extra, default=str)}"
        logging.critical(message, *args, exc_info=exc_info, **kwargs)
    
    @staticmethod
    def exception(
        message: str,
        *args,
        exc: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Log an exception with full traceback.
        
        Args:
            message: Log message
            exc: Optional exception object
            context: Optional context information
        """
        log_data = {
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        if exc:
            log_data["error_type"] = type(exc).__name__
            log_data["error_message"] = str(exc)
            log_data["traceback"] = traceback.format_exc()
        
        if context:
            log_data["context"] = context
        
        logging.error(f"[EXCEPTION] {json.dumps(log_data, default=str)}", *args, **kwargs)
    
    @staticmethod
    def json(
        level: int,
        event: str,
        data: Dict[str, Any],
        **kwargs
    ):
        """
        Log a JSON-formatted message.
        
        Args:
            level: Logging level
            event: Event name/type
            data: Data to log as JSON
        """
        log_entry = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data
        }
        logging.log(level, f"[JSON_LOG] {json.dumps(log_entry, default=str)}", **kwargs)
    
    @staticmethod
    def structured(
        level: int,
        message: str,
        **fields
    ):
        """
        Log a structured message with key-value pairs.
        
        Args:
            level: Logging level
            message: Base message
            **fields: Key-value pairs to include
        """
        fields_str = " | ".join(f"{k}={_safe_repr(v)}" for k, v in fields.items())
        if fields_str:
            message = f"{message} | {fields_str}"
        logging.log(level, message)
    
    @classmethod
    def step(cls, step_name: str, step_number: int, status: str = "started", **details):
        """
        Log a pipeline step.
        
        Args:
            step_name: Name of the step
            step_number: Step number in sequence
            status: Step status (started, completed, failed)
            **details: Additional details
        """
        log_data = {
            "step_name": step_name,
            "step_number": step_number,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **details
        }
        
        if status == "failed":
            logging.error(f"[STEP] {json.dumps(log_data, default=str)}")
        else:
            logging.info(f"[STEP] {json.dumps(log_data, default=str)}")
    
    @classmethod
    def llm_interaction(
        cls,
        action: str,
        model: str,
        provider: str,
        **details
    ):
        """
        Log an LLM interaction.
        
        Args:
            action: Action type (call_start, call_end, error)
            model: Model name
            provider: Provider name
            **details: Additional details
        """
        log_data = {
            "action": action,
            "model": model,
            "provider": provider,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **details
        }
        logging.info(f"[LLM] {json.dumps(log_data, default=str)}")
    
    @classmethod
    def query_event(cls, event: str, **details):
        """
        Log a query processing event.
        
        Args:
            event: Event type
            **details: Event details
        """
        log_data = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **details
        }
        logging.info(f"[QUERY] {json.dumps(log_data, default=str)}")
