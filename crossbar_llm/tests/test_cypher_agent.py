import pytest

import numpy as np

from copy import deepcopy
from types import SimpleNamespace
from textwrap import dedent

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from crossbar_llm.agent_tools.cypher_agent import CypherAgent, handle_embedding
from crossbar_llm.agent_tools.config import LLMConfig, Neo4jConfig
from crossbar_llm.agent_tools.entity_resolver import EntityResolver
from crossbar_llm.agent_tools.llm_factory import (
    BiologicalRelevanceValidatorStrategy,
    EntityResolutionStrategy,
    FollowUpQuestionStrategy,
    ResolvedEntity,
)


def patch_agent_config(mocker, **overrides):
    defaults = {
        "max_iterations": 3,
        "enable_web_search": False,
        "enable_entity_resolution": True,
        "web_search_model": "gpt-5.1",
        "biological_relevance_validation_model": "gpt-5.4-nano",
        "keep_last_n_messages": 24,
    }
    defaults.update(overrides)
    return mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.AgentConfig",
        return_value=SimpleNamespace(**defaults),
    )


def make_attempt(**overrides):
    attempt = {
        "attempt_number": 1,
        "cypher_query": "MATCH (n) RETURN n",
        "is_valid": False,
        "syntax_valid": False,
        "schema_valid": False,
        "property_valid": False,
        "syntax_errors": ["Syntax error"],
        "schema_errors": ["Schema error"],
        "property_errors": ["Property error"],
        "execution_ok": False,
        "execution_error": None,
        "attempt_source": "generation",
    }
    attempt.update(overrides)
    return attempt


@pytest.fixture
def mock_llm_config():
    return LLMConfig(
        model="gpt-5.1",
        provider="openai",
        temperature=0.0,
        timeout=60,
        max_retries=2,
    )


@pytest.fixture
def llm_config_integration():
    return LLMConfig(
        model="gpt-5.1",
        provider="openai",
        temperature=0.0,
        timeout=60,
        max_retries=2,
    )


@pytest.fixture
def mock_neo4j_config():
    return Neo4jConfig(
        neo4j_usr="neo4j",
        neo4j_password="password",
        neo4j_db_name="neo4j",
        neo4j_uri="bolt://localhost:7687",
    )


@pytest.fixture
def neo4j_config_integration():
    return Neo4jConfig()


@pytest.fixture
def vector_index_config_path(tmp_path):
    config_path = tmp_path / "vector_mappings.yaml"
    config_path.write_text(
        dedent(
        """
        Anc2vecEmbeddings:
          index_name: Anc2vecEmbeddings
          property_name: embedding
          vector_size: 3
        """.strip())
    )
    return config_path


@pytest.fixture
def mock_entity_resolver(mocker):
    entity_resolver = mocker.MagicMock(spec=EntityResolver)
    entity_resolver.entity_search_tool = mocker.MagicMock(name="entity_search_tool")
    return entity_resolver


@pytest.fixture
def mock_llm_factory(mocker):
    llm_factory = mocker.MagicMock()
    methods = [
        "create_cypher_llm",
        "create_web_search_llm",
        "create_output_parser_llm",
        "create_entity_resolution_llm",
        "create_entity_resolution_llm_with_tools",
        "create_follow_up_question_llm",
        "create_biological_relevance_validator_llm",
    ]
    for method in methods:
        getattr(llm_factory, method).return_value = mocker.MagicMock()

    mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.LLMFactory",
        return_value=llm_factory,
    )
    return llm_factory


@pytest.fixture
def mock_neo4j_client_cls(mocker):
    neo4j_client = mocker.MagicMock()
    neo4j_client.create_graph_schema_variables.return_value = {
        "nodes": [{"labels": ["Gene"]}, {"labels": ["Disease"]}],
        "node_properties": [
            {"labels": "Gene", "properties": [{"property": "gene_symbol", "type": "STRING"}]},
            {"labels": "Disease", "properties": [{"property": "name", "type": "STRING"}]},
        ],
        "edges": ["(:Gene)-[:Gene_is_related_to_disease]->(:Disease)"],
        "edge_properties": [
            {"type": "Gene_is_related_to_disease", "properties": [{"property": "reference", "type": "STRING"}]}
        ],
    }
    neo4j_client.get_db_version.return_value = "5.22.0"
    neo4j_client.execute_query.return_value = [{"gene_symbol": "TP53"}]

    return mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.Neo4jClient",
        return_value=neo4j_client,
    )


@pytest.fixture
def mock_cypher_agent(
    mock_llm_config,
    mock_neo4j_config,
    mock_entity_resolver,
    mock_llm_factory,
    mock_neo4j_client_cls,
    vector_index_config_path,
):
    return CypherAgent(
        llm_config=mock_llm_config,
        neo4j_config=mock_neo4j_config,
        entity_resolver=mock_entity_resolver,
        vector_index_config_path=vector_index_config_path,
    )


