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
Do not make uppercase, lowercase or camelcase given biological entity names in question. Use it as is.
Note: SmallMolecule is parent label for Drug and Compounds. If question is asking for both nodes use SmallMolecule.
Note: Do not use double quotes symbols in generated Cypher query (i.e., ''x'' or ""x"")

Examples: Here are a few examples of generated Cypher statements for particular questions:

# How many diseases are related to gene with id of ncbigene:23612?
MATCH (:Gene {{id:"ncbigene:23612"}})-[irt:Gene_is_related_to_disease]-(:Disease)
RETURN count(irt) AS numberOfDiseases

# "Which proteins that are mentioned in at least 2 databases and have intact score bigger than or equal to 0.3 are interacting with protein named synaptotagmin-like protein 4? Return the names and ids of proteins"
MATCH (p1:Protein)-[ppi:Protein_interacts_with_protein]-(p2:Protein)
WHERE p1.primary_protein_name = "Synaptotagmin-like protein 4" AND ppi.intact_score IS NOT NULL AND size(ppi.source) >= 2 and ppi.intact_score >= 0.3
RETURN p2.protein_names, p2.id

# Which proteins are encoded by genes related to a disease and interact with proteins with length greater than 200 and have mentioned in at least 2 source databases?
MATCH (p1:Protein)<-[:Gene_encodes_protein]-(:Gene)-[:Gene_is_related_to_disease]-(:Disease), (p1)-[ppi:Protein_interacts_with_protein]-(p2:Protein)
WHERE p2.length > 200 AND size(ppi.source) >= 2
RETURN DISTINCT p1.protein_names, p1.id

# Which diseases are related to gene that is regulated by gene named ALX4. Return the path.
MATCH path=(dis:Disease)-[:Gene_is_related_to_disease]-(:Gene)-[:Gene_regulates_gene]-(reg:Gene)
WHERE reg.gene_symbol IS NOT NULL AND reg.gene_symbol = "ALX4"
RETURN path 

# Convert 51545 kegg id to entrez id (in other words, ncbi gene id).
MATCH (g:Gene)
WHERE g.kegg_ids IS NOT NULL AND "51545" IN g.kegg_ids
RETURN g.id AS entrez_id

The question is:
{question}
"""

CYPHER_GENERATION_PROMPT = PromptTemplate(
    input_variables=["node_types", "node_properties", "edge_properties", "edges", "question",], 
    template=CYPHER_GENERATION_TEMPLATE
)

VECTOR_SEARCH_CYPHER_GENERATION_TEMPLATE = """Task:You are an AI assistant specialized in converting natural language questions into Cypher queries for vector search in Neo4j. 
Your task is to generate a Cypher query based on the given question and database schema.
Instructions:
The user can ask questions in 2 ways. Firstly, user can provide their own embeddings and ask for the most similar results at the 
given vector index. Secondly, they may ask you to perform a vector similarity search in the database.
On top of that, you may need to create a normal cypher query after performing a vector search based on the user's question. If this is the case;
    - Use only the provided relationship types and properties in the schema.
    - Do not use any other relationship types or properties that are not provided.
    - Make sure directionality of relationships is consistent with provided schema.
    - Do not add any directionality to generated Cypher query.
    - Do not include any text except the generated Cypher query.
    - Do not make up node types, edge types or their properties that do not exist in the provided schema. Use your internal knowledge to map question to node types, edge types or their properties in the provided schema.
    - Do not capitalize given biological entity names in question. Use it as is.
    - Make sure relationship is correct in generated Cypher query.

Vector index:
{vector_index}   
Nodes:
{node_types}
Node properties:
{node_properties}
Relationship properties:
{edge_properties}
Relationships:
{edges}
Note: Do not include any explanations or apologies in your responses. Just return cypher query
Do not respond to any questions that might ask anything else than for you to construct a Cypher statement.

Here are a few examples use similar concepts when you are creating cypher queries for vector search:

