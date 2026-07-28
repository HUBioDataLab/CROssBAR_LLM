import pytest
from textwrap import dedent
from crossbar_llm.agent_tools.validators import extract_cypher, load_schemas, validate_query, validate_and_correct_query
from crossbar_llm.agent_tools.validators import Schema, QueryCorrector
from crossbar_llm.agent_tools.config import Neo4jConfig


@pytest.fixture
def mock_neo4j_cfg():
    return Neo4jConfig(
        neo4j_usr="neo4j",
        neo4j_password="password",
        neo4j_db_name="neo4j",
        neo4j_uri="bolt://localhost:7687",
    )

@pytest.fixture
def neo4j_cfg_integration():
    return Neo4jConfig()

@pytest.fixture
def mock_driver(mocker):
    fake_driver = mocker.MagicMock()
    mocker.patch(
        "crossbar_llm.agent_tools.validators.GraphDatabase.driver",
        return_value=fake_driver,
    )
    return fake_driver

def build_str_schemas(edge_schema):
    str_schemas = ""
    to_be_replaced = ["(", ")", ":", "[", "]", ">", "<"]
    for e in edge_schema:
        splitted = e.strip().split("-")
        splitted_corrected = []
        for s in splitted:
            for t in to_be_replaced:
                s = s.replace(t, "")
            splitted_corrected.append(s)
        add =", ("+", ".join(splitted_corrected)+")"
        str_schemas += add
    
    return str_schemas.strip(",").strip()



def test_extract_cypher():
    text = """
    Here is the Cypher query you can use:
    ```cypher
    MATCH (g:Gene)-[:Gene_is_related_to_disease]-(d:Disease)
    WHERE d.name = 'psoriasis'
    RETURN DISTINCT g.gene_symbol, g.id
    ```
    This query will return the gene symbols and IDs of genes that are related to psoriasis.
    """
    expected_cypher = "MATCH (g:Gene)-[:Gene_is_related_to_disease]-(d:Disease)\nWHERE d.name = 'psoriasis'\nRETURN DISTINCT g.gene_symbol, g.id"
    assert extract_cypher(text) == expected_cypher

def test_load_schemas():
    edge_schema = [
        "(:SmallMolecule)-[:Drug_targets_protein]->(:Protein)",
        "(:Gene)-[:Gene_is_related_to_disease]->(:Disease)",
    ]

    str_schemas = build_str_schemas(edge_schema)
    schemas = load_schemas(str_schemas)
    
    assert isinstance(schemas, list)
    assert all(isinstance(s, Schema) for s in schemas)
    assert len(schemas) == 2
    assert schemas[0].left_node == "SmallMolecule"
    assert schemas[0].relation == "Drug_targets_protein"
    assert schemas[0].right_node == "Protein"
    assert schemas[1].left_node == "Gene"
    assert schemas[1].relation == "Gene_is_related_to_disease"
    assert schemas[1].right_node == "Disease"


def test_query_corrector_with_wrong_relation_direction():
    edge_schema = [
        "(:Gene)-[:Gene_is_related_to_disease]->(:Disease)",
    ]

    str_schemas = build_str_schemas(edge_schema)
    schemas = load_schemas(str_schemas)

    wrong_relation_direction_query = "MATCH (g:Gene)<-[:Gene_is_related_to_disease]-(d:Disease)\nWHERE d.name = 'psoriasis'\nRETURN DISTINCT g.gene_symbol, g.id"

    corrected_query = "MATCH (g:Gene)-[:Gene_is_related_to_disease]->(d:Disease)\nWHERE d.name = 'psoriasis'\nRETURN DISTINCT g.gene_symbol, g.id"

    query_corrector = QueryCorrector(schemas)
    
    assert query_corrector.correct_query(wrong_relation_direction_query) == corrected_query

