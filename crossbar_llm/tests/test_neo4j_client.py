import pytest
import json
import neo4j

from crossbar_llm.agent_tools.neo4j_client import (
    Neo4jClient,
    node_properties_query,
    node_query,
    rel_properties_query,
    rel_query,
)
from crossbar_llm.agent_tools.config import Neo4jConfig


@pytest.fixture
def mock_neo4j_client(tmp_path):
    c = Neo4jClient(cfg=Neo4jConfig())
    c.file_path = tmp_path / "graph_schema.json"
    return c

@pytest.fixture
def mock_driver(mocker):
    fake_driver = mocker.MagicMock()
    fake_driver.__enter__.return_value = fake_driver
    fake_driver.__exit__.return_value = False
    return fake_driver

@pytest.fixture
def neo4j_client_integration():
    return Neo4jClient(cfg=Neo4jConfig())



def test_remove_embedding_attribute(mock_neo4j_client):
    data = {
        "name": "Target",
        "embedding": [0.1, 0.2],
        "nested": {
            "score": 0.9,
            "deep_embedding": [0.3, 0.4]
        },
        "list": [
            {"id": 1, "node_embedding": [0.5]},
            {"id": 2}
        ]
    }

    cleaned = mock_neo4j_client.remove_embedding_attribute(data)
    assert "embedding" not in cleaned
    assert "deep_embedding" not in cleaned["nested"]
    assert "node_embedding" not in cleaned["list"][0]
    assert cleaned["name"] == "Target"
    assert cleaned["nested"]["score"] == 0.9
    assert cleaned["list"][0]["id"] == 1
    assert cleaned["list"][1]["id"] == 2

def test_create_graph_schema_variables_uses_cached_file(mock_neo4j_client):
    cached = {
        "nodes": [{"labels": ["Protein"]}],
        "node_properties": [{
            "labels": "BiologicalProcess",
            "properties": [
                {"property": "name", "type": "STRING"},
            ]
            }],
        "edges": ["(:BiologicalProcess)-[:Biological_process_is_a_biological_process]->(:BiologicalProcess)"],
        "edge_properties": [
            {
                "properties": [
                    {"property": "reference", "type": "STRING"},
                ],
                "type": "Protein_involved_in_biological_process"
            }
        ],
    }

    mock_neo4j_client.file_path.write_text(json.dumps(cached))

    schema = mock_neo4j_client.create_graph_schema_variables()
    assert schema == cached

def test_create_graph_schema_variables_queries_db_and_writes_file(mock_neo4j_client, mocker, mock_driver):
    expected_schema = {
        "nodes": [{"labels": ["Protein"]}],
        "node_properties": [{
            "labels": "BiologicalProcess",
            "properties": [
                {"property": "name", "type": "STRING"},
            ]
            }],
        "edges": ["(:BiologicalProcess)-[:Biological_process_is_a_biological_process]->(:BiologicalProcess)"],
        "edge_properties": [
            {
                "properties": [
                    {"property": "reference", "type": "STRING"},
                ],
                "type": "Protein_involved_in_biological_process"
            }
        ],
    }

    mock_driver.execute_query.side_effect = [
        (
            [{"output": expected_schema["node_properties"][0]}],
            None,
            None,
        ),
        (
            [{"output": expected_schema["nodes"][0]}],
            None,
            None,
        ),
        (
            [{"output": expected_schema["edge_properties"][0]}],
            None,
            None,
        ),
        (
            [{"output": expected_schema["edges"][0]}],
            None,
            None,
        ),
    ]

    mocker.patch(
        "crossbar_llm.agent_tools.neo4j_client.GraphDatabase.driver",
        return_value=mock_driver,
    )

    result = mock_neo4j_client.create_graph_schema_variables()
    assert result == expected_schema
    assert mock_neo4j_client.file_path.exists()
    assert json.loads(mock_neo4j_client.file_path.read_text()) == expected_schema

    assert mock_driver.execute_query.call_count == 4

    mock_driver.execute_query.assert_any_call(
        node_properties_query,
        database_=mock_neo4j_client.cfg.neo4j_db_name,
    )
    mock_driver.execute_query.assert_any_call(
        node_query,
        database_=mock_neo4j_client.cfg.neo4j_db_name,
    )
    mock_driver.execute_query.assert_any_call(
        rel_properties_query,
        database_=mock_neo4j_client.cfg.neo4j_db_name,
    )
    mock_driver.execute_query.assert_any_call(
        rel_query,
        database_=mock_neo4j_client.cfg.neo4j_db_name,
    )


