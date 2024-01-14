import neo4j
from functools import cache
from pydantic import validate_call
from utils import timer_func

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

rel_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE type = "RELATIONSHIP" AND elementType = "node"
UNWIND other AS other_node
RETURN "(:" + label + ")-[:" + property + "]->(:" + toString(other_node) + ")" AS output
"""

class Neo4jGraphHelper:
    def __init__(self, URI, user, password, db_name):
        self.URI = URI
        self.AUTH = (user, password)
        self.db_name = db_name

    @validate_call
    @timer_func
    @cache
    def create_graph_schema_variables(self):
        with neo4j.GraphDatabase.driver(self.URI, auth=self.AUTH) as driver:
            # Node property filtering
            records, _, _ = driver.execute_query(node_properties_query, database_=self.db_name)
            node_results = [res["output"] for res in records]

            selected_nodes = ["SideEffect", "EcNumber", "Phenotype", "Pathway", "MolecularMixture", "SmallMolecule", 
                            "MolecularFunction", "BiologicalProcess", "CellularComponent", "Gene", "Protein", 
                            "Disease", "OrganismTaxon", "ProteinDomain"]

            for n in node_results:
                n["properties"] = [prop for prop in n["properties"] if prop["property"] != "preferred_id"]

            node_results_filtered = [n for n in node_results if n["labels"] in selected_nodes]

            # Relation type filtering
            records, _, _ = driver.execute_query(rel_query, database_=self.db_name)
            edge_results_filtered = []
            to_be_replaced = ["(", ")", ":", "[", "]", ">", "<"]
            for res in records:        
                splitted = res.values()[0].split("-")
                splitted_corrected = []
                for i in splitted:
                    for j in to_be_replaced:
                        i = i.replace(j, "")
                    splitted_corrected.append(i)


                if splitted_corrected[0] in selected_nodes and splitted_corrected[2] in selected_nodes:
                    edge_results_filtered.append(res.values()[0])

            # Relation property filtering
            records, _, _ = driver.execute_query(rel_properties_query, database_=self.db_name)
            edge_properties_results_filtered = [res.values()[0] for res in records]

        return {
            "nodes": selected_nodes,
            "node_properties": node_results_filtered,
            "edges": edge_results_filtered,
            "edge_properties": edge_properties_results_filtered
        }

    @validate_call
    def execute(self, query, top_k=None):
        with neo4j.GraphDatabase.driver(self.URI, auth=self.AUTH) as driver:
            records, _, _ = driver.execute_query(query, database_=self.db_name)
            results = [res.data() for index, res in enumerate(records) if not top_k or index < top_k]
        return results
