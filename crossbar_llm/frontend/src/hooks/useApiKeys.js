import { useState, useEffect } from 'react';
import api from '../services/api';

/**
 * Hook for managing API keys status.
 * Fetches which providers have API keys stored on the server.
 * 
 * @param {string} provider - Currently selected provider
 * @param {function} setApiKey - Function to update the API key state
 * @returns {{ apiKeysStatus: Object, apiKeysLoaded: boolean }}
 */
export function useApiKeys(provider, setApiKey) {
  const [apiKeysStatus, setApiKeysStatus] = useState({});
  const [apiKeysLoaded, setApiKeysLoaded] = useState(false);

  // Fetch API keys status on mount
  useEffect(() => {
    const fetchApiKeysStatus = async () => {
      try {
        const response = await api.get('/api_keys_status/');
        if (response.data) {
          setApiKeysStatus(response.data);
          setApiKeysLoaded(true);
          if (provider && response.data[provider]) {
            setApiKey('env');
          }
        }
      } catch (error) {
        console.error('Error fetching API keys status:', error);
        setApiKeysLoaded(true);
      }
    };
    fetchApiKeysStatus();
  }, [provider, setApiKey]);

  // When provider changes, update API key
  useEffect(() => {
    if (apiKeysLoaded && provider) {
      if (apiKeysStatus[provider]) {
        setApiKey('env');
      } else {
        setApiKey('');
      }
    }
  }, [provider, apiKeysStatus, apiKeysLoaded, setApiKey]);

  return { apiKeysStatus, apiKeysLoaded };
}

export default useApiKeys;
