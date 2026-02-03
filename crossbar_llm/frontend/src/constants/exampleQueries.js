/**
 * Example queries for the CROssBAR chat interface.
 * These are displayed in the right panel for users to try.
 */

// Regular example queries (non-vector search)
export const exampleQueries = [
  "Which Gene is related to the Disease named psoriasis?",
  "What proteins does the drug named Caffeine target?",
  "Which drugs target proteins associated with Alzheimer disease?",
  "Which pathways are associated with both diabetes mellitus and T-cell non-Hodgkin lymphoma? Return only signaling pathways.",
  "What are the common side effects of drugs targeting the EGFR gene's protein?",
];

// Vector search example queries with configuration
export const vectorExampleQueries = [
  {
    question: "Give me distinct Biological Processes that are similar to 'cell growth' Biological Process and drugs targeting proteins involved in these similar processes. Return 10 similar Biological Processes.",
    vectorCategory: "BiologicalProcess",
    embeddingType: "Anc2vec",
  },
  {
    question: "Find a protein domain that is similar to the domain with ID 'interpro:IPR000719'. Then, find proteins that possess this similar domain.",
    vectorCategory: "ProteinDomain",
    embeddingType: "Dom2vec",
  },
  {
    question: "Give me the names of top 10 Proteins that are targeted by Small Molecules similar to the given embedding.",
    vectorCategory: "SmallMolecule",
    embeddingType: "Selformer",
    vectorFilePath: "small_molecule_embedding.npy",
  },
  {
    question: "What are the most similar proteins to the given protein?",
    vectorCategory: "Protein",
    embeddingType: "Esm2",
    vectorFilePath: "protein_embedding.npy",
  },
  {
    question: "Find diseases related to proteins with similar structure to this embedding.",
    vectorCategory: "Protein",
    embeddingType: "Esm2",
    vectorFilePath: "protein_embedding.npy",
  },
];
