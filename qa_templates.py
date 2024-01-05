from langchain.prompts import PromptTemplate


CYPHER_GENERATION_TEMPLATE = """Task:Generate Cypher statement to query a graph database.
Instructions:
Use only the provided relationship types and properties in the schema.
Do not use any other relationship types or properties that are not provided.
Make sure directionality of relationships is consistent with provided schema.
Nodes:
{node_types}
Node properties:
{node_properties}
Relationship properties:
{edge_properties}
Relationships:
{edges}
Note: Do not include any explanations or apologies in your responses.
Do not respond to any questions that might ask anything else than for you to construct a Cypher statement.
Do not include any text except the generated Cypher statement.
Note: SmallMolecule means drug and MolecularMixture means compound
Examples: Here are a few examples of generated Cypher statements for particular questions:

# How many diseases are related to gene with id of ncbigene:23612?
MATCH (:Gene {{id:"ncbigene:23612"}})-[irt:Gene_is_related_to_disease]->(:Disease)
RETURN count(irt) AS numberOfDiseases

# "Which proteins that are mentioned in at least 2 databases and have intact score bigger than or equal to 0.3 are interacting with protein named synaptotagmin-like protein 4? Return the names and ids of proteins"
MATCH (p1:Protein)-[ppi:Interacts_With]-(p2:Protein)
WHERE "Synaptotagmin-like protein 4" in p1.protein_names AND size(ppi.source) >= 2 and ppi.intact_score >= 0.3
RETURN p2.protein_names, p2.id

The question is:
{question}
"""

CYPHER_GENERATION_TEMPLATE_DENEME = """Task:Generate Cypher statement to query a graph database.
Instructions:
Use only the provided relationship types and properties in the schema.
Do not use any other relationship types or properties that are not provided.
Make sure directionality of relationships is consistent with provided schema.
Before creating Cypher queries, break the question into pieces and understand what is being asked of you
and give a confidence score between 0-1 on how confident you are about the cypher queries you create.
Nodes:
{node_types}
Node properties:
{node_properties}
Relationship properties:
{edge_properties}
Relationships:
{edges}
Note: Do not include any explanations or apologies in your responses.
Note: SmallMolecule means drug and MolecularMixture means compound.

Examples: Here are a few examples of generated Cypher statements for particular questions:

# How many diseases are related to gene with id of ncbigene:23612?
MATCH (:Gene {{id:"ncbigene:23612"}})-[irt:Gene_is_related_to_disease]->(:Disease)
RETURN count(irt) AS numberOfDiseases

# "Which proteins that are mentioned in at least 2 databases and have intact score bigger than or equal to 0.3 are interacting with protein named synaptotagmin-like protein 4? Return the names and ids of proteins"
MATCH (p1:Protein)-[ppi:Interacts_With]-(p2:Protein)
WHERE "Synaptotagmin-like protein 4" in p1.protein_names AND size(ppi.source) >= 2 and ppi.intact_score >= 0.3
RETURN p2.protein_names, p2.id

The question is:
{question}
"""

CYPHER_GENERATION_PROMPT = PromptTemplate(
    input_variables=["node_types", "node_properties", "edge_properties", "edges", "question",], 
    template=CYPHER_GENERATION_TEMPLATE_DENEME
)

CYPHER_OUTPUT_PARSER_TEMPLATE = """Task:Parse output of Cypher statement to natural language text based on
given question in order to answer it.
Instructions:
Output is formatted as list of dictionaries. You will parse them into natural language text based
on given question.
Example:
    Cypher Output: [{{'p.node_name': 'ITPR2'}}, {{'p.node_name': 'ITPR3'}}, {{'p.node_name': 'PDE1A'}}]
    Question: What proteins does the drug named Caffeine target?
    Natural language answer: The drug named Caffeine targets the proteins ITPR2, ITPR3, and PDE1A.

Note: Do not include every field of dictionary, return fields matching the question. Priotrize dictionary fields that have name of entity.
Note: Do not delete curies
Cypher Output: 
{output}
Question: 
{input_question}"""

CYPHER_OUTPUT_PARSER_PROMPT = PromptTemplate(input_variables=["output", "input_question"], template=CYPHER_OUTPUT_PARSER_TEMPLATE)