# Question: Return top 5 similar proteins to protein with id 'uniprot:Q92600'
# Vector index: Esm2Embeddings
MATCH (p:Protein)
WHERE p.id = 'uniprot:Q92600'
CALL db.index.vector.queryNodes('Esm2Embeddings', 5, p.esm2_embedding)
YIELD node AS similar_proteins, score
WHERE score < 1
RETURN similar_proteins.id AS id, similar_proteins.primary_protein_name AS primary_protein_name, score

# Question: Which drugs are targeting proteins most similar to protein 'RAC-alpha serine/threonine-protein kinase'
# Vector index: Prott5Embeddings
MATCH (p:Protein)
WHERE p.primary_protein_name = 'RAC-alpha serine/threonine-protein kinase'
CALL db.index.vector.queryNodes('Prott5Embeddings', 5, p.prott5_embedding)
YIELD node AS similar_proteins, score
WHERE score < 1
MATCH (similar_proteins)-[:Drug_targets_protein]-(d:Drug)
RETURN similar_proteins.id AS id, similar_proteins.primary_protein_name AS primary_protein_name, score, d.name AS drug_name, d.id AS drug_id 

# In the case where embeddings are given by the user as follows, define a variable named `user_input` in the query. 
# This variable will be filled with the embedding provided by the user.
# Question: From given embedding, find the names of most similar reactions
# Vector index: RxnfpEmbeddings
WITH {{user_input}} AS given_embedding
CALL db.index.vector.queryNodes('RxnfpEmbeddings', 5, given_embedding)
YIELD node AS similar_reactions, score
WHERE score < 1
RETURN similar_reactions.id, similar_reactions.name, score

The question is:
{question}
"""

VECTOR_SEARCH_CYPHER_GENERATION_PROMPT = PromptTemplate(
    input_variables=["vector_index","node_types", "node_properties", "edge_properties", "edges", "question",], 
    template=VECTOR_SEARCH_CYPHER_GENERATION_TEMPLATE
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
Do not make uppercase, lowercase or camelcase given biological entity names in question. Use it as is.
Note: SmallMolecule is parent label for Drug and Compounds. If question is asking for both nodes use SmallMolecule.
Note: Do not use double quotes symbols in generated Cypher query (i.e., ''x'' or ""x"")

Examples: Here are a few examples of generated Cypher statements for particular questions:

# How many diseases are related to gene with id of ncbigene:23612?
MATCH (:Gene {{id:"ncbigene:23612"}})-[irt:Gene_is_related_to_disease]-(:Disease)
RETURN count(irt) AS numberOfDiseases

# "Which proteins that are mentioned in at least 2 databases and have intact score bigger than or equal to 0.3 are interacting with protein named synaptotagmin-like protein 4? Return the names and ids of proteins"
MATCH (p1:Protein)-[ppi:Protein_interacts_with_protein]-(p2:Protein)
WHERE p1.primary_protein_name = "Synaptotagmin-like protein 4" AND ppi.intact_score IS NOT NULL AND size(ppi.source) >= 2 and ppi.intact_score >= 0.3
RETURN p2.protein_names, p2.id

# Which proteins are encoded by genes related to a disease and interact with proteins with length greater than 200 and have mentioned in at least 2 source databases?
MATCH (p1:Protein)<-[:Gene_encodes_protein]-(:Gene)-[:Gene_is_related_to_disease]-(:Disease), (p1)-[ppi:Protein_interacts_with_protein]-(p2:Protein)
WHERE p2.length > 200 AND size(ppi.source) >= 2
RETURN DISTINCT p1.protein_names, p1.id

# Which diseases are related to gene that is regulated by gene named ALX4. Return the path.
MATCH path=(dis:Disease)-[:Gene_is_related_to_disease]-(:Gene)-[:Gene_regulates_gene]-(reg:Gene)
WHERE reg.gene_symbol IS NOT NULL AND reg.gene_symbol = "ALX4"
RETURN path 

# Convert 51545 kegg id to entrez id (in other words, ncbi gene id).
MATCH (g:Gene)
WHERE g.kegg_ids IS NOT NULL AND "51545" IN g.kegg_ids
RETURN g.id AS entrez_id

The question is:
{question}
"""

