"""
Neo4j Query Corrector

This module provides query correction functionality to fix Cypher queries
based on the graph schema. It validates and corrects relationship directions.

Enhanced with ultra-detailed logging for all correction steps.
"""

import json
import re
import traceback
from collections import namedtuple
from time import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import validate_call

from .utils import Logger
from .structured_logger import (
    QueryCorrectionLog,
    get_structured_logger,
    log_query_correction,
    get_current_query_log,
)


@validate_call
def extract_cypher(text: str) -> str:
    """
    Extract Cypher code from a text that may contain markdown code blocks.
    
    Args:
        text: Text to extract Cypher code from.
        
    Returns:
        Cypher code extracted from the text.
    """
    Logger.debug(
        "[EXTRACT_CYPHER] Extracting Cypher code from text",
        extra={"text_length": len(text), "text_preview": text[:100]}
    )
    
    # The pattern to find Cypher code enclosed in triple backticks
    pattern = r"```(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    
    if matches:
        result = matches[0]
        Logger.debug(
            "[EXTRACT_CYPHER] Found code block",
            extra={"extracted_length": len(result)}
        )
    else:
        result = text
        Logger.debug("[EXTRACT_CYPHER] No code block found, using raw text")
    
    return result


Schema = namedtuple("Schema", ["left_node", "relation", "right_node"])