@pytest.fixture
def cypher_agent_integration_fixture(
    llm_config_integration,
    neo4j_config_integration,
    mock_entity_resolver,
    mock_llm_factory,
    mock_neo4j_client_cls,
    vector_index_config_path,
):
    return CypherAgent(
        llm_config=llm_config_integration,
        neo4j_config=neo4j_config_integration,
        entity_resolver=mock_entity_resolver,
        vector_index_config_path=vector_index_config_path,
    )


@pytest.fixture
def base_state():
    return {
        "question": "Which genes are related to psoriasis?",
        "resolved_entities": None,
        "current_cypher": "MATCH (n) RETURN n",
        "retry_count": 0,
        "cypher_mode": "db_search",
        "vector_index": None,
        "embedding": None,
        "is_ok": False,
        "cypher_attempts": [],
        "cypher_source": "generation",
        "execution_result": None,
        "final_answer": None,
        "use_web_search": False,
        "web_search_result": None,
        "follow_up_questions": None,
        "execution_control": "generate_and_run",
        "human_review_action": "approve",
        "biological_relevance": True,
        "messages": [],
    }


def test_route_after_biological_relevance_validation_returns_end(mock_cypher_agent, base_state):
    state = deepcopy(base_state)
    state["biological_relevance"] = False
    assert mock_cypher_agent.route_after_biological_relevance_validation(state) == "end"


def test_route_after_biological_relevance_validation_returns_entity_resolution(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, enable_entity_resolution=True)
    state = deepcopy(base_state)
    state["biological_relevance"] = True
    assert mock_cypher_agent.route_after_biological_relevance_validation(state) == "entity_resolution"


def test_route_after_biological_relevance_validation_returns_generate_cypher(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, enable_entity_resolution=False)
    state = deepcopy(base_state)
    state["biological_relevance"] = True
    assert mock_cypher_agent.route_after_biological_relevance_validation(state) == "generate_cypher"


def test_route_after_validate_returns_execute_cypher(mock_cypher_agent, base_state):
    state = deepcopy(base_state)
    state["cypher_attempts"] = [make_attempt(is_valid=True)]
    state["execution_control"] = "generate_and_run"
    assert mock_cypher_agent.route_after_validate(state) == "execute_cypher"


def test_route_after_validate_returns_human_review(mock_cypher_agent, base_state):
    state = deepcopy(base_state)
    state["cypher_attempts"] = [make_attempt(is_valid=True)]
    state["execution_control"] = "generate"
    assert mock_cypher_agent.route_after_validate(state) == "human_review"


def test_route_after_validate_returns_retry(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, max_iterations=3, enable_web_search=False)
    state = deepcopy(base_state)
    state["retry_count"] = 1
    state["cypher_attempts"] = [make_attempt(is_valid=False)]
    assert mock_cypher_agent.route_after_validate(state) == "retry"


def test_route_after_validate_returns_web_search(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, max_iterations=1, enable_web_search=True)
    state = deepcopy(base_state)
    state["retry_count"] = 1
    state["use_web_search"] = False
    state["cypher_attempts"] = [make_attempt(is_valid=False)]
    assert mock_cypher_agent.route_after_validate(state) == "web_search"


def test_route_after_validate_returns_fail(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, max_iterations=1, enable_web_search=False)
    state = deepcopy(base_state)
    state["retry_count"] = 1
    state["cypher_attempts"] = [make_attempt(is_valid=False)]
    assert mock_cypher_agent.route_after_validate(state) == "fail"


def test_route_after_execution_returns_answer(mock_cypher_agent, base_state):
    state = deepcopy(base_state)
    state["is_ok"] = True
    assert mock_cypher_agent.route_after_execution(state) == "answer"


def test_route_after_execution_returns_retry(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, max_iterations=2, enable_web_search=False)
    state = deepcopy(base_state)
    state["retry_count"] = 1
    state["is_ok"] = False
    assert mock_cypher_agent.route_after_execution(state) == "retry"


def test_route_after_execution_returns_web_search(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, max_iterations=1, enable_web_search=True)
    state = deepcopy(base_state)
    state["retry_count"] = 1
    state["use_web_search"] = False
    state["is_ok"] = False
    assert mock_cypher_agent.route_after_execution(state) == "web_search"


def test_route_after_execution_returns_fail(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, max_iterations=1, enable_web_search=False)
    state = deepcopy(base_state)
    state["retry_count"] = 1
    state["is_ok"] = False
    assert mock_cypher_agent.route_after_execution(state) == "fail"


def test_trim_messages_returns_combined_messages_under_limit(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, keep_last_n_messages=5)
    state = deepcopy(base_state)
    state["messages"] = [HumanMessage(content="old-1"), AIMessage(content="old-2")]
    new_messages = [AIMessage(content="new-1")]

    result = mock_cypher_agent.trim_messages(state, new_messages)

    assert result == state["messages"] + new_messages