def test_query_corrector_with_wrong_node_labels():
    edge_schema = [
        "(:Gene)-[:Gene_is_related_to_disease]->(:Disease)",
    ]

    str_schemas = build_str_schemas(edge_schema)
    schemas = load_schemas(str_schemas)

    wrong_node_labels_query = "MATCH (g:Protein)-[:Gene_is_related_to_disease]->(d:Illness)\nWHERE d.name = 'psoriasis'\nRETURN DISTINCT g.gene_symbol, g.id"

    query_corrector = QueryCorrector(schemas)

    assert query_corrector.correct_query(wrong_node_labels_query) == ""

def test_query_corrector_with_wrong_relation_label():
    edge_schema = [
        "(:Gene)-[:Gene_is_related_to_disease]->(:Disease)",
    ]

    str_schemas = build_str_schemas(edge_schema)
    schemas = load_schemas(str_schemas)

    wrong_relation_label_query = "MATCH (g:Gene)-[:RelatedTo]->(d:Disease)\nWHERE d.name = 'psoriasis'\nRETURN DISTINCT g.gene_symbol, g.id"

    query_corrector = QueryCorrector(schemas)

    assert query_corrector.correct_query(wrong_relation_label_query) == ""

def test_query_corrector_with_correct_query():
    edge_schema = [
        "(:Gene)-[:Gene_is_related_to_disease]->(:Disease)",
    ]

    str_schemas = build_str_schemas(edge_schema)
    schemas = load_schemas(str_schemas)

    correct_query = "MATCH (g:Gene)-[:Gene_is_related_to_disease]->(d:Disease)\nWHERE d.name = 'psoriasis'\nRETURN DISTINCT g.gene_symbol, g.id"

    query_corrector = QueryCorrector(schemas)

    assert query_corrector.correct_query(correct_query) == correct_query


def test_validate_query_returns_ok_true_when_all_validators_pass(mock_neo4j_cfg, mock_driver, mocker):

    mock_neo4j_driver = mocker.patch(
        "crossbar_llm.agent_tools.validators.GraphDatabase.driver",
        return_value=mock_driver,
    )

    syntax_validator_instance = mocker.MagicMock()
    syntax_validator_instance.validate.return_value = (True, [])

    schema_validator_instance = mocker.MagicMock()
    schema_validator_instance.validate.return_value = (0.95, [])

    properties_validator_instance = mocker.MagicMock()
    properties_validator_instance.validate.return_value = (0.93, [])

    syntax_validator_mock = mocker.patch(
        "crossbar_llm.agent_tools.validators.SyntaxValidator",
        return_value=syntax_validator_instance,
    )
    schema_validator_mock = mocker.patch(
        "crossbar_llm.agent_tools.validators.SchemaValidator",
        return_value=schema_validator_instance,
    )
    properties_validator_mock = mocker.patch(
        "crossbar_llm.agent_tools.validators.PropertiesValidator",
        return_value=properties_validator_instance,
    )

    result = validate_query("MATCH (n) RETURN n", mock_neo4j_cfg)

    mock_neo4j_driver.assert_called_once_with(
        mock_neo4j_cfg.neo4j_uri,
        auth=(mock_neo4j_cfg.neo4j_usr, mock_neo4j_cfg.neo4j_password),
    )
    syntax_validator_mock.assert_called_once_with(mock_driver)
    schema_validator_mock.assert_called_once_with(mock_driver)
    properties_validator_mock.assert_called_once_with(mock_driver)

    syntax_validator_instance.validate.assert_called_once_with(
        "MATCH (n) RETURN n",
        database_name=mock_neo4j_cfg.neo4j_db_name,
    )
    schema_validator_instance.validate.assert_called_once_with(
        "MATCH (n) RETURN n",
        database_name=mock_neo4j_cfg.neo4j_db_name,
    )
    properties_validator_instance.validate.assert_called_once_with(
        "MATCH (n) RETURN n",
        database_name=mock_neo4j_cfg.neo4j_db_name,
        strict=True,
    )

    mock_driver.close.assert_called_once()

    assert result == {
        "ok": True,
        "checks": {
            "syntax": {"ok": True, "message": []},
            "schema": {"ok": True, "message": []},
            "properties": {"ok": True, "message": []},
        },
    }

