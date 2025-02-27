import React, { useEffect, useState, useRef } from 'react';
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
  useTheme,
} from '@mui/material';
import AutocompleteTextField from './AutocompleteTextField';
import axios from '../services/api';
import SampleQuestions from './SampleQuestions';

function QueryInput({ 
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
  const [runnedQuery, setRunnedQuery] = useState(false);
  const [generatedQuery, setGeneratedQuery] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState('');
  const [showWarning, setShowWarning] = useState(false);
  const [realtimeLogs, setRealtimeLogs] = useState('');
  const eventSourceRef = useRef(null);
  const theme = useTheme();

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
      'claude-3-5-sonnet-latest',
      'claude-3-7-sonnet-latest',
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
      'gemini-2.0-flash-thinking-exp-01-21',
      'gemini-2.0-pro-exp-02-05',
      'gemini-2.0-flash',
      'gemini-2.0-flash-lite',
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

  // Modify the setupLogStream function to better handle the connection and errors
  const setupLogStream = () => {
      if (verbose) {
          console.log('Setting up log stream for verbose mode');
          // Close any existing connection
          if (eventSourceRef.current) {
              eventSourceRef.current.close();
          }
          
          setRealtimeLogs('Connecting to log stream...\n');
          
          // Create new EventSource connection with a timestamp to avoid caching
          const timestamp = new Date().getTime();
          eventSourceRef.current = new EventSource(`/stream-logs?t=${timestamp}`);
          
          eventSourceRef.current.onopen = () => {
              setRealtimeLogs(prev => prev + 'Log stream connected successfully\n');
          };
          
          eventSourceRef.current.onmessage = (event) => {
              try {
                  const data = JSON.parse(event.data);
                  setRealtimeLogs(prev => prev + data.log + '\n');
                  
                  // Auto-scroll to bottom of log container
                  if (logContainerRef.current) {
                      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
                  }
              } catch (e) {
                  console.error('Error parsing log data:', e);
                  setRealtimeLogs(prev => prev + `Error parsing log: ${e.message}\n`);
              }
          };
          
          eventSourceRef.current.onerror = (error) => {
              console.error('EventSource failed:', error);
              setRealtimeLogs(prev => prev + `EventSource error: Connection to log stream failed or was closed\n`);
              // Try to reconnect after a delay
              setTimeout(() => {
                  if (verbose && !eventSourceRef.current) {
                      setupLogStream();
                  }
              }, 5000);
          };
      }
  };
  
  const cleanupLogStream = () => {
      if (eventSourceRef.current) {
          console.log('Cleaning up log stream');
          eventSourceRef.current.close();
          eventSourceRef.current = null;
      }
  };

  // Add a ref for auto-scrolling the log container
  const logContainerRef = useRef(null);

  // Cleanup on component unmount
  useEffect(() => {
      return () => cleanupLogStream();
  }, []);

  // Setup log stream when verbose mode changes
  useEffect(() => {
      if (verbose) {
          setupLogStream();
      } else {
          cleanupLogStream();
          setRealtimeLogs('');
      }
  }, [verbose]);

  useEffect(() => {
      return () => cleanupLogStream();
  }, []);

  const handleGenerateQuery = async () => {
    setLoading(true);
    setRealtimeLogs(verbose ? 'Generating Cypher query...\n' : '');
    setLogs('');
    try {
      if (verbose) {
        setRealtimeLogs(prev => prev + `Sending request with parameters:\n- Question: ${question}\n- Model: ${llmType}\n- Top K: ${topK}\n- Verbose: ${verbose}\n`);
      }
      
      const response = await axios.post('/generate_query/', {
        question,
        llm_type: llmType,
        top_k: topK,
        api_key: apiKey,
        verbose,
      });
      
      setGeneratedQuery(response.data.query);
      setQueryResult(response.data.query);
      setExecutionResult(null);
      setRunnedQuery(false);
      setError(null);
      
      if (verbose) {
        if (response.data.logs) {
          setLogs(response.data.logs);
          setRealtimeLogs(prev => prev + 'Query generation completed successfully!\n');
        } else {
          setRealtimeLogs(prev => prev + 'Warning: No logs returned from server despite verbose mode enabled\n');
        }
      }
      
      addLatestQuery({
        question: question,
        query: response.data.query,
        type: 'Generate Query',
        llmType: llmType,
        naturalAnswer: 'N/A',
      });
    } catch (err) {
      console.error(err);
      const errorMessage = err.response?.data?.detail?.error || 'Error generating query.';
      const errorLogs = err.response?.data?.detail?.logs || '';
      
      if (verbose) {
        setRealtimeLogs(prev => prev + `ERROR: ${errorMessage}\n`);
        if (errorLogs) {
          setLogs(errorLogs);
        }
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };
  
  const handleRunGeneratedQuery = async () => {
    setLoading(true);
    setLogs('');
    setRealtimeLogs(verbose ? 'Executing Cypher query...\n' : '');
    try {
      if (verbose) {
        setRealtimeLogs(prev => prev + `Query to execute:\n${generatedQuery}\n\n`);
      }
      
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
      
      if (verbose) {
        if (response.data.logs) {
          setLogs(response.data.logs);
          setRealtimeLogs(prev => prev + 'Query executed successfully!\n');
        } else {
          setRealtimeLogs(prev => prev + 'Warning: No logs returned from server despite verbose mode enabled\n');
        }
      }
      
      addLatestQuery({
        question: question,
        query: generatedQuery,
        type: 'Run Query',
        llmType: llmType,
        naturalAnswer: response.data.response,
      });
    } catch (err) {
      console.error(err);
      const errorMessage = err.response?.data?.detail?.error || 'Error executing query.';
      const errorLogs = err.response?.data?.detail?.logs || '';
      
      if (verbose) {
        setRealtimeLogs(prev => prev + `ERROR: ${errorMessage}\n`);
        if (errorLogs) {
          setLogs(errorLogs);
        }
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };
  
  const handleGenerateAndRun = async () => {
    setLoading(true);
    setLogs('');
    setRealtimeLogs(verbose ? 'Generating and executing Cypher query...\n' : '');
    try {
      if (verbose) {
        setRealtimeLogs(prev => prev + `Step 1: Generating query for question: "${question}"\n`);
      }
      
      const generateQueryResponse = await axios.post('/generate_query/', {
        question,
        llm_type: llmType,
        top_k: topK,
        api_key: apiKey,
        verbose,
      });
      
      const generatedQuery = generateQueryResponse.data.query;
      
      if (verbose) {
        setRealtimeLogs(prev => prev + `Query generated: ${generatedQuery}\n\nStep 2: Executing the generated query\n`);
      }
      
      const runQueryResponse = await axios.post('/run_query/', {
        query: generatedQuery,
        question,
        llm_type: llmType,
        top_k: topK,
        api_key: apiKey,
        verbose,
      });
      
      setGeneratedQuery(generatedQuery);
      setQueryResult(generatedQuery);
      setExecutionResult(runQueryResponse.data);
      setRunnedQuery(true);
      setError(null);
      
      if (verbose) {
        if (runQueryResponse.data.logs) {
          setLogs(runQueryResponse.data.logs);
          setRealtimeLogs(prev => prev + 'Query generated and executed successfully!\n');
        } else {
          setRealtimeLogs(prev => prev + 'Warning: No logs returned from server despite verbose mode enabled\n');
        }
      }
      
      addLatestQuery({
        question: question,
        query: generatedQuery,
        type: 'Generate & Run Query',
        llmType: llmType,
        naturalAnswer: runQueryResponse.data.response,
      });
    } catch (err) {
      console.error(err);
      const errorMessage = err.response?.data?.detail?.error || 'Error generating and running query.';
      const errorLogs = err.response?.data?.detail?.logs || '';
      
      if (verbose) {
        setRealtimeLogs(prev => prev + `ERROR: ${errorMessage}\n`);
        if (errorLogs) {
          setLogs(errorLogs);
        }
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleSampleQuestionClick = (sampleQuestion) => {
    setQuestion(sampleQuestion.question);
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
      <SampleQuestions onClick={handleSampleQuestionClick} isVectorTab={false}/>
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
          variant="outlined"
          fullWidth
          onClick={handleRunGeneratedQuery}
          disabled={!generatedQuery || loading}
        >
          Run Generated Query
        </Button>
      </Box>
      <Button
        variant="outlined"
        fullWidth
        onClick={handleGenerateAndRun}
        sx={{ 
          mt: 2,
          border: '2px solid #ff0000',
          color: '#ff0000',
          backgroundColor: 'transparent',
          '&:hover': {
            backgroundColor: 'rgba(255, 0, 0, 0.04)',
            border: '2px solid #ff0000',
          },
          '&.Mui-disabled': {
            border: theme.palette.mode === 'dark' ? '2px solid rgba(255, 0, 0, 0.3)' : '2px solid rgba(255, 0, 0, 0.3)',
            color: theme.palette.mode === 'dark' ? 'rgba(255, 0, 0, 0.3)' : 'rgba(255, 0, 0, 0.3)',
          }
        }}
        disabled={loading || !question || !provider || !llmType || !apiKey || !topK}
      >
        Generate & Run Query
      </Button>
      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
          <CircularProgress />
        </Box>
      )}
      {/* Real-time logs from EventSource */}
      {verbose && (
        <Box
          sx={{
            backgroundColor: theme.palette.mode === 'dark' ? '#1e1e1e' : '#f5f5f5',
            padding: 2,
            borderRadius: 1,
            overflow: 'auto',
            maxHeight: 200,
            mt: 2,
            border: `1px solid ${theme.palette.divider}`
          }}
          ref={logContainerRef}
        >
          <Typography variant="subtitle2" gutterBottom>Real-time Logs:</Typography>
          <pre
            style={{
              margin: 0,
              fontFamily: 'monospace',
              fontSize: 12,
              color: theme.palette.text.primary,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word'
            }}
          >
            {realtimeLogs || 'Waiting for logs...'}
          </pre>
        </Box>
      )}
      
      {/* Final logs from API response */}
      {logs && verbose && (
        <Box
          sx={{
            backgroundColor: theme.palette.mode === 'dark' ? '#1e1e1e' : '#f5f5f5',
            padding: 2,
            borderRadius: 1,
            overflow: 'auto',
            maxHeight: 300,
            mt: 2,
            border: `1px solid ${theme.palette.divider}`
          }}
        >
          <Typography variant="subtitle2" gutterBottom>Complete Logs:</Typography>
          <pre
            style={{
              margin: 0,
              fontFamily: 'monospace',
              fontSize: 12,
              color: theme.palette.text.primary,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word'
            }}
          >
            {logs}
          </pre>
        </Box>
      )}
      
      {error && (
        <Typography color="error" align="center" sx={{ mt: 2 }}>
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

export default QueryInput;