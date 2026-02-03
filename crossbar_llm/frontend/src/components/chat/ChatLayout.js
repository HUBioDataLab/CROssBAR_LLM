import React, { useState, useRef, useEffect, useCallback } from 'react';
import { flushSync } from 'react-dom';
import {
  Box,
  Snackbar,
  Alert,
  Zoom,
  useTheme,
} from '@mui/material';

// Chat components
import ChatHeader from './ChatHeader';
import ChatMessages from './ChatMessages';
import ChatInput from './ChatInput';

// Sidebar components
import { RightPanel } from '../sidebar';

// Visualization
import { NodeVisualization } from '../visualization';

// Common components
import { ErrorDisplay } from '../common';

// Hooks
import { useApiKeys } from '../../hooks/useApiKeys';
import { useModels } from '../../hooks/useModels';
import { useSemanticSearch } from '../../hooks/useSemanticSearch';
import { useAutocomplete } from '../../hooks/useAutocomplete';
import { useCopyToClipboard } from '../../hooks/useCopyToClipboard';

// Constants
import { DRAWER_WIDTH } from '../../constants';

// API
import api from '../../services/api';
import axios from 'axios';

/**
 * Main chat layout component - refactored to use modular components.
 */
function ChatLayout({
  // State props from App
  provider,
  setProvider,
  llmType,
  setLlmType,
  apiKey,
  setApiKey,
  sessionId,
  conversationHistory,
  addConversationTurn,
  startNewConversation,
  question,
  setQuestion,
  queryResult,
  setQueryResult,
  executionResult,
  setExecutionResult,
  realtimeLogs,
  setRealtimeLogs,
  pendingFollowUp,
  setPendingFollowUp,
}) {
  const theme = useTheme();
  const inputRef = useRef(null);
  const suggestionsRef = useRef(null);
  const inputContainerRef = useRef(null);
  const abortControllerRef = useRef(null);

  // Local state
  const [isLoading, setIsLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState('');
  const [pendingUserQuestion, setPendingUserQuestion] = useState('');
  const [error, setError] = useState(null);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [topK, setTopK] = useState(10);
  const [verbose, setVerbose] = useState(false);
  
  // Query editing state
  const [editableQuery, setEditableQuery] = useState('');
  const [originalQuery, setOriginalQuery] = useState('');
  const [pendingQuestion, setPendingQuestion] = useState('');
  const [queryGenerated, setQueryGenerated] = useState(false);
  const [isEditingQuery, setIsEditingQuery] = useState(false);
  
  // Expanded sections in right panel
  const [expandedSections, setExpandedSections] = useState({
    examples: true,
    settings: false,
    vectorConfig: false,
    query: true,
    results: false,
    visualization: true,
    logs: false,
  });

  // Custom hooks
  const { apiKeysStatus, apiKeysLoaded } = useApiKeys(provider, setApiKey);
  const { modelChoices, modelsLoaded } = useModels();
  const semanticSearch = useSemanticSearch();
  const autocomplete = useAutocomplete(question, setQuestion);
  const { copiedIndex, copySnackbar, handleCopy, setCopySnackbar } = useCopyToClipboard();

  // Ref to hold handleSubmit for use in useEffect
  const handleSubmitRef = useRef(null);

  // Sync editable query with queryResult
  useEffect(() => {
    if (queryResult && !queryGenerated) {
      setEditableQuery(queryResult);
      setOriginalQuery(queryResult);
    }
  }, [queryResult, queryGenerated]);

  // Handle pending follow-up
  useEffect(() => {
    if (pendingFollowUp && question === pendingFollowUp && !isLoading) {
      setPendingFollowUp(null);
      if (handleSubmitRef.current) {
        handleSubmitRef.current();
      }
    }
  }, [pendingFollowUp, question, isLoading, setPendingFollowUp]);

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    setCurrentStep('');
  };

  // Check if settings are valid
  const isSettingsValid = useCallback(() => {
    if (!provider) return false;
    if (!llmType) return false;
    if (!apiKeysStatus[provider] && !apiKey) return false;
    return true;
  }, [provider, llmType, apiKeysStatus, apiKey]);

  // Check if query result has valid data
  const hasValidResults = useCallback((result) => {
    if (!result) return false;
    if (!Array.isArray(result)) return false;
    if (result.length === 0) return false;
    if (result.length === 1 && typeof result[0] === 'string' && 
        result[0].toLowerCase().includes('did not return any result')) {
      return false;
    }
    return true;
  }, []);

  // Get effective API key
  const getEffectiveApiKey = useCallback(() => {
    return (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;
  }, [apiKeysStatus, provider, apiKey]);

  // Build request data
  const buildRequestData = useCallback((userQuestion) => {
    const requestData = {
      question: userQuestion,
      llm_type: llmType,
      provider,
      api_key: getEffectiveApiKey(),
      verbose,
      top_k: topK,
      session_id: sessionId,
    };

    if (semanticSearch.semanticSearchEnabled && semanticSearch.vectorCategory && semanticSearch.embeddingType) {
      requestData.vector_index = semanticSearch.embeddingType;
      requestData.vector_category = semanticSearch.vectorCategory;
      if (semanticSearch.vectorFile) {
        requestData.embedding = JSON.stringify(semanticSearch.vectorFile);
      }
    }

    return requestData;
  }, [llmType, provider, getEffectiveApiKey, verbose, topK, sessionId, semanticSearch]);

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

  // Generate query only
  const handleGenerateOnly = async (e) => {
    e?.preventDefault();
    if (!question.trim() || isLoading) return;

    if (!isSettingsValid()) {
      setExpandedSections(prev => ({ ...prev, settings: true }));
      setError('Please configure model settings first');
      return;
    }

    if (!semanticSearch.isConfigValid()) {
      setExpandedSections(prev => ({ ...prev, vectorConfig: true }));
      setError('Please configure vector search settings (category and embedding type)');
      return;
    }

    flushSync(() => {
      setExpandedSections(prev => ({ ...prev, settings: false, examples: false }));
    });

    const userQuestion = question.trim();
    setPendingQuestion(userQuestion);
    setQuestion('');
    setPendingUserQuestion(userQuestion);
    setError(null);
    setIsLoading(true);
    setCurrentStep('Generating Cypher query...');

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      const requestData = buildRequestData(userQuestion);
      const generateResponse = await api.post('/generate_query/', requestData, { signal });

      const cypherQuery = generateResponse.data.query;
      setQueryResult(cypherQuery);
      setEditableQuery(cypherQuery);
      setOriginalQuery(cypherQuery);
      setQueryGenerated(true);
      setIsEditingQuery(false);
      setExpandedSections(prev => ({ ...prev, query: true }));

    } catch (err) {
      handleError(err);
      setPendingQuestion('');
      setPendingUserQuestion('');
    } finally {
      setIsLoading(false);
      setCurrentStep('');
      abortControllerRef.current = null;
    }
  };

  // Run the edited query
  const handleRunEditedQuery = async () => {
    if (!editableQuery.trim() || isLoading) return;
    if (!pendingQuestion) {
      setError('No question associated with this query');
      return;
    }

    flushSync(() => {
      setExpandedSections(prev => ({ ...prev, examples: false }));
    });
    
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
        is_semantic_search: semanticSearch.semanticSearchEnabled,
        vector_category: semanticSearch.semanticSearchEnabled ? semanticSearch.vectorCategory : null,
      }, { signal });

      setExecutionResult({
        result: runResponse.data.result,
        response: runResponse.data.response,
        followUpQuestions: runResponse.data.follow_up_questions || [],
      });

      setQueryResult(editableQuery);

      addConversationTurn({
        question: pendingQuestion,
        cypherQuery: editableQuery,
        response: runResponse.data.response,
        result: runResponse.data.result,
        followUpQuestions: runResponse.data.follow_up_questions || [],
        isSemanticSearch: semanticSearch.semanticSearchEnabled,
        vectorConfig: semanticSearch.semanticSearchEnabled 
          ? { vectorCategory: semanticSearch.vectorCategory, embeddingType: semanticSearch.embeddingType } 
          : null,
      });

      setQueryGenerated(false);
      setPendingQuestion('');
      setIsEditingQuery(false);

      if (hasValidResults(runResponse.data.result)) {
        setExpandedSections(prev => ({ ...prev, visualization: true }));
      }

    } catch (err) {
      handleError(err);
      setPendingUserQuestion('');
    } finally {
      setIsLoading(false);
      setCurrentStep('');
      setPendingUserQuestion('');
      abortControllerRef.current = null;
    }
  };

  // Generate and run query
  const handleSubmit = async (e) => {
    e?.preventDefault();
    if (!question.trim() || isLoading) return;

    if (!isSettingsValid()) {
      setExpandedSections(prev => ({ ...prev, settings: true }));
      setError('Please configure model settings first');
      return;
    }

    if (!semanticSearch.isConfigValid()) {
      setExpandedSections(prev => ({ ...prev, vectorConfig: true }));
      setError('Please configure vector search settings (category and embedding type)');
      return;
    }

    flushSync(() => {
      setExpandedSections(prev => ({ ...prev, settings: false, examples: false }));
    });

    const userQuestion = question.trim();
    setQuestion('');
    setPendingUserQuestion(userQuestion);
    setError(null);
    setIsLoading(true);
    setCurrentStep('Generating Cypher query...');
    setQueryGenerated(false);
    setPendingQuestion('');

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      const requestData = buildRequestData(userQuestion);
      const generateResponse = await api.post('/generate_query/', requestData, { signal });

      const cypherQuery = generateResponse.data.query;
      setQueryResult(cypherQuery);
      setEditableQuery(cypherQuery);
      setOriginalQuery(cypherQuery);
      setCurrentStep('Executing query...');

      const runResponse = await api.post('/run_query/', {
        query: cypherQuery,
        question: userQuestion,
        llm_type: llmType,
        provider,
        api_key: getEffectiveApiKey(),
        verbose,
        top_k: topK,
        session_id: sessionId,
        is_semantic_search: semanticSearch.semanticSearchEnabled,
        vector_category: semanticSearch.semanticSearchEnabled ? semanticSearch.vectorCategory : null,
      }, { signal });

      setExecutionResult({
        result: runResponse.data.result,
        response: runResponse.data.response,
        followUpQuestions: runResponse.data.follow_up_questions || [],
      });

      addConversationTurn({
        question: userQuestion,
        cypherQuery: cypherQuery,
        response: runResponse.data.response,
        result: runResponse.data.result,
        followUpQuestions: runResponse.data.follow_up_questions || [],
        isSemanticSearch: semanticSearch.semanticSearchEnabled,
        vectorConfig: semanticSearch.semanticSearchEnabled 
          ? { vectorCategory: semanticSearch.vectorCategory, embeddingType: semanticSearch.embeddingType } 
          : null,
      });

      if (hasValidResults(runResponse.data.result)) {
        setExpandedSections(prev => ({ ...prev, visualization: true }));
      }

    } catch (err) {
      handleError(err);
      setPendingUserQuestion('');
    } finally {
      setIsLoading(false);
      setCurrentStep('');
      setPendingUserQuestion('');
      abortControllerRef.current = null;
    }
  };

  // Assign to ref for use in useEffect
  handleSubmitRef.current = handleSubmit;

  const handleFollowUpClick = (followUpQuestion, turn) => {
    if (turn?.isSemanticSearch && turn?.vectorConfig) {
      semanticSearch.setSemanticSearchEnabled(true);
      semanticSearch.setVectorCategory(turn.vectorConfig.vectorCategory || '');
      semanticSearch.setEmbeddingType(turn.vectorConfig.embeddingType || '');
    }
    setQuestion(followUpQuestion);
    setPendingFollowUp(followUpQuestion);
  };

  const handleExampleClick = async (example) => {
    if (typeof example === 'object' && example.question) {
      setQuestion(example.question);
      if (example.vectorCategory) {
        semanticSearch.setSemanticSearchEnabled(true);
        semanticSearch.setVectorCategory(example.vectorCategory);
        semanticSearch.setEmbeddingType(example.embeddingType || '');
        setExpandedSections(prev => ({ ...prev, vectorConfig: true }));
        
        if (example.vectorFilePath) {
          try {
            await semanticSearch.loadVectorFileFromPath(example.vectorFilePath);
          } catch (err) {
            setError(err.message);
          }
        }
      }
    } else {
      setQuestion(example);
    }
    inputRef.current?.focus();
  };

  const handleSemanticSearchToggle = (enabled) => {
    semanticSearch.setSemanticSearchEnabled(enabled);
    if (enabled) {
      setExpandedSections(prev => ({ ...prev, vectorConfig: true }));
    }
  };

  const handleVectorFileChange = async (file) => {
    if (!file) return;
    try {
      await semanticSearch.handleVectorFileUpload(file);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <Box sx={{ 
      display: 'flex', 
      height: 'calc(100vh - 64px)', 
      overflow: 'hidden', 
      mt: '64px', 
      width: '100%',
    }}>
      {/* Main Chat Panel */}
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          minWidth: 0,
          transition: 'all 0.3s ease',
        }}
      >
        <ChatHeader
          messageCount={conversationHistory.length}
          rightPanelOpen={rightPanelOpen}
          onToggleRightPanel={() => setRightPanelOpen(!rightPanelOpen)}
          onNewConversation={startNewConversation}
        />

        <ChatMessages
          conversationHistory={conversationHistory}
          isLoading={isLoading}
          pendingUserQuestion={pendingUserQuestion}
          currentStep={currentStep}
          queryResult={queryResult}
          semanticSearchEnabled={semanticSearch.semanticSearchEnabled}
          vectorCategory={semanticSearch.vectorCategory}
          onCopy={handleCopy}
          copiedIndex={copiedIndex}
          onFollowUpClick={handleFollowUpClick}
        />

        <ErrorDisplay error={error} />

        <ChatInput
          question={question}
          onQuestionChange={autocomplete.handleAutocompleteChange}
          onSubmit={handleSubmit}
          onGenerateOnly={handleGenerateOnly}
          onCancel={handleCancel}
          isLoading={isLoading}
          semanticSearchEnabled={semanticSearch.semanticSearchEnabled}
          onSemanticSearchToggle={handleSemanticSearchToggle}
          vectorCategory={semanticSearch.vectorCategory}
          embeddingType={semanticSearch.embeddingType}
          onConfigureVectorSearch={() => setExpandedSections(prev => ({ ...prev, vectorConfig: !prev.vectorConfig }))}
          showSuggestions={autocomplete.showSuggestions}
          displaySuggestions={autocomplete.displaySuggestions}
          selectedSuggestionIndex={autocomplete.selectedSuggestionIndex}
          onSuggestionClick={autocomplete.handleSuggestionClick}
          onAutocompleteKeyDown={autocomplete.handleAutocompleteKeyDown}
          inputRef={inputRef}
          suggestionsRef={suggestionsRef}
          inputContainerRef={inputContainerRef}
          queryGenerated={queryGenerated}
          pendingQuestion={pendingQuestion}
          onRunEditedQuery={handleRunEditedQuery}
          onEditQuery={() => {
            setExpandedSections(prev => ({ ...prev, query: true }));
            setIsEditingQuery(true);
          }}
          onDismissQuery={() => {
            setQueryGenerated(false);
            setPendingQuestion('');
            setEditableQuery('');
            setOriginalQuery('');
          }}
        />
      </Box>

      {/* Right Panel */}
      <RightPanel
        isOpen={rightPanelOpen}
        expandedSections={expandedSections}
        onToggleSection={toggleSection}
        semanticSearchEnabled={semanticSearch.semanticSearchEnabled}
        onExampleClick={handleExampleClick}
        provider={provider}
        setProvider={setProvider}
        llmType={llmType}
        setLlmType={setLlmType}
        apiKey={apiKey}
        setApiKey={setApiKey}
        apiKeysStatus={apiKeysStatus}
        apiKeysLoaded={apiKeysLoaded}
        modelChoices={modelChoices}
        topK={topK}
        setTopK={setTopK}
        verbose={verbose}
        setVerbose={setVerbose}
        isSettingsValid={isSettingsValid()}
        vectorCategory={semanticSearch.vectorCategory}
        onCategoryChange={semanticSearch.setVectorCategory}
        embeddingType={semanticSearch.embeddingType}
        onEmbeddingTypeChange={semanticSearch.setEmbeddingType}
        vectorFile={semanticSearch.vectorFile}
        selectedFile={semanticSearch.selectedFile}
        onFileChange={handleVectorFileChange}
        isVectorConfigValid={semanticSearch.isConfigValid()}
        queryResult={queryResult}
        editableQuery={editableQuery}
        originalQuery={originalQuery}
        setEditableQuery={setEditableQuery}
        queryGenerated={queryGenerated}
        isEditingQuery={isEditingQuery}
        setIsEditingQuery={setIsEditingQuery}
        pendingQuestion={pendingQuestion}
        isLoading={isLoading}
        onRunQuery={handleRunEditedQuery}
        onCopy={handleCopy}
        copiedIndex={copiedIndex}
        executionResult={executionResult}
        hasValidResults={hasValidResults(executionResult?.result)}
        NodeVisualization={NodeVisualization}
        realtimeLogs={realtimeLogs}
      />

      {/* Snackbar for copy feedback */}
      <Snackbar
        open={copySnackbar}
        autoHideDuration={1500}
        onClose={() => setCopySnackbar(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Zoom in={copySnackbar}>
          <Alert severity="success" variant="filled" sx={{ borderRadius: '12px' }}>
            Copied to clipboard
          </Alert>
        </Zoom>
      </Snackbar>
    </Box>
  );
}

export default ChatLayout;
