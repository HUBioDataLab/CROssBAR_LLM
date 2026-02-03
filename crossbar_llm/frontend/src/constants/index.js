/**
 * Central export for all constants.
 */
export { nodeTypeColors, getNodeTypeColor } from './nodeTypeColors';
export { exampleQueries, vectorExampleQueries } from './exampleQueries';
export { 
  nodeLabelToVectorIndexNames, 
  getEmbeddingTypesForCategory, 
  getVectorCategories 
} from './vectorIndexMappings';
export { 
  supportedModels, 
  isModelSupported, 
  NEO4J_BROWSER_URL, 
  DRAWER_WIDTH 
} from './supportedModels';
