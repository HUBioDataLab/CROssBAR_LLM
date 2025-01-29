import React, { useState } from 'react';
import {
  Button,
  Box,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Typography,
  TextField,
  FormControlLabel,
  Checkbox,
  CircularProgress,
} from '@mui/material';
import AutocompleteTextField from './AutocompleteTextField';
import axios from '../services/api';
import SampleQuestions from './SampleQuestions';
import VectorUpload from './VectorUpload';

function VectorSearch({ 
  setQueryResult, 
  setExecutionResult, 
  addLatestQuery,
  provider,
  setProvider,
  llmType,
  setLlmType,
  apiKey,
  setApiKey 
}) {
  const [question, setQuestion] = useState('');
  const [topK, setTopK] = useState(5);
  const [verbose, setVerbose] = useState(false);
  const [vectorCategory, setVectorCategory] = useState('');
  const [embeddingType, setEmbeddingType] = useState('');
  const [vectorFile, setVectorFile] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [runnedQuery, setRunnedQuery] = useState(false);
  const [generatedQuery, setGeneratedQuery] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showWarning, setShowWarning] = useState(false);
  const [logs, setLogs] = useState('');

  const modelChoices = {
    OpenAI: [
      'gpt-4o',
      'gpt-4o-mini',
      'gpt-3.5-turbo',
      'gpt-4-turbo',
      'gpt-3.5-turbo-instruct',
      { value: 'separator', label: '──────────' },
      'gpt-3.5-turbo-1106',
      'gpt-3.5-turbo-0125',
      'gpt-4-0125-preview',
      'gpt-4-turbo-preview',
      'gpt-4-1106-preview',
      'gpt-4-32k-0613',
      'gpt-4-0613',
      'gpt-3.5-turbo-16k',
    ],
    Anthropic: [
      'claude-3-5-sonnet-20240620',
      'claude-3-opus-20240229',
      'claude-3-sonnet-20240229',
      'claude-3-haiku-20240307',
      { value: 'separator', label: '──────────' },
      'claude-2.1',
      'claude-2.0',
      'claude-instant-1.2',
    ],
    OpenRouter: [
      "deepseek/deepseek-r1",
      "deepseek/deepseek-r1-distill-llama-70b",
      "deepseek/deepseek-r1:free",
      "deepseek/deepseek-r1:nitro",
      "deepseek/deepseek-chat",
    ], 
    Google: [
      'gemini-pro',
      'gemini-1.5-pro-latest',
      'gemini-1.5-flash-latest',
    ],
    Groq: [
      'llama3-8b-8192',
      'llama3-70b-8192',
      'mixtral-8x7b-32768',
      'gemma-7b-it',
      'gemma2-9b-it',
    ],
    Ollama: [
      'codestral:latest',
      'llama3:instruct',
      'tomasonjo/codestral-text2cypher:latest',
      'tomasonjo/llama3-text2cypher-demo:latest',
      'llama3.1:8b',
      'qwen2:7b-instruct',
      'gemma2:latest',
    ],
    Nvidia: [
      'meta/llama-3.1-405b-instruct',
      'meta/llama-3.1-70b-instruct',
      'meta/llama-3.1-8b-instruct',
      'nv-mistralai/mistral-nemo-12b-instruct',
      'mistralai/mixtral-8x22b-instruct-v0.1',
      'mistralai/mistral-large-2-instruct',
      'nvidia/nemotron-4-340b-instruct',
    ],
  };

  const supportedModels = ['gpt-4o', 'claude3.5', 'llama3.2-405b', 'deepseek/deepseek-r1']; 

  const handleGenerateQuery = async () => {
    setLoading(true);
    setLogs('');
    try {
      const embedding = JSON.stringify(vectorFile);

      const response = await axios.post('/generate_query/', {
        question,
        llm_type: llmType,
        top_k: topK,
        api_key: apiKey,
        verbose,
        vector_index: embeddingType,
        embedding: embedding,
      });
      setGeneratedQuery(response.data.query);
      setQueryResult(response.data.query);
      setExecutionResult(null);
      setRunnedQuery(false);
      setError(null);
      if (verbose && response.data.logs) {
        setLogs(response.data.logs);
      }
      addLatestQuery({
        question: question,
        query: response.data.query,
        type: 'Generate Query',
        llmType: llmType,
      });
    } catch (err) {
      console.error(err);
      setError('Error generating query.');
    } finally {
      setLoading(false);
    }
  };

  const handleRunGeneratedQuery = async () => {
    setLoading(true);
    setLogs('');
    try {
      const response = await axios.post('/run_query/', {
        query: generatedQuery,
        question,
        llm_type: llmType,
        top_k: topK,
        api_key: apiKey,
        verbose,
      });
      setExecutionResult(response.data);
      setRunnedQuery(true);
      setError(null);
      if (verbose && response.data.logs) {
        setLogs(response.data.logs);
      }
      addLatestQuery({
        question: question,
        query: generatedQuery,
        type: 'Run Query',
        llmType: llmType,
      });
    } catch (err) {
      console.error(err);
      setError('Error executing query.');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateAndRun = async () => {
    setLoading(true);
    setLogs('');
    try {
      const embedding = JSON.stringify(vectorFile);
      const generateQueryResponse = await axios.post('/generate_query/', {
        question,
        llm_type: llmType,
        top_k: topK,
        api_key: apiKey,
        verbose,
        vector_index: embeddingType,
        embedding: embedding,
      });
      const runQueryResponse = await axios.post('/run_query/', {
        query: generateQueryResponse.data.query,
        question,
        llm_type: llmType,
        top_k: topK,
        api_key: apiKey,
        verbose,
      });
      setGeneratedQuery(generateQueryResponse.data.query);
      setQueryResult(generateQueryResponse.data.query);
      setExecutionResult(runQueryResponse.data);
      setRunnedQuery(true);
      setError(null);
      if (verbose && runQueryResponse.data.logs) {
        setLogs(runQueryResponse.data.logs);
      }
      addLatestQuery({
        question: question,
        query: generateQueryResponse.data.query,
        type: 'Generate & Run Query',
        llmType: llmType,
      });
    } catch (err) {
      console.error(err);
      setError('Error generating and running query.');
    } finally {
      setLoading(false);
    }
  };

  const handleSampleQuestionClick = async (sampleQuestionObj) => {
    setQuestion(sampleQuestionObj.question);
    if (sampleQuestionObj.vectorCategory) {
      setVectorCategory(sampleQuestionObj.vectorCategory);
    }
    if (sampleQuestionObj.embeddingType) {
      setEmbeddingType(sampleQuestionObj.embeddingType);
    }
    if (sampleQuestionObj.vectorData) {
      setVectorFile(sampleQuestionObj.vectorData);
    }
    if (sampleQuestionObj.vectorFilePath) {
      try {
        console.log('Using vector file from public folder:', sampleQuestionObj.vectorFilePath);
        const response = await fetch(`${process.env.PUBLIC_URL}/${sampleQuestionObj.vectorFilePath}`);
        const blob = await response.blob();
        const file = new File([blob], sampleQuestionObj.vectorFilePath);
        
        setSelectedFile(file);
      } catch (error) {
        console.error('Error fetching vector file:', error);
      }
    }
  };

  const handleUpload = () => {
    const file = selectedFile;
    console.log('Uploading file:', file);
    if (!file || !vectorCategory) {
      alert('Please select a file and vector category.');
      return;
    }

    const formData = new FormData();
    formData.append('vector_category', vectorCategory);
    if (embeddingType) {
      formData.append('embedding_type', embeddingType);
    }
    formData.append('file', file);

    axios
      .post('/upload_vector/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })
      .then((response) => {
        console.log('File uploaded successfully:', response.data);
        alert('File uploaded successfully.');
        setVectorFile(response.data); // Update vectorFile with response
      })
      .catch((error) => {
        console.error('Error uploading file:', error);
        alert(error.response?.data?.detail || 'Error uploading file.');
      });
  };

  return (
    <div>
      {/* Autocomplete Text Field */}
      <AutocompleteTextField
        label="Enter your question"
        value={question}
        setValue={setQuestion}
        placeholder="Type your question here..."
        required
      />
      <SampleQuestions onClick={handleSampleQuestionClick} isVectorTab={true} />

      {/* Provider Selection */}
      <FormControl fullWidth margin="normal" required>
        <InputLabel id="provider-label">Provider</InputLabel>
        <Select
          labelId="provider-label"
          value={provider}
          onChange={(e) => {
            setProvider(e.target.value);
            setLlmType('');
          }}
          label="Provider"
        >
          {Object.keys(modelChoices).map((providerName) => (
            <MenuItem key={providerName} value={providerName}>
              {providerName}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      {/* LLM Type Selection */}
      {provider && (
        <FormControl fullWidth margin="normal" required>
          <InputLabel id="llm-type-label">LLM Type</InputLabel>
          <Select
            labelId="llm-type-label"
            value={llmType}
            onChange={(e) => {
              const selectedModel = e.target.value;
              if (selectedModel !== 'separator') {
                setLlmType(selectedModel);
                if (!supportedModels.includes(selectedModel)) {
                  setShowWarning(true);
                } else {
                  setShowWarning(false);
                }
              }
            }}
            label="LLM Type"
          >
            {modelChoices[provider].map((model) => (
              typeof model === 'object' ? (
                <MenuItem key={model.value} value={model.value} disabled sx={{ opacity: 0.5 }}>
                  {model.label}
                </MenuItem>
              ) : (
              <MenuItem key={model} value={model}>
                {model}
              </MenuItem>
              )
            ))}
          </Select>
        </FormControl>
      )}
      {showWarning && (
              <Typography color="warning" sx={{ mt: 2 }}>
                Warning: Smaller language models may produce inaccurate 
                or fabricated responses ("hallucinations") so we recommend
                using larger models such as Claude Sonnet, GPT-4, and Meta Llama 3.1 405B for accurate results. 
              </Typography>
            )}
      {/* API Key Input */}
      <TextField
        label="API Key for LLM"
        type="password"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        fullWidth
        margin="normal"
        helperText="Enter your API key for the selected LLM."
        required
      />
      {/* Limit Query Return Selection */}
      <FormControl fullWidth margin="normal" required>
        <InputLabel id="top-k-label">Limit Query Return</InputLabel>
        <Select
          labelId="top-k-label"
          value={topK}
          onChange={(e) => setTopK(e.target.value)}
          label="Limit Query Return"
        >
          {[1, 3, 5, 10, 15, 20, 50, 100].map((k) => (
            <MenuItem key={k} value={k}>
              {k}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      {/* Verbose Mode Checkbox */}
      <FormControlLabel
        control={
          <Checkbox
            checked={verbose}
            onChange={(e) => setVerbose(e.target.checked)}
          />
        }
        label="Enable Verbose Mode"
      />

      {/* Vector Upload Component */}
      <VectorUpload
        vectorCategory={vectorCategory}
        setVectorCategory={setVectorCategory}
        embeddingType={embeddingType}
        setEmbeddingType={setEmbeddingType}
        vectorFile={vectorFile}
        setVectorFile={setVectorFile}
        selectedFile={selectedFile}
        setSelectedFile={setSelectedFile}
        handleUpload={handleUpload}
      />
      {/* Buttons */}
      <Box sx={{ 
        display: 'flex', 
        gap: 2, 
        mt: 2,
        flexDirection: { xs: 'column', sm: 'row' }
      }}>
        <Button
          variant="outlined"
          fullWidth
          onClick={handleGenerateQuery}
          disabled={loading || !question || !provider || !llmType || !apiKey || !topK}
        >
          Generate Cypher Query
        </Button>
        <Button
          variant="contained"
          fullWidth
          onClick={handleRunGeneratedQuery}
          disabled={!generatedQuery || loading}
        >
          Run Generated Query
        </Button>
      </Box>
      <Button
        variant="contained"
        fullWidth
        onClick={handleGenerateAndRun}
        sx={{ mt: 2 }}
        disabled={loading || !question || !provider || !llmType || !apiKey || !topK}
      >
        Generate & Run Query
      </Button>
      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
          <CircularProgress />
        </Box>
      )}
      {logs && (
        <Box
          sx={{
            backgroundColor: '#2d2d2d',
            padding: 2,
            borderRadius: 1,
            overflow: 'auto',
            maxHeight: 200,
            mt: 2,
          }}
        >
          <pre
            style={{
              margin: 0,
              fontFamily: 'monospace',
              fontSize: 12,
              color: '#cccccc',
            }}
          >
            {logs}
          </pre>
        </Box>
      )}
      {error && (
        <Typography color="error" align="center">
          {error}
        </Typography>
      )}
      {/* Generated Query TextArea */}
      {generatedQuery && !runnedQuery && (
        <TextField
          label="Generated Cypher Query"
          value={generatedQuery}
          onChange={(e) => setGeneratedQuery(e.target.value)}
          fullWidth
          multiline
          rows={4}
          margin="normal"
        />
      )}
    </div>
  );
}

export default VectorSearch;