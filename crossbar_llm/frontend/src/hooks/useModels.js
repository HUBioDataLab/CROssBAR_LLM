import { useState, useEffect } from 'react';
import { getAvailableModels } from '../services/api';

/**
 * Hook for fetching available LLM models from the backend.
 * 
 * @returns {{ modelChoices: Object, modelsLoaded: boolean }}
 */
export function useModels() {
  const [modelChoices, setModelChoices] = useState({});
  const [modelsLoaded, setModelsLoaded] = useState(false);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const models = await getAvailableModels();
        setModelChoices(models);
        setModelsLoaded(true);
      } catch (error) {
        console.error('Error fetching available models:', error);
        setModelChoices({});
        setModelsLoaded(true);
      }
    };
    fetchModels();
  }, []);

  return { modelChoices, modelsLoaded };
}

export default useModels;
