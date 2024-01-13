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

@validate_call
@timer_func
@cache
def create_graph_schema_variables(URI: str, user: str, password: str, db_name: str) -> dict[str, list]:
    AUTH = (user, password)

    with neo4j.GraphDatabase.driver(URI, auth=AUTH) as driver:
        # node property filtering
        records, _, _ = driver.execute_query(node_properties_query, database_=db_name)
        node_results = []
        for res in records:
            node_results.append(res["output"])

        selected_nodes = ["SideEffect", "EcNumber", "Phenotype", "Pathway", "MolecularMixture", "SmallMolecule", 
                        "MolecularFunction", "BiologicalProcess", "CellularComponent", "Gene", "Protein", 
                        "Disease", "OrganismTaxon", "ProteinDomain"]
        
        for n in node_results:
            for prop in n["properties"]:
                if prop["property"] == "preferred_id":                  
                    n["properties"].remove(prop)
        

        node_results_filtered = [_dict for _dict in node_results if _dict["labels"] in selected_nodes]

        # relation type filtering
        records, _, _ = driver.execute_query(rel_query, database_=db_name)  
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

        # relation property filtering
        records, _, _ = driver.execute_query(rel_properties_query, database_=db_name)

        edge_properties_results_filtered = []
        for res in records:
            edge_properties_results_filtered.append(res.values()[0])

    
    return {"nodes": selected_nodes, 
            "node_properties": node_results_filtered, 
            "edges": edge_results_filtered, 
            "edge_properties": edge_properties_results_filtered}

