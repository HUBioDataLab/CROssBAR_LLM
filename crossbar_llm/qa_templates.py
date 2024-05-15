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
Do not add any directionality to generated Cypher query.
Do not include any text except the generated Cypher query.
Do not make up node types, edge types or their properties that do not exist in the provided schema. Use your internal knowledge to map question to node types, edge types or their properties in the provided schema.
Do not change given biological entity names in question. Use it as is.
Note: SmallMolecule means drug and MolecularMixture means compound
Examples: Here are a few examples of generated Cypher statements for particular questions:

# How many diseases are related to gene with id of ncbigene:23612?
MATCH (:Gene {{id:"ncbigene:23612"}})-[irt:Gene_is_related_to_disease]-(:Disease)
RETURN count(irt) AS numberOfDiseases

# "Which proteins that are mentioned in at least 2 databases and have intact score bigger than or equal to 0.3 are interacting with protein named synaptotagmin-like protein 4? Return the names and ids of proteins"
MATCH (p1:Protein)-[ppi:Interacts_With]-(p2:Protein)
WHERE "Synaptotagmin-like protein 4" in p1.protein_names AND size(ppi.source) >= 2 and ppi.intact_score >= 0.3
RETURN p2.protein_names, p2.id

# Which proteins are encoded by genes related to a disease and interact with proteins with length greater than 200 and have mentioned in at least 2 source databases?
MATCH (p1:Protein)-[:Encodes]-(:Gene)-[:Gene_is_related_to_disease]-(:Disease), (p1)-[ppi:Interacts_With]-(p2:Protein)
WHERE p2.length > 200 AND size(ppi.source) >= 2
RETURN DISTINCT p1.protein_names, p1.id

# Which diseases are related to gene that is regulated by gene named ALX4. Return the path.
MATCH path=(dis:Disease)-[:Gene_is_related_to_disease]-(:Gene)-[:Gene_regulates_gene]-(reg:Gene)
WHERE "ALX4" IN reg.genes
RETURN path

# Convert 51545 kegg id to entrez id (in other words, ncbi gene id).
MATCH (g:Gene)
WHERE "51545" IN g.kegg
RETURN g.id AS entrez_id

The question is:
{question}
"""

CYPHER_GENERATION_TEMPLATE_TRIAL = """Task:Generate Cypher statement to query a graph database.
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
MATCH (:Gene {{id:"ncbigene:23612"}})-[irt:Gene_is_related_to_disease]-(:Disease)
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
    template=CYPHER_GENERATION_TEMPLATE
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
Note: Do not print intermediate steps just give natural language answer

Cypher Output: 
{output}
Question: 
{input_question}"""

CYPHER_OUTPUT_PARSER_PROMPT = PromptTemplate(input_variables=["output", "input_question"], 
                                             template=CYPHER_OUTPUT_PARSER_TEMPLATE)



QUESTION_GENERATOR_TEMPLATE = """
Task: You will generate question types to be translated from text into Cypher query language according to the 
given neo4j graph database schema. Create a wide variety of questions from provided schema. Use only the schema given to you
for question generation. Make questions as diverse as possible.
For some of questions I will provide you schematic representation of question. ∧ symbol means conjunction of paths at shared node type.
Create following type of questions:
- Property questions -> From the given type of node and relationship properties create diverse set of questions
- One-hop questions
- Two hop questions
- Three hop questions
- Counter questions
- Questions that use and/or/both
- (node type 1) -> (node type 2) -> (node type 3) ∧ (node type 4) -> (node type 5) -> (node type 3)
For this given path ask questions about node type 3 or its properties
- (node type 1) -> (node type 2) - [relation type 1]-> (node type 3) ∧ (node type 4) -> (node type 5) -[relation type 2]-> (node type 3)
For this given path ask questions about relation type 1 properties or relation type 2 properties
- (node type 1) -> (node type 2) -> (node type 3) ∧ (node type 4) -> (node type 5) -> (node type 3) ∧ (node type 3) -> (node type 6)
For this given path ask questions about node type 6 or its properties
- (node type 1) -> (node type 2) -> (node type 3) ∧ (node type 4) -> (node type 5) -> (node type 3) ∧ (node type 7) -> (node type 8) -> (node type 6) ∧ (node type 3) -> (node type 6)
For this given path ask questions about node type 6 or its properties

Create 10 questions for each category. Use the provided information in the schema. DO NOT CREATE SAME TYPE OF QUESTIONS. MAKE THEM DIFFERENT.

In the provided schema you will get node and relationship types along with their properties. Here is the schema:
Nodes:
{node_types}
Node properties:
{node_properties}
Relationship properties:
{edge_properties}
Relationships:
{edges}
"""

QUESTION_GENERATOR_PROMPT = PromptTemplate(
    input_variables=["node_types", "node_properties", "edge_properties", "edges", "question"], 
    template=QUESTION_GENERATOR_TEMPLATE
)
