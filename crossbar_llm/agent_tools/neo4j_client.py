from neo4j import GraphDatabase
from .config import Neo4jConfig, VectorMappings, FullTextIndexMappings
from pydantic import validate_call
from typing_extensions import Self
from typing import Any

import os
import json
import re
import neo4j
from pathlib import Path


from .logging_config import get_logger, log_execution_time

logger = get_logger(__name__)

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


class Neo4jClient:
    def __init__(
        self,
        cfg: Neo4jConfig,
        reset_schema: bool = False,
        create_vector_indexes: bool = False,
        delete_vector_indexes: bool = False,
        create_fulltext_indexes: bool = False,
        delete_fulltext_indexes: bool = False,

    ):

        self.cfg = cfg
        self.file_path = Path(__file__).resolve().parent / "graph_schema.json"

        self.driver = GraphDatabase.driver(
            self.cfg.neo4j_uri, auth=(self.cfg.neo4j_usr, self.cfg.neo4j_password)
        )

        self.vector_mappings = VectorMappings()
        logger.debug(
            "Vector index mappings loaded successfully",
            event_type="config_load",
            component="Neo4jClient.__init__",
        )

        self.fulltext_index_mappings = FullTextIndexMappings()
        logger.debug(
            "Full-text index mappings loaded successfully",
            event_type="config_load",
            component="Neo4jClient.__init__",
        )

        startup_actions = (
            (reset_schema, self.reset_db_schema),
            (create_vector_indexes, self.create_vector_indexes),
            (delete_vector_indexes, self.delete_vector_indexes),
            (create_fulltext_indexes, self.create_fulltext_indexes),
            (delete_fulltext_indexes, self.delete_fulltext_indexes),
        )

        for should_run, action in startup_actions:
            if should_run:
                logger.info(
                    "Running Neo4j startup action",
                    event_type="startup_action",
                    component="Neo4jClient.__init__",
                    action=action.__name__
                )
                action()
        

        logger.info(
            "Neo4jClient initialized successfully",
            event_type="initialization",
            component="Neo4jClient.__init__",
            graph_schema_path=self.file_path,
            create_vector_indexes=create_vector_indexes,
            delete_vector_indexes=delete_vector_indexes,
            create_fulltext_indexes=create_fulltext_indexes,
            delete_fulltext_indexes=delete_fulltext_indexes
        )

    def close_driver(self) -> None:
        if getattr(self, "driver", None) is not None:
            self.driver.close()
            logger.info(
                "Neo4j driver closed successfully",
                event_type="driver_close",
                component="Neo4jClient.close_driver"
            )

    @log_execution_time(logger, component="Neo4jClient.create_graph_schema_variables")
    def create_graph_schema_variables(self) -> dict:

        # Check if the graph schema file already exists
        if os.path.isfile(self.file_path):
            with open(self.file_path) as fp:
                return json.load(fp)
            
            logger.debug(
                "Loaded graph schema from cache file",
                event_type="graph_schema_cache_load",
                component="Neo4jClient.create_graph_schema_variables"
            )

        else:
            # If graph schema file does not exist, query the database to create it
            logger.info(
                "Graph schema cache missing, rebuilding from database",
                event_type="graph_schema_rebuild_started",
                component="Neo4jClient.create_graph_schema_variables"
            )

            with self.driver.session(
                database=self.cfg.neo4j_db_name,
                default_access_mode=neo4j.READ_ACCESS
            ) as session:
                node_property_records = session.run(node_properties_query)
                node_property_results = [res["output"] for res in node_property_records]

                node_result_records = session.run(node_query)
                node_results = [res["output"] for res in node_result_records]

                edge_property_records = session.run(rel_properties_query)
                edge_property_results = [res["output"] for res in edge_property_records]

                edge_result_records = session.run(rel_query)
                edge_results = [res["output"] for res in edge_result_records]

                schema = {
                    "nodes": node_results,
                    "node_properties": node_property_results,
                    "edges": edge_results,
                    "edge_properties": edge_property_results,
                }

                # Save the schema to a JSON file for future use
                with open(self.file_path, "w") as fp:
                    json.dump(schema, fp)
                
                logger.info(
                    "Graph schema rebuilt and saved",
                    event_type="graph_schema_rebuild_completed",
                    component="Neo4jClient.create_graph_schema_variables",
                    node_count=len(node_results),
                    edge_count=len(edge_results),
                    schema_file_path=self.file_path
                )

                return schema

    def reset_db_schema(self):
        if os.path.isfile(self.file_path):
            os.remove(self.file_path)
            logger.info(
                "Removed cached graph schema file",
                event_type="graph_schema_cache_reset",
                component="Neo4jClient.reset_db_schema",
                schema_file_path=self.file_path
            )

    def get_db_version(self):
        if os.path.isfile(self.file_path):
            with open(self.file_path) as fp:
                data = json.load(fp)
                if data.get("db_version"):
                    logger.debug(
                        "Retrieved database version from cache",
                        event_type="db_version_loaded_from_cache",
                        component="Neo4jClient.get_db_version",
                        schema_file_path=self.file_path
                    )
                    return data["db_version"]
        
        _ = self.create_graph_schema_variables()
        with open(self.file_path) as fp:
            data = json.load(fp)
        
        with self.driver.session(
            database=self.cfg.neo4j_db_name,
            default_access_mode=neo4j.READ_ACCESS
        ) as session:
            query = "CALL dbms.components() YIELD name, versions, edition UNWIND versions AS version RETURN version"
            record = session.run(query)

            version = record.single().data()["version"]
            
            # Update the schema file with the version
            with open(self.file_path, "r+") as fp:
                data = json.load(fp)
                data["db_version"] = version
                fp.seek(0)
                json.dump(data, fp)
            
            logger.info(
                "Retrieved database version from Neo4j and updated cache",
                event_type="db_version_retrieved_and_cached",
                component="Neo4jClient.get_db_version",
                db_version=version,
                schema_file_path=self.file_path
            )
            return version

    @validate_call
    def remove_embedding_attribute(self, data: dict) -> dict:

        keys_to_delete = set()

        for k, v in data.items():
            if "embedding" in k:
                keys_to_delete.add(k)

            elif isinstance(v, dict):
                data[k] = self.remove_embedding_attribute(v)

            elif isinstance(v, list):
                for i in range(len(v)):
                    if isinstance(v[i], dict):
                        v[i] = self.remove_embedding_attribute(v[i])

        for k in keys_to_delete:
            del data[k]

        logger.debug(
            "Removed embedding attributes from query result",
            event_type="embedding_attribute_removal",
            component="Neo4jClient.remove_embedding_attribute",
            cleaned_data=data,
            removed_keys=sorted(keys_to_delete)
        )

        return data
    
    @log_execution_time(logger, component="Neo4jClient.create_vector_indexes")
    @validate_call
    def create_vector_indexes(self, similarity_function: str = "cosine") -> bool:
        logger.info(
            "Creating vector indexes in Neo4j",
            event_type="vector_index_creation_started",
            component="Neo4jClient.create_vector_indexes",
            similarity_function=similarity_function
        )

        with self.driver.session(
            database=self.cfg.neo4j_db_name,
            default_access_mode=neo4j.WRITE_ACCESS
        ) as session:

            for node_label, index_config in self.vector_mappings.model_dump(exclude_none=True).items():
                if isinstance(index_config, list):
                    for config in index_config:

                        logger.debug(
                            "Creating vector index for node label",
                            event_type="vector_index_creation",
                            component="Neo4jClient.create_vector_indexes",
                            node_label=node_label,
                            index_name=config["index_name"],
                            property_name=config["property_name"],
                            vector_size=config["vector_size"]
                        )

                        query = f"""
                        CREATE VECTOR INDEX {config["index_name"]} IF NOT EXISTS
                        FOR (m:{node_label})
                        ON m.{config["property_name"]}
                        OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {config["vector_size"]},
                        `vector.similarity_function`: '{similarity_function}'
                        }}}}
                        """
                        _ = session.run(query)

                        logger.info(
                            "Created vector index for node label",
                            event_type="vector_index_created",
                            component="Neo4jClient.create_vector_indexes",
                            node_label=node_label,
                            index_name=config["index_name"],
                            property_name=config["property_name"],
                            vector_size=config["vector_size"]
                        )

                else:

                    logger.debug(
                        "Creating vector index for node label",
                        event_type="vector_index_creation",
                        component="Neo4jClient.create_vector_indexes",
                        node_label=node_label,
                        index_name=index_config["index_name"],
                        property_name=index_config["property_name"],
                        vector_size=index_config["vector_size"],
                        similarity_function=similarity_function
                    )

                    query = f"""
                    CREATE VECTOR INDEX {index_config["index_name"]} IF NOT EXISTS
                    FOR (m:{node_label})
                    ON m.{index_config["property_name"]}
                    OPTIONS {{indexConfig: {{
                    `vector.dimensions`: {index_config["vector_size"]},
                    `vector.similarity_function`: '{similarity_function}'
                    }}}}
                    """
                    _ = session.run(query)

                    logger.info(
                        "Created vector index for node label",
                        event_type="vector_index_created",
                        component="Neo4jClient.create_vector_indexes",
                        node_label=node_label,
                        index_name=index_config["index_name"],
                        property_name=index_config["property_name"],
                        vector_size=index_config["vector_size"]
                    )

        return True

    @log_execution_time(logger, component="Neo4jClient.delete_vector_indexes")
    def delete_vector_indexes(self) -> bool:
        logger.info(
            "Deleting vector indexes in Neo4j",
            event_type="vector_index_deletion_started",
            component="Neo4jClient.delete_vector_indexes"
        )

        with self.driver.session(
            database=self.cfg.neo4j_db_name,
            default_access_mode=neo4j.WRITE_ACCESS
        ) as session:
            
            query = """
            SHOW VECTOR INDEXES YIELD name
            RETURN name
            """
            records = session.run(query)

            indexes = []
            for res in records:
                indexes.append(res.data()["name"])

            for vector_index in indexes:
                query = f"""
                DROP INDEX {vector_index}
                """
                session.run(query).consume()

                logger.debug(
                    "Deleted vector index",
                    event_type="vector_index_deleted",
                    component="Neo4jClient.delete_vector_indexes",
                    index_name=vector_index
                )
        
        logger.info(
            "Completed deletion of vector indexes",
            event_type="vector_index_deletion_completed",
            component="Neo4jClient.delete_vector_indexes",
            deleted_index_count=len(indexes),
            indexes_deleted=sorted(indexes)
        )

        return True
    
    @log_execution_time(logger, component="Neo4jClient.create_fulltext_indexes")
    def create_fulltext_indexes(self) -> bool:

        logger.info(
            "Creating full-text indexes in Neo4j",
            event_type="fulltext_index_creation_started",
            component="Neo4jClient.create_fulltext_indexes"
        )

        with self.driver.session(
            database=self.cfg.neo4j_db_name,
            default_access_mode=neo4j.WRITE_ACCESS
        ) as session:
            
            for node_label, index_config in self.fulltext_index_mappings.model_dump(exclude_none=True).items():
                
                query = f"""
                CREATE FULLTEXT INDEX {index_config["index_name"]} IF NOT EXISTS
                FOR (n:{node_label}) ON EACH [n.{index_config["property_name"]}]
                OPTIONS {{ 
                indexConfig: {{
                    `fulltext.analyzer`: '{index_config["fulltext_analyzer"]}'
                    }}
                }}
                """
                _ = session.run(query)

                logger.debug(
                    "Created full-text index for node label",
                    event_type="fulltext_index_created",
                    component="Neo4jClient.create_fulltext_indexes",
                    node_label=node_label,
                    index_name=index_config["index_name"],
                    property_name=index_config["property_name"],
                    fulltext_analyzer=index_config["fulltext_analyzer"]
                )
        
        logger.info(
            "Completed creation of full-text indexes",
            event_type="fulltext_index_creation_completed",
            component="Neo4jClient.create_fulltext_indexes",
            created_index_count=len(self.fulltext_index_mappings.model_dump(exclude_none=True)),
            indexes_created=sorted([config["index_name"] for config in self.fulltext_index_mappings.model_dump(exclude_none=True).values()])
        )

        return True
    
    @log_execution_time(logger, component="Neo4jClient.delete_fulltext_indexes")
    def delete_fulltext_indexes(self) -> bool:

        logger.info(
            "Deleting full-text indexes in Neo4j",
            event_type="fulltext_index_deletion_started",
            component="Neo4jClient.delete_fulltext_indexes"
        )

        with self.driver.session(
            database=self.cfg.neo4j_db_name,
            default_access_mode=neo4j.WRITE_ACCESS
        ) as session:
            query = f"""
            SHOW FULLTEXT INDEXES YIELD name
            RETURN name
            """
            records = session.run(query)

            indexes = []
            for res in records:
                indexes.append(res.data()["name"])

            for fulltext_index in indexes:
                query = f"""
                DROP INDEX {fulltext_index}
                """
                session.run(query).consume()

                logger.debug(
                    "Deleted full-text index",
                    event_type="fulltext_index_deleted",
                    component="Neo4jClient.delete_fulltext_indexes",
                    index_name=fulltext_index
                )
        
        logger.info(
            "Completed deletion of full-text indexes",
            event_type="fulltext_index_deletion_completed",
            component="Neo4jClient.delete_fulltext_indexes",
            deleted_index_count=len(indexes),
            indexes_deleted=sorted(indexes)
        )

        return True
    
    def verify_db_connection(self) -> bool:
        logger.info(
            "Verifying database connection",
            event_type="db_connection_verification_started",
            component="Neo4jClient.verify_db_connection"
        )

        self.driver.verify_connectivity(database=self.cfg.neo4j_db_name)
        logger.info(
            "Database connection verified successfully",
            event_type="db_connection_verification_completed",
            component="Neo4jClient.verify_db_connection"
        )
        return True
    
    @log_execution_time(logger, component="Neo4jClient.execute_query")
    def execute_query(self, query: str, top_k: int = 10, disable_limit: bool = False) -> list[Any] | str:
        """
        Execute a Cypher query against the Neo4j database and return the results.
        Args:
            query: The Cypher query to be executed.
            top_k: The maximum number of results to return.
            disable_limit: Whether to disable the limit clause.
        Returns:
            A list of dictionaries representing the query results, or an error message string.
        """
        logger.debug(
            "Executing Cypher query",
            event_type="query_execution_started",
            component="Neo4jClient.execute_query",
            query=query,
            top_k=top_k,
            disable_limit=disable_limit
        )
        regex_pattern = r"\bLIMIT\s+\d+\b"
        if disable_limit:
            query = re.sub(regex_pattern, "", query.strip()).strip()
        elif "show" in query.lower():
            query = query.strip()
        elif "LIMIT" in query:
            logger.debug(
                "Query already contains a LIMIT clause, replacing it with the specified top_k value",
                event_type="query_limit_replacement",
                component="Neo4jClient.execute_query",
                original_query=query,
                top_k=top_k
            )
            regex_pattern = r"\bLIMIT\s+\d+\b"
            query = re.sub(regex_pattern, f" LIMIT {top_k}", query.strip())
        else:
            query = query.strip() + f" LIMIT {top_k}"

        with self.driver.session(
            database=self.cfg.neo4j_db_name,
            default_access_mode=neo4j.READ_ACCESS,
            ) as session:
            try:
                records = session.run(query)

                # Remove embedding attributes from the results that confuse LLMs
                results = []
                for res in records:
                    data = res.data()
                    results.append(self.remove_embedding_attribute(data))

                if not results:
                    logger.warning(
                        "Executed Cypher query does not return any results",
                        event_type="query_execution_completed_no_results",
                        component="Neo4jClient.execute_query",
                        query=query
                    )

                logger.info(
                    "Executed Cypher query successfully",
                    event_type="query_execution_completed",
                    component="Neo4jClient.execute_query",
                    query=query,
                    top_k=top_k,
                    result_count=len(results)
                )
                return results

            except neo4j.exceptions.CypherSyntaxError as e:
                logger.error(
                    "Cypher syntax error during query execution",
                    event_type="query_execution_error",
                    component="Neo4jClient.execute_query",
                    query=query,
                    error_type=type(e).__name__,
                    error_message=str(e)
                )
                return f"Cypher Syntax Error: {str(e)}"

            except neo4j.exceptions.CypherTypeError as e:
                logger.error(
                    "Cypher type error during query execution",
                    event_type="query_execution_error",
                    component="Neo4jClient.execute_query",
                    query=query,
                    error_type=type(e).__name__,
                    error_message=str(e)
                )
                return f"Cypher Type Error: {str(e)}"

            except neo4j.exceptions.DatabaseError as e:
                logger.error(
                    "Database error during query execution",
                    event_type="query_execution_error",
                    component="Neo4jClient.execute_query",
                    query=query,
                    error_type=type(e).__name__,
                    error_message=str(e)
                )
                return f"The database failed to service the request: {str(e)}"

            except Exception as e:
                logger.error(
                    "Unexpected error during query execution",
                    event_type="query_execution_error",
                    component="Neo4jClient.execute_query",
                    query=query,
                    error_type=type(e).__name__,
                    error_message=str(e)
                )
                return f"An error occurred while executing the query: {str(e)}"


    @log_execution_time(logger, component="Neo4jClient.fulltext_search")
    def fulltext_search(self, node_label: str, search_term: str, top_k: int = 10, add_idx: bool = True) -> list[Any] | str:
        
        # ------------------------------------
        #  MAYBE WE CAN ALSO RETURN NODE IDS
        # ------------------------------------

        logger.debug(
            "Performing Fulltext search query",
            event_type="fulltext_search_started",
            component="Neo4jClient.fulltext_search",
            node_label=node_label,
            search_term=search_term,
            top_k=top_k,
            add_idx=add_idx
        )
        
        query = f"""
        CALL db.index.fulltext.queryNodes("{self.fulltext_index_mappings.get_index_name_by_node_type(node_label)}", "{search_term}") YIELD node, score
        RETURN node.{self.fulltext_index_mappings.get_property_name_by_node_type(node_label)} AS name, ROUND(score, 3) AS score
        ORDER BY score DESC
        """
        if add_idx:
            records = self.execute_query(query, top_k=top_k)
            if not records or isinstance(records, str):
                logger.warning(
                    "Fulltext search returned no records or an error",
                    event_type="fulltext_search_no_results",
                    component="Neo4jClient.fulltext_search",
                    node_label=node_label,
                    search_term=search_term,
                    results=records
                )
                return records

            result = []
            for idx, record in enumerate(records, start=1):
                result.append({"rank": idx} | record)

            return result
        
        execution_result = self.execute_query(query, top_k=top_k)

        logger.info(
            "Fulltext search completed successfully",
            event_type="fulltext_search_completed",
            component="Neo4jClient.fulltext_search",
            node_label=node_label,
            search_term=search_term,
            ranked=add_idx,
            result_count=len(execution_result) if isinstance(execution_result, list) else 0
        )

        return execution_result
    
    # In case I decide to use it as a context manager in the future
    def __enter__(self) -> Self:
        return self
    
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.close_driver()
        return False
