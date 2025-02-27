from timeit import default_timer as timer
import logging

def timer_func(func):
    def wrapper(*args, **kwargs):
        t1 = timer()
        logging.debug(f"Starting {func.__name__}()")
        result = func(*args, **kwargs)
        t2 = timer()
        execution_time = t2-t1
        logging.info(f'{func.__name__}() executed in {execution_time:.6f}s')
        return result
    return wrapper

class Logger:
    """
    Enhanced logging class that provides consistent logging across the backend
    with different verbosity levels.
    """
    
    @staticmethod
    def debug(message, *args, **kwargs):
        """Log detailed debugging information"""
        logging.debug(message, *args, **kwargs)
        
    @staticmethod
    def info(message, *args, **kwargs):
        """Log general information about application progress"""
        logging.info(message, *args, **kwargs)
        
    @staticmethod
    def warning(message, *args, **kwargs):
        """Log warnings that don't prevent the app from working"""
        logging.warning(message, *args, **kwargs)
        
    @staticmethod
    def error(message, *args, **kwargs):
        """Log errors that prevent functions from working properly"""
        logging.error(message, *args, **kwargs)
    
    @staticmethod
    def critical(message, *args, **kwargs):
        """Log critical errors that prevent the app from working properly"""
        logging.critical(message, *args, **kwargs)
