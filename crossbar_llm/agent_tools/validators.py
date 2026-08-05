from typing import Literal

from CyVer import SyntaxValidator, SchemaValidator, PropertiesValidator
from neo4j import GraphDatabase
from textwrap import dedent

import re
from collections import namedtuple
from pydantic import validate_call

from .config import Neo4jConfig
from .logging_config import get_logger
logger = get_logger(__name__)

@validate_call(validate_return=True)
def extract_cypher(text: str) -> str:
    """Extract Cypher code from a text.
    Args:
        text: Text to extract Cypher code from.
    Returns:
        Cypher code extracted from the text.
    """
    # The pattern to find Cypher code enclosed in triple backticks
    pattern = r"```(.*?)```"
    # Find all matches in the input text
    matches = re.findall(pattern, text, re.DOTALL)
    result = matches[0] if matches else text

    extracted_cypher = dedent(result.replace("cypher", "")).strip()
    logger.debug(
        "Extracted Cypher from text",
        event_type="cypher_extracted",
        component="extract_cypher",
        had_matches=bool(matches),
        extracted_cypher_preview=extracted_cypher
    )
    return extracted_cypher

Schema = namedtuple("Schema", ["left_node", "relation", "right_node"])

@validate_call(validate_return=True)
def load_schemas(str_schemas: str) -> list[Schema]:
    """
    Args:
        str_schemas: string of schemas
    """
    values = str_schemas.replace("(", "").replace(")", "").split(",")
    schemas = []
    for i in range(len(values)//3):
        schemas.append(
            Schema(
                values[i*3].strip(), 
                values[i*3+1].strip(), 
                values[i*3+2].strip()
            )
        )
    logger.debug(
        "Loaded schemas from string",
        event_type="schemas_loaded",
        component="load_schemas",
        schema_count=len(schemas)
    )
    return schemas

class QueryCorrector:
    
    property_pattern = re.compile(r"\{.+?\}")
    node_pattern = re.compile(r"\(.+?\)")
    path_pattern = re.compile(r"(\([^\,\(\)]*?(\{.+\})?[^\,\(\)]*?\))(<?-)(\[.*?\])?(->?)(\([^\,\(\)]*?(\{.+\})?[^\,\(\)]*?\))")
    node_relation_node_pattern = re.compile(r"(\()+(?P<left_node>[^()]*?)\)(?P<relation>.*?)\((?P<right_node>[^()]*?)(\))+")
    relation_type_pattern = re.compile(r":(?P<relation_type>.+?)?(\{.+\})?]")
    
    def __init__(self, schemas: list[Schema]):
        """
        Args:
            schemas: list of schemas
        """
        self.schemas = schemas
        logger.debug(
            "QueryCorrector initialized",
            event_type="query_corrector_initialized",
            component="QueryCorrector",
            schema_count=len(schemas)
        )
    
    def clean_node(self, node: str) -> str:
        """
        Args:
            node: node in string format
        
        """
        node = re.sub(self.property_pattern, "", node)
        node = node.replace("(", "")
        node = node.replace(")", "")
        node = node.strip()
        return node
        
    def detect_node_variables(self, query: str) -> dict[str, list[str]]:
        """
        Args:
            query: cypher query
        """
        nodes = re.findall(self.node_pattern, query)
        nodes = [self.clean_node(node) for node in nodes]
        res = {}
        for node in nodes:
            parts = node.split(":")
            if parts == "":
                continue
            variable = parts[0]
            if variable not in res:
                res[variable] = []
            res[variable] += parts[1:]
        
        logger.debug(
            "Detected node variables",
            event_type="node_variables_detected",
            component="QueryCorrector.detect_node_variables",
            variable_count=len(res),
            variables=list(res.keys())
        )
        return res
        
    def extract_paths(self, query: str) -> 'list[str]':
        """
        Args:
            query: cypher query
        """
        paths = []
        idx = 0
        while matched := self.path_pattern.findall(query[idx:]):
            matched = matched[0]
            matched = [
                m for i, m in enumerate(matched) if i not in [1, len(matched) - 1]
            ]
            path = "".join(matched)

            absolute_pos = query.find(path, idx)
            if absolute_pos == -1:
                break

            next_idx = absolute_pos + len(path) - len(matched[-1])
            if next_idx <= idx:
                logger.error(
                    "extract_paths made no forward progress",
                    event_type="no_forward_progress",
                    component="QueryCorrector.extract_paths",
                    idx=idx,
                    next_idx=next_idx,
                    path=path
                )
                raise RuntimeError(
                    f"extract_paths made no forward progress: idx={idx}, next_idx={next_idx}, path={path!r}"
                )
            
            paths.append(path)
            idx = next_idx

        logger.debug(
            "Extracted paths",
            event_type="paths_extracted",
            component="QueryCorrector.extract_paths",
            path_count=len(paths)
        )
        return paths
        
    def judge_direction(self, relation: str) -> str:
        """
        Args:
            relation: relation in string format
        """
        direction = "BIDIRECTIONAL"
        if relation[0] == "<":
            direction = "INCOMING"
        if relation[-1] == ">":
            direction = "OUTGOING"
        return direction
        
    def extract_node_variable(self, part: str) -> str:
        """
        Args:
            part: node in string format
        """
        part = part.lstrip("(").rstrip(")")
        idx = part.find(":")
        if idx != -1:
            part = part[:idx]
        return None if part == "" else part
        
    def detect_labels(self, str_node: str, node_variable_dict: dict) -> list[str]:
        """
        Args:
            str_node: node in string format
            node_variable_dict: dictionary of node variables
        """
        splitted = str_node.split(":")
        variable = splitted[0]
        labels = []
        if variable in node_variable_dict:
            labels = node_variable_dict[variable]
        elif variable == "" and len(splitted) > 1:
            labels = splitted[1:]

        return labels
    
    def verify_schema(self, from_node_labels: list[str], relation_types: list[str], to_node_labels: list[str]) -> bool:
        """
        Args:
            from_node_labels: labels of the from node
            relation_type: type of the relation
            to_node_labels: labels of the to node
        """

        valid_schemas = self.schemas
        if from_node_labels != []:
            from_node_labels = [label.strip('`') for label in from_node_labels]
            valid_schemas = [schema for schema in valid_schemas if schema[0] in from_node_labels]
        if to_node_labels != []:
            to_node_labels = [label.strip('`') for label in to_node_labels]
            valid_schemas = [schema for schema in valid_schemas if schema[2] in to_node_labels]
        if relation_types != []:
            relation_types = [type.strip('`') for type in relation_types]
            valid_schemas = [schema for schema in valid_schemas if schema[1] in relation_types]
        is_valid = valid_schemas != []

        logger.debug(
            "Verified schema compatibility",
            event_type="schema_verified",
            component="QueryCorrector.verify_schema",
            from_node_labels=from_node_labels,
            relation_types=relation_types,
            to_node_labels=to_node_labels,
            is_valid=is_valid,
            valid_schema_count=len(valid_schemas)
        )
        return is_valid
    
    def detect_relation_types(self, str_relation: str) -> tuple[str, list[str]]:
        """
        Args:
            str_relation: relation in string format
        """
        relation_direction = self.judge_direction(str_relation)        
        relation_type = self.relation_type_pattern.search(str_relation)
        if relation_type is None or relation_type.group('relation_type') is None:
            logger.debug(
                "No explicit relation type detected",
                event_type="relation_type_detection",
                component="QueryCorrector.detect_relation_types",
                relation=str_relation,
                relation_direction=relation_direction
            )

            return relation_direction, []
        
        relation_types = [t.strip().strip('!') for t in relation_type.group('relation_type').split("|")]
        logger.debug(
            "Detected relation types",
            event_type="relation_type_detected",
            component="QueryCorrector.detect_relation_types",
            relation=str_relation,
            relation_direction=relation_direction,
            relation_types=relation_types
        )
        return relation_direction, relation_types
        
    def correct_query(self, query: str) -> str:
        """
        Args:
            query: cypher query
        """

        logger.debug(
            "Starting query correction",
            event_type="query_correction_start",
            component="QueryCorrector.correct_query",
            query=query
        )

        node_variable_dict = self.detect_node_variables(query)
        paths = self.extract_paths(query)
        for path in paths:
            original_path = path
            start_idx = 0
            while start_idx < len(path):
                match_res = re.match(self.node_relation_node_pattern, path[start_idx:])
                if match_res is None:
                    break
                start_idx += match_res.start()
                match_dict = match_res.groupdict()
                left_node_labels = self.detect_labels(match_dict["left_node"], node_variable_dict)
                right_node_labels = self.detect_labels(match_dict["right_node"], node_variable_dict)
                end_idx = start_idx + 4 + len(match_dict["left_node"]) + len(match_dict["relation"]) + len(match_dict["right_node"])
                original_partial_path = original_path[start_idx:end_idx+1]
                relation_direction, relation_types = self.detect_relation_types(match_dict["relation"])
                
                if relation_types != [] and ''.join(relation_types).find('*') != -1:
                    logger.debug(
                        "Skipping path with wildcard relation type during correction",
                        event_type="relation_type_skipped",
                        component="QueryCorrector.correct_query",
                        path=path,
                        relation=match_dict["relation"],
                        relation_types=relation_types
                    )
                    start_idx += len(match_dict["left_node"]) + len(match_dict["relation"]) + 2
                    continue
                
                if relation_direction == "OUTGOING":
                    is_legal = self.verify_schema(left_node_labels, relation_types, right_node_labels)
                    if not is_legal:
                        is_legal = self.verify_schema(right_node_labels, relation_types, left_node_labels)
                        if is_legal:
                            
                            corrected_relation = "<" + match_dict["relation"][:-1]
                            corrected_partial_path = original_partial_path.replace(match_dict["relation"], corrected_relation)
                            query = query.replace(original_partial_path, corrected_partial_path)
                            logger.info(
                                "Corrected outgoing relation direction",
                                event_type="relation_direction_corrected",
                                component="QueryCorrector.correct_query",
                                original_path=original_partial_path,
                                corrected_path=corrected_partial_path
                            )
                        else:
                            logger.warning(
                                "Query correction failed because no valid schema matched",
                                event_type="relation_direction_correction_failed",
                                component="QueryCorrector.correct_query",
                                path=original_partial_path,
                                left_node_labels=left_node_labels,
                                relation_types=relation_types,
                                right_node_labels=right_node_labels
                            )
                            return ""
                elif relation_direction == "INCOMING":
                    is_legal = self.verify_schema(right_node_labels, relation_types, left_node_labels)
                    if not is_legal:
                        is_legal = self.verify_schema(left_node_labels, relation_types, right_node_labels)
                        if is_legal:
                            corrected_relation = match_dict["relation"][1:] + ">"
                            corrected_partial_path = original_partial_path.replace(match_dict["relation"], corrected_relation)
                            query = query.replace(original_partial_path, corrected_partial_path)
                            logger.info(
                                "Corrected incoming relation direction",
                                event_type="relation_direction_corrected",
                                component="QueryCorrector.correct_query",
                                original_path=original_partial_path,
                                corrected_path=corrected_partial_path
                            )
                        else:
                            # Logger.warning("No valid schema found for path, query cannot be corrected")
                            logger.warning(
                                "Query correction failed because no valid schema matched",
                                event_type="relation_direction_correction_failed",
                                component="QueryCorrector.correct_query",
                                path=original_partial_path,
                                left_node_labels=left_node_labels,
                                relation_types=relation_types,
                                right_node_labels=right_node_labels
                            )
                            return ""
                else:
                    is_legal = self.verify_schema(left_node_labels, relation_types, right_node_labels)
                    is_legal |= self.verify_schema(right_node_labels, relation_types, left_node_labels)
                    if not is_legal:
                        logger.warning(
                            "Query correction failed because no valid schema matched",
                            event_type="relation_direction_correction_failed",
                            component="QueryCorrector.correct_query",
                            path=original_partial_path,
                            left_node_labels=left_node_labels,
                            relation_types=relation_types,
                            right_node_labels=right_node_labels
                        )
                        return ""
                
                start_idx += len(match_dict["left_node"]) + len(match_dict["relation"]) + 2
        
        return query
    
    def __call__(self, query: str) -> str:
        """
        Correct the query to make it valid. If it cannot be corrected, return an empty string.
        Args:
            query: cypher query
        """
        return self.correct_query(query)

@validate_call
def correct_query(query: str, edge_schema: list) -> str:
    """
    Correct a Cypher query based on edge schemas
    
    Args:
        query: cypher query
        edge_schema: list of edge schemas
        
    Returns:
        Corrected query or empty string if cannot be corrected
    """

    logger.debug(
        "Started top-level query correction",
        event_type="query_correction_started",
        component="correct_query",
        initial_query=query,
        edge_schema=edge_schema
    )
    
    # in case generated text has non-cypher text, extract cypher from it
    query = extract_cypher(query)

    # prepare edge schemas
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
    
    schemas = load_schemas(str_schemas.strip(",").strip())
    query_corrector = QueryCorrector(schemas)
    
    corrected_query = query_corrector(query)
    if corrected_query:
       logger.info(
           "Query successfully corrected",
           event_type="query_corrected",
           component="correct_query",
           corrected_query=corrected_query
        )
    else:
        logger.warning(
            "Query could not be corrected",
            event_type="query_correction_failed",
            component="correct_query",
            initial_query=query
        )
    
    return corrected_query

@validate_call(validate_return=True)
def validate_query(query: str, cfg: Neo4jConfig, cypher_mode: Literal["vector_search", "db_search"], strict: bool = True) -> dict:
    """
    Validate the Cypher query syntax, schema, and properties.
    
    Args:
        query: Cypher query to validate.
        cfg: Neo4j configuration.
        strict: If True, infer a label only when one label fits all accessed properties; if False, pick the most compatible label and include all accessed properties.
        For more info, refer to CyVer documentation: https://gitlab.com/netmode/CyVer/-/wikis/home/PropertiesValidator
    Returns:
        Validation report with per-check status and metadata.
    """

    logger.debug(
        "Started query validation",
        event_type="query_validation_started",
        component="validate_query",
        query=query,
        strict=strict
    )

    # define driver
    driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_usr, cfg.neo4j_password))
    
    # validate syntax
    syntax_validator =  SyntaxValidator(driver)
    is_valid, syntax_metadata = syntax_validator.validate(query, database_name=cfg.neo4j_db_name)
    checks = {
        "syntax": {"ok": bool(is_valid), "message": syntax_metadata},
    }

    logger.debug(
        "Syntax validation completed",
        event_type="query_validation_step",
        component="validate_query",
        validator="syntax",
        ok=bool(is_valid),
        syntax_metadata=checks["syntax"]["message"]
    )
    
    # validate schema
    schema_validator =  SchemaValidator(driver)
    schema_score, schema_metadata = schema_validator.validate(query, database_name=cfg.neo4j_db_name)
    checks["schema"] = {"ok": schema_score >= 0.9 if isinstance(schema_score, (int, float)) else False, "message": schema_metadata}

    logger.debug(
        "Schema validation completed",
        event_type="query_validation_step",
        component="validate_query",
        validator="schema",
        ok=checks["schema"]["ok"],
        schema_metadata=checks["schema"]["message"]
    )
    
    if cypher_mode == "db_search":
        # validate properties
        properties_validator =  PropertiesValidator(driver)
        props_score, properties_metadata = properties_validator.validate(
            query, database_name=cfg.neo4j_db_name, strict=strict
        )
        
        checks["properties"] = {"ok": props_score >= 0.9 if isinstance(props_score, (int, float)) else False, "message": properties_metadata}

        logger.debug(
            "Properties validation completed",
            event_type="query_validation_step",
            component="validate_query",
            validator="properties",
            ok=checks["properties"]["ok"],
            properties_metadata=checks["properties"]["message"]
        )

        # close driver
        driver.close()
    
    else:
        checks["properties"] = {"ok": True, "message": "Properties validation skipped for vector_search mode."}


    result = {
        "ok": all(check["ok"] for check in checks.values()),
        "checks": checks,
    }

    logger.info(
        "Query validation completed",
        event_type="query_validation_completed",
        component="validate_query",
        ok=result["ok"],
        syntax_ok=checks["syntax"]["ok"],
        schema_ok=checks["schema"]["ok"],
        properties_ok=checks["properties"]["ok"]
    )

    return result