def test_validate_query_returns_ok_false_when_syntax_fails(mock_neo4j_cfg, mock_driver, mocker):

    syntax_validator_instance = mocker.MagicMock()
    syntax_validator_instance.validate.return_value = (False, ["Syntax error"])

    schema_validator_instance = mocker.MagicMock()
    schema_validator_instance.validate.return_value = (0.95, [])

    properties_validator_instance = mocker.MagicMock()
    properties_validator_instance.validate.return_value = (0.95, [])

    mocker.patch(
        "crossbar_llm.agent_tools.validators.SyntaxValidator",
        return_value=syntax_validator_instance,
    )
    mocker.patch(
        "crossbar_llm.agent_tools.validators.SchemaValidator",
        return_value=schema_validator_instance,
    )
    mocker.patch(
        "crossbar_llm.agent_tools.validators.PropertiesValidator",
        return_value=properties_validator_instance,
    )

    result = validate_query("INVALID QUERY", mock_neo4j_cfg)

    assert result["ok"] is False
    assert result["checks"]["syntax"] == {"ok": False, "message": ["Syntax error"]}
    assert result["checks"]["schema"]["ok"] is True
    assert result["checks"]["properties"]["ok"] is True


@pytest.mark.parametrize(
    ("schema_score", "props_score", "expected_schema_ok", "expected_props_ok"),
    [
        (0.9, 0.9, True, True),
        (0.89, 0.9, False, True),
        (0.9, 0.89, True, False),
    ],
)
def test_validate_query_uses_threshold_of_point_9(
    mock_neo4j_cfg,
    mock_driver,
    mocker,
    schema_score,
    props_score,
    expected_schema_ok,
    expected_props_ok,
    ):

    syntax_validator_instance = mocker.MagicMock()
    syntax_validator_instance.validate.return_value = (True, [])

    schema_validator_instance = mocker.MagicMock()
    schema_validator_instance.validate.return_value = (schema_score, ["schema message"])

    properties_validator_instance = mocker.MagicMock()
    properties_validator_instance.validate.return_value = (props_score, ["property message"])

    mocker.patch(
        "crossbar_llm.agent_tools.validators.SyntaxValidator",
        return_value=syntax_validator_instance,
    )
    mocker.patch(
        "crossbar_llm.agent_tools.validators.SchemaValidator",
        return_value=schema_validator_instance,
    )
    mocker.patch(
        "crossbar_llm.agent_tools.validators.PropertiesValidator",
        return_value=properties_validator_instance,
    )

    result = validate_query("MATCH (n) RETURN n", mock_neo4j_cfg)

    assert result["checks"]["schema"]["ok"] is expected_schema_ok
    assert result["checks"]["properties"]["ok"] is expected_props_ok
    assert result["ok"] is (True and expected_schema_ok and expected_props_ok)

def test_validate_query_passes_strict_flag_to_properties_validator(mock_neo4j_cfg, mock_driver, mocker):

    syntax_validator_instance = mocker.MagicMock()
    syntax_validator_instance.validate.return_value = (True, [])

    schema_validator_instance = mocker.MagicMock()
    schema_validator_instance.validate.return_value = (1.0, [])

    properties_validator_instance = mocker.MagicMock()
    properties_validator_instance.validate.return_value = (1.0, [])

    mocker.patch(
        "crossbar_llm.agent_tools.validators.SyntaxValidator",
        return_value=syntax_validator_instance,
    )
    mocker.patch(
        "crossbar_llm.agent_tools.validators.SchemaValidator",
        return_value=schema_validator_instance,
    )
    mocker.patch(
        "crossbar_llm.agent_tools.validators.PropertiesValidator",
        return_value=properties_validator_instance,
    )

    validate_query("MATCH (n) RETURN n", mock_neo4j_cfg, strict=False)

    properties_validator_instance.validate.assert_called_once_with(
        "MATCH (n) RETURN n",
        database_name=mock_neo4j_cfg.neo4j_db_name,
        strict=False,
    )