def test_trim_messages_returns_remove_message_and_last_messages_over_limit(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, keep_last_n_messages=2)
    state = deepcopy(base_state)
    state["messages"] = [HumanMessage(content="old-1"), AIMessage(content="old-2")]
    new_messages = [AIMessage(content="new-1")]

    result = mock_cypher_agent.trim_messages(state, new_messages)

    assert isinstance(result[0], RemoveMessage)
    assert result[0].id == REMOVE_ALL_MESSAGES
    assert result[1].content == "old-2"
    assert result[2].content == "new-1"


def test_biological_relevance_validation_node_with_relevant_question(mock_cypher_agent, base_state):
    mock_cypher_agent.llm_factory.create_biological_relevance_validator_llm.return_value.invoke.return_value = {
        "parsed": BiologicalRelevanceValidatorStrategy(relevant=True, reason=None)
    }

    result = mock_cypher_agent.biological_relevance_validation_node(deepcopy(base_state))

    assert result == {
        "biological_relevance": True,
        "final_answer": None,
    }


def test_biological_relevance_validation_node_with_irrelevant_question(mock_cypher_agent, base_state):
    mock_cypher_agent.llm_factory.create_biological_relevance_validator_llm.return_value.invoke.return_value = {
        "parsed": BiologicalRelevanceValidatorStrategy(relevant=False, reason="The question is about finance.")
    }

    result = mock_cypher_agent.biological_relevance_validation_node(deepcopy(base_state))

    assert result["biological_relevance"] is False
    assert "outside the biological/biomedical domain" in result["final_answer"]
    assert "The question is about finance." in result["final_answer"]


def test_entity_resolution_node_returns_no_entities_extracted(mock_cypher_agent, base_state, mock_entity_resolver):
    mock_entity_resolver.run_entity_llm_stage.return_value = EntityResolutionStrategy(entities=[])

    result = mock_cypher_agent.entity_resolution_node(deepcopy(base_state))

    assert result == {"resolved_entities": "No entities extracted"}


def test_entity_resolution_node_returns_mismatch_message(mock_cypher_agent, base_state, mock_entity_resolver):
    extraction = EntityResolutionStrategy(
        entities=[
            ResolvedEntity(entity_string="psoriasis", node_type="Disease"),
            ResolvedEntity(entity_string="TP53", node_type="Gene"),
        ]
    )
    tool_plan = SimpleNamespace(tool_calls=[{"id": "call-1", "args": {"node_type": "Disease", "entity_name": "psoriasis"}}])
    mock_entity_resolver.run_entity_llm_stage.side_effect = [extraction, tool_plan]

    result = mock_cypher_agent.entity_resolution_node(deepcopy(base_state))

    assert "Length of tool calls (1) does not match length of extracted entities (2)." in result["resolved_entities"]


def test_entity_resolution_node_returns_filtered_resolved_entities(mock_cypher_agent, base_state, mock_entity_resolver):
    extraction = EntityResolutionStrategy(
        entities=[ResolvedEntity(entity_string="psoriasis", node_type="Disease")]
    )
    tool_plan = SimpleNamespace(
        tool_calls=[{"id": "call-1", "args": {"node_type": "Disease", "entity_name": "psoriasis"}}]
    )
    resolution = EntityResolutionStrategy(
        entities=[
            ResolvedEntity(entity_string="psoriasis", node_type="Disease", resolved_name="Psoriasis"),
            ResolvedEntity(entity_string="unknown", node_type="Disease", resolved_name=None),
        ]
    )

    mock_entity_resolver.run_entity_llm_stage.side_effect = [extraction, tool_plan, resolution]
    mock_entity_resolver.run_single_entity_tool_call_with_retry.return_value = SimpleNamespace(
        as_tool_message=AIMessage(content="tool-response")
    )

    result = mock_cypher_agent.entity_resolution_node(deepcopy(base_state))

    assert result == {
        "resolved_entities": [
            {
                "entity_name_in_user_question": "psoriasis",
                "resolved_entity_name_in_db": "Psoriasis",
            }
        ]
    }


def test_entity_resolution_node_returns_no_entities_resolved(mock_cypher_agent, base_state, mock_entity_resolver):
    extraction = EntityResolutionStrategy(
        entities=[ResolvedEntity(entity_string="psoriasis", node_type="Disease")]
    )
    tool_plan = SimpleNamespace(
        tool_calls=[{"id": "call-1", "args": {"node_type": "Disease", "entity_name": "psoriasis"}}]
    )
    resolution = EntityResolutionStrategy(
        entities=[ResolvedEntity(entity_string="psoriasis", node_type="Disease", resolved_name=None)]
    )

    mock_entity_resolver.run_entity_llm_stage.side_effect = [extraction, tool_plan, resolution]
    mock_entity_resolver.run_single_entity_tool_call_with_retry.return_value = SimpleNamespace(
        as_tool_message=AIMessage(content="tool-response")
    )

    result = mock_cypher_agent.entity_resolution_node(deepcopy(base_state))

    assert result == {"resolved_entities": "No entities resolved"}


