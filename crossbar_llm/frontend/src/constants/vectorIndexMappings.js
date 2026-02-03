/**
 * Mapping from node labels to their corresponding vector index names.
 * Used for semantic/vector search configuration.
 */
export const nodeLabelToVectorIndexNames = {
  SmallMolecule: "Selformer",
  Drug: "Selformer",
  Compound: "Selformer",
  Protein: ["Prott5", "Esm2"],
  GOTerm: "Anc2vec",
  CellularComponent: "Anc2vec",
  BiologicalProcess: "Anc2vec",
  MolecularFunction: "Anc2vec",
  Phenotype: "Cada",
  Disease: "Doc2vec",
  ProteinDomain: "Dom2vec",
  EcNumber: "Rxnfp",
  Pathway: "Biokeen",
};

/**
 * Get available embedding types for a vector category.
 * @param {string} category - The vector category (node label)
 * @returns {string|string[]|null} The embedding type(s) available
 */
export const getEmbeddingTypesForCategory = (category) => {
  return nodeLabelToVectorIndexNames[category] || null;
};

/**
 * Get all available vector categories.
 * @returns {string[]} Array of category names
 */
export const getVectorCategories = () => {
  return Object.keys(nodeLabelToVectorIndexNames);
};