def test_validate_and_correct_query_returns_validation_result_when_validation_fails(mock_neo4j_cfg, mocker):
    validate_query_mock = mocker.patch(
        "crossbar_llm.agent_tools.validators.validate_query",
        return_value={
            "ok": False,
            "checks": {
                "syntax": {"ok": False, "message": ["Syntax error"]},
                "schema": {"ok": True, "message": []},
                "properties": {"ok": True, "message": []},
            },
        },
    )
    correct_query_mock = mocker.patch("crossbar_llm.agent_tools.validators.correct_query")

    result = validate_and_correct_query(
        query="INVALID QUERY",
        cfg=mock_neo4j_cfg,
        edge_schema=["(:Gene)-[:Gene_is_related_to_disease]->(:Disease)"],
    )

    validate_query_mock.assert_called_once_with("INVALID QUERY", mock_neo4j_cfg, True)
    correct_query_mock.assert_not_called()

    assert result == {
        "ok": False,
        "checks": {
            "syntax": {"ok": False, "message": ["Syntax error"]},
            "schema": {"ok": True, "message": []},
            "properties": {"ok": True, "message": []},
        },
        "corrected_query": None,
    }

def test_validate_and_correct_query_sets_corrected_query_when_validation_passes(mock_neo4j_cfg, mocker):
    validate_query_mock = mocker.patch(
        "crossbar_llm.agent_tools.validators.validate_query",
        return_value={
            "ok": True,
            "checks": {
                "syntax": {"ok": True, "message": []},
                "schema": {"ok": True, "message": []},
                "properties": {"ok": True, "message": []},
            },
        },
    )
    correct_query_mock = mocker.patch(
        "crossbar_llm.agent_tools.validators.correct_query",
        return_value="MATCH (g:Gene)-[:Gene_is_related_to_disease]->(d:Disease) RETURN g",
    )

    edge_schema = ["(:Gene)-[:Gene_is_related_to_disease]->(:Disease)"]

    result = validate_and_correct_query(
        query="MATCH (g:Gene)-[:Gene_is_related_to_disease]->(d:Disease) RETURN g",
        cfg=mock_neo4j_cfg,
        edge_schema=edge_schema,
    )

    validate_query_mock.assert_called_once_with(
        "MATCH (g:Gene)-[:Gene_is_related_to_disease]->(d:Disease) RETURN g",
        mock_neo4j_cfg,
        True,
    )
    correct_query_mock.assert_called_once_with(
        "MATCH (g:Gene)-[:Gene_is_related_to_disease]->(d:Disease) RETURN g",
        edge_schema,
    )

    assert result == {
        "ok": True,
        "checks": {
            "syntax": {"ok": True, "message": []},
            "schema": {"ok": True, "message": []},
            "properties": {"ok": True, "message": []},
        },
        "corrected_query": "MATCH (g:Gene)-[:Gene_is_related_to_disease]->(d:Disease) RETURN g",
    }

def test_validate_and_correct_query_marks_schema_failure_when_correction_returns_empty_string(mock_neo4j_cfg, mocker):
    mocker.patch(
        "crossbar_llm.agent_tools.validators.validate_query",
        return_value={
            "ok": True,
            "checks": {
                "syntax": {"ok": True, "message": []},
                "schema": {"ok": True, "message": []},
                "properties": {"ok": True, "message": []},
            },
        },
    )
    mocker.patch(
        "crossbar_llm.agent_tools.validators.correct_query",
        return_value="",
    )

    result = validate_and_correct_query(
        query="MATCH (g:Gene)-[:WRONG_REL]->(d:Disease) RETURN g",
        cfg=mock_neo4j_cfg,
        edge_schema=["(:Gene)-[:REL]->(:Disease)"],
    )

    assert result["ok"] is False
    assert result["corrected_query"] is None
    assert result["checks"]["schema"]["ok"] is False
    assert result["checks"]["schema"]["message"] == [
        "Schema correction failed: The query's relationship directions or node labels do not match any allowed edge schema."
    ]