def test_generate_cypher_node_db_search_uses_parsed_cypher(mock_cypher_agent, base_state):
    mock_cypher_agent.cypher_llm.invoke.return_value = {
        "parsed": SimpleNamespace(cypher_query="MATCH (g:Gene) RETURN g"),
        "raw": SimpleNamespace(response_metadata={"input_tokens": 1}),
    }

    result = mock_cypher_agent.generate_cypher_node(deepcopy(base_state))

    assert result == {
        "current_cypher": "MATCH (g:Gene) RETURN g",
        "retry_count": 0,
        "cypher_source": "generation",
    }


def test_generate_cypher_node_vector_search_formats_with_embedding(mock_cypher_agent, base_state, mocker):
    state = deepcopy(base_state)
    state["cypher_mode"] = "vector_search"
    state["embedding"] = [0.1, 0.2, 0.3]
    state["vector_index"] = "Anc2vecEmbeddings"

    mock_cypher_agent.cypher_llm.invoke.return_value = {
        "parsed": SimpleNamespace(cypher_query="RETURN {user_input}"),
        "raw": SimpleNamespace(response_metadata={"input_tokens": 1}),
    }
    handle_embedding_mock = mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.handle_embedding",
        return_value=[0.1, 0.2, 0.3],
    )

    result = mock_cypher_agent.generate_cypher_node(state)

    handle_embedding_mock.assert_called_once()
    assert result["current_cypher"] == "RETURN [0.1, 0.2, 0.3]"


def test_generate_cypher_node_vector_search_skips_format_without_embedding(mock_cypher_agent, base_state, mocker):
    state = deepcopy(base_state)
    state["cypher_mode"] = "vector_search"
    state["embedding"] = None
    state["vector_index"] = "Anc2vecEmbeddings"

    mock_cypher_agent.cypher_llm.invoke.return_value = {
        "parsed": SimpleNamespace(cypher_query="RETURN {user_input}"),
        "raw": SimpleNamespace(response_metadata={"input_tokens": 1}),
    }
    handle_embedding_mock = mocker.patch("crossbar_llm.agent_tools.cypher_agent.handle_embedding")

    result = mock_cypher_agent.generate_cypher_node(state)

    handle_embedding_mock.assert_not_called()
    assert result["current_cypher"] == "RETURN {user_input}"


def test_validate_cypher_node_appends_valid_attempt(mock_cypher_agent, base_state, mock_neo4j_config, mocker):
    mocker.patch("crossbar_llm.agent_tools.cypher_agent.Neo4jConfig", return_value=mock_neo4j_config)
    mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.validate_and_correct_query",
        return_value={
            "ok": True,
            "checks": {
                "syntax": {"ok": True, "message": []},
                "schema": {"ok": True, "message": []},
                "properties": {"ok": True, "message": []},
            },
            "corrected_query": None,
        },
    )

    result = mock_cypher_agent.validate_cypher_node(deepcopy(base_state))

    assert len(result["cypher_attempts"]) == 1
    assert result["cypher_attempts"][0]["is_valid"] is True
    assert "current_cypher" not in result


def test_validate_cypher_node_updates_current_cypher_when_corrected(mock_cypher_agent, base_state, mock_neo4j_config, mocker):
    mocker.patch("crossbar_llm.agent_tools.cypher_agent.Neo4jConfig", return_value=mock_neo4j_config)
    mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.validate_and_correct_query",
        return_value={
            "ok": True,
            "checks": {
                "syntax": {"ok": True, "message": []},
                "schema": {"ok": True, "message": []},
                "properties": {"ok": True, "message": []},
            },
            "corrected_query": "MATCH (g:Gene) RETURN g",
        },
    )

    result = mock_cypher_agent.validate_cypher_node(deepcopy(base_state))

    assert result["current_cypher"] == "MATCH (g:Gene) RETURN g"
    assert result["cypher_attempts"][0]["is_valid"] is True


def test_validate_cypher_node_appends_failure_metadata(mock_cypher_agent, base_state, mock_neo4j_config, mocker):
    mocker.patch("crossbar_llm.agent_tools.cypher_agent.Neo4jConfig", return_value=mock_neo4j_config)
    mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.validate_and_correct_query",
        return_value={
            "ok": False,
            "checks": {
                "syntax": {"ok": False, "message": ["Syntax error"]},
                "schema": {"ok": True, "message": []},
                "properties": {"ok": False, "message": ["Property error"]},
            },
            "corrected_query": None,
        },
    )

    result = mock_cypher_agent.validate_cypher_node(deepcopy(base_state))

    attempt = result["cypher_attempts"][0]
    assert attempt["is_valid"] is False
    assert attempt["syntax_errors"] == ["Syntax error"]
    assert attempt["schema_errors"] is None
    assert attempt["property_errors"] == ["Property error"]


