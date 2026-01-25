"""
Neo4j Query Executor and Schema Extractor

This module provides functionality for executing Cypher queries against
Neo4j and extracting graph schema information.

Enhanced with ultra-detailed logging for all database operations.
"""

import json
import os
import re
import traceback
from time import time
from typing import Any, Dict, List, Optional, Union

import neo4j
from pydantic import validate_call

from .utils import Logger, timer_func, detailed_timer
from .structured_logger import (
    Neo4jExecutionLog,
    get_structured_logger,
    log_neo4j_execution,
    get_current_query_log,
)


# Schema extraction queries
node_properties_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE NOT type = "RELATIONSHIP" AND elementType = "node"
WITH label AS nodeLabels, collect({property:property, type:type}) AS properties
RETURN {labels: nodeLabels, properties: properties} AS output
"""

rel_properties_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE NOT type = "RELATIONSHIP" AND elementType = "relationship"
WITH label AS nodeLabels, collect({property:property, type:type}) AS properties
RETURN {type: nodeLabels, properties: properties} AS output
"""

node_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE NOT type = "RELATIONSHIP" AND elementType = "node"
WITH collect(distinct label) AS nodeLabels
RETURN {labels: nodeLabels} AS output
"""

rel_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE type = "RELATIONSHIP" AND elementType = "node"
UNWIND other AS other_node
RETURN "(:" + label + ")-[:" + property + "]->(:" + toString(other_node) + ")" AS output
"""


