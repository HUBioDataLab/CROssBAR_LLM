import pytest

from crossbar_llm.agent_tools.entity_resolver import (
    EntityResolver,
    ToolSearchResult,
    ToolCandidate,
    ToolErrorResult,
)
from crossbar_llm.agent_tools.config import Neo4jConfig, LLMConfig
from crossbar_llm.agent_tools.neo4j_client import Neo4jClient
from crossbar_llm.agent_tools.prompt import ENTITY_RESOLUTION_TEMPLATE
from crossbar_llm.agent_tools.llm_factory import LLMFactory

from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain_core.messages import ToolMessage, AIMessage

from textwrap import dedent


@pytest.fixture
def fulltext_index_config_path(tmp_path):
    config_path = tmp_path / "fulltext_index_mappings.yaml"
    config_path.write_text(
        dedent(
            """
            Gene:
              index_name: GeneNames
              property_name: gene_symbol
              fulltext_analyzer: standard-no-stop-words
            Pathway:
              index_name: PathwayNames
              property_name: name
              fulltext_analyzer: english
            Protein:
              index_name: ProteinNames
              property_name: primary_protein_name
              fulltext_analyzer: english
            """
        ).strip()
    )
    return config_path


@pytest.fixture
def mock_entity_resolver(mocker, fulltext_index_config_path):
    fake_neo4j_client = mocker.MagicMock()
    return EntityResolver(
        neo4j_client=fake_neo4j_client,
        fulltext_index_config_path=fulltext_index_config_path,
    )

@pytest.fixture
def entity_resolver_integration():
    return EntityResolver(neo4j_client=Neo4jClient(Neo4jConfig()))


@pytest.fixture
def entity_resolution_llm():
    return LLMFactory(cfg=LLMConfig(model="gpt-5.4-mini", provider="openai")).create_entity_resolution_llm()

@pytest.fixture
def entity_resolution_prompt():
    return ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(ENTITY_RESOLUTION_TEMPLATE),
            HumanMessagePromptTemplate.from_template("User question: {question}"),
        ]
    )
    


def test_entity_search_tool_returns_candidates_payload(mock_entity_resolver):
    mock_entity_resolver.neo4j_client.fulltext_search.return_value = [
        {"name": "TP53", "score": 0.99, "rank": 1},
    ]

    result = mock_entity_resolver.entity_search_tool.invoke(
        {"node_type": "Gene", "entity_name": "TP53"}
    )

    mock_entity_resolver.neo4j_client.fulltext_search.assert_called_once_with("Gene", "TP53")
    
    assert result == {
        "candidates": [{"name": "TP53", "score": 0.99, "rank": 1}],
        "error": None,
    }


def test_entity_search_tool_returns_error_payload(mock_entity_resolver):
    mock_entity_resolver.neo4j_client.fulltext_search.return_value = "query failed"

    result = mock_entity_resolver.entity_search_tool.invoke(
        {"node_type": "Gene", "entity_name": "TP53"}
    )

    mock_entity_resolver.neo4j_client.fulltext_search.assert_called_once_with("Gene", "TP53")

    assert result == {
        "candidates": None,
        "error": "query failed",
    }


def test_run_entity_search_returns_tool_search_result(mock_entity_resolver, mocker):
    mock_entity_resolver.entity_search_tool = mocker.Mock()
    mock_entity_resolver.entity_search_tool.invoke.return_value = {
        "candidates": [
            {"name": "TP53", "score": 0.99, "rank": 1},
            {"name": "TP63", "score": 0.75, "rank": 2},
        ],
        "error": None,
    }

    result = mock_entity_resolver.run_entity_search("Gene", "TP53")

    assert isinstance(result, ToolSearchResult)
    assert result.candidates == [
        ToolCandidate(name="TP53", score=0.99, rank=1),
        ToolCandidate(name="TP63", score=0.75, rank=2),
    ]

