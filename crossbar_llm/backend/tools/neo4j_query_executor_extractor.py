import json
import os
import re

import neo4j
from .utils import timer_func
from pydantic import validate_call

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
        self.URI = URI
        self.AUTH = (user, password)
        self.db_name = db_name

        if reset_schema:
            self.reset_db_schema()

        if create_vector_indexes:
            self.create_vector_indexes()

        if delete_vector_indexes:
            self.delete_vector_indexes()

    @timer_func
    def create_graph_schema_variables(self):
        file_path = os.path.join(os.getcwd(), "graph_schema.json")
        if os.path.isfile(file_path):
            with open(file_path) as fp:
                return json.load(fp)
        else:
            with neo4j.GraphDatabase.driver(self.URI, auth=self.AUTH) as driver:
                # Node property filtering
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

                # Node type selection
                records, _, _ = driver.execute_query(node_query, database_=self.db_name)
                node_results_filtered = [res["output"] for res in records]

                # Relation type filtering
                records, _, _ = driver.execute_query(rel_query, database_=self.db_name)
                edge_results_filtered = []
                for res in records:
                    edge_results_filtered.append(res.values()[0])

                # Relation property filtering
                records, _, _ = driver.execute_query(
                    rel_properties_query, database_=self.db_name
                )
                edge_properties_results_filtered = [res.values()[0] for res in records]

            schema = {
                "nodes": node_results_filtered,
                "node_properties": node_property_results,
                "edges": edge_results_filtered,
                "edge_properties": edge_properties_results_filtered,
            }

            if not os.path.isfile(file_path):
                with open(file_path, "w") as fp:
                    json.dump(schema, fp)

            return schema

    def reset_db_schema(self) -> None:
        file_path = os.path.join(os.getcwd(), "graph_schema.json")
        if os.path.isfile(file_path):
            os.remove(file_path)

    @validate_call
    def execute(self, query: str, top_k: int = 5):

        if "LIMIT" in query:
            regex_pattern = r"\bLIMIT\s+\d+\b"
            query = re.sub(regex_pattern, f" LIMIT {top_k}", query.strip().strip("\n"))
        else:
            query = query.strip().strip("\n") + f" LIMIT {top_k}"

        with neo4j.GraphDatabase.driver(self.URI, auth=self.AUTH) as driver:
            records, _, _ = driver.execute_query(
                query, database_=self.db_name, routing_="r"
            )
            if not records:
                return "Given cypher query did not return any result"

            results = []
            for index, res in enumerate(records):
                data = res.data()
                data = self.remove_embedding_attribute(data)
                results.append(data)

                if top_k and index > top_k:
                    break

        return results

    def remove_embedding_attribute(self, data: dict) -> dict:

        keys_to_delete = set()

        for k, v in data.items():
            if "embedding" in k:
                keys_to_delete.add(k)

            elif isinstance(v, dict):
                data[k] = self.remove_embedding_attribute(v)
        
        for k in keys_to_delete:
            del data[k]

        return data

    @validate_call
    def create_vector_indexes(self, similarity_function: str = "cosine") -> bool:

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

        with neo4j.GraphDatabase.driver(self.URI, auth=self.AUTH) as driver:

            for (
                node_label,
                vector_index_name,
            ) in node_label_to_vector_index_names.items():
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

        return True

    def delete_vector_indexes(self) -> bool:
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

            for vector_index in indexes:
                query = f"""
                DROP INDEX {vector_index}
                """
                _, _, _ = driver.execute_query(
                    query, database_=self.db_name, routing_="w"
                )

        return True