def test_get_db_version_returns_cached_value(mock_neo4j_client):
    mock_neo4j_client.file_path.write_text(
        json.dumps(
            {
                "nodes": [],
                "node_properties": [],
                "edges": [],
                "edge_properties": [],
                "db_version": "5.22.0",
            }
        )
    )

    assert mock_neo4j_client.get_db_version() == "5.22.0"

def test_get_db_version_queries_db_and_caches_result(mock_neo4j_client, mocker, mock_driver):
    mock_neo4j_client.file_path.write_text(json.dumps({
        "nodes": [],
        "node_properties": [],
        "edges": [],
        "edge_properties": [],
    }))

    fake_record = mocker.MagicMock()
    fake_record.data.return_value = {"version": "5.22.0"}

    mock_driver.execute_query.return_value = ([fake_record], None, None)

    mocker.patch(
        "crossbar_llm.agent_tools.neo4j_client.GraphDatabase.driver",
        return_value=mock_driver,
    )

    assert mock_neo4j_client.get_db_version() == "5.22.0"

    cached = json.loads(mock_neo4j_client.file_path.read_text())
    assert cached["db_version"] == "5.22.0"


@pytest.mark.parametrize(
    ("query", "top_k", "expected_fragment"),
    [
        ("MATCH (n) RETURN n", 5, "LIMIT 5"),
        ("MATCH (n) RETURN n LIMIT 99", 3, "LIMIT 3"),
        ("SHOW INDEXES", 7, "SHOW INDEXES"),
    ],
)
def test_execute_query_limit_injection(mock_neo4j_client, mocker, mock_driver, query, top_k, expected_fragment):
    fake_record = mocker.MagicMock()
    fake_record.data.return_value = {"name": "ProteinA", "embedding": [0.1, 0.2]}
    mock_driver.execute_query.return_value = (
        [fake_record],
        None,
        None,
    )

    mocker.patch(
        "crossbar_llm.agent_tools.neo4j_client.GraphDatabase.driver",
        return_value=mock_driver,
    )

    result = mock_neo4j_client.execute_query(query, top_k=top_k)

    assert mock_driver.execute_query.call_count == 1
    assert expected_fragment in mock_driver.execute_query.call_args.args[0]
    assert result == [{"name": "ProteinA"}]

@pytest.mark.parametrize(
    ("error", "expected_prefix"),
    [
        (neo4j.exceptions.CypherSyntaxError("bad syntax"), "Cypher Syntax Error:"),
        (neo4j.exceptions.CypherTypeError("bad type"), "Cypher Type Error:"),
        (neo4j.exceptions.DatabaseError("db failed"), "The database failed to service the request:"),
        (RuntimeError("boom"), "An error occurred while executing the query:"),
    ],
)
def test_execute_query_maps_errors(mock_neo4j_client, mocker, mock_driver, error, expected_prefix):
    mock_driver.execute_query.side_effect = error

    mocker.patch(
        "crossbar_llm.agent_tools.neo4j_client.GraphDatabase.driver",
        return_value=mock_driver,
    )

    result = mock_neo4j_client.execute_query("MATCH (n) RETURN n")

    assert isinstance(result, str)
    assert result.startswith(expected_prefix)

def test_fulltext_search_adds_rank(mock_neo4j_client, mocker):
    mocked_execute_query = mocker.patch.object(
        mock_neo4j_client,
        "execute_query",
        return_value=[
        {"name": "ProteinA", "score": 1.0},
        {"name": "ProteinB", "score": 0.9},
        ]
    )

    result = mock_neo4j_client.fulltext_search("Protein", "protein", top_k=2, add_idx=True)

    mocked_execute_query.assert_called_once()
    assert result == [
        {"rank": 1, "name": "ProteinA", "score": 1.0},
        {"rank": 2, "name": "ProteinB", "score": 0.9},
    ]

