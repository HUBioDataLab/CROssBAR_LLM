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

# Rate limit: enforced by default. Set CROSSBAR_RATE_LIMIT=false or 0 to disable.
_rate_limit_env = os.getenv("CROSSBAR_RATE_LIMIT", "").lower()
RATE_LIMITING_ENABLED = _rate_limit_env not in ("false", "0")

# Environment-specific settings
SETTINGS = {
    "csrf_enabled": IS_PRODUCTION,
    "rate_limiting_enabled": RATE_LIMITING_ENABLED,
    "debug_logging": IS_DEVELOPMENT,
    # Rate limiting settings
    "rate_limits": {
        # Use production limits when rate limiting is enabled; otherwise use
        # very large numbers (instead of infinity) to avoid JSON serialization issues
        "minute": 6 if RATE_LIMITING_ENABLED else 10000000,  # Requests per minute
        "hour": 20 if RATE_LIMITING_ENABLED else 10000000,  # Requests per hour
        "day": 50 if RATE_LIMITING_ENABLED else 10000000,  # Requests per day
    },
}

# Centralized provider configuration
# Keys are provider identifiers expected from the client/backend logic
PROVIDER_ENV_MAP = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Human-friendly display names for responses
PROVIDER_DISPLAY_NAME = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "groq": "Groq",
    "nvidia": "Nvidia",
    "openrouter": "OpenRouter",
}

PRODUCTION_FREE_ENV_MODELS = {
    "gpt-5-mini",
    "gemini-3-flash-preview",
}


def get_setting(key, default=None):
    """Get a setting from the configuration."""
    return SETTINGS.get(key, default)


def get_provider_env_var(provider: str) -> str | None:
    """Return the environment variable name for a given provider identifier.
    Provider matching is case-insensitive.
    """
    if not provider:
        return None
    key = provider.lower().strip()
    return PROVIDER_ENV_MAP.get(key)


def get_provider_for_model(model_name: str) -> str | None:
    """Determine provider from model name using centralized configuration.
    Returns a provider identifier or None if not recognized.
    """
    if not model_name:
        return None

    from models_config import get_provider_for_model_name

    display_name = get_provider_for_model_name(model_name)
    if not display_name:
        return None

    display_to_provider = {
        "OpenAI": "openai",
        "Anthropic": "anthropic",
        "Google": "google",
        "Groq": "groq",
        "Nvidia": "nvidia",
        "OpenRouter": "openrouter",
        "Ollama": "ollama",
    }

    return display_to_provider.get(display_name)


def get_api_keys_status() -> dict:
    """Return a mapping of provider display names to availability booleans."""
    status = {}
    for provider, env_var in PROVIDER_ENV_MAP.items():
        value = os.getenv(env_var, "")
        status[PROVIDER_DISPLAY_NAME.get(provider, provider)] = (
            value != "" and value != "default"
        )
    return status


def is_env_model_allowed(model_name: str) -> bool:
    """Return whether a model is allowed with api_key='env' in this environment."""
    if not model_name:
        return False
    if IS_DEVELOPMENT:
        return True
    return model_name in PRODUCTION_FREE_ENV_MODELS