def test_validate_cypher_node_raises_when_invalid_with_corrected_query(mock_cypher_agent, base_state, mock_neo4j_config, mocker):
    mocker.patch("crossbar_llm.agent_tools.cypher_agent.Neo4jConfig", return_value=mock_neo4j_config)
    mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.validate_and_correct_query",
        return_value={
            "ok": False,
            "checks": {
                "syntax": {"ok": False, "message": ["Syntax error"]},
                "schema": {"ok": False, "message": ["Schema error"]},
                "properties": {"ok": False, "message": ["Property error"]},
            },
            "corrected_query": "MATCH (n) RETURN n",
        },
    )

    with pytest.raises(ValueError, match="Corrected query should not be provided when the original query is invalid."):
        mock_cypher_agent.validate_cypher_node(deepcopy(base_state))


def test_human_review_node_returns_approve(mock_cypher_agent, base_state, mocker):
    mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.interrupt",
        return_value={"action": "approve"},
    )

    result = mock_cypher_agent.human_review_node(deepcopy(base_state))

    assert result == {"human_review_action": "approve"}


def test_human_review_node_returns_edit(mock_cypher_agent, base_state, mocker):
    mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.interrupt",
        return_value={"action": "edit", "edited_cypher": "MATCH (g:Gene) RETURN g"},
    )

    result = mock_cypher_agent.human_review_node(deepcopy(base_state))

    assert result == {
        "human_review_action": "edit",
        "current_cypher": "MATCH (g:Gene) RETURN g",
        "cypher_source": "human_edit",
    }


def test_human_review_node_raises_without_edited_cypher(mock_cypher_agent, base_state, mocker):
    mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.interrupt",
        return_value={"action": "edit"},
    )

    with pytest.raises(ValueError, match="Edited Cypher must be a non-empty string."):
        mock_cypher_agent.human_review_node(deepcopy(base_state))


def test_human_review_node_raises_with_invalid_action(mock_cypher_agent, base_state, mocker):
    mocker.patch(
        "crossbar_llm.agent_tools.cypher_agent.interrupt",
        return_value={"action": "ignore"},
    )

    with pytest.raises(ValueError, match="Review payload must contain action='approve' or action='edit'."):
        mock_cypher_agent.human_review_node(deepcopy(base_state))


def test_execute_cypher_node_raises_without_attempts(mock_cypher_agent, base_state):
    with pytest.raises(ValueError, match="No cypher attempt found for execution."):
        mock_cypher_agent.execute_cypher_node(deepcopy(base_state))


def test_execute_cypher_node_marks_string_error_as_failure(mock_cypher_agent, base_state, mock_neo4j_client_cls):
    mock_neo4j_client_cls.return_value.execute_query.return_value = "Database error"
    state = deepcopy(base_state)
    state["cypher_attempts"] = [make_attempt(is_valid=True, execution_ok=False)]

    result = mock_cypher_agent.execute_cypher_node(state)

    assert result["is_ok"] is False
    assert result["execution_result"] is None
    assert result["cypher_attempts"][-1]["execution_ok"] is False
    assert result["cypher_attempts"][-1]["execution_error"] == "Database error"
    assert result["cypher_attempts"][-1]["is_valid"] is False


def test_execute_cypher_node_marks_empty_results_as_failure(mock_cypher_agent, base_state, mock_neo4j_client_cls):
    mock_neo4j_client_cls.return_value.execute_query.return_value = []
    state = deepcopy(base_state)
    state["cypher_attempts"] = [make_attempt(is_valid=True, execution_ok=False)]

    result = mock_cypher_agent.execute_cypher_node(state)

    assert result["is_ok"] is False
    assert result["execution_result"] is None
    assert result["cypher_attempts"][-1]["execution_error"] == "Query executed successfully but returned no results."


def test_execute_cypher_node_marks_successful_results(mock_cypher_agent, base_state, mock_neo4j_client_cls):
    mock_neo4j_client_cls.return_value.execute_query.return_value = [{"gene_symbol": "TP53"}]
    state = deepcopy(base_state)
    state["cypher_attempts"] = [make_attempt(is_valid=True, execution_ok=False)]

    result = mock_cypher_agent.execute_cypher_node(state)

    assert result["is_ok"] is True
    assert result["execution_result"] == [{"gene_symbol": "TP53"}]
    assert result["cypher_attempts"][-1]["execution_ok"] is True
    assert result["cypher_attempts"][-1]["execution_error"] is None
    assert result["cypher_attempts"][-1]["is_valid"] is True


