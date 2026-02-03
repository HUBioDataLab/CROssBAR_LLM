/**
 * List of supported/recommended LLM models.
 * These models are highlighted in the model selection dropdown.
 */
export const supportedModels = [
  'gpt-5.1',
  'gpt-4o',
  'o4-mini',
  'claude-sonnet-4-5',
  'claude-opus-4-1',
  'llama3.2-405b',
  'deepseek/deepseek-r1',
  'gemini-2.5-pro',
  'gemini-2.5-flash',
];

/**
 * Check if a model is in the supported/recommended list.
 * @param {string} modelName - The name of the model
 * @returns {boolean} Whether the model is supported
 */
export const isModelSupported = (modelName) => {
  return supportedModels.includes(modelName);
};

/**
 * Neo4j browser URL for direct query execution.
 */
export const NEO4J_BROWSER_URL = 'https://neo4j.crossbarv2.hubiodatalab.com/browser/?preselectAuthMethod=[NO_AUTH]&dbms=bolt://neo4j.crossbarv2.hubiodatalab.com';

/**
 * Default drawer width for the right panel.
 */
export const DRAWER_WIDTH = 420;
