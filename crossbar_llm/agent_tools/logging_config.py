import structlog # type: ignore
import logging
import time

from functools import wraps
from pathlib import Path

from pydantic import DirectoryPath, validate_call

from logging.handlers import RotatingFileHandler


def configure_logging(
    *,
    log_dir: Path = Path(__file__).parent / "logs",
    pipeline_version: str = "0.1.0",
    max_log_file_size: int = 50 * 1024 * 1024,
    backup_count: int = 3,
    session_id: str,
    app_logger_names: tuple[str, ...] = ("agent_tools",),
):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"session_{session_id}.jsonl"

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(ensure_ascii=False),
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.stdlib.add_logger_name,
        ],
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_log_file_size,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.WARNING)
    root_logger.addHandler(logging.NullHandler())

    for logger_name in app_logger_names:
        app_logger = logging.getLogger(logger_name)
        for handler in app_logger.handlers[:]:
            handler.close()
            app_logger.removeHandler(handler)
        app_logger.setLevel(logging.DEBUG)
        app_logger.addHandler(file_handler)
        app_logger.propagate = False

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.format_exc_info,
            structlog.processors.StackInfoRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    structlog.contextvars.bind_contextvars(
        session_id=session_id,
        pipeline_version=pipeline_version,
    )


def _clear_logging_handlers(logger: logging.Logger):
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

def _reset_logging_state(
        *,
        app_logger_names: tuple[str, ...] = ("agent_tools",),
        reset_root_logger: bool = True,
        root_level: int = logging.NOTSET,
        app_level: int = logging.NOTSET,
        app_propagate: bool = True,
        attach_root_null_handler: bool = True,
    ):

    structlog.contextvars.clear_contextvars()

    if reset_root_logger:
        root_logger = logging.getLogger()
        _clear_logging_handlers(root_logger)
        root_logger.setLevel(root_level)
        if attach_root_null_handler:
            root_logger.addHandler(logging.NullHandler())

    for logger_name in app_logger_names:
        app_logger = logging.getLogger(logger_name)
        _clear_logging_handlers(app_logger)
        app_logger.setLevel(app_level)
        app_logger.propagate = app_propagate

def reset_logging(
        *,
        app_logger_names: tuple[str, ...] = ("agent_tools",),
        reset_root_logger: bool = True,
    ):
    _reset_logging_state(
        app_logger_names=app_logger_names,
        reset_root_logger=reset_root_logger,
        root_level=logging.NOTSET,
        app_level=logging.NOTSET,
        app_propagate=True,
        attach_root_null_handler=True,
    )


def disable_logging(
        *,
        app_logger_names: tuple[str, ...] = ("agent_tools",),
        reset_root_logger: bool = True,
    ):
    _reset_logging_state(
        app_logger_names=app_logger_names,
        reset_root_logger=reset_root_logger,
        root_level=logging.CRITICAL,
        app_level=logging.CRITICAL,
        app_propagate=False,
        attach_root_null_handler=True,
    )

    for logger_name in app_logger_names:
        app_logger = logging.getLogger(logger_name)
        app_logger.disabled = True
    

    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

        
def get_logger(name: str):
    return structlog.get_logger(name)


def log_execution_time(logger, *, component: str, event_type: str = "timing"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_seconds = time.perf_counter() - start_time
                elapsed_ms = round(elapsed_seconds * 1000, 3)
                elapsed_s = round(elapsed_seconds, 3)
                elapsed_min = round(elapsed_seconds / 60, 3)
                logger.info(
                    f"{func.__name__} execution completed",
                    component=component,
                    event_type=event_type,
                    function_name=func.__name__,
                    elapsed_miliseconds=elapsed_ms,
                    elapsed_seconds=elapsed_s,
                    elapsed_minutes=elapsed_min,
                )
        return wrapper
    return decorator

@validate_call(validate_return=True)
def count_log_files(log_dir: DirectoryPath) -> int:
    return len(list(log_dir.glob("*.jsonl")))

@validate_call(validate_return=True)
def get_log_file_path(log_dir: DirectoryPath, session_id: str) -> Path:
    log_file = log_dir / f"session_{session_id}.jsonl"
    if not log_file.exists():
        raise FileNotFoundError(f"No log file found for session_id '{session_id}' in directory '{log_dir}'.")
    return Path(log_file).absolute()

@validate_call(validate_return=True)
def get_log_dir_size_as_megabytes(log_dir: DirectoryPath) -> float:
    total_size_bytes = sum(f.stat().st_size for f in log_dir.glob("*.jsonl") if f.is_file())
    return total_size_bytes / (1024 * 1024) # Convert to megabytes

@validate_call
def delete_log_files(log_dir: DirectoryPath) -> None:
    for log_file in log_dir.glob("*.jsonl"):
        if log_file.is_file():
            log_file.unlink()



    
