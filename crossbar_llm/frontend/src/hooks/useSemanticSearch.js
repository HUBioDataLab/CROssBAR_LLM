import { useState, useCallback } from 'react';
import api from '../services/api';
import { nodeLabelToVectorIndexNames } from '../constants';

/**
 * Hook for managing semantic/vector search state.
 * 
 * @returns {Object} Semantic search state and handlers
 */
export function useSemanticSearch() {
  const [semanticSearchEnabled, setSemanticSearchEnabled] = useState(false);
  const [vectorCategory, setVectorCategory] = useState('');
  const [embeddingType, setEmbeddingType] = useState('');
  const [vectorFile, setVectorFile] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);

  // Handle category change
  const handleCategoryChange = useCallback((category) => {
    setVectorCategory(category);
    setVectorFile(null);
    setSelectedFile(null);
    
    const options = nodeLabelToVectorIndexNames[category];
    if (Array.isArray(options)) {
      setEmbeddingType('');
    } else if (options) {
      setEmbeddingType(options);
    } else {
      setEmbeddingType('');
    }
  }, []);

  // Handle toggle
  const handleToggle = useCallback((enabled) => {
    setSemanticSearchEnabled(enabled);
    if (!enabled) {
      // Clear config when disabled
      setVectorCategory('');
      setEmbeddingType('');
      setVectorFile(null);
      setSelectedFile(null);
    }
  }, []);

  // Load vector file from public folder path
  const loadVectorFileFromPath = useCallback(async (filePath) => {
    try {
      const response = await fetch(`/${filePath}`);
      const arrayBuffer = await response.arrayBuffer();
      const uint8Array = new Uint8Array(arrayBuffer);
      const vectorData = Array.from(uint8Array);
      setVectorFile(vectorData);
      return vectorData;
    } catch (error) {
      console.error('Error loading vector file:', error);
      throw new Error(`Failed to load vector file: ${filePath}`);
    }
  }, []);

  // Handle vector file upload
  const handleVectorFileUpload = useCallback(async (file) => {
    if (!file) return null;
    
    setSelectedFile(file);
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('vector_category', vectorCategory);
      formData.append('embedding_type', embeddingType);
      
      const response = await api.post('/upload_vector/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      
      setVectorFile(response.data);
      setSelectedFile(null);
      return response.data;
    } catch (error) {
      console.error('Error uploading vector file:', error);
      setSelectedFile(null);
      throw new Error(`Failed to upload vector file: ${error.message}`);
    }
  }, [vectorCategory, embeddingType]);

  // Check if configuration is valid
  const isConfigValid = useCallback(() => {
    if (!semanticSearchEnabled) return true;
    return vectorCategory && embeddingType;
  }, [semanticSearchEnabled, vectorCategory, embeddingType]);

  // Reset all state
  const reset = useCallback(() => {
    setSemanticSearchEnabled(false);
    setVectorCategory('');
    setEmbeddingType('');
    setVectorFile(null);
    setSelectedFile(null);
  }, []);

  return {
    // State
    semanticSearchEnabled,
    vectorCategory,
    embeddingType,
    vectorFile,
    selectedFile,
    // Setters
    setSemanticSearchEnabled: handleToggle,
    setVectorCategory: handleCategoryChange,
    setEmbeddingType,
    setVectorFile,
    setSelectedFile,
    // Handlers
    loadVectorFileFromPath,
    handleVectorFileUpload,
    isConfigValid,
    reset,
  };
}

export default useSemanticSearch;
