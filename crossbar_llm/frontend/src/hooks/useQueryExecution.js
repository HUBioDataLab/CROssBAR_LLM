import { useState, useRef, useCallback } from 'react';
import api from '../services/api';
import axios from 'axios';

/**
 * Hook for managing query generation and execution.
 * 
 * @param {Object} config - Configuration object
 * @returns {Object} Query execution state and handlers
 */
export function useQueryExecution({
  provider,
  llmType,
  apiKey,
  apiKeysStatus,
  sessionId,
  semanticSearchEnabled,
  vectorCategory,
  embeddingType,
  vectorFile,
  topK,
  verbose,
  addConversationTurn,
}) {
  const [isLoading, setIsLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState('');
  const [error, setError] = useState(null);
  const [queryResult, setQueryResult] = useState(null);
  const [editableQuery, setEditableQuery] = useState('');
  const [originalQuery, setOriginalQuery] = useState('');
  const [pendingQuestion, setPendingQuestion] = useState('');
  const [queryGenerated, setQueryGenerated] = useState(false);
  const [isEditingQuery, setIsEditingQuery] = useState(false);
  const [executionResult, setExecutionResult] = useState(null);
  const [pendingUserQuestion, setPendingUserQuestion] = useState('');

  const abortControllerRef = useRef(null);

  // Get effective API key
  const getEffectiveApiKey = useCallback(() => {
    return (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;
  }, [apiKeysStatus, provider, apiKey]);

  // Build request data
  const buildRequestData = useCallback((question) => {
    const requestData = {
      question,
      llm_type: llmType,
      provider,
      api_key: getEffectiveApiKey(),
      verbose,
      top_k: topK,
      session_id: sessionId,
    };

    if (semanticSearchEnabled && vectorCategory && embeddingType) {
      requestData.vector_index = embeddingType;
      requestData.vector_category = vectorCategory;
      if (vectorFile) {
        requestData.embedding = JSON.stringify(vectorFile);
      }
    }

    return requestData;
  }, [llmType, provider, getEffectiveApiKey, verbose, topK, sessionId, semanticSearchEnabled, vectorCategory, embeddingType, vectorFile]);

  // Handle errors
  const handleError = useCallback((err) => {
    if (axios.isCancel(err) || err.name === 'CanceledError' || err.name === 'AbortError') {
      console.log('Request cancelled');
      return;
    }
    
    console.error('Error:', err);
    let errorMessage = 'An error occurred';
    const detail = err.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (Array.isArray(detail)) {
        errorMessage = detail.map(e => e.msg || JSON.stringify(e)).join(', ');
      } else if (typeof detail === 'object') {
        errorMessage = detail.msg || detail.error || JSON.stringify(detail);
      }
    } else if (err.message) {
      errorMessage = err.message;
    }
    setError(errorMessage);
  }, []);

  // Generate query only (without running)
  const handleGenerateOnly = useCallback(async (question) => {
    if (!question.trim() || isLoading) return;

    setPendingQuestion(question);
    setPendingUserQuestion(question);
    setError(null);
    setIsLoading(true);
    setCurrentStep('Generating Cypher query...');

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      const requestData = buildRequestData(question);
      const generateResponse = await api.post('/generate_query/', requestData, { signal });

      const cypherQuery = generateResponse.data.query;
      setQueryResult(cypherQuery);
      setEditableQuery(cypherQuery);
      setOriginalQuery(cypherQuery);
      setQueryGenerated(true);
      setIsEditingQuery(false);

      return cypherQuery;
    } catch (err) {
      handleError(err);
      setPendingQuestion('');
      setPendingUserQuestion('');
      return null;
    } finally {
      setIsLoading(false);
      setCurrentStep('');
      abortControllerRef.current = null;
    }
  }, [isLoading, buildRequestData, handleError]);

  // Run the edited query
  const handleRunEditedQuery = useCallback(async () => {
    if (!editableQuery.trim() || isLoading) return;
    if (!pendingQuestion) {
      setError('No question associated with this query');
      return;
    }

    setError(null);
    setPendingUserQuestion(pendingQuestion);
    setIsLoading(true);
    setCurrentStep('Executing query...');

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      const runResponse = await api.post('/run_query/', {
        query: editableQuery,
        question: pendingQuestion,
        llm_type: llmType,
        provider,
        api_key: getEffectiveApiKey(),
        verbose,
        top_k: topK,
        session_id: sessionId,
        is_semantic_search: semanticSearchEnabled,
        vector_category: semanticSearchEnabled ? vectorCategory : null,
      }, { signal });

      const result = {
        result: runResponse.data.result,
        response: runResponse.data.response,
        followUpQuestions: runResponse.data.follow_up_questions || [],
      };
      setExecutionResult(result);
      setQueryResult(editableQuery);

      // Add to conversation history
      addConversationTurn({
        question: pendingQuestion,
        cypherQuery: editableQuery,
        response: runResponse.data.response,
        result: runResponse.data.result,
        followUpQuestions: runResponse.data.follow_up_questions || [],
        isSemanticSearch: semanticSearchEnabled,
        vectorConfig: semanticSearchEnabled ? { vectorCategory, embeddingType } : null,
      });

      // Reset query editing state
      setQueryGenerated(false);
      setPendingQuestion('');
      setIsEditingQuery(false);

      return result;
    } catch (err) {
      handleError(err);
      setPendingUserQuestion('');
      return null;
    } finally {
      setIsLoading(false);
      setCurrentStep('');
      setPendingUserQuestion('');
      abortControllerRef.current = null;
    }
  }, [editableQuery, isLoading, pendingQuestion, llmType, provider, getEffectiveApiKey, verbose, topK, sessionId, semanticSearchEnabled, vectorCategory, embeddingType, addConversationTurn, handleError]);

  // Generate and run query
  const handleSubmit = useCallback(async (question) => {
    if (!question.trim() || isLoading) return;

    setPendingUserQuestion(question);
    setError(null);
    setIsLoading(true);
    setCurrentStep('Generating Cypher query...');
    
    // Reset query editing state
    setQueryGenerated(false);
    setPendingQuestion('');

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      const requestData = buildRequestData(question);

      // Step 1: Generate Cypher query
      const generateResponse = await api.post('/generate_query/', requestData, { signal });

      const cypherQuery = generateResponse.data.query;
      setQueryResult(cypherQuery);
      setEditableQuery(cypherQuery);
      setOriginalQuery(cypherQuery);
      setCurrentStep('Executing query...');

      // Step 2: Run the query
      const runResponse = await api.post('/run_query/', {
        query: cypherQuery,
        question,
        llm_type: llmType,
        provider,
        api_key: getEffectiveApiKey(),
        verbose,
        top_k: topK,
        session_id: sessionId,
        is_semantic_search: semanticSearchEnabled,
        vector_category: semanticSearchEnabled ? vectorCategory : null,
      }, { signal });

      const result = {
        result: runResponse.data.result,
        response: runResponse.data.response,
        followUpQuestions: runResponse.data.follow_up_questions || [],
      };
      setExecutionResult(result);

      // Add to conversation history
      addConversationTurn({
        question,
        cypherQuery,
        response: runResponse.data.response,
        result: runResponse.data.result,
        followUpQuestions: runResponse.data.follow_up_questions || [],
        isSemanticSearch: semanticSearchEnabled,
        vectorConfig: semanticSearchEnabled ? { vectorCategory, embeddingType } : null,
      });

      return result;
    } catch (err) {
      handleError(err);
      setPendingUserQuestion('');
      return null;
    } finally {
      setIsLoading(false);
      setCurrentStep('');
      setPendingUserQuestion('');
      abortControllerRef.current = null;
    }
  }, [isLoading, buildRequestData, llmType, provider, getEffectiveApiKey, verbose, topK, sessionId, semanticSearchEnabled, vectorCategory, embeddingType, addConversationTurn, handleError]);

  // Cancel ongoing request
  const handleCancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    setCurrentStep('');
  }, []);

  // Reset query editing state
  const resetQueryState = useCallback(() => {
    setQueryGenerated(false);
    setPendingQuestion('');
    setEditableQuery('');
    setOriginalQuery('');
  }, []);

  // Reset editable query to original
  const resetToOriginalQuery = useCallback(() => {
    setEditableQuery(originalQuery);
  }, [originalQuery]);

  return {
    // State
    isLoading,
    currentStep,
    error,
    queryResult,
    editableQuery,
    originalQuery,
    pendingQuestion,
    queryGenerated,
    isEditingQuery,
    executionResult,
    pendingUserQuestion,
    // Setters
    setError,
    setQueryResult,
    setEditableQuery,
    setOriginalQuery,
    setPendingQuestion,
    setQueryGenerated,
    setIsEditingQuery,
    setExecutionResult,
    // Handlers
    handleGenerateOnly,
    handleRunEditedQuery,
    handleSubmit,
    handleCancel,
    resetQueryState,
    resetToOriginalQuery,
  };
}

export default useQueryExecution;