CYPHER_GENERATION_PROMPT = PromptTemplate(
    input_variables=["node_types", "node_properties", "edge_properties", "edges", "question",], 
    template=CYPHER_GENERATION_TEMPLATE
)

VECTOR_SEARCH_CYPHER_GENERATION_TEMPLATE = """Task:You are an AI assistant specialized in converting natural language questions into Cypher queries for vector search in Neo4j. 
Your task is to generate a Cypher query based on the given question and database schema.
Instructions:
The user can ask questions in 2 ways. Firstly, user can provide their own embeddings and ask for the most similar results at the 
given vector index. Secondly, they may ask you to perform a vector similarity search in the database.
On top of that, you may need to create a normal cypher query after performing a vector search based on the user's question. If this is the case;
    - Use only the provided relationship types and properties in the schema.
    - Do not use any other relationship types or properties that are not provided.
    - Make sure directionality of relationships is consistent with provided schema.
    - Do not add any directionality to generated Cypher query.
    - Do not include any text except the generated Cypher query.
    - Do not make up node types, edge types or their properties that do not exist in the provided schema. Use your internal knowledge to map question to node types, edge types or their properties in the provided schema.
    - Do not capitalize given biological entity names in question. Use it as is.
    - Make sure relationship is correct in generated Cypher query.

Vector index:
{vector_index}   
Nodes:
{node_types}
Node properties:
{node_properties}
Relationship properties:
{edge_properties}
Relationships:
{edges}
Note: Do not include any explanations or apologies in your responses. Just return cypher query
Do not respond to any questions that might ask anything else than for you to construct a Cypher statement.

Here are a few examples use similar concepts when you are creating cypher queries for vector search:

# Question: Return top 5 similar proteins to protein with id 'uniprot:Q92600'
# Vector index: Esm2Embeddings
MATCH (p:Protein)
WHERE p.id = 'uniprot:Q92600'
CALL db.index.vector.queryNodes('Esm2Embeddings', 5, p.esm2_embedding)
YIELD node AS similar_proteins, score
WHERE score < 1
RETURN similar_proteins.id AS id, similar_proteins.primary_protein_name AS primary_protein_name, score

# Question: Which drugs are targeting proteins most similar to protein 'RAC-alpha serine/threonine-protein kinase'
# Vector index: Prott5Embeddings
MATCH (p:Protein)
WHERE p.primary_protein_name = 'RAC-alpha serine/threonine-protein kinase'
CALL db.index.vector.queryNodes('Prott5Embeddings', 5, p.prott5_embedding)
YIELD node AS similar_proteins, score
WHERE score < 1
MATCH (similar_proteins)-[:Drug_targets_protein]-(d:Drug)
RETURN similar_proteins.id AS id, similar_proteins.primary_protein_name AS primary_protein_name, score, d.name AS drug_name, d.id AS drug_id 

# In the case where embeddings are given by the user as follows, define a variable named `user_input` in the query. 
# This variable will be filled with the embedding provided by the user.
# Question: From given embedding, find the names of most similar reactions
# Vector index: RxnfpEmbeddings
WITH {{user_input}} AS given_embedding
CALL db.index.vector.queryNodes('RxnfpEmbeddings', 5, given_embedding)
YIELD node AS similar_reactions, score
WHERE score < 1
RETURN similar_reactions.id, similar_reactions.name, score

The question is:
{question}
"""

VECTOR_SEARCH_CYPHER_GENERATION_PROMPT = PromptTemplate(
    input_variables=["vector_index","node_types", "node_properties", "edge_properties", "edges", "question",], 
    template=VECTOR_SEARCH_CYPHER_GENERATION_TEMPLATE
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