@pytest.mark.integration
def test_validate_query_integration_with_valid_query(neo4j_cfg_integration):
    query = """
    MATCH (g:Gene)-[:Gene_is_related_to_disease]->(d:Disease)
    RETURN g.id AS gene_id, d.name AS disease_name
    LIMIT 3
    """.strip()

    result = validate_query(query, neo4j_cfg_integration)

    assert isinstance(result, dict)
    assert "ok" in result
    assert "checks" in result
    assert set(result["checks"].keys()) == {"syntax", "schema", "properties"}
    assert isinstance(result["checks"]["syntax"]["ok"], bool)
    assert isinstance(result["checks"]["schema"]["ok"], bool)
    assert isinstance(result["checks"]["properties"]["ok"], bool)

@pytest.mark.integration
def test_validate_query_integration_with_invalid_syntax(neo4j_cfg_integration):
    query = "MACH (g:Gene) RETURN g"

    result = validate_query(query, neo4j_cfg_integration)

    assert result["ok"] is False
    assert result["checks"]["syntax"]["ok"] is False

@pytest.mark.integration
def test_validate_query_integration_with_wrong_relation_direction(neo4j_cfg_integration):
    query = """
    MATCH (g:Gene)<-[:Gene_is_related_to_disease]-(d:Disease)
    RETURN g.id AS gene_id, d.name AS disease_name
    LIMIT 3
    """.strip()

    result = validate_query(query, neo4j_cfg_integration)

    assert isinstance(result, dict)
    assert result["checks"]["syntax"]["ok"] is True
    assert result["checks"]["schema"]["ok"] is False

@pytest.mark.integration
def test_validate_query_integration_with_invalid_property(neo4j_cfg_integration):
    query = """
    MATCH (g:Gene)-[:Gene_is_related_to_disease]->(d:Disease)
    RETURN g.this_property_does_not_exist AS gene_value
    LIMIT 3
    """.strip()

    result = validate_query(query, neo4j_cfg_integration)

    assert isinstance(result, dict)
    assert result["checks"]["syntax"]["ok"] is True
    assert result["checks"]["properties"]["ok"] is False


@pytest.mark.integration
def test_validate_and_correct_query_integration_corrects_relation_direction(neo4j_cfg_integration):
    query = """
    MATCH (g:Gene)<-[:Gene_is_related_to_disease]-(d:Disease)
    RETURN g.gene_symbol, g.id
    """.strip()

    edge_schema = [
        "(:Gene)-[:Gene_is_related_to_disease]->(:Disease)",
    ]

    result = validate_and_correct_query(query, neo4j_cfg_integration, edge_schema=edge_schema)

    assert isinstance(result, dict)
    assert "ok" in result
    assert "checks" in result
    assert "corrected_query" in result

    if result["ok"]:
        assert result["corrected_query"] is not None
        assert "[:Gene_is_related_to_disease]->" in result["corrected_query"]

@pytest.mark.integration
def test_validate_and_correct_query_integration_returns_expected_shape(neo4j_cfg_integration):
    query = """
    MATCH (g:Gene)-[:Gene_is_related_to_disease]->(d:Disease)
    RETURN g.gene_symbol, g.id
    LIMIT 3
    """.strip()

    edge_schema = [
        "(:Gene)-[:Gene_is_related_to_disease]->(:Disease)",
    ]

    result = validate_and_correct_query(query, neo4j_cfg_integration, edge_schema=edge_schema)

    assert isinstance(result, dict)
    assert "ok" in result
    assert "checks" in result
    assert "corrected_query" in result

@pytest.mark.integration
def test_validate_and_correct_query_integration_with_wrong_relation_label(neo4j_cfg_integration):
    query = """
    MATCH (g:Gene)-[:DefinitelyWrongRelation]->(d:Disease)
    RETURN g.gene_symbol, g.id
    """.strip()

    edge_schema = [
        "(:Gene)-[:Gene_is_related_to_disease]->(:Disease)",
    ]

    result = validate_and_correct_query(query, neo4j_cfg_integration, edge_schema=edge_schema)

    assert isinstance(result, dict)
    assert result["ok"] is False and result["corrected_query"] is None