@validate_call(validate_return=True)
def validate_and_correct_query(query: str, cfg: Neo4jConfig, edge_schema: list, cypher_mode: Literal["vector_search", "db_search"], strict: bool = True) -> dict:
    """
    Validate a Cypher query and, if it passes, attempt to correct it using the provided edge schema. 
    Calls validate_query to assess syntax/schema/properties and correct_query to fix relationship directions that violate the schema.
    Args:
        query: Cypher query to validate and correct.
        cfg: Neo4j configuration.
        edge_schema: list of edge schemas for correction.
        cypher_mode: The mode of Cypher query execution.
        strict: If True, infer a label only when one label fits all accessed properties; if False, pick the most compatible label and include all accessed properties.
    Returns:
        A dictionary containing the validation result and the corrected query if validation and correction are successful.
        The dictionary has the following structure:
        {
            "ok": bool,
            "checks": dict,
            "corrected_query": Optional[str]
        }
    """
    # ---------------------------
    # MAYBE PUT CORRECTION BEFORE VALIDATION?
    # BECAUSE FOR SOME CASES CORRECTION CAN FIX SCHEMA ERRORS, SUCH AS `WrongDirectionPathWarning` FROM VALIDATION STEP.
    # ---------------------------
    logger.debug(
        "Started query validation and correction",
        event_type="validate_and_correct_query_started",
        component="validate_and_correct_query",
        query=query,
        edge_schema=edge_schema,
        strict=strict
    )
    
    result = validate_query(query, cfg, cypher_mode, strict)
    result["corrected_query"] = None

    if result["ok"]:
        # if the query is validated, correct the query
        corrected_query = correct_query(query, edge_schema)

        # if correction fails, mark it as schema problem
        if not corrected_query:
            result["ok"] = False
            result["checks"]["schema"] = {
                "ok": False,
                "message": [
                    "Schema correction failed: The query's relationship directions or node labels do not match any allowed edge schema."
                ]
            }

            logger.warning(
                "Query correction failed after successful validation",
                event_type="query_correction_failed_after_validation",
                component="validate_and_correct_query",
                initial_query=query,
                edge_schema=edge_schema,
                validation_checks=result["checks"]
            )
        
        # if correction succeeds, add corrected query to result
        else:
            result["corrected_query"] = corrected_query

            logger.info(
                "Query successfully validated and corrected",
                event_type="query_validated_and_corrected",
                component="validate_and_correct_query",
                initial_query=query,
                corrected_query=corrected_query,
                edge_schema=edge_schema,
                validation_checks=result["checks"]
            )
    else:
        logger.warning(
            "Query validation failed",
            event_type="query_validation_failed",
            component="validate_and_correct_query",
            query=query,
            validation_checks=result["checks"]
        )
    
    return result

    