def test_fulltext_search_without_rank_returns(mock_neo4j_client, mocker):
    raw_results = [{"name": "ProteinA", "score": 1.0}]
    mocked_execute_query = mocker.patch.object(
        mock_neo4j_client,
        "execute_query",
        return_value=raw_results,
    )

    result = mock_neo4j_client.fulltext_search("Protein", "protein", top_k=1, add_idx=False)

    mocked_execute_query.assert_called_once()
    assert result == raw_results

def test_fulltext_search_returns_error_passthrough(mock_neo4j_client, mocker):
    mocked_execute_query = mocker.patch.object(
        mock_neo4j_client,
        "execute_query",
        return_value="db error",
    )

    result = mock_neo4j_client.fulltext_search("Protein", "protein", top_k=1, add_idx=True)

    mocked_execute_query.assert_called_once()
    assert result == "db error"

def test_init_runs_enabled_startup_actions(mocker):
    reset_db_schema_mock = mocker.patch.object(Neo4jClient, "reset_db_schema")
    create_vector_indexes_mock = mocker.patch.object(Neo4jClient, "create_vector_indexes")
    delete_vector_indexes_mock = mocker.patch.object(Neo4jClient, "delete_vector_indexes")
    create_fulltext_indexes_mock = mocker.patch.object(Neo4jClient, "create_fulltext_indexes")
    delete_fulltext_indexes_mock = mocker.patch.object(Neo4jClient, "delete_fulltext_indexes")

    Neo4jClient(
        cfg=Neo4jConfig(),
        reset_schema=True,
        create_vector_indexes=True,
        delete_vector_indexes=True,
        create_fulltext_indexes=True,
        delete_fulltext_indexes=True,
    )

    reset_db_schema_mock.assert_called_once()
    create_vector_indexes_mock.assert_called_once()
    delete_vector_indexes_mock.assert_called_once()
    create_fulltext_indexes_mock.assert_called_once()
    delete_fulltext_indexes_mock.assert_called_once()


@pytest.mark.integration
def test_execute_query_with_top_k_integration(neo4j_client_integration):
    result = neo4j_client_integration.execute_query("MATCH (n) RETURN n.id AS id", top_k=3)
    assert isinstance(result, list)
    assert len(result) <= 3
    for record in result:
        assert "id" in record

@pytest.mark.integration
def test_execute_query_returns_error_string_for_invalid_cypher(neo4j_client_integration):
    result = neo4j_client_integration.execute_query("MACH (n) RETURN n")
    assert isinstance(result, str)
    assert result.startswith("Cypher Syntax Error:")

@pytest.mark.integration
def test_fulltext_search_integration(neo4j_client_integration):
    result = neo4j_client_integration.fulltext_search("SmallMolecule", "2-(4-hydroxybiphenyl-3-yl)-4-methyl-1H-isoindole-1,3(2H)-dione", top_k=2, add_idx=False)
    assert isinstance(result, list) and len(result) <= 2
    for record in result:
        assert "name" in record
    

@pytest.mark.integration
def test_fulltext_search_error_passthrough_integration(neo4j_client_integration):
    result = neo4j_client_integration.fulltext_search("OrganismTaxon", "Rotavirus A (strain RVA/Human/Venezuela/M37/1982/G1P2A[6]) (RV-A)", top_k=2, add_idx=False)
    assert isinstance(result, str) and result.startswith("An error occurred while executing the query")

@pytest.mark.integration
def test_fulltext_search_no_results_integration(neo4j_client_integration):
    result = neo4j_client_integration.fulltext_search("Protein", "NonExistentProtein12345", top_k=2, add_idx=False)
    assert isinstance(result, list) and len(result) == 0


@pytest.mark.integration
def test_verify_db_connection_integration(neo4j_client_integration):
    result = neo4j_client_integration.verify_db_connection()
    assert result is True