@validate_call
def load_schemas(str_schemas: str) -> List[Schema]:
    """
    Parse schema string into list of Schema namedtuples.
    
    Args:
        str_schemas: String representation of schemas
        
    Returns:
        List of Schema namedtuples
    """
    Logger.debug(
        "[LOAD_SCHEMAS] Loading schemas from string",
        extra={"string_length": len(str_schemas), "preview": str_schemas[:100]}
    )
    
    values = str_schemas.replace("(", "").replace(")", "").split(",")
    schemas = []
    
    for i in range(len(values) // 3):
        schema = Schema(
            values[i * 3].strip(),
            values[i * 3 + 1].strip(),
            values[i * 3 + 2].strip()
        )
        schemas.append(schema)
    
    Logger.debug(
        "[LOAD_SCHEMAS] Schemas loaded",
        extra={"schema_count": len(schemas)}
    )
    
    return schemas


class QueryCorrector:
    """
    QueryCorrector class for validating and correcting Cypher queries.
    
    Validates relationship directions against the graph schema and
    corrects them if necessary. Includes detailed logging of all
    correction steps.
    """
    
    property_pattern = re.compile(r"\{.+?\}")
    node_pattern = re.compile(r"\(.+?\)")
    path_pattern = re.compile(
        r"(\([^\,\(\)]*?(\{.+\})?[^\,\(\)]*?\))(<?-)(\[.*?\])?(->?)(\([^\,\(\)]*?(\{.+\})?[^\,\(\)]*?\))"
    )
    node_relation_node_pattern = re.compile(
        r"(\()+(?P<left_node>[^()]*?)\)(?P<relation>.*?)\((?P<right_node>[^()]*?)(\))+"
    )
    relation_type_pattern = re.compile(r":(?P<relation_type>.+?)?(\{.+\})?]")
    
    def __init__(self, schemas: List[Schema]):
        """
        Initialize the QueryCorrector with graph schemas.
        
        Args:
            schemas: List of Schema namedtuples representing valid relationships
        """
        self.schemas = schemas
        self.correction_log = QueryCorrectionLog()
        self.corrections: List[Dict[str, Any]] = []
        
        Logger.debug(
            "[QUERY_CORRECTOR_INIT] QueryCorrector initialized",
            extra={"schema_count": len(schemas)}
        )
    
    def clean_node(self, node: str) -> str:
        """Clean a node string by removing properties and parentheses."""
        original = node
        node = re.sub(self.property_pattern, "", node)
        node = node.replace("(", "").replace(")", "").strip()
        
        if original != node:
            Logger.debug(
                "[CLEAN_NODE] Node cleaned",
                extra={"original": original, "cleaned": node}
            )
        
        return node
    
    def detect_node_variables(self, query: str) -> Dict[str, List[str]]:
        """
        Detect all node variables and their labels in the query.
        
        Args:
            query: Cypher query string
            
        Returns:
            Dictionary mapping variable names to their labels
        """
        Logger.debug("[DETECT_NODE_VARS] Starting node variable detection")
        
        nodes = re.findall(self.node_pattern, query)
        nodes = [self.clean_node(node) for node in nodes]
        
        result: Dict[str, List[str]] = {}
        for node in nodes:
            parts = node.split(":")
            if parts == "":
                continue
            variable = parts[0]
            if variable not in result:
                result[variable] = []
            result[variable] += parts[1:]
        
        Logger.debug(
            "[DETECT_NODE_VARS] Node variables detected",
            extra={
                "variable_count": len(result),
                "variables": {k: v for k, v in list(result.items())[:5]}  # First 5
            }
        )
        
        return result
    
    def extract_paths(self, query: str) -> List[str]:
        """
        Extract all relationship paths from the query.
        
        Args:
            query: Cypher query string
            
        Returns:
            List of path strings
        """
        Logger.debug("[EXTRACT_PATHS] Starting path extraction")
        
        paths = []
        idx = 0
        
        while matched := self.path_pattern.findall(query[idx:]):
            matched = matched[0]
            matched = [
                m for i, m in enumerate(matched) if i not in [1, len(matched) - 1]
            ]
            path = "".join(matched)
            idx = query.find(path) + len(path) - len(matched[-1])
            paths.append(path)
        
        Logger.debug(
            "[EXTRACT_PATHS] Paths extracted",
            extra={
                "path_count": len(paths),
                "paths": [p[:50] for p in paths]  # First 50 chars of each
            }
        )
        
        return paths
    
    def judge_direction(self, relation: str) -> str:
        """
        Determine the direction of a relationship.
        
        Args:
            relation: Relationship string
            
        Returns:
            Direction: "INCOMING", "OUTGOING", or "BIDIRECTIONAL"
        """
        direction = "BIDIRECTIONAL"
        if relation[0] == "<":
            direction = "INCOMING"
        if relation[-1] == ">":
            direction = "OUTGOING"
        
        Logger.debug(
            "[JUDGE_DIRECTION] Direction determined",
            extra={"relation": relation[:30], "direction": direction}
        )
        
        return direction
    
    def extract_node_variable(self, part: str) -> Optional[str]:
        """Extract the variable name from a node string."""
        part = part.lstrip("(").rstrip(")")
        idx = part.find(":")
        if idx != -1:
            part = part[:idx]
        return None if part == "" else part
    
    def detect_labels(self, str_node: str, node_variable_dict: Dict) -> List[str]:
        """
        Detect labels for a node.
        
        Args:
            str_node: Node string
            node_variable_dict: Dictionary of known node variables
            
        Returns:
            List of labels
        """
        splitted = str_node.split(":")
        variable = splitted[0]
        labels = []
        
        if variable in node_variable_dict:
            labels = node_variable_dict[variable]
        elif variable == "" and len(splitted) > 1:
            labels = splitted[1:]
        
        Logger.debug(
            "[DETECT_LABELS] Labels detected",
            extra={"node": str_node, "labels": labels}
        )
        
        return labels
    
    def verify_schema(
        self,
        from_node_labels: List[str],
        relation_types: List[str],
        to_node_labels: List[str]
    ) -> bool:
        """
        Verify if a relationship pattern matches any valid schema.
        
        Args:
            from_node_labels: Labels of the source node
            relation_types: Relationship types
            to_node_labels: Labels of the target node
            
        Returns:
            True if valid schema found, False otherwise
        """
        valid_schemas = self.schemas
        schemas_checked = len(valid_schemas)
        
        if from_node_labels:
            from_node_labels = [label.strip('`') for label in from_node_labels]
            valid_schemas = [s for s in valid_schemas if s[0] in from_node_labels]
        
        if to_node_labels:
            to_node_labels = [label.strip('`') for label in to_node_labels]
            valid_schemas = [s for s in valid_schemas if s[2] in to_node_labels]
        
        if relation_types:
            relation_types = [t.strip('`') for t in relation_types]
            valid_schemas = [s for s in valid_schemas if s[1] in relation_types]
        
        is_valid = len(valid_schemas) > 0
        
        Logger.debug(
            "[VERIFY_SCHEMA] Schema verification",
            extra={
                "from_labels": from_node_labels,
                "relation_types": relation_types,
                "to_labels": to_node_labels,
                "schemas_checked": schemas_checked,
                "matching_schemas": len(valid_schemas),
                "is_valid": is_valid
            }
        )
        
        return is_valid
    
    def detect_relation_types(self, str_relation: str) -> Tuple[str, List[str]]:
        """
        Detect the direction and types of a relationship.
        
        Args:
            str_relation: Relationship string
            
        Returns:
            Tuple of (direction, list of relation types)
        """
        relation_direction = self.judge_direction(str_relation)
        relation_type = self.relation_type_pattern.search(str_relation)
        
        if relation_type is None or relation_type.group('relation_type') is None:
            Logger.debug(
                "[DETECT_RELATION_TYPES] No relation type found",
                extra={"relation": str_relation[:50]}
            )
            return relation_direction, []
        
        relation_types = [
            t.strip().strip('!') 
            for t in relation_type.group('relation_type').split("|")
        ]
        
        Logger.debug(
            "[DETECT_RELATION_TYPES] Relation types detected",
            extra={
                "relation": str_relation[:50],
                "direction": relation_direction,
                "types": relation_types
            }
        )
        
        return relation_direction, relation_types
    
    def correct_query(self, query: str) -> str:
        """
        Correct a Cypher query by fixing relationship directions.
        
        Args:
            query: Cypher query to correct
            
        Returns:
            Corrected query, or empty string if uncorrectable
        """
        correction_start_time = time()
        self.correction_log.original_query = query
        self.corrections = []
        
        Logger.info(
            "[CORRECT_QUERY] Starting query correction",
            extra={
                "query_length": len(query),
                "query_preview": query[:200]
            }
        )
        
        try:
            node_variable_dict = self.detect_node_variables(query)
            paths = self.extract_paths(query)
            
            Logger.info(
                "[CORRECT_QUERY] Query analysis",
                extra={
                    "node_variables_count": len(node_variable_dict),
                    "paths_count": len(paths)
                }
            )
            
            path_number = 0
            for path in paths:
                path_number += 1
                original_path = path
                
                Logger.debug(
                    f"[CORRECT_QUERY] Processing path {path_number}/{len(paths)}",
                    extra={"path": original_path[:100]}
                )
                
                start_idx = 0
                while start_idx < len(path):
                    match_res = re.match(self.node_relation_node_pattern, path[start_idx:])
                    if match_res is None:
                        break
                    
                    start_idx += match_res.start()
                    match_dict = match_res.groupdict()
                    
                    left_node_labels = self.detect_labels(
                        match_dict["left_node"], node_variable_dict
                    )
                    right_node_labels = self.detect_labels(
                        match_dict["right_node"], node_variable_dict
                    )
                    
                    end_idx = (
                        start_idx + 4 + 
                        len(match_dict["left_node"]) + 
                        len(match_dict["relation"]) + 
                        len(match_dict["right_node"])
                    )
                    original_partial_path = original_path[start_idx:end_idx + 1]
                    relation_direction, relation_types = self.detect_relation_types(
                        match_dict["relation"]
                    )
                    
                    # Skip wildcard relations
                    if relation_types and '*' in ''.join(relation_types):
                        Logger.debug(
                            "[CORRECT_QUERY] Skipping wildcard relation",
                            extra={"relation_types": relation_types}
                        )
                        start_idx += len(match_dict["left_node"]) + len(match_dict["relation"]) + 2
                        continue
                    
                    correction_info = {
                        "path_number": path_number,
                        "left_node": match_dict["left_node"],
                        "left_labels": left_node_labels,
                        "relation": match_dict["relation"],
                        "relation_types": relation_types,
                        "relation_direction": relation_direction,
                        "right_node": match_dict["right_node"],
                        "right_labels": right_node_labels,
                        "original_partial_path": original_partial_path,
                    }
                    
                    if relation_direction == "OUTGOING":
                        is_legal = self.verify_schema(
                            left_node_labels, relation_types, right_node_labels
                        )
                        correction_info["schema_check"] = "left->right"
                        correction_info["initial_valid"] = is_legal
                        
                        if not is_legal:
                            # Try reverse direction
                            is_legal = self.verify_schema(
                                right_node_labels, relation_types, left_node_labels
                            )
                            correction_info["reverse_valid"] = is_legal
                            
                            if is_legal:
                                # Apply correction
                                corrected_relation = "<" + match_dict["relation"][:-1]
                                corrected_partial_path = original_partial_path.replace(
                                    match_dict["relation"], corrected_relation
                                )
                                query = query.replace(original_partial_path, corrected_partial_path)
                                
                                correction_info["action"] = "reversed_to_incoming"
                                correction_info["corrected_relation"] = corrected_relation
                                correction_info["corrected_partial_path"] = corrected_partial_path
                                
                                Logger.info(
                                    "[CORRECT_QUERY] Direction corrected: outgoing -> incoming",
                                    extra=correction_info
                                )
                                
                                self.corrections.append(correction_info)
                            else:
                                # Cannot correct
                                correction_info["action"] = "failed"
                                correction_info["failure_reason"] = "no_valid_schema"
                                self.corrections.append(correction_info)
                                
                                Logger.warning(
                                    "[CORRECT_QUERY] No valid schema found for outgoing path",
                                    extra=correction_info
                                )
                                
                                self._finalize_correction_log(
                                    "", 
                                    correction_start_time, 
                                    success=False,
                                    failure_reason="No valid schema found for path"
                                )
                                return ""
                    
                    elif relation_direction == "INCOMING":
                        is_legal = self.verify_schema(
                            right_node_labels, relation_types, left_node_labels
                        )
                        correction_info["schema_check"] = "right->left"
                        correction_info["initial_valid"] = is_legal
                        
                        if not is_legal:
                            # Try reverse direction
                            is_legal = self.verify_schema(
                                left_node_labels, relation_types, right_node_labels
                            )
                            correction_info["reverse_valid"] = is_legal
                            
                            if is_legal:
                                # Apply correction
                                corrected_relation = match_dict["relation"][1:] + ">"
                                corrected_partial_path = original_partial_path.replace(
                                    match_dict["relation"], corrected_relation
                                )
                                query = query.replace(original_partial_path, corrected_partial_path)
                                
                                correction_info["action"] = "reversed_to_outgoing"
                                correction_info["corrected_relation"] = corrected_relation
                                correction_info["corrected_partial_path"] = corrected_partial_path
                                
                                Logger.info(
                                    "[CORRECT_QUERY] Direction corrected: incoming -> outgoing",
                                    extra=correction_info
                                )
                                
                                self.corrections.append(correction_info)
                            else:
                                # Cannot correct
                                correction_info["action"] = "failed"
                                correction_info["failure_reason"] = "no_valid_schema"
                                self.corrections.append(correction_info)
                                
                                Logger.warning(
                                    "[CORRECT_QUERY] No valid schema found for incoming path",
                                    extra=correction_info
                                )
                                
                                self._finalize_correction_log(
                                    "", 
                                    correction_start_time, 
                                    success=False,
                                    failure_reason="No valid schema found for path"
                                )
                                return ""
                    
                    else:  # BIDIRECTIONAL
                        is_legal = self.verify_schema(
                            left_node_labels, relation_types, right_node_labels
                        )
                        is_legal |= self.verify_schema(
                            right_node_labels, relation_types, left_node_labels
                        )
                        correction_info["schema_check"] = "bidirectional"
                        correction_info["initial_valid"] = is_legal
                        
                        if not is_legal:
                            correction_info["action"] = "failed"
                            correction_info["failure_reason"] = "no_valid_schema_bidirectional"
                            self.corrections.append(correction_info)
                            
                            Logger.warning(
                                "[CORRECT_QUERY] No valid schema found for bidirectional path",
                                extra=correction_info
                            )
                            
                            self._finalize_correction_log(
                                "", 
                                correction_start_time, 
                                success=False,
                                failure_reason="No valid schema found for bidirectional path"
                            )
                            return ""
                    
                    start_idx += len(match_dict["left_node"]) + len(match_dict["relation"]) + 2
            
            # Success
            self._finalize_correction_log(query, correction_start_time, success=True)
            
            Logger.info(
                "[CORRECT_QUERY] Query correction completed successfully",
                extra={
                    "corrections_made": len(self.corrections),
                    "final_query_preview": query[:200]
                }
            )
            
            return query
            
        except Exception as e:
            Logger.exception(
                "[CORRECT_QUERY] Error during query correction",
                exc=e,
                context={"query": query[:200]}
            )
            
            self._finalize_correction_log(
                "", 
                correction_start_time, 
                success=False,
                failure_reason=f"Exception: {str(e)}"
            )
            raise
    
    def _finalize_correction_log(
        self, 
        final_query: str, 
        start_time: float,
        success: bool,
        failure_reason: Optional[str] = None
    ):
        """Finalize and store the correction log."""
        duration_ms = (time() - start_time) * 1000
        
        self.correction_log.final_query = final_query
        self.correction_log.corrections = self.corrections
        self.correction_log.success = success
        self.correction_log.failure_reason = failure_reason
        self.correction_log.schemas_checked = len(self.schemas)
        self.correction_log.duration_ms = duration_ms
        
        # Log to structured logger
        log_query_correction(self.correction_log)
        
        Logger.debug(
            "[CORRECT_QUERY] Correction log finalized",
            extra={
                "success": success,
                "corrections_count": len(self.corrections),
                "duration_ms": duration_ms
            }
        )
    
    def __call__(self, query: str) -> str:
        """Correct the query to make it valid."""
        return self.correct_query(query)


@validate_call
def correct_query(query: str, edge_schema: list) -> str:
    """
    Main function to correct a Cypher query based on edge schemas.
    
    This is the primary entry point for query correction.
    
    Args:
        query: Cypher query to correct
        edge_schema: List of edge schema strings
        
    Returns:
        Corrected query or empty string if cannot be corrected
    """
    correction_start_time = time()
    
    Logger.info(
        "[CORRECT_QUERY_MAIN] Starting query correction process",
        extra={
            "query_length": len(query),
            "query_preview": query[:200],
            "edge_schema_count": len(edge_schema)
        }
    )
    
    try:
        # Extract cypher from potential markdown
        query = extract_cypher(query.strip("\n"))
        
        # Parse edge schemas
        str_schemas = ""
        to_be_replaced = ["(", ")", ":", "[", "]", ">", "<"]
        
        for e in edge_schema:
            splitted = e.strip().split("-")
            splitted_corrected = []
            for s in splitted:
                for t in to_be_replaced:
                    s = s.replace(t, "")
                splitted_corrected.append(s)
            add = ", (" + ", ".join(splitted_corrected) + ")"
            str_schemas += add
        
        schemas = load_schemas(str_schemas.strip(",").strip())
        
        Logger.debug(
            "[CORRECT_QUERY_MAIN] Schemas parsed",
            extra={"schema_count": len(schemas)}
        )
        
        # Create corrector and run
        query_corrector = QueryCorrector(schemas)
        corrected_query = query_corrector(query)
        
        duration_ms = (time() - correction_start_time) * 1000
        
        if corrected_query:
            Logger.info(
                "[CORRECT_QUERY_MAIN] Query successfully corrected",
                extra={
                    "original_query_preview": query[:100],
                    "corrected_query_preview": corrected_query[:100],
                    "query_changed": query != corrected_query,
                    "duration_ms": duration_ms
                }
            )
        else:
            Logger.warning(
                "[CORRECT_QUERY_MAIN] Query could not be corrected",
                extra={
                    "original_query_preview": query[:100],
                    "duration_ms": duration_ms
                }
            )
        
        return corrected_query
        
    except Exception as e:
        duration_ms = (time() - correction_start_time) * 1000
        
        Logger.exception(
            "[CORRECT_QUERY_MAIN] Error in query correction",
            exc=e,
            context={
                "query_preview": query[:100],
                "duration_ms": duration_ms
            }
        )
        raise
