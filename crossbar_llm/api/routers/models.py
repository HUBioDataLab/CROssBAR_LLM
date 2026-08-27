from fastapi import APIRouter

from crossbar_llm.agent_tools.config import ModelsConfig
from crossbar_llm.api.schemas.responses import ModelsResponse, ProviderModels

router = APIRouter(
    prefix="/models",
    tags=["models"],
)


@router.get("", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    """Expose the server-side model configuration so clients can populate their
    provider/model selectors from a single source of truth (models_config.yaml).
    """
    config = ModelsConfig()

    providers: dict[str, ProviderModels] = {}
    default_provider = ""
    default_model = ""

    # provider_aliases maps runtime name -> display name (e.g. "google_genai" -> "Google").
    for runtime_name, display_name in config.provider_aliases.items():
        provider_config = getattr(config, display_name, None)
        if provider_config is None:
            continue

        free_models = sorted(provider_config.free_models)
        providers[runtime_name] = ProviderModels(
            models=sorted(provider_config.models),
            free_models=free_models,
        )

        # Seed defaults from the first provider that offers a free model.
        if not default_provider and free_models:
            default_provider = runtime_name
            default_model = free_models[0]

    # Fallback: first provider/model if none exposed a free model.
    if not default_provider and providers:
        default_provider = next(iter(providers))
        default_model = providers[default_provider].models[0] if providers[default_provider].models else ""

    return ModelsResponse(
        providers=providers,
        default_provider=default_provider,
        default_model=default_model,
        supported_models_for_search=sorted(config.supported_models_for_search),
    )
