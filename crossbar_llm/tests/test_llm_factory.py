import pytest
from crossbar_llm.agent_tools.llm_factory import (
    ResolvedEntity,
    FollowUpQuestionStrategy,
    LLMFactory,
)

from crossbar_llm.agent_tools.config import (
    LLMConfig,
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











