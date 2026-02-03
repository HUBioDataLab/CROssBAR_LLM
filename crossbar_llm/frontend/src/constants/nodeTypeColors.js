/**
 * Color mappings for different biological entity types in the knowledge graph.
 * Used for autocomplete badges and entity visualization.
 */
export const nodeTypeColors = {
  Gene: { bg: '#287271', text: '#FFFFFF' },
  Protein: { bg: '#3aa6a4', text: '#FFFFFF' },
  Drug: { bg: '#815ac0', text: '#FFFFFF' },
  Disease: { bg: '#079dbb', text: '#FFFFFF' },
  Compound: { bg: '#d2b7e5', text: '#FFFFFF' },
  Pathway: { bg: '#720026', text: '#FFFFFF' },
  Phenotype: { bg: '#58d0e8', text: '#FFFFFF' },
  SmallMolecule: { bg: '#815ac0', text: '#FFFFFF' },
  GOTerm: { bg: '#4a9c6d', text: '#FFFFFF' },
  CellularComponent: { bg: '#4a9c6d', text: '#FFFFFF' },
  BiologicalProcess: { bg: '#4a9c6d', text: '#FFFFFF' },
  MolecularFunction: { bg: '#4a9c6d', text: '#FFFFFF' },
  ProteinDomain: { bg: '#e07b53', text: '#FFFFFF' },
  EcNumber: { bg: '#8b6914', text: '#FFFFFF' },
  OrganismTaxon: { bg: '#5c6bc0', text: '#FFFFFF' },
  SideEffect: { bg: '#ef5350', text: '#FFFFFF' },
  default: { bg: '#A5ABB6', text: '#FFFFFF' },
};

/**
 * Get color for a node type, falling back to default if not found.
 * @param {string} nodeType - The type of the node
 * @returns {{ bg: string, text: string }} The color configuration
 */
export const getNodeTypeColor = (nodeType) => {
  return nodeTypeColors[nodeType] || nodeTypeColors.default;
};