class Neo4jGraphHelper:
    """
    Helper class for Neo4j database operations.
    
    Provides methods for:
    - Extracting graph schema
    - Executing Cypher queries
    - Managing vector indexes
    
    All operations include detailed logging for debugging and analysis.
    """
    
    def __init__(
        self,
        URI: str,
        user: str,
        password: str,
        db_name: str,
        reset_schema: bool,
        create_vector_indexes: bool,
        delete_vector_indexes: bool = False,
    ):
        """
        Initialize the Neo4jGraphHelper.
        
        Args:
            URI: Neo4j connection URI
            user: Database username
            password: Database password
            db_name: Database name
            reset_schema: Whether to reset the cached schema
            create_vector_indexes: Whether to create vector indexes
            delete_vector_indexes: Whether to delete existing vector indexes
        """
        self.URI = URI
        self.AUTH = (user, password)
        self.db_name = db_name
        
        Logger.info(
            "[NEO4J_HELPER_INIT] Initializing Neo4jGraphHelper",
            extra={
                "uri": URI,
                "database": db_name,
                "reset_schema": reset_schema,
                "create_vector_indexes": create_vector_indexes,
                "delete_vector_indexes": delete_vector_indexes
            }
        )
        
        # Test connection
        self._test_connection()

        if reset_schema:
            Logger.info("[NEO4J_HELPER_INIT] Resetting database schema cache")
            self.reset_db_schema()

        if create_vector_indexes:
            Logger.info("[NEO4J_HELPER_INIT] Creating vector indexes")
            self.create_vector_indexes()

        if delete_vector_indexes:
            Logger.info("[NEO4J_HELPER_INIT] Deleting vector indexes")
            self.delete_vector_indexes()
        
        Logger.info("[NEO4J_HELPER_INIT] Initialization complete")
    
    def _test_connection(self) -> bool:
        """Test the Neo4j connection."""
        try:
            connection_start = time()
            with neo4j.GraphDatabase.driver(self.URI, auth=self.AUTH) as driver:
                driver.verify_connectivity()
            connection_time_ms = (time() - connection_start) * 1000
            
            Logger.info(
                "[NEO4J_CONNECTION] Connection test successful",
                extra={
                    "uri": self.URI,
                    "database": self.db_name,
                    "connection_time_ms": connection_time_ms
                }
            )
            return True
        except Exception as e:
            Logger.exception(
                "[NEO4J_CONNECTION] Connection test failed",
                exc=e,
                context={"uri": self.URI, "database": self.db_name}
            )
            raise

    @timer_func
    def create_graph_schema_variables(self) -> Dict[str, Any]:
        """
        Create or load graph schema variables.
        
        Loads from cache if available, otherwise extracts from database.
        
        Returns:
            Dictionary containing nodes, node_properties, edges, edge_properties
        """
        schema_start_time = time()
        file_path = os.path.join(os.getcwd(), "graph_schema.json")
        
        Logger.info(
            "[SCHEMA_EXTRACTION] Starting schema extraction",
            extra={"cache_path": file_path}
        )
        
        if os.path.isfile(file_path):
            Logger.info("[SCHEMA_EXTRACTION] Loading schema from cache")
            try:
                with open(file_path) as fp:
                    schema = json.load(fp)
                
                schema_time_ms = (time() - schema_start_time) * 1000
                Logger.info(
                    "[SCHEMA_EXTRACTION] Schema loaded from cache",
                    extra={
                        "node_types": len(schema.get("nodes", [])),
                        "edge_types": len(schema.get("edges", [])),
                        "load_time_ms": schema_time_ms
                    }
                )
                return schema
            except Exception as e:
                Logger.warning(
                    "[SCHEMA_EXTRACTION] Failed to load cached schema, extracting from database",
                    extra={"error": str(e)}
                )
        
        Logger.info("[SCHEMA_EXTRACTION] Extracting schema from database")
        
        try:
            with neo4j.GraphDatabase.driver(self.URI, auth=self.AUTH) as driver:
                # Node property filtering
                Logger.debug("[SCHEMA_EXTRACTION] Extracting node properties")
                query_start = time()
                records, _, _ = driver.execute_query(
                    node_properties_query, database_=self.db_name
                )
                node_property_results = [res["output"] for res in records]
                
                for n in node_property_results:
                    n["properties"] = [
                        prop
                        for prop in n["properties"]
                        if prop["property"] != "preferred_id"
                    ]
                
                Logger.debug(
                    "[SCHEMA_EXTRACTION] Node properties extracted",
                    extra={
                        "count": len(node_property_results),
                        "time_ms": (time() - query_start) * 1000
                    }
                )

                # Node type selection
                Logger.debug("[SCHEMA_EXTRACTION] Extracting node types")
                query_start = time()
                records, _, _ = driver.execute_query(node_query, database_=self.db_name)
                node_results_filtered = [res["output"] for res in records]
                
                Logger.debug(
                    "[SCHEMA_EXTRACTION] Node types extracted",
                    extra={
                        "count": len(node_results_filtered),
                        "time_ms": (time() - query_start) * 1000
                    }
                )

                # Relation type filtering
                Logger.debug("[SCHEMA_EXTRACTION] Extracting relationship types")
                query_start = time()
                records, _, _ = driver.execute_query(rel_query, database_=self.db_name)
                edge_results_filtered = []
                for res in records:
                    edge_results_filtered.append(res.values()[0])
                
                Logger.debug(
                    "[SCHEMA_EXTRACTION] Relationship types extracted",
                    extra={
                        "count": len(edge_results_filtered),
                        "time_ms": (time() - query_start) * 1000
                    }
                )

                # Relation property filtering
                Logger.debug("[SCHEMA_EXTRACTION] Extracting relationship properties")
                query_start = time()
                records, _, _ = driver.execute_query(
                    rel_properties_query, database_=self.db_name
                )
                edge_properties_results_filtered = [res.values()[0] for res in records]
                
                Logger.debug(
                    "[SCHEMA_EXTRACTION] Relationship properties extracted",
                    extra={
                        "count": len(edge_properties_results_filtered),
                        "time_ms": (time() - query_start) * 1000
                    }
                )

            schema = {
                "nodes": node_results_filtered,
                "node_properties": node_property_results,
                "edges": edge_results_filtered,
                "edge_properties": edge_properties_results_filtered,
            }

            # Cache the schema
            if not os.path.isfile(file_path):
                try:
                    with open(file_path, "w") as fp:
                        json.dump(schema, fp)
                    Logger.info("[SCHEMA_EXTRACTION] Schema cached to file")
                except Exception as e:
                    Logger.warning(
                        "[SCHEMA_EXTRACTION] Failed to cache schema",
                        extra={"error": str(e)}
                    )

            schema_time_ms = (time() - schema_start_time) * 1000
            Logger.info(
                "[SCHEMA_EXTRACTION] Schema extraction complete",
                extra={
                    "node_types": len(node_results_filtered),
                    "node_properties_count": len(node_property_results),
                    "edge_types": len(edge_results_filtered),
                    "edge_properties_count": len(edge_properties_results_filtered),
                    "total_time_ms": schema_time_ms
                }
            )

            return schema
            
        except Exception as e:
            schema_time_ms = (time() - schema_start_time) * 1000
            Logger.exception(
                "[SCHEMA_EXTRACTION] Schema extraction failed",
                exc=e,
                context={"time_ms": schema_time_ms}
            )
            raise

    def reset_db_schema(self) -> None:
        """Reset the cached database schema."""
        file_path = os.path.join(os.getcwd(), "graph_schema.json")
        
        if os.path.isfile(file_path):
            os.remove(file_path)
            Logger.info(
                "[SCHEMA_RESET] Schema cache deleted",
                extra={"path": file_path}
            )
        else:
            Logger.debug(
                "[SCHEMA_RESET] No schema cache to delete",
                extra={"path": file_path}
            )

    @validate_call
    def execute(self, query: str, top_k: int = 5) -> Union[List[Dict], str]:
        """
        Execute a Cypher query against the Neo4j database.
        
        Args:
            query: Cypher query to execute
            top_k: Maximum number of results to return
            
        Returns:
            List of result dictionaries, or error message string
        """
        execution_log = Neo4jExecutionLog()
        execution_start_time = time()
        
        original_query = query
        execution_log.query = original_query
        execution_log.top_k = top_k
        
        Logger.info(
            "[NEO4J_EXECUTE] Starting query execution",
            extra={
                "query_preview": query[:200],
                "query_length": len(query),
                "top_k": top_k
            }
        )
        
        try:
            # Apply LIMIT clause
            if "LIMIT" in query:
                regex_pattern = r"\bLIMIT\s+\d+\b"
                query = re.sub(regex_pattern, f" LIMIT {top_k}", query.strip().strip("\n"))
                Logger.debug(
                    "[NEO4J_EXECUTE] Replaced existing LIMIT clause",
                    extra={"new_limit": top_k}
                )
            else:
                query = query.strip().strip("\n") + f" LIMIT {top_k}"
                Logger.debug(
                    "[NEO4J_EXECUTE] Added LIMIT clause",
                    extra={"limit": top_k}
                )
            
            execution_log.query_with_limit = query
            
            # Execute query
            Logger.debug("[NEO4J_EXECUTE] Connecting to database")
            connection_start = time()
            
            with neo4j.GraphDatabase.driver(self.URI, auth=self.AUTH) as driver:
                connection_time_ms = (time() - connection_start) * 1000
                execution_log.connection_status = "connected"
                
                Logger.debug(
                    "[NEO4J_EXECUTE] Connection established",
                    extra={"connection_time_ms": connection_time_ms}
                )
                
                query_start = time()
                records, summary, keys = driver.execute_query(
                    query, database_=self.db_name, routing_="r"
                )
                query_time_ms = (time() - query_start) * 1000
                
                Logger.debug(
                    "[NEO4J_EXECUTE] Query executed",
                    extra={
                        "query_time_ms": query_time_ms,
                        "record_count": len(records) if records else 0
                    }
                )
                
                if not records:
                    execution_log.result_count = 0
                    execution_log.execution_time_ms = (time() - execution_start_time) * 1000
                    
                    Logger.info(
                        "[NEO4J_EXECUTE] Query returned no results",
                        extra={
                            "query_preview": query[:100],
                            "execution_time_ms": execution_log.execution_time_ms
                        }
                    )
                    
                    log_neo4j_execution(execution_log)
                    return "Given cypher query did not return any result"

                # Process results
                results = []
                for index, res in enumerate(records):
                    data = res.data()
                    data = self.remove_embedding_attribute(data)
                    results.append(data)

                    if top_k and index >= top_k:
                        break
                
                execution_time_ms = (time() - execution_start_time) * 1000
                
                # Update execution log
                execution_log.result_count = len(results)
                execution_log.execution_time_ms = execution_time_ms
                execution_log.result_sample = results[:3]  # First 3 results as sample
                execution_log.full_results = results
                
                Logger.info(
                    "[NEO4J_EXECUTE] Query execution successful",
                    extra={
                        "result_count": len(results),
                        "execution_time_ms": execution_time_ms,
                        "query_time_ms": query_time_ms,
                        "connection_time_ms": connection_time_ms,
                        "result_sample": str(results[:2])[:300]  # First 2 results, truncated
                    }
                )
                
                # Log detailed results at DEBUG level
                Logger.debug(
                    "[NEO4J_EXECUTE] Full results",
                    extra={"results": str(results)[:2000]}
                )
                
                log_neo4j_execution(execution_log)
                return results
                
        except neo4j.exceptions.CypherSyntaxError as e:
            execution_time_ms = (time() - execution_start_time) * 1000
            
            execution_log.error = f"CypherSyntaxError: {str(e)}"
            execution_log.error_traceback = traceback.format_exc()
            execution_log.execution_time_ms = execution_time_ms
            execution_log.connection_status = "error"
            
            Logger.error(
                "[NEO4J_EXECUTE] Cypher syntax error",
                extra={
                    "error": str(e),
                    "query_preview": query[:200],
                    "execution_time_ms": execution_time_ms
                }
            )
            
            log_neo4j_execution(execution_log)
            raise
            
        except neo4j.exceptions.ClientError as e:
            execution_time_ms = (time() - execution_start_time) * 1000
            
            execution_log.error = f"ClientError: {str(e)}"
            execution_log.error_traceback = traceback.format_exc()
            execution_log.execution_time_ms = execution_time_ms
            execution_log.connection_status = "error"
            
            Logger.error(
                "[NEO4J_EXECUTE] Neo4j client error",
                extra={
                    "error": str(e),
                    "query_preview": query[:200],
                    "execution_time_ms": execution_time_ms
                }
            )
            
            log_neo4j_execution(execution_log)
            raise
            
        except neo4j.exceptions.DatabaseError as e:
            execution_time_ms = (time() - execution_start_time) * 1000
            
            execution_log.error = f"DatabaseError: {str(e)}"
            execution_log.error_traceback = traceback.format_exc()
            execution_log.execution_time_ms = execution_time_ms
            execution_log.connection_status = "error"
            
            Logger.error(
                "[NEO4J_EXECUTE] Neo4j database error",
                extra={
                    "error": str(e),
                    "query_preview": query[:200],
                    "execution_time_ms": execution_time_ms
                }
            )
            
            log_neo4j_execution(execution_log)
            raise
            
        except Exception as e:
            execution_time_ms = (time() - execution_start_time) * 1000
            
            execution_log.error = f"{type(e).__name__}: {str(e)}"
            execution_log.error_traceback = traceback.format_exc()
            execution_log.execution_time_ms = execution_time_ms
            execution_log.connection_status = "error"
            
            Logger.exception(
                "[NEO4J_EXECUTE] Query execution failed",
                exc=e,
                context={
                    "query_preview": query[:200],
                    "execution_time_ms": execution_time_ms
                }
            )
            
            log_neo4j_execution(execution_log)
            raise

    def remove_embedding_attribute(self, data: Dict) -> Dict:
        """
        Remove embedding attributes from result data.
        
        Embeddings are large arrays that are not useful in results.
        
        Args:
            data: Result dictionary
            
        Returns:
            Dictionary with embedding attributes removed
        """
        keys_to_delete = set()
        embeddings_removed = 0

        for k, v in data.items():
            if "embedding" in k:
                keys_to_delete.add(k)
                embeddings_removed += 1
            elif isinstance(v, dict):
                data[k] = self.remove_embedding_attribute(v)
        
        for k in keys_to_delete:
            del data[k]
        
        if embeddings_removed > 0:
            Logger.debug(
                "[NEO4J_EXECUTE] Removed embedding attributes",
                extra={"count": embeddings_removed}
            )

        return data

    @validate_call
    def create_vector_indexes(self, similarity_function: str = "cosine") -> bool:
        """
        Create vector indexes for similarity search.
        
        Args:
            similarity_function: Similarity function (cosine, euclidean, etc.)
            
        Returns:
            True if successful
        """
        index_start_time = time()
        
        Logger.info(
            "[VECTOR_INDEX] Creating vector indexes",
            extra={"similarity_function": similarity_function}
        )

        node_label_to_vector_index_names = {
            "SmallMolecule": "SelformerEmbeddings",
            "Protein": ["Prott5Embeddings", "Esm2Embeddings"],
            "GOTerm": "Anc2vecEmbeddings",
            "Phenotype": "CadaEmbeddings",
            "Disease": "Doc2vecEmbeddings",
            "ProteinDomain": "Dom2vecEmbeddings",
            "EcNumber": "RxnfpEmbeddings",
            "Pathway": "BiokeenEmbeddings",
            "Gene": "NtEmbeddings",
        }

        node_label_to_property = {
            "Protein": ["prott5_embedding", "esm2_embedding"],
            "ProteinDomain": "dom2vec_embedding",
            "GOTerm": "anc2vec_embedding",
            "SmallMolecule": "selformer_embedding",
            "Disease": "doc2vec_embedding",
            "Phenotype": "cada_embedding",
            "Pathway": "biokeen_embedding",
            "EcNumber": "rxnfp_embedding",
            "Gene": "nt_embedding",
        }

        vector_index_name_to_property = {
            "Prott5Embeddings": "prott5_embedding",
            "Esm2Embeddings": "esm2_embedding",
        }

        property_to_vector_size = {
            "prott5_embedding": 1024,
            "esm2_embedding": 1280,
            "dom2vec_embedding": 50,
            "anc2vec_embedding": 200,
            "selformer_embedding": 768,
            "doc2vec_embedding": 100,
            "cada_embedding": 160,
            "biokeen_embedding": 200,
            "rxnfp_embedding": 256,
            "nt_embedding": 2560,
        }

        indexes_created = 0
        
        try:
            with neo4j.GraphDatabase.driver(self.URI, auth=self.AUTH) as driver:
                for node_label, vector_index_name in node_label_to_vector_index_names.items():
                    if isinstance(vector_index_name, str):
                        query = f"""
                        CREATE VECTOR INDEX {vector_index_name} IF NOT EXISTS
                        FOR (m:{node_label})
                        ON m.{node_label_to_property[node_label]}
                        OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {property_to_vector_size[node_label_to_property[node_label]]},
                        `vector.similarity_function`: '{similarity_function}'
                        }}}}
                        """
                        _, _, _ = driver.execute_query(
                            query, database_=self.db_name, routing_="w"
                        )
                        indexes_created += 1
                        
                        Logger.debug(
                            "[VECTOR_INDEX] Created index",
                            extra={
                                "index_name": vector_index_name,
                                "node_label": node_label
                            }
                        )
                    else:
                        for n in vector_index_name:
                            query = f"""
                            CREATE VECTOR INDEX {n} IF NOT EXISTS
                            FOR (m:{node_label})
                            ON m.{vector_index_name_to_property[n]}
                            OPTIONS {{indexConfig: {{
                            `vector.dimensions`: {property_to_vector_size[vector_index_name_to_property[n]]},
                            `vector.similarity_function`: '{similarity_function}'
                            }}}}
                            """
                            _, _, _ = driver.execute_query(
                                query, database_=self.db_name, routing_="w"
                            )
                            indexes_created += 1
                            
                            Logger.debug(
                                "[VECTOR_INDEX] Created index",
                                extra={
                                    "index_name": n,
                                    "node_label": node_label
                                }
                            )

            index_time_ms = (time() - index_start_time) * 1000
            Logger.info(
                "[VECTOR_INDEX] Vector indexes created",
                extra={
                    "indexes_created": indexes_created,
                    "time_ms": index_time_ms
                }
            )

            return True
            
        except Exception as e:
            Logger.exception(
                "[VECTOR_INDEX] Failed to create vector indexes",
                exc=e
            )
            raise

    def delete_vector_indexes(self) -> bool:
        """
        Delete all vector indexes.
        
        Returns:
            True if successful
        """
        delete_start_time = time()
        
        Logger.info("[VECTOR_INDEX] Deleting vector indexes")
        
        try:
            with neo4j.GraphDatabase.driver(self.URI, auth=self.AUTH) as driver:
                query = """
                SHOW VECTOR INDEXES YIELD name
                RETURN *
                """
                records, _, _ = driver.execute_query(
                    query, database_=self.db_name, routing_="r"
                )

                indexes = []
                for res in records:
                    indexes.append(res.data()["name"])
                
                Logger.debug(
                    "[VECTOR_INDEX] Found indexes to delete",
                    extra={"indexes": indexes}
                )

                for vector_index in indexes:
                    query = f"""
                    DROP INDEX {vector_index}
                    """
                    _, _, _ = driver.execute_query(
                        query, database_=self.db_name, routing_="w"
                    )
                    
                    Logger.debug(
                        "[VECTOR_INDEX] Deleted index",
                        extra={"index_name": vector_index}
                    )

            delete_time_ms = (time() - delete_start_time) * 1000
            Logger.info(
                "[VECTOR_INDEX] Vector indexes deleted",
                extra={
                    "indexes_deleted": len(indexes),
                    "time_ms": delete_time_ms
                }
            )

            return True
            
        except Exception as e:
            Logger.exception(
                "[VECTOR_INDEX] Failed to delete vector indexes",
                exc=e
            )
            raise
