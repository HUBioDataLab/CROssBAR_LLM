import pytest
from pydantic import ValidationError
from crossbar_llm.agent_tools.config import (
    LLMConfig,
    ReasoningConfig, 
    ModelsConfig, 
    ProviderConfig, 
    FullTextIndexConfig, 
    FullTextIndexMappings,
    VectorMappings,
    VectorIndexConfig,
    APIKeyConfig,
)

@pytest.fixture
def mock_models_config():
    return ModelsConfig(
        OpenAI=ProviderConfig(models={"gpt-4", "gpt-3.5"}, free_models={"gpt-3.5"}),
        Anthropic=ProviderConfig(models={"claude-3"}, free_models=set()),
        Google=ProviderConfig(models=set(), free_models=set()),
        Groq=ProviderConfig(models=set(), free_models=set()),
        OpenRouter=ProviderConfig(models=set(), free_models=set()),
        Ollama=ProviderConfig(models=set(), free_models=set()),
        provider_aliases={"openai": "OpenAI", "anthropic": "Anthropic"},
        provider_to_api_key_attr={"OpenAI": "openai_api_key", "Anthropic": "anthropic_api_key"},
        supported_models_for_search={"gpt-4"}
    )

@pytest.fixture
def mock_full_text_index_mappings():
    return FullTextIndexMappings()

@pytest.fixture
def mock_vector_mappings():
    return VectorMappings()

def test_llm_config_splits_correctly():
    config = LLMConfig(model="openai:gpt-4", reasoning=ReasoningConfig())
    assert config.provider == "openai"
    assert config.model == "gpt-4"

def test_llm_config_multiple_colons_raises_error():
    with pytest.raises(ValidationError):
        LLMConfig(model="openai:gpt-4:extra", reasoning=ReasoningConfig())

def test_llm_config_conflict_raises_error():
    with pytest.raises(ValidationError):
        LLMConfig(model="openai:gpt-4", provider="anthropic", reasoning=ReasoningConfig())


def test_models_config_validate_provider_model(mock_models_config):

    # 1. Valid case
    assert mock_models_config.validate_provider_model("OpenAI", "gpt-5.4") is True

    # 3. Invalid model for provider
    with pytest.raises(ValueError) as excinfo:
        mock_models_config.validate_provider_model("OpenAI", "claude-3")
    assert "Model 'claude-3' not found under provider 'OpenAI'" in str(excinfo.value)

    # 4. Invalid provider
    with pytest.raises(ValueError) as excinfo:
        mock_models_config.validate_provider_model("UnknownProvider", "gpt-4")
    assert "Provider 'UnknownProvider' not found" in str(excinfo.value)

def test_models_config_get_provider_by_model(mock_models_config):

    assert mock_models_config.get_provider_by_model("gpt-5.4") == "openai"
    assert mock_models_config.get_provider_by_model("claude-haiku-4-5") == "anthropic"
    
    with pytest.raises(ValueError):
        mock_models_config.get_provider_by_model("non-existent-model")


def test_full_text_index_mappings_get_node_types(mock_full_text_index_mappings):
    assert mock_full_text_index_mappings.get_node_types() == {"SideEffect", "Gene", "GOTerm", "ProteinDomain", "SmallMolecule", "Pathway", "Protein", "Phenotype", "OrganismTaxon", "Disease", "EcNumber"}

def test_full_text_index_mappings_get_index_name_by_node_type(mock_full_text_index_mappings):
    assert mock_full_text_index_mappings.get_index_name_by_node_type("Gene") == "GeneNames"
    
    with pytest.raises(ValueError):
        mock_full_text_index_mappings.get_index_name_by_node_type("NonExistentNodeType")

def test_full_text_index_mappings_get_property_name_by_node_type(mock_full_text_index_mappings):
    assert mock_full_text_index_mappings.get_property_name_by_node_type("SideEffect") == "name"
    
    with pytest.raises(ValueError):
        mock_full_text_index_mappings.get_property_name_by_node_type("NonExistentNodeType")

def test_vector_mappings_index_name_to_vector_size(mock_vector_mappings):
    expected = {
        "SelformerEmbeddings": 768,
        "Anc2vecEmbeddings": 200,
        "CadaEmbeddings": 160,
        "Doc2vecEmbeddings": 100,
        "Dom2vecEmbeddings": 50,
        "Prott5Embeddings": 1024,
        "Esm2Embeddings": 1280,
        "RxnfpEmbeddings": 256,
        "BiokeenEmbeddings": 200,
        "NtEmbeddings": 2560,
    }
    assert mock_vector_mappings.index_name_to_vector_size() == expected


def test_api_key_config_get_api_key():
    config = APIKeyConfig(
        _env_file=None,
        OPENAI_API_KEY="test-openai-key",
        GROQ_API_KEY=None,
    )

    provider_to_api_key_attr = {
        "OpenAI": "openai_api_key",
        "Groq": "groq_api_key"
    }

    assert config.get_api_key("OpenAI", provider_to_api_key_attr).get_secret_value() == "test-openai-key"

    with pytest.raises(ValueError):
        config.get_api_key("UnknownProvider", provider_to_api_key_attr)

    with pytest.raises(ValueError):
        config.get_api_key("Groq", provider_to_api_key_attr)