@pytest.mark.parametrize(
    "tool_response",
    [
        "database offline",
        {"candidates": None, "error": "invalid fulltext query"},
    ],
)
def test_run_entity_search_returns_tool_error_result(mock_entity_resolver, mocker, tool_response):
    mock_entity_resolver.entity_search_tool = mocker.Mock()
    mock_entity_resolver.entity_search_tool.invoke.return_value = tool_response

    result = mock_entity_resolver.run_entity_search("Gene", "TP53")

    mock_entity_resolver.entity_search_tool.invoke.assert_called_once_with({"node_type": "Gene", "entity_name": "TP53"})

    assert isinstance(result, ToolErrorResult)
    assert result.entity_name == "TP53"
    assert result.node_type == "Gene"
    assert result.error == (tool_response if isinstance(tool_response, str) else tool_response["error"])


def test_run_entity_llm_stage_formats_messages_and_appends_prior_messages(mock_entity_resolver, mocker):
    prompt = mocker.MagicMock()
    llm = mocker.MagicMock()
    prompt.format_messages.return_value = ["system-message"]
    llm.invoke.return_value = "llm-response"

    result = mock_entity_resolver.run_entity_llm_stage(
        mode="resolution",
        question="Which protein is relevant?",
        extracted_entities='{"entities": []}',
        prior_messages=["prior-message"],
        llm=llm,
        prompt=prompt,
    )

    assert result == "llm-response"
    llm.invoke.assert_called_once_with(["system-message", "prior-message"])

def test_run_single_entity_tool_call_with_retry_returns_initial_success(mock_entity_resolver, mocker):
    search_result = ToolSearchResult(
        entity_name="TP/53",
        node_type="Gene",
        candidates=[ToolCandidate(name="TP53", score=0.99, rank=1)],
    )

    mocker.patch.object(mock_entity_resolver, "run_entity_search", return_value=search_result)
    mocker.patch.object(mock_entity_resolver, "run_entity_llm_stage")

    result = mock_entity_resolver.run_single_entity_tool_call_with_retry(
        tool_call={"id": "call-1", "args": {"node_type": "Gene", "entity_name": "TP/53"}},
        question="Find TP53",
        llm=mocker.MagicMock(),
        prompt=mocker.MagicMock(),
    )

    assert result.tool_args == {"node_type": "Gene", "entity_name": "TP53"}
    assert result.correction_attempts == 0
    assert result.was_corrected is False


def test_run_single_entity_tool_call_with_retry_repairs_failed_lookup(mock_entity_resolver, mocker):
    initial_error = ToolErrorResult(
        entity_name="TP/53",
        node_type="Gene",
        error="syntax error",
    )
    repaired_result = ToolSearchResult(
        entity_name="TP53",
        node_type="Gene",
        candidates=[ToolCandidate(name="TP53", score=0.99, rank=1)],
    )

    mocker.patch.object(
        mock_entity_resolver,
        "run_entity_search",
        side_effect=[initial_error, repaired_result],
    )
    mocker.patch.object(
        mock_entity_resolver,
        "run_entity_llm_stage",
        return_value=mocker.Mock(
            tool_calls=[{"id": "repair-1", "args": {"node_type": "Gene", "entity_name": "TP53"}}]
        ),
    )

    result = mock_entity_resolver.run_single_entity_tool_call_with_retry(
        tool_call={"id": "call-1", "args": {"node_type": "Gene", "entity_name": "TP/53"}},
        question="Find TP53",
        llm=mocker.MagicMock(),
        prompt=mocker.MagicMock(),
    )

    assert result.tool_args == {"node_type": "Gene", "entity_name": "TP53"}
    assert result.correction_attempts == 1
    assert result.was_corrected is True

def test_run_single_entity_tool_call_with_retry_stops_when_repair_returns_no_tool_calls(mock_entity_resolver, mocker):
    initial_error = ToolErrorResult(
        entity_name="TP53",
        node_type="Gene",
        error="not found",
    )

    mocker.patch.object(mock_entity_resolver, "run_entity_search", return_value=initial_error)
    mocker.patch.object(
        mock_entity_resolver,
        "run_entity_llm_stage",
        return_value=mocker.Mock(tool_calls=[]),
    )

    result = mock_entity_resolver.run_single_entity_tool_call_with_retry(
        tool_call={"id": "call-1", "args": {"node_type": "Gene", "entity_name": "TP53"}},
        question="Find TP53",
        llm=mocker.MagicMock(),
        prompt=mocker.MagicMock(),
    )

    assert result.tool_response is initial_error
    assert result.correction_attempts == 0
    assert result.was_corrected is False