def test_error_correction_node_raises_without_attempts(mock_cypher_agent, base_state):
    with pytest.raises(ValueError, match="No cypher attempts available for error correction."):
        mock_cypher_agent.error_correction_node(deepcopy(base_state))


def test_error_correction_node_raises_for_already_successful_attempt(mock_cypher_agent, base_state):
    state = deepcopy(base_state)
    state["cypher_attempts"] = [make_attempt(is_valid=True, execution_ok=True)]

    with pytest.raises(ValueError, match="The last cypher attempt is already valid and executed successfully. Error correction should not be triggered."):
        mock_cypher_agent.error_correction_node(state)


def test_error_correction_node_returns_corrected_cypher(mock_cypher_agent, base_state):
    mock_cypher_agent.cypher_llm.invoke.return_value = {
        "parsed": SimpleNamespace(cypher_query="MATCH (g:Gene) RETURN g")
    }
    state = deepcopy(base_state)
    state["cypher_attempts"] = [make_attempt(is_valid=False, execution_ok=False)]

    result = mock_cypher_agent.error_correction_node(state)

    assert result == {
        "current_cypher": "MATCH (g:Gene) RETURN g",
        "retry_count": 1,
        "cypher_source": "error_correction",
    }


def test_generate_answer_node_raises_without_execution_result(mock_cypher_agent, base_state):
    with pytest.raises(ValueError, match="Execution result is empty. Somehow we reached answer generation without a successful execution. This should not happen."):
        mock_cypher_agent.generate_answer_node(deepcopy(base_state))


def test_generate_answer_node_returns_final_answer_and_messages(mock_cypher_agent, base_state):
    mock_cypher_agent.output_parser_llm.invoke.return_value = {
        "parsed": SimpleNamespace(final_answer="TP53 is related to psoriasis.")
    }
    state = deepcopy(base_state)
    state["execution_result"] = [{"gene_symbol": "TP53"}]

    result = mock_cypher_agent.generate_answer_node(state)

    assert result["final_answer"] == "TP53 is related to psoriasis."
    assert len(result["messages"]) == 3
    assert result["messages"][0].content == f"User question: {state['question']}"
    assert result["messages"][1].content == f"Generated cypher: {state['current_cypher']}"
    assert result["messages"][2].content == "Answer: TP53 is related to psoriasis."


def test_follow_up_question_node_raises_without_final_answer(mock_cypher_agent, base_state):
    with pytest.raises(ValueError, match="Final answer is empty. Cannot generate follow-up questions."):
        mock_cypher_agent.follow_up_question_node(deepcopy(base_state))


def test_follow_up_question_node_returns_questions_for_db_search(mock_cypher_agent, base_state):
    mock_cypher_agent.llm_factory.create_follow_up_question_llm.return_value.invoke.return_value = {
        "parsed": FollowUpQuestionStrategy(
            question_1="What other genes are involved?",
            question_2="Which diseases are connected to TP53?",
            question_3="Are there related pathways?",
        )
    }
    state = deepcopy(base_state)
    state["final_answer"] = "TP53 is related to psoriasis."

    result = mock_cypher_agent.follow_up_question_node(state)

    assert result == {
        "follow_up_questions": [
            "What other genes are involved?",
            "Which diseases are connected to TP53?",
            "Are there related pathways?",
        ]
    }


def test_follow_up_question_node_vector_search_branch_raises_current_type_error(mock_cypher_agent, base_state):
    state = deepcopy(base_state)
    state["cypher_mode"] = "vector_search"
    state["final_answer"] = "Answer"
    state["vector_index"] = "Anc2vecEmbeddings"

    with pytest.raises(TypeError):
        mock_cypher_agent.follow_up_question_node(state)


def test_web_search_node_raises_when_disabled(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, enable_web_search=False)
    state = deepcopy(base_state)
    state["cypher_attempts"] = [make_attempt(is_valid=False, execution_ok=False)]

    with pytest.raises(ValueError, match="Web search is not enabled in the agent configuration."):
        mock_cypher_agent.web_search_node(state)


def test_web_search_node_raises_without_attempts(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, enable_web_search=True)

    with pytest.raises(ValueError, match="No cypher attempts available for error correction."):
        mock_cypher_agent.web_search_node(deepcopy(base_state))


def test_web_search_node_raises_for_already_successful_attempt(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, enable_web_search=True)
    state = deepcopy(base_state)
    state["cypher_attempts"] = [make_attempt(is_valid=True, execution_ok=True)]

    with pytest.raises(ValueError, match="The last cypher attempt is already valid and executed successfully. Error correction should not be triggered."):
        mock_cypher_agent.web_search_node(state)


