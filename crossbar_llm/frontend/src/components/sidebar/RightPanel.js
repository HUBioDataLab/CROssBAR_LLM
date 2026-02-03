import React from 'react';
import {
  Box,
  Typography,
  alpha,
  useTheme,
} from '@mui/material';
import ExampleQueries from './ExampleQueries';
import ModelSettings from './ModelSettings';
import VectorSearchConfig from './VectorSearchConfig';
import QueryEditor from './QueryEditor';
import ResultsSection from './ResultsSection';
import DebugLogs from './DebugLogs';
import { DRAWER_WIDTH } from '../../constants';

/**
 * Right panel container with all sidebar sections.
 */
function RightPanel({
  isOpen,
  expandedSections,
  onToggleSection,
  // Example queries props
  semanticSearchEnabled,
  onExampleClick,
  // Model settings props
  provider,
  setProvider,
  llmType,
  setLlmType,
  apiKey,
  setApiKey,
  apiKeysStatus,
  apiKeysLoaded,
  modelChoices,
  topK,
  setTopK,
  verbose,
  setVerbose,
  isSettingsValid,
  // Vector search props
  vectorCategory,
  onCategoryChange,
  embeddingType,
  onEmbeddingTypeChange,
  vectorFile,
  selectedFile,
  onFileChange,
  isVectorConfigValid,
  // Query editor props
  queryResult,
  editableQuery,
  originalQuery,
  setEditableQuery,
  queryGenerated,
  isEditingQuery,
  setIsEditingQuery,
  pendingQuestion,
  isLoading,
  onRunQuery,
  onCopy,
  copiedIndex,
  // Results props
  executionResult,
  hasValidResults,
  // Node visualization
  NodeVisualization,
  // Debug logs
  realtimeLogs,
}) {
  const theme = useTheme();

  return (
    <Box
      sx={{
        width: isOpen ? DRAWER_WIDTH : 0,
        flexShrink: 0,
        height: '100%',
        borderLeft: isOpen ? `1px solid ${theme.palette.divider}` : 'none',
        backgroundColor: alpha(theme.palette.background.paper, 0.95),
        backdropFilter: 'blur(10px)',
        transition: 'width 0.3s ease',
        overflow: 'hidden',
      }}
    >
      <Box sx={{ p: 2, overflow: 'auto', height: '100%', width: DRAWER_WIDTH }}>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, px: 1 }}>
          Options & Details
        </Typography>

        {/* Example Queries Section */}
        <ExampleQueries
          expanded={expandedSections.examples}
          onToggle={() => onToggleSection('examples')}
          semanticSearchEnabled={semanticSearchEnabled}
          onExampleClick={onExampleClick}
        />

        {/* Settings Section */}
        <ModelSettings
          expanded={expandedSections.settings}
          onToggle={() => onToggleSection('settings')}
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
          isSettingsValid={isSettingsValid}
        />

        {/* Vector Search Configuration Section */}
        {semanticSearchEnabled && (
          <VectorSearchConfig
            expanded={expandedSections.vectorConfig}
            onToggle={() => onToggleSection('vectorConfig')}
            vectorCategory={vectorCategory}
            onCategoryChange={onCategoryChange}
            embeddingType={embeddingType}
            onEmbeddingTypeChange={onEmbeddingTypeChange}
            vectorFile={vectorFile}
            selectedFile={selectedFile}
            onFileChange={onFileChange}
            isConfigValid={isVectorConfigValid}
          />
        )}

        {/* Generated Query Section */}
        {(queryResult || editableQuery) && (
          <QueryEditor
            expanded={expandedSections.query}
            onToggle={() => onToggleSection('query')}
            queryResult={queryResult}
            editableQuery={editableQuery}
            originalQuery={originalQuery}
            setEditableQuery={setEditableQuery}
            queryGenerated={queryGenerated}
            isEditingQuery={isEditingQuery}
            setIsEditingQuery={setIsEditingQuery}
            pendingQuestion={pendingQuestion}
            isLoading={isLoading}
            onRunQuery={onRunQuery}
            onCopy={onCopy}
            copiedIndex={copiedIndex}
          />
        )}

        {/* Node Visualization Section */}
        {hasValidResults && NodeVisualization && (
          <NodeVisualization executionResult={executionResult} />
        )}

        {/* Raw Results Section */}
        {hasValidResults && executionResult?.result && (
          <ResultsSection
            expanded={expandedSections.results}
            onToggle={() => onToggleSection('results')}
            results={executionResult.result}
          />
        )}

        {/* Debug Logs Section */}
        <DebugLogs
          expanded={expandedSections.logs}
          onToggle={() => onToggleSection('logs')}
          logs={realtimeLogs}
        />
      </Box>
    </Box>
  );
}

export default RightPanel;
