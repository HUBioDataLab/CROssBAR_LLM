"""
Configuration module for CROssBAR LLM backend.
Handles environment-specific settings.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Determine environment
ENV = os.getenv("CROSSBAR_ENV", "development").lower()
IS_PRODUCTION = ENV == "production"
IS_DEVELOPMENT = not IS_PRODUCTION

# Environment-specific settings
SETTINGS = {
    "csrf_enabled": IS_PRODUCTION,
    "rate_limiting_enabled": IS_PRODUCTION,
    "debug_logging": IS_DEVELOPMENT,
    # Rate limiting settings
    "rate_limits": {
        # Use a very large number in development mode instead of infinity
        # to avoid JSON serialization issues
        "minute": 6 if IS_PRODUCTION else 10000000,  # Requests per minute
        "hour": 20 if IS_PRODUCTION else 10000000,   # Requests per hour
        "day": 50 if IS_PRODUCTION else 10000000,    # Requests per day
    }
}

def get_setting(key, default=None):
    """Get a setting from the configuration."""
    return SETTINGS.get(key, default)
