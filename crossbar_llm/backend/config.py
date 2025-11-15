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
        "hour": 20 if IS_PRODUCTION else 10000000,  # Requests per hour
        "day": 50 if IS_PRODUCTION else 10000000,  # Requests per day
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

# Optional: known model-to-provider hints for backward compatibility
OPENAI_SPECIAL_MODELS = {
    "gpt-4.1",
    "o4-mini-latest",
    "o3-latest",
    "o3-mini-latest",
    "o1-latest",
    "o1-mini-latest",
    "o1-pro-latest",
}

# Heuristics for model to provider mapping (best effort)
# This should be used only as a fallback when provider is not supplied
MODEL_PROVIDER_RULES = [
    (lambda m: m.startswith("gpt") or m in OPENAI_SPECIAL_MODELS, "openai"),
    (lambda m: m.startswith("claude"), "anthropic"),
    (lambda m: m.startswith("gemini"), "google"),
    (lambda m: m.startswith("llama") or m.startswith("mixtral") or m.startswith("groq") or m.startswith("moonshotai") or m.startswith("meta-llama"), "groq"),
    (lambda m: m.startswith("meta/llama") or m.startswith("mistralai") or m.startswith("qwen") or m.startswith("deepseek-ai"), "nvidia"),
    (lambda m: m.startswith("deepseek"), "openrouter"),
]


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
    """Best-effort inference of provider from model name.
    Returns a provider identifier or None if not recognized.
    """
    if not model_name:
        return None
    name = model_name.strip()
    for predicate, provider in MODEL_PROVIDER_RULES:
        try:
            if predicate(name):
                return provider
        except Exception:
            continue
    return None


def get_api_keys_status() -> dict:
    """Return a mapping of provider display names to availability booleans."""
    status = {}
    for provider, env_var in PROVIDER_ENV_MAP.items():
        value = os.getenv(env_var, "")
        status[PROVIDER_DISPLAY_NAME.get(provider, provider)] = (
            value != "" and value != "default"
        )
    return status