def test_web_search_node_returns_new_cypher(mock_cypher_agent, base_state, mocker):
    patch_agent_config(mocker, enable_web_search=True)
    mock_cypher_agent.web_search_llm.invoke.return_value = {
        "parsed": SimpleNamespace(cypher_query="MATCH (d:Disease) RETURN d")
    }
    state = deepcopy(base_state)
    state["cypher_attempts"] = [make_attempt(is_valid=False, execution_ok=False)]

    result = mock_cypher_agent.web_search_node(state)

    assert result == {
        "current_cypher": "MATCH (d:Disease) RETURN d",
        "retry_count": 1,
        "cypher_source": "web_search",
    }


def test_fail_node_raises_when_final_answer_exists(mock_cypher_agent, base_state):
    state = deepcopy(base_state)
    state["final_answer"] = "Already answered"

    with pytest.raises(ValueError, match="Final answer is already generated. Fail node should not be triggered."):
        mock_cypher_agent.fail_node(state)


def test_fail_node_returns_fallback_message(mock_cypher_agent, base_state):
    result = mock_cypher_agent.fail_node(deepcopy(base_state))

    assert result == {
        "final_answer": "I'm sorry, but I couldn't find an answer to your question after multiple attempts. Please try rephrasing your question or ask about something else.",
    }


@pytest.mark.integration
def test_build_graph_integration_exits_early_for_irrelevant_question(cypher_agent_integration_fixture, base_state, mocker):
    patch_agent_config(mocker)
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "biological_relevance_validation_node",
        return_value={
            "biological_relevance": False,
            "final_answer": "Your question is outside the biological/biomedical domain.\nReason: It is about finance.",
        },
    )

    graph = cypher_agent_integration_fixture.build_graph(checkpointer=None)
    result = graph.invoke(deepcopy(base_state))

    assert result["final_answer"] == "Your question is outside the biological/biomedical domain.\nReason: It is about finance."


@pytest.mark.integration
def test_build_graph_integration_happy_path(cypher_agent_integration_fixture, base_state, mocker):
    patch_agent_config(mocker, enable_entity_resolution=True)
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "biological_relevance_validation_node",
        return_value={"biological_relevance": True, "final_answer": None},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "entity_resolution_node",
        return_value={"resolved_entities": [{"entity_name_in_user_question": "psoriasis", "resolved_entity_name_in_db": "Psoriasis"}]},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "generate_cypher_node",
        return_value={"current_cypher": "MATCH (g:Gene) RETURN g", "retry_count": 0, "cypher_source": "generation"},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "validate_cypher_node",
        return_value={"cypher_attempts": [make_attempt(is_valid=True, syntax_valid=True, schema_valid=True, property_valid=True, syntax_errors=None, schema_errors=None, property_errors=None)]},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "execute_cypher_node",
        return_value={
            "cypher_attempts": [make_attempt(is_valid=True, execution_ok=True, execution_error=None)],
            "is_ok": True,
            "execution_result": [{"gene_symbol": "TP53"}],
        },
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "generate_answer_node",
        return_value={"final_answer": "TP53 is related to psoriasis.", "messages": []},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "follow_up_question_node",
        return_value={"follow_up_questions": ["Q1", "Q2", "Q3"]},
    )

    graph = cypher_agent_integration_fixture.build_graph(checkpointer=None)
    result = graph.invoke(deepcopy(base_state))

    assert result["final_answer"] == "TP53 is related to psoriasis."
    assert result["follow_up_questions"] == ["Q1", "Q2", "Q3"]


@pytest.mark.integration
def test_build_graph_integration_retry_then_success(cypher_agent_integration_fixture, base_state, mocker):
    patch_agent_config(mocker, max_iterations=2, enable_web_search=False)
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "biological_relevance_validation_node",
        return_value={"biological_relevance": True, "final_answer": None},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "entity_resolution_node",
        return_value={"resolved_entities": "No entities resolved"},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "generate_cypher_node",
        return_value={"current_cypher": "MATCH bad", "retry_count": 0, "cypher_source": "generation"},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "validate_cypher_node",
        side_effect=[
            {"cypher_attempts": [make_attempt(is_valid=False)]},
            {"cypher_attempts": [make_attempt(is_valid=True, syntax_valid=True, schema_valid=True, property_valid=True, syntax_errors=None, schema_errors=None, property_errors=None)]},
        ],
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "error_correction_node",
        return_value={"current_cypher": "MATCH corrected", "retry_count": 1, "cypher_source": "error_correction"},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "execute_cypher_node",
        return_value={
            "cypher_attempts": [make_attempt(is_valid=True, execution_ok=True, execution_error=None)],
            "is_ok": True,
            "execution_result": [{"gene_symbol": "TP53"}],
        },
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "generate_answer_node",
        return_value={"final_answer": "Recovered answer", "messages": []},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "follow_up_question_node",
        return_value={"follow_up_questions": ["Q1", "Q2", "Q3"]},
    )

    graph = cypher_agent_integration_fixture.build_graph(checkpointer=None)
    result = graph.invoke(deepcopy(base_state))

    assert result["final_answer"] == "Recovered answer"
    assert result["retry_count"] == 1


