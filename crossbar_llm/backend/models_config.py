MODELS_CONFIG = {
    "OpenAI": [
        "gpt-4.1",
        "o4-mini-latest",
        "o3-latest",
        "o3-mini-latest",
        "o1-latest",
        "o1-mini-latest",
        "o1-pro-latest",
    ],
    "Anthropic": [
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-opus-4-1",
    ],
    "Google": [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ],
    "Groq": [
        "llama-3.3-70b-versatile",
        "deepseek-r1-distill-llama-70b",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "moonshotai/kimi-k2-instruct",
        "groq/compound",
        "groq/compound-mini",
    ],
    "Nvidia": [
        "meta/llama-3.1-405b-instruct",
        "meta/llama-3.1-70b-instruct",
        "meta/llama-3.1-8b-instruct",
        "meta/llama-4-maverick-17b-128e-instruct",
        "meta/llama-4-scout-17b-16e-instruct",
        "mistralai/mixtral-8x22b-instruct-v0.1",
        "qwen/qwen3-235b-a22b",
        "moonshotai/kimi-k2-instruct",
        "deepseek-ai/deepseek-r1",
    ],
    "OpenRouter": [
        "deepseek/deepseek-r1-distill-llama-70b",
        "deepseek/deepseek-r1:free",
        "deepseek/deepseek-r1",
        "deepseek/deepseek-chat",
        "qwen/qwen3-235b-a22b-2507",
        "moonshotai/kimi-k2",
        "x-ai/grok-4",
        "x-ai/grok-3",
        "tencent/hunyuan-a13b-instruct",
    ],
    "Ollama": [
        "codestral:latest",
        "llama3:instruct",
        "tomasonjo/codestral-text2cypher:latest",
        "tomasonjo/llama3-text2cypher-demo:latest",
        "llama3.1:8b",
        "qwen2:7b-instruct",
        "gemma2:latest",
    ],
}


def get_all_models():
    """
    Get all model configurations.
    Returns a dictionary with provider names as keys and model lists as values.
    """
    return MODELS_CONFIG


def get_models_by_provider(provider: str):
    """
    Get models for a specific provider.
    
    Args:
        provider: The provider name (case-insensitive)
    
    Returns:
        List of model names for the provider, or empty list if not found
    """
    for key, models in MODELS_CONFIG.items():
        if key.lower() == provider.lower():
            return models
    return []


def get_all_model_names():
    """
    Get a flat list of all model names across all providers.
    
    Returns:
        List of all model names
    """
    all_models = []
    for models in MODELS_CONFIG.values():
        all_models.extend(models)
    return all_models


def get_provider_for_model_name(model_name: str):
    """
    Find which provider a model belongs to.
    
    Args:
        model_name: The model name to search for
    
    Returns:
        Provider name if found, None otherwise
    """
    for provider, models in MODELS_CONFIG.items():
        if model_name in models:
            return provider
    return None

