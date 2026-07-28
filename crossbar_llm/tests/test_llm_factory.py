import pytest
from crossbar_llm.agent_tools.llm_factory import (
    ResolvedEntity,
    FollowUpQuestionStrategy,
    LLMFactory
)

from crossbar_llm.agent_tools.config import (
    LLMConfig,
    ReasoningConfig
)

from langchain.chat_models import BaseChatModel


@pytest.fixture
def mock_llm_factory(request):
    model = getattr(request, "param", "gpt-5.4")
    return LLMFactory(
        cfg=LLMConfig(model=model)
    )


@pytest.mark.parametrize("resolved_entity", [
    ResolvedEntity(
        entity_string="psoriasis",
        node_type="Disease",
        resolved_name="Null",
    ),
    ResolvedEntity(
        entity_string="psoriasis",
        node_type="Disease",
        resolved_name="none",
    ),
    ResolvedEntity(
        entity_string="psoriasis",
        node_type="Disease",
        resolved_name="   ",
    ),
])

def test_resolved_entity_normalizes_none_like_strings(resolved_entity : ResolvedEntity):
    assert resolved_entity.resolved_name is None


def test_follow_up_question_strategy_to_list():
    strategy = FollowUpQuestionStrategy(
        question_1="Q1",
        question_2="Q2",
        question_3="Q3"
    )

    assert strategy.to_list() == ["Q1", "Q2", "Q3"]

def test_apply_reasoning_disabled_returns_kwargs_unchanged():
    factory = LLMFactory(
        cfg=LLMConfig(
            model="gpt-5.4",
            reasoning=ReasoningConfig(enabled=False),
        )
    )

    kwargs = {
        "model": "gpt-5.4",
        "model_provider": "openai",
        "temperature": 1.0,
    }

    result = factory._apply_reasoning("openai", kwargs)
    
    assert result == kwargs

def test_apply_reasoning_openai_adds_reasoning_kwargs():
    factory = LLMFactory(
        cfg=LLMConfig(
            model="gpt-5.4",
            reasoning=ReasoningConfig(
                enabled=True,
                effort="medium",
                openai_reasoning_summary="detailed",
                use_responses_api=True,
            ),
        )
    )

    kwargs = {
        "model": "gpt-5.4",
        "model_provider": "openai",
        "temperature": 1.0,
    }

    result = factory._apply_reasoning("openai", kwargs)

    assert result["use_responses_api"] is True
    assert result["reasoning"] == {
        "effort": "medium",
        "summary": "detailed",
    }

    assert kwargs == {
        "model": "gpt-5.4",
        "model_provider": "openai",
        "temperature": 1.0,
    }

def test_apply_reasoning_anthropic_adds_reasoning_kwargs():
    factory = LLMFactory(
        cfg=LLMConfig(
            model="claude-haiku-4-5",
            reasoning=ReasoningConfig(
                enabled=True,
                effort="high",
                anthropic_thinking_type="enabled",
                budget_tokens=2048,
            ),
        )
    )

    kwargs = {
        "model": "claude-haiku-4-5",
        "model_provider": "anthropic",
    }

    result = factory._apply_reasoning("anthropic", kwargs)

    assert result["thinking"] == {
        "type": "enabled",
        "budget_tokens": 2048,
    }

def test_apply_reasoning_google_genai_adds_reasoning_kwargs():
    factory = LLMFactory(
        cfg=LLMConfig(
            model="gemini-3-pro-preview",
            reasoning=ReasoningConfig(
                enabled=True,
                effort="low",
                include_thoughts=True,
            ),
        )
    )

    kwargs = {
        "model": "gemini-3-pro-preview",
        "model_provider": "google_genai",
    }

    result = factory._apply_reasoning("google_genai", kwargs)

    assert result["thinking_level"] == "low"
    assert result["include_thoughts"] is True

def test_apply_reasoning_openrouter_adds_reasoning_kwargs():
    factory = LLMFactory(
        cfg=LLMConfig(
            model="deepseek/deepseek-v4-flash",
            reasoning=ReasoningConfig(
                enabled=True,
                effort="medium",
            ),
        )
    )

    kwargs = {
        "model": "deepseek/deepseek-v4-flash",
        "model_provider": "openrouter",
    }

    result = factory._apply_reasoning("openrouter", kwargs)

    assert result["reasoning"] == {
        "effort": "medium",
    }

def test_apply_reasoning_groq_adds_reasoning_kwargs():
    factory = LLMFactory(
        cfg=LLMConfig(
            model="llama-3.3-70b-versatile",
            provider="groq",
            reasoning=ReasoningConfig(
                enabled=True,
                effort="medium",
                include_reasoning=True,
            ),
        )
    )

    kwargs = {
        "model": "llama-3.3-70b-versatile",
        "model_provider": "groq",
    }

    result = factory._apply_reasoning("groq", kwargs)

    assert result["include_reasoning"] is True

def test_apply_reasoning_unsupported_provider_raises_error():
    factory = LLMFactory(
        cfg=LLMConfig(
            model="gpt-5.4",
            reasoning=ReasoningConfig(
                enabled=True,
                effort="medium",
            ),
        )
    )

    kwargs = {
        "model": "gpt-5.4",
        "model_provider": "unsupported_provider",
    }

    with pytest.raises(ValueError) as excinfo:
        factory._apply_reasoning("unsupported_provider", kwargs)

    assert "Provider 'unsupported_provider' is not supported." in str(excinfo.value)


@pytest.mark.integration
def test_get_base_model_integrity(mock_llm_factory):
    llm = mock_llm_factory.get_base_model()
    assert isinstance(llm, BaseChatModel)

@pytest.mark.integration
def test_create_cypher_llm_integrity(mock_llm_factory):
    llm = mock_llm_factory.create_cypher_llm()
    assert llm is not None
    assert "CypherStrategy" in str(llm)

@pytest.mark.integration
def test_create_output_parser_llm_integrity(mock_llm_factory):
    llm = mock_llm_factory.create_output_parser_llm()
    assert llm is not None
    assert "OutputParserStrategy" in str(llm)

@pytest.mark.parametrize("mock_llm_factory", ["gpt-5.1", "gemini-3-pro-preview"], indirect=True)
@pytest.mark.integration
def test_create_web_search_llm_integrity(mock_llm_factory):
    llm = mock_llm_factory.create_web_search_llm()
    assert llm is not None
    assert "CypherStrategy" in str(llm)

@pytest.mark.integration
def test_create_web_search_llm_invalid_model(mock_llm_factory):
    with pytest.raises(ValueError):
        mock_llm_factory.create_web_search_llm(model="unsupported-model")

@pytest.mark.integration
def test_create_entity_resolution_llm_integrity(mock_llm_factory):
    llm = mock_llm_factory.create_entity_resolution_llm()
    assert llm is not None
    assert "EntityResolutionStrategy" in str(llm)

@pytest.mark.integration
def test_create_entity_resolution_llm_with_tools_integrity(mock_llm_factory):
    def dummy_tool(input: str) -> str:
        return f"Processed {input}"
    
    llm = mock_llm_factory.create_entity_resolution_llm_with_tools(tools=[dummy_tool])
    assert llm is not None
    assert "dummy_tool" in str(llm)

@pytest.mark.integration
def test_create_follow_up_question_llm_integrity(mock_llm_factory):
    llm = mock_llm_factory.create_follow_up_question_llm()
    assert llm is not None
    assert "FollowUpQuestionStrategy" in str(llm)