@pytest.mark.integration
def test_build_graph_integration_human_review_path(cypher_agent_integration_fixture, base_state, mocker):
    patch_agent_config(mocker)
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "biological_relevance_validation_node",
        return_value={"biological_relevance": True, "final_answer": None},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "entity_resolution_node",
        return_value={"resolved_entities": "No entities resolved"},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "generate_cypher_node",
        return_value={"current_cypher": "MATCH (g:Gene) RETURN g", "retry_count": 0, "cypher_source": "generation"},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "validate_cypher_node",
        return_value={"cypher_attempts": [make_attempt(is_valid=True, syntax_valid=True, schema_valid=True, property_valid=True, syntax_errors=None, schema_errors=None, property_errors=None)]},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "human_review_node",
        return_value={"human_review_action": "approve"},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "execute_cypher_node",
        return_value={
            "cypher_attempts": [make_attempt(is_valid=True, execution_ok=True, execution_error=None)],
            "is_ok": True,
            "execution_result": [{"gene_symbol": "TP53"}],
        },
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "generate_answer_node",
        return_value={"final_answer": "Reviewed answer", "messages": []},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "follow_up_question_node",
        return_value={"follow_up_questions": ["Q1", "Q2", "Q3"]},
    )

    graph = cypher_agent_integration_fixture.build_graph(checkpointer=None)
    state = deepcopy(base_state)
    state["execution_control"] = "generate"
    result = graph.invoke(state)

    assert result["human_review_action"] == "approve"
    assert result["final_answer"] == "Reviewed answer"


@pytest.mark.integration
def test_build_graph_integration_reaches_fail_after_exhausted_retries(cypher_agent_integration_fixture, base_state, mocker):
    patch_agent_config(mocker, max_iterations=1, enable_web_search=False)
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "biological_relevance_validation_node",
        return_value={"biological_relevance": True, "final_answer": None},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "entity_resolution_node",
        return_value={"resolved_entities": "No entities resolved"},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "generate_cypher_node",
        return_value={"current_cypher": "MATCH bad", "retry_count": 0, "cypher_source": "generation"},
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "validate_cypher_node",
        side_effect=[
            {"cypher_attempts": [make_attempt(is_valid=False)]},
            {"cypher_attempts": [make_attempt(is_valid=False)]},
        ],
    )
    mocker.patch.object(
        cypher_agent_integration_fixture,
        "error_correction_node",
        return_value={"current_cypher": "MATCH still_bad", "retry_count": 1, "cypher_source": "error_correction"},
    )

    graph = cypher_agent_integration_fixture.build_graph(checkpointer=None)
    result = graph.invoke(deepcopy(base_state))

    assert result["final_answer"] == "I'm sorry, but I couldn't find an answer to your question after multiple attempts. Please try rephrasing your question or ask about something else."

@pytest.mark.parametrize(
    "embedding, vector_index, index_name_to_vector_size, expected_message",
    [
        (
            np.array([0.1, 0.2, np.nan]),
            "Anc2vecEmbeddings",
            {"Anc2vecEmbeddings": 300},
            "NaN value found in provided embedding",
        ),
        (
            np.array([0.1, 0.2, np.inf]),
            "Anc2vecEmbeddings",
            {"Anc2vecEmbeddings": 300},
            "Infinite value found in provided embedding",
        ),
        (
            np.array([1, 2, 3], dtype=int),
            "Anc2vecEmbeddings",
            {"Anc2vecEmbeddings": 300},
            "Input embedding must be a float array",
        ),
        (
            np.array([[0.1, 0.2], [0.3, 0.4]]),
            "Anc2vecEmbeddings",
            {"Anc2vecEmbeddings": 300},
            "Input embedding must be a 1D array",
        ),
        (
            np.random.rand(450),
            "Anc2vecEmbeddings",
            {"Anc2vecEmbeddings": 300},
            "Invalid embedding vector shape provided. Expected 300, got 450",
        ),
    ]
)
def test_handle_embedding_raises_value_error(
    embedding,
    vector_index,
    index_name_to_vector_size,
    expected_message,
):
    with pytest.raises(ValueError, match=expected_message):
        handle_embedding(embedding, vector_index, index_name_to_vector_size)


def test_handle_embedding_valid_input():

    result = handle_embedding(np.random.rand(300), "Anc2vecEmbeddings", {"Anc2vecEmbeddings": 300})
    assert isinstance(result, list)
    assert len(result) == 300
    assert all(isinstance(x, float) for x in result)