@pytest.mark.integration
def test_entity_search_tool_integration_returns_payload(entity_resolver_integration):
    result = entity_resolver_integration.entity_search_tool.invoke(
        {"node_type": "Gene", "entity_name": "TP53"}
    )

    assert isinstance(result, dict)
    assert "candidates" in result
    assert "error" in result
    if result["error"] is None:
        assert isinstance(result["candidates"], list)
        first_candidate = result["candidates"][0]
        assert "name" in first_candidate
        assert "score" in first_candidate
        assert "rank" in first_candidate
    
    else:
        assert result["candidates"] is None
        assert isinstance(result["error"], str)

@pytest.mark.integration
def test_run_entity_search_integration_returns_typed_result(entity_resolver_integration):
    result = entity_resolver_integration.run_entity_search(
        node_type="Gene",
        entity_name="TP53",
    )

    assert isinstance(result, (ToolSearchResult, ToolErrorResult))

    if isinstance(result, ToolSearchResult):
        assert result.node_type == "Gene"
        assert result.entity_name == "TP53"
    else:
        assert isinstance(result.error, str)

@pytest.mark.integration
def test_run_entity_search_integration_handles_unknown_entity(entity_resolver_integration):
    result = entity_resolver_integration.run_entity_search(
        node_type="Gene",
        entity_name="THIS_ENTITY_SHOULD_NOT_EXIST_123456",
    )

    assert isinstance(result, (ToolSearchResult, ToolErrorResult))

    if isinstance(result, ToolSearchResult):
        assert result.is_empty is True
        assert result.candidates == []


@pytest.mark.integration
def test_run_single_entity_tool_call_with_retry_integration_db_only(entity_resolver_integration, mocker):
    mock_llm = mocker.MagicMock()
    mock_prompt = mocker.MagicMock()

    mocker.patch.object(
        entity_resolver_integration,
        "run_entity_llm_stage",
        return_value=mocker.Mock(
            tool_calls=[
                {
                    "id": "repair-1",
                    "args": {"node_type": "Gene", "entity_name": "TP53"},
                }
            ]
        ),
    )

    result = entity_resolver_integration.run_single_entity_tool_call_with_retry(
        tool_call={
            "id": "call-1",
            "args": {"node_type": "Gene", "entity_name": "TP/53"},
        },
        question="Find TP53",
        llm=mock_llm,
        prompt=mock_prompt,
    )

    assert result.tool_call_id == "call-1"
    assert result.tool_args["node_type"] == "Gene"
    assert isinstance(result.correction_attempts, int)


@pytest.mark.integration
def test_run_entity_llm_stage_integration(entity_resolver_integration, entity_resolution_llm, entity_resolution_prompt):
    
    prior_messages = [
        AIMessage(
            content="I will resolve the entity using the search tool.",
            tool_calls=[
                {
                    "id": "call-1",
                    "name": "entity_search_tool",
                    "args": {
                        "node_type": "Gene",
                        "entity_name": "TP53",
                    },
                }
            ],
        ),
        ToolMessage(
            tool_call_id="call-1",
            content=ToolSearchResult(
                entity_name="TP53",
                node_type="Gene",
                candidates=[
                    ToolCandidate(name="TP53", score=0.99, rank=1),
                    ToolCandidate(name="tp53", score=0.90, rank=2),
                    ToolCandidate(name="TP63", score=0.69, rank=3),
                ],
            ).model_dump_json(),
        ),
    ]

    result = entity_resolver_integration.run_entity_llm_stage(
        mode="resolution",
        question="Which genes are relevant for TP53 <Gene>?",
        extracted_entities='{"entities": [{"entity_string": "TP53", "node_type": "Gene", "resolved_name":null,"resolved_name_score":null,"resolved_name_order":null}]}',
        prior_messages=[*prior_messages],
        llm=entity_resolution_llm,
        prompt=entity_resolution_prompt,
    )

    assert result is not None
    assert result.entities is not None
    assert result.entities[0].entity_string == "TP53"
    assert result.entities[0].node_type == "Gene"
    assert result.entities[0].resolved_name is not None
    assert result.entities[0].resolved_name_score is not None
    assert result.entities[0].resolved_name_order is not None
