import React, { useState, useRef, useEffect, useCallback } from 'react';
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
  Paper,
  Collapse,
  Alert,
  Tooltip,
  IconButton,
  Grid,
  Zoom,
  Divider,
  Chip,
  alpha,
  Switch,
  Fade,
  InputAdornment,
  useMediaQuery,
  Backdrop,
  LinearProgress,
} from '@mui/material';
import AutocompleteTextField from './AutocompleteTextField';
import axios from 'axios';
import api, { getAvailableModels } from '../services/api';
import SampleQuestions from './SampleQuestions';
import VectorUpload from './VectorUpload';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SendIcon from '@mui/icons-material/Send';
import TuneIcon from '@mui/icons-material/Tune';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import StorageIcon from '@mui/icons-material/Storage';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import TerminalIcon from '@mui/icons-material/Terminal';
import KeyIcon from '@mui/icons-material/Key';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CodeIcon from '@mui/icons-material/Code';
import RestoreIcon from '@mui/icons-material/Restore';
import StopIcon from '@mui/icons-material/Stop';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import NodeVisualization from './NodeVisualization';

function VectorSearch({
  setQueryResult,
  setExecutionResult,
  addLatestQuery,
  provider,
  setProvider,
  llmType,
  setLlmType,
  apiKey,
  setApiKey,
  question,
  setQuestion,
  setRealtimeLogs
}) {
  const [topK, setTopK] = useState(10);
  const [verbose, setVerbose] = useState(false);
  const [vectorCategory, setVectorCategory] = useState('');
  const [embeddingType, setEmbeddingType] = useState('');
  const [vectorFile, setVectorFile] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [runnedQuery, setRunnedQuery] = useState(false);
  const [generatedQuery, setGeneratedQuery] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeButton, setActiveButton] = useState(null);
  const [showWarning, setShowWarning] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showDebugLogs, setShowDebugLogs] = useState(false);
  const [highlightSettings, setHighlightSettings] = useState(false);
  const [logs, setLogs] = useState('');
  const [localRealtimeLogs, setLocalRealtimeLogs] = useState('');
  const [apiKeysStatus, setApiKeysStatus] = useState({});
  const [apiKeysLoaded, setApiKeysLoaded] = useState(false);
  const [modelChoices, setModelChoices] = useState({});
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);
  const [retryCountdown, setRetryCountdown] = useState(0);
  const [limitType, setLimitType] = useState('');
  const [originalQuery, setOriginalQuery] = useState('');
  // Local state for displaying NodeVisualization
  const [localExecutionResult, setLocalExecutionResult] = useState(null);
  // Refs for scroll sync between textarea and syntax highlighter
  const textareaRef = useRef(null);
  const highlighterRef = useRef(null);
  const eventSourceRef = useRef(null);
  const logContainerRef = useRef(null);
  const theme = useTheme();
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const dropzoneRef = useRef(null);
  const isFirstRender = useRef(true);
  const abortControllerRef = useRef(null);
  const countdownTimerRef = useRef(null);

  const supportedModels = ['gpt-5.1', 'gpt-4o', 'o4-mini', 'claude-sonnet-4-5', 'claude-opus-4-1', 'llama3.2-405b', 'deepseek/deepseek-r1', 'gemini-2.5-pro', 'gemini-2.5-flash'];

  // Fetch available models on component mount
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const models = await getAvailableModels();
        setModelChoices(models);
        setModelsLoaded(true);
      } catch (error) {
        console.error('Error fetching available models:', error);
        // Fallback to empty object if fetch fails
        setModelChoices({});
        setModelsLoaded(true);
      }
    };

    fetchModels();
  }, []);

  // Fetch API keys status on component mount
  useEffect(() => {
    const fetchApiKeysStatus = async () => {
      try {
        const response = await api.get('/api_keys_status/');
        if (response.data) {
          setApiKeysStatus(response.data);
          setApiKeysLoaded(true);

          // Set API key to "env" if the selected provider has an API key in .env
          if (provider && response.data[provider]) {
            setApiKey('env');
          }
        }
      } catch (error) {
        console.error('Error fetching API keys status:', error);
      }
    };

    fetchApiKeysStatus();
  }, [provider, setApiKey]);

  // Check if the selected provider requires an API key to be entered
  const providerNeedsApiKey = useCallback(() => {
    if (!apiKeysLoaded) return true;

    // If the provider has an API key in .env and user wants to use it,
    // no need to enter one
    if (apiKeysStatus[provider] && apiKey === 'env') {
      return false;
    }

    // These providers always need an API key if not in .env
    return provider === 'OpenAI' || provider === 'Anthropic' || provider === 'OpenRouter' ||
      provider === 'Google' || provider === 'Groq' || provider === 'Nvidia';
  }, [provider, apiKeysStatus, apiKeysLoaded, apiKey]);

  // When provider changes, update API key if needed
  useEffect(() => {
    if (apiKeysLoaded && provider) {
      if (apiKeysStatus[provider]) {
        // Provider has an API key in .env
        setApiKey('env');
      } else {
        // Provider doesn't have an API key in .env, clear it
        setApiKey('');
      }
    }
  }, [provider, apiKeysStatus, apiKeysLoaded, setApiKey]);

  // Update both local and app-level realtime logs
  const updateRealtimeLogs = useCallback((newLogs) => {
    if (typeof newLogs === 'function') {
      setLocalRealtimeLogs(newLogs);
      setRealtimeLogs(newLogs);
    } else {
      setLocalRealtimeLogs(newLogs);
      setRealtimeLogs(newLogs);
    }
  }, [setRealtimeLogs]);

  // Clear logs
  const clearLogs = useCallback(() => {
    setLocalRealtimeLogs('');
    setRealtimeLogs('');
    console.log('Logs cleared');
  }, [setRealtimeLogs]);

  // Function to check if settings are valid
  const isSettingsValid = () => {
    // Check if provider is selected
    if (!provider) return false;

    // Check if model is selected
    if (!llmType) return false;

    // Check if API key is provided for providers that need it
    // Only check if provider needs a key AND user is not using the env key
    if (providerNeedsApiKey() && apiKey !== 'env' && !apiKey) {
      return false;
    }

    // Check if topK is set
    if (!topK) return false;

    // Check if embedding type is set (required for vector search)
    if (!embeddingType) return false;

    return true;
  };

  // Highlight settings button when hovering over action buttons if settings are not valid
  const handleActionButtonHover = (isHovering) => {
    if (!isSettingsValid() && isHovering) {
      setHighlightSettings(true);
    } else if (!isHovering) {
      // Use a timeout to prevent flickering when moving between buttons
      setTimeout(() => {
        setHighlightSettings(false);
      }, 300);
    }
  };

  // Reset highlight when settings become valid
  useEffect(() => {
    if (isSettingsValid()) {
      setHighlightSettings(false);
    }
  }, [provider, llmType, apiKey, topK]);

  // Enhanced log streaming setup with better error handling and reconnection
  const setupLogStream = () => {
    if (verbose) {
      console.log('Setting up log stream for vector search verbose mode');

      // Close any existing connection but don't clear logs
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      // Don't add any initialization messages

      try {
        // Create new EventSource connection with a timestamp to avoid caching
        const timestamp = new Date().getTime();
        eventSourceRef.current = new EventSource(`/stream-logs?t=${timestamp}`);

        // Connection opened successfully - no message needed
        eventSourceRef.current.onopen = () => {
          // Just auto-scroll to bottom of log container
          if (logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
          }
        };

        // Handle incoming messages
        eventSourceRef.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.log) {
              updateRealtimeLogs(prev => prev + data.log + '\n');

              // Auto-scroll to bottom of log container
              if (logContainerRef.current) {
                logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
              }
            }
          } catch (e) {
            console.error('Error parsing log data:', e);
            // Don't add error messages to the logs
          }
        };

        // Handle connection errors - don't add messages about connection issues
        eventSourceRef.current.onerror = (error) => {
          console.error('EventSource failed:', error);

          // Try to reconnect after a delay if verbose is still enabled
          if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
          }

          setTimeout(() => {
            if (verbose && !eventSourceRef.current) {
              setupLogStream();
            }
          }, 3000);
        };
      } catch (error) {
        console.error('Error setting up log stream:', error);
        // Don't add error messages to the logs
      }
    }
  };

  // Improved cleanup function - don't clear logs when cleaning up
  const cleanupLogStream = () => {
    if (eventSourceRef.current) {
      console.log('Cleaning up log stream');
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      // Don't clear logs here
    }
  };

  // Setup log stream when verbose mode changes
  useEffect(() => {
    if (verbose) {
      setupLogStream();
    } else {
      cleanupLogStream();
      // Clear logs only when verbose mode is explicitly disabled
      clearLogs();
    }
  }, [verbose, clearLogs]);

  // Cleanup on component unmount
  useEffect(() => {
    return () => cleanupLogStream();
  }, []);

  // Listen for clear logs event
  useEffect(() => {
    const handleClearLogs = () => {
      clearLogs();
    };

    window.addEventListener('clearDebugLogs', handleClearLogs);

    return () => {
      window.removeEventListener('clearDebugLogs', handleClearLogs);
    };
  }, [clearLogs]);

  // Helper function to handle rate limiting errors
  const handleRateLimitError = (error) => {
    if (error.response && error.response.status === 429) {
      const retrySeconds = error.response.data.detail?.retry_after || 60;
      const limitType = error.response.data.detail?.limit_type || "minute";
      setRateLimited(true);
      setRetryAfter(retrySeconds);
      setRetryCountdown(retrySeconds);
      setLimitType(limitType);

      // Clear any existing countdown timer
      if (countdownTimerRef.current) {
        clearInterval(countdownTimerRef.current);
      }

      // Set up countdown timer
      countdownTimerRef.current = setInterval(() => {
        setRetryCountdown(prev => {
          if (prev <= 1) {
            clearInterval(countdownTimerRef.current);
            setRateLimited(false);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      return error.response.data.detail?.error || `Rate limit exceeded. Please try again in ${retrySeconds} seconds.`;
    }

    // Handle other types of errors
    if (error.response?.data?.detail) {
      if (typeof error.response.data.detail === 'object') {
        return error.response.data.detail.error ||
          error.response.data.detail.msg ||
          JSON.stringify(error.response.data.detail);
      }
      return error.response.data.detail;
    }

    return error.message || 'An unknown error occurred';
  };

  // Clean up the countdown timer on unmount
  useEffect(() => {
    return () => {
      if (countdownTimerRef.current) {
        clearInterval(countdownTimerRef.current);
      }
    };
  }, []);

  const handleAbort = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setLoading(false);
      setActiveButton(null);
      updateRealtimeLogs(prev => prev + 'Operation aborted by user.\n');
    }
  };

  const handleGenerateQuery = async () => {
    if (!isSettingsValid()) {
      alert("Please configure the LLM settings and select a vector type first");
      setShowSettings(true);
      setHighlightSettings(true);
      return;
    }

    // Prevent submitting if rate limited
    if (rateLimited) {
      return;
    }

    // Clear any previous errors and results at the start of the operation
    setError(null);
    setQueryResult(null);
    setExecutionResult(null);
    setLocalExecutionResult(null);

    // Create a new AbortController
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    setLoading(true);
    setActiveButton('generate');
    updateRealtimeLogs(verbose ? 'Generating Cypher query...\n' : '');
    setLogs('');

    try {
      if (verbose) {
        updateRealtimeLogs(prev => prev + `Sending request with parameters:
- Question: ${question}
- Model: ${llmType}
- Top K: ${topK}
- Vector Category: ${vectorCategory}
- Embedding Type: ${embeddingType}
- Verbose: ${verbose}
- Vector file size: ${vectorFile ? JSON.stringify(vectorFile).length : 0} bytes
`);
      }

      // Update API key to use from environment if available
      const effectiveApiKey = (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;

      const embedding = vectorFile ? JSON.stringify(vectorFile) : null;
      const response = await api.post('/generate_query/', {
        question,
        provider,
        llm_type: llmType,
        top_k: topK,
        api_key: effectiveApiKey,
        verbose,
        vector_index: embeddingType,
        embedding: embedding,
        vector_category: vectorCategory,
      }, { signal });

      // Process the query result before setting it
      const queryData = response.data.query;

      // Set the generated query regardless of type
      setGeneratedQuery(queryData);
      setOriginalQuery(queryData);

      // Set the query result for display
      setQueryResult(queryData);
      setExecutionResult(null);
      setLocalExecutionResult(null);
      setRunnedQuery(false);

      if (verbose) {
        if (response.data.logs) {
          setLogs(response.data.logs);
          updateRealtimeLogs(prev => prev + 'Query generation with vector search completed successfully!\n');
        } else {
          updateRealtimeLogs(prev => prev + 'Warning: No logs returned from server despite verbose mode enabled\n');
        }
      }

      addLatestQuery({
        question: question,
        query: queryData,
        timestamp: new Date().toISOString(),
        queryType: 'generated',
        vectorIndex: vectorCategory,
        embedding: embeddingType
      });
    } catch (err) {
      if (axios.isCancel(err)) {
        console.log('Request canceled:', err.message);
      } else {
        console.error(err);
        // Use the rate limit handler
        const errorMessage = handleRateLimitError(err);
        setError(errorMessage);

        if (verbose) {
          updateRealtimeLogs(prev => prev + `ERROR: ${errorMessage}\n`);
        }
      }
    } finally {
      if (!signal.aborted) {
        setLoading(false);
        setActiveButton(null);
        abortControllerRef.current = null;
      }
    }
  };

  const handleRunGeneratedQuery = async () => {
    if (!generatedQuery) return;

    if (!isSettingsValid()) {
      alert("Please configure the LLM settings and select a vector type first");
      setShowSettings(true);
      setHighlightSettings(true);
      return;
    }

    // Prevent submitting if rate limited
    if (rateLimited) {
      return;
    }

    // Clear any previous errors and results at the start of the operation
    setError(null);
    setQueryResult(null);
    setExecutionResult(null);
    setLocalExecutionResult(null);

    // Create a new AbortController
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    setLoading(true);
    setActiveButton('run');
    setLogs('');
    updateRealtimeLogs(prev => prev + 'Executing Cypher query from vector search...\n');

    try {
      if (verbose) {
        updateRealtimeLogs(prev => prev + `Query to execute:\n${generatedQuery}\n\n`);
      }

      // Update API key to use from environment if available
      const effectiveApiKey = (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;

      const response = await api.post('/run_query/', {
        query: generatedQuery,
        question,
        provider,
        llm_type: llmType,
        top_k: topK,
        api_key: effectiveApiKey,
        verbose,
      }, { signal });

      setExecutionResult({
        result: response.data.result,
        response: response.data.response
      });
      setLocalExecutionResult({
        result: response.data.result,
        response: response.data.response
      });
      setRunnedQuery(true);

      if (verbose) {
        if (response.data.logs) {
          setLogs(response.data.logs);
          updateRealtimeLogs(prev => prev + 'Query executed successfully!\n');
        } else {
          updateRealtimeLogs(prev => prev + 'Warning: No logs returned from server despite verbose mode enabled\n');
        }
      }

      addLatestQuery({
        question: question,
        query: generatedQuery,
        timestamp: new Date().toISOString(),
        queryType: 'run',
        response: response.data.response,
        vectorIndex: vectorCategory,
        embedding: embeddingType
      });
    } catch (err) {
      if (axios.isCancel(err)) {
        console.log('Request canceled:', err.message);
      } else {
        console.error(err);
        // Use the rate limit handler
        const errorMessage = handleRateLimitError(err);
        setError(errorMessage);

        if (verbose) {
          updateRealtimeLogs(prev => prev + `ERROR: ${errorMessage}\n`);
        }
      }
    } finally {
      if (!signal.aborted) {
        setLoading(false);
        setActiveButton(null);
        abortControllerRef.current = null;
      }
    }
  };

  const handleGenerateAndRun = async () => {
    if (!isSettingsValid()) {
      alert("Please configure the LLM settings and select a vector type first");
      setShowSettings(true);
      setHighlightSettings(true);
      return;
    }

    // Prevent submitting if rate limited
    if (rateLimited) {
      return;
    }

    // Clear any previous errors and results at the start of the operation
    setError(null);
    setQueryResult(null);
    setExecutionResult(null);
    setLocalExecutionResult(null);

    // Create a new AbortController
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    setLoading(true);
    setActiveButton('generateAndRun');
    updateRealtimeLogs(verbose ? 'Generating and running Cypher query...\n' : '');
    setRunnedQuery(false);
    setGeneratedQuery('');
    setLogs('');
    clearLogs();

    if (verbose) {
      updateRealtimeLogs('Starting vector search query generation...\n');
    }

    try {
      // Update API key to use from environment if available
      const effectiveApiKey = (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;

      // Prepare the request data
      const requestData = {
        question,
        provider,
        llm_type: llmType,
        api_key: effectiveApiKey,
        top_k: topK,
        verbose,
      };

      // Add vector data if available, otherwise just use vector index for category-based search
      if (vectorFile) {
        requestData.embedding = JSON.stringify(vectorFile);
        requestData.vector_index = embeddingType;
      } else if (selectedFile) {
        // If we have a selected file but no vectorFile data yet,
        // we need to include the file in the request
        requestData.vector_index = embeddingType;

        // Create a FormData object to send the file
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('vector_category', vectorCategory);
        formData.append('embedding_type', embeddingType);

        if (verbose) {
          updateRealtimeLogs(prev => prev + `Uploading vector file: ${selectedFile.name}\n`);
        }

        try {
          // Upload the file first
          const uploadResponse = await api.post('/upload_vector/', formData, {
            headers: {
              'Content-Type': 'multipart/form-data',
            },
            signal,
          });

          if (verbose) {
            updateRealtimeLogs(prev => prev + `File uploaded successfully\n`);
          }

          // Use the uploaded vector data
          requestData.embedding = JSON.stringify(uploadResponse.data);
          setVectorFile(uploadResponse.data);
        } catch (error) {
          throw new Error(`Error uploading vector file: ${error.message}`);
        }
      } else if (vectorCategory && embeddingType) {
        // Use category-based vector search without specific embedding
        requestData.vector_index = embeddingType;
        requestData.vector_category = vectorCategory;
        if (verbose) {
          updateRealtimeLogs(prev => prev + `Using category-based vector search for ${vectorCategory} with ${embeddingType} embeddings\n`);
        }
      }

      if (verbose) {
        updateRealtimeLogs(prev => prev + `Generating vector search query with parameters:\n` +
          `Question: ${question}\n` +
          `Provider: ${provider}\n` +
          `Model: ${llmType}\n` +
          `Top K: ${topK}\n` +
          `Vector Category: ${vectorCategory || 'N/A'}\n` +
          `Embedding Type: ${embeddingType || 'N/A'}\n` +
          `Vector Data: ${vectorFile ? 'Provided' : 'Not provided'}\n\n`);
      }

      const response = await api.post('/generate_query/', requestData, { signal });

      // Process the query result
      const generatedQuery = response.data.query;

      // Handle case where generatedQuery is an object
      const queryString = typeof generatedQuery === 'object' ? JSON.stringify(generatedQuery) : generatedQuery;

      setGeneratedQuery(queryString);
      setOriginalQuery(queryString);

      if (verbose) {
        updateRealtimeLogs(prev => prev + `Generated query: ${queryString}\n\n`);

        if (response.data.logs) {
          setLogs(response.data.logs);
        }
      }

      // Now run the generated query
      if (verbose) {
        updateRealtimeLogs(prev => prev + `Running the generated query...\n`);
      }

      // Prepare the run query request
      const runRequestData = {
        question: question,
        query: queryString,
        llm_type: llmType,
        top_k: topK,
        api_key: effectiveApiKey,
        verbose: verbose
      };

      const runRequestDataWithProvider = { ...runRequestData, provider };
      const runResponse = await api.post('/run_query/', runRequestDataWithProvider, { signal });

      setExecutionResult({
        result: runResponse.data.result,
        response: runResponse.data.response
      });
      setLocalExecutionResult({
        result: runResponse.data.result,
        response: runResponse.data.response
      });
      setQueryResult(queryString);
      setRunnedQuery(true);

      if (verbose) {
        updateRealtimeLogs(prev => prev + `Query execution completed successfully!\n`);

        if (runResponse.data.logs) {
          setLogs(prev => prev + '\n\n' + runResponse.data.logs);
        }
      }

      // Update the latest queries
      addLatestQuery({
        question: question,
        query: queryString,
        timestamp: new Date().toISOString(),
        queryType: 'vector',
        response: runResponse.data.response,
        vectorCategory: vectorCategory,
        embeddingType: embeddingType
      });
    } catch (err) {
      if (axios.isCancel(err)) {
        console.log('Request canceled:', err.message);
      } else {
        console.error('Error in vector search:', err);

        // Use the rate limit handler
        const errorMessage = handleRateLimitError(err);
        setError(errorMessage);

        if (verbose) {
          updateRealtimeLogs(prev => prev + `ERROR: ${errorMessage}\n`);
        }
      }
    } finally {
      if (!signal.aborted) {
        setLoading(false);
        setActiveButton(null);
        abortControllerRef.current = null;
      }
    }
  };

  const handleSampleQuestionClick = async (sampleQuestionObj) => {
    if (!sampleQuestionObj) return;

    // Clear any previous errors
    setError(null);

    // Handle both string and object formats for backward compatibility
    if (typeof sampleQuestionObj === 'string') {
      setQuestion(sampleQuestionObj);
      return;
    }

    // Set the question
    setQuestion(sampleQuestionObj.question || '');

    // Reset vector-related state
    setVectorCategory('');
    setEmbeddingType('');
    setVectorFile(null);
    setSelectedFile(null);

    // Set vector category if provided
    if (sampleQuestionObj.vectorCategory) {
      console.log('Setting vector category:', sampleQuestionObj.vectorCategory);
      setVectorCategory(sampleQuestionObj.vectorCategory);
    }

    // Set embedding type if provided
    if (sampleQuestionObj.embeddingType) {
      console.log('Setting embedding type:', sampleQuestionObj.embeddingType);
      setEmbeddingType(sampleQuestionObj.embeddingType);
    }

    // Set vector data if provided
    if (sampleQuestionObj.vectorData) {
      console.log('Setting vector data');
      setVectorFile(sampleQuestionObj.vectorData);
    }

    // Load vector file if path is provided
    if (sampleQuestionObj.vectorFilePath) {
      try {
        console.log('Loading vector file from path:', sampleQuestionObj.vectorFilePath);
        if (verbose) {
          updateRealtimeLogs(prev => prev + `Loading vector file from public folder: ${sampleQuestionObj.vectorFilePath}\n`);
        }

        const response = await fetch(`${process.env.PUBLIC_URL}/${sampleQuestionObj.vectorFilePath}`);

        if (!response.ok) {
          const errorMsg = `Failed to fetch vector file: ${response.status} ${response.statusText}`;
          console.error(errorMsg);
          setError(errorMsg);
          if (verbose) {
            updateRealtimeLogs(prev => prev + `Error: ${errorMsg}\n`);
          }
          return;
        }

        // For NPY files, we need to handle them as binary data
        const blob = await response.blob();
        const file = new File([blob], sampleQuestionObj.vectorFilePath);

        // Set the selected file for upload
        setSelectedFile(file);

        if (verbose) {
          updateRealtimeLogs(prev => prev + `Vector file loaded successfully: ${file.name}\n`);
        }
      } catch (error) {
        console.error('Error loading vector file:', error);
        setError(`Error loading vector file: ${error.message}`);
        if (verbose) {
          updateRealtimeLogs(prev => prev + `Error loading vector file: ${error.message}\n`);
        }
      }
    } else if (sampleQuestionObj.vectorCategory) {
      // If a vector category is specified, no warning needed since file upload is optional
      if (verbose) {
        updateRealtimeLogs(prev => prev + `Vector category set to ${sampleQuestionObj.vectorCategory}. Ready for category-based vector search.\n`);
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

    // Prevent submitting if rate limited
    if (rateLimited) {
      return;
    }

    if (verbose) {
      updateRealtimeLogs(prev => prev + `Uploading vector file: ${file.name} (${file.size} bytes)\nCategory: ${vectorCategory}\nEmbedding Type: ${embeddingType || 'N/A'}\n`);
    }

    const formData = new FormData();
    formData.append('vector_category', vectorCategory);
    if (embeddingType) {
      formData.append('embedding_type', embeddingType);
    }
    formData.append('file', file);

    api
      .post('/upload_vector/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })
      .then((response) => {
        console.log('File uploaded successfully:', response.data);
        if (verbose) {
          updateRealtimeLogs(prev => prev + `File uploaded successfully. Vector size: ${response.data.vector_data ? response.data.vector_data.length : 'unknown'} elements\n`);
        }
        setVectorFile(response.data); // Update vectorFile with response
      })
      .catch((error) => {
        console.error('Error uploading file:', error);
        // Use the rate limit handler
        const errorMessage = handleRateLimitError(error);
        setError(errorMessage);

        if (verbose) {
          updateRealtimeLogs(prev => prev + `Error uploading file: ${errorMessage}\n`);
        }
      });
  };

  const toggleSettings = () => {
    setShowSettings(!showSettings);
  };

  return (
    <Box>
      <Paper
        elevation={0}
        sx={{
          p: 0,
          mb: 4,
          borderRadius: '24px',
          overflow: 'hidden',
          border: theme => `1px solid ${theme.palette.divider}`,
          backdropFilter: 'blur(10px)',
          backgroundColor: theme => theme.palette.mode === 'dark'
            ? alpha(theme.palette.background.paper, 0.8)
            : alpha(theme.palette.background.paper, 0.8),
          position: 'relative',
        }}
      >
        {/* Loading Overlay */}
        {loading && (
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: theme => alpha(theme.palette.background.paper, 0.4),
              backdropFilter: 'blur(8px)',
              zIndex: 1000,
              borderRadius: '24px',
            }}
          >
            <CircularProgress size={60} thickness={4} />
            <Typography variant="h6" sx={{ mt: 3, fontWeight: 500 }}>
              {activeButton === 'generate' && 'Generating Query...'}
              {activeButton === 'run' && 'Running Query...'}
              {activeButton === 'generateAndRun' && 'Generating & Running Query...'}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              This may take a few moments
            </Typography>
            <Button
              variant="outlined"
              color="error"
              onClick={handleAbort}
              startIcon={<StopIcon />}
              sx={{
                mt: 3,
                borderRadius: '12px',
                px: 3,
              }}
            >
              Abort Operation
            </Button>
          </Box>
        )}

        <Box sx={{ p: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h5" sx={{ fontWeight: 600, letterSpacing: '-0.01em' }}>
              Semantic Search
            </Typography>
            <Box>
              <Tooltip title="Model Settings">
                <Button
                  onClick={toggleSettings}
                  color={showSettings || highlightSettings ? "primary" : "default"}
                  startIcon={<TuneIcon />}
                  variant={showSettings ? "contained" : "text"}
                  size="small"
                  sx={{
                    borderRadius: '12px',
                    backgroundColor: (showSettings && !highlightSettings)
                      ? (theme.palette.mode === 'dark' ? alpha(theme.palette.primary.main, 0.15) : alpha(theme.palette.primary.main, 0.08))
                      : highlightSettings ? (theme.palette.mode === 'dark' ? alpha(theme.palette.primary.main, 0.15) : alpha(theme.palette.primary.main, 0.08)) : 'transparent',
                    transition: 'all 0.3s ease',
                    animation: highlightSettings ? 'pulse 1.5s infinite' : 'none',
                    transform: highlightSettings ? 'scale(1.05)' : 'scale(1)',
                    '@keyframes pulse': {
                      '0%': {
                        boxShadow: '0 0 0 0 rgba(25, 118, 210, 0.7)'
                      },
                      '70%': {
                        boxShadow: '0 0 0 10px rgba(25, 118, 210, 0)'
                      },
                      '100%': {
                        boxShadow: '0 0 0 0 rgba(25, 118, 210, 0)'
                      }
                    }
                  }}
                >
                  Configure Model Settings
                </Button>
              </Tooltip>
              <Tooltip title="Help">
                <IconButton
                  onClick={() => setShowWarning(!showWarning)}
                  color={showWarning ? "primary" : "default"}
                  sx={{
                    ml: 1,
                    borderRadius: '12px',
                    backgroundColor: showWarning
                      ? (theme.palette.mode === 'dark' ? alpha(theme.palette.primary.main, 0.15) : alpha(theme.palette.primary.main, 0.08))
                      : 'transparent'
                  }}
                >
                  <HelpOutlineIcon />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>

          <Collapse in={showWarning}>
            <Alert
              severity="info"
              sx={{
                mb: 3,
                borderRadius: '16px',
                '& .MuiAlert-icon': {
                  alignItems: 'center'
                }
              }}
              icon={<LightbulbOutlinedIcon />}
            >
              Ask any biomedical question with vector search to query the CROssBAR knowledge graph. Upload a vector file to enhance your search results.
            </Alert>
          </Collapse>

          <Box sx={{ mb: 3 }}>
            <AutocompleteTextField
              value={question}
              setValue={setQuestion}
              onKeyPress={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleGenerateAndRun();
                }
              }}
              placeholder="E.g., Find proteins similar to BRCA1 that are associated with breast cancer"
              fullWidth
              multiline
              rows={3}
              variant="outlined"
              disabled={loading}
              sx={{
                '& .MuiOutlinedInput-root': {
                  borderRadius: '16px',
                  fontSize: '1rem',
                  backgroundColor: theme => theme.palette.mode === 'dark'
                    ? alpha(theme.palette.background.subtle, 0.3)
                    : alpha(theme.palette.background.subtle, 0.3),
                }
              }}
            />
          </Box>

          <Collapse in={showSettings}>
            <Paper
              elevation={0}
              sx={{
                p: 3,
                mb: 3,
                borderRadius: '16px',
                backgroundColor: theme => theme.palette.mode === 'dark'
                  ? alpha(theme.palette.background.subtle, 0.5)
                  : alpha(theme.palette.background.subtle, 0.5),
              }}
            >
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 3 }}>
                Model Settings
              </Typography>

              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                {/* First row - Provider and Model */}
                <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                  <Box sx={{ flex: '1 1 250px', minWidth: '250px' }}>
                    <FormControl fullWidth variant="outlined" size="small">
                      <InputLabel id="provider-label">Provider</InputLabel>
                      <Select
                        labelId="provider-label"
                        value={provider}
                        onChange={(e) => {
                          const selectedProvider = e.target.value;
                          setProvider(selectedProvider);

                          // Automatically select the first available model for the provider
                          if (selectedProvider && modelChoices[selectedProvider]) {
                            const firstModel = modelChoices[selectedProvider].find(model =>
                              typeof model === 'string' // Skip separator and label objects
                            );
                            if (firstModel) {
                              setLlmType(firstModel);
                            } else {
                              setLlmType('');
                            }
                          } else {
                            setLlmType('');
                          }
                        }}
                        label="Provider"
                      >
                        <MenuItem value="">
                          <em>Select a provider</em>
                        </MenuItem>
                        {Object.keys(modelChoices).map((providerName) => (
                          <MenuItem key={providerName} value={providerName}>
                            {providerName}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Box>

                  <Box sx={{ flex: '1 1 250px', minWidth: '250px' }}>
                    <FormControl fullWidth variant="outlined" size="small" disabled={!provider}>
                      <InputLabel id="model-label">Model</InputLabel>
                      <Select
                        labelId="model-label"
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
                        label="Model"
                      >
                        <MenuItem value="">
                          <em>Select a model</em>
                        </MenuItem>
                        {provider && modelChoices[provider] && modelChoices[provider].map((model) => {
                          // For separator items, render a divider
                          if (typeof model === 'object' && model.value === 'separator') {
                            return <Divider key={model.label} sx={{ my: 1 }} />;
                          }

                          // For label items, render a non-selectable label
                          if (typeof model === 'object' && model.value === 'label') {
                            return (
                              <MenuItem
                                key={`label-${model.label}`}
                                disabled
                                sx={{
                                  opacity: 0.7,
                                  fontWeight: 'bold',
                                  fontSize: '0.85rem',
                                  pointerEvents: 'none',
                                  '&.Mui-disabled': {
                                    opacity: 0.7
                                  }
                                }}
                              >
                                {model.label}
                              </MenuItem>
                            );
                          }

                          // For regular model items
                          return (
                            <MenuItem key={model} value={model}>
                              {model}
                              {supportedModels.includes(model) && (
                                <Chip
                                  label="Recommended"
                                  size="small"
                                  color="primary"
                                  sx={{ ml: 1, height: '20px', fontSize: '0.65rem' }}
                                />
                              )}
                            </MenuItem>
                          );
                        })}
                      </Select>
                    </FormControl>
                  </Box>
                </Box>

                {/* Ollama Warning */}
                {provider === 'Ollama' && (
                  <Alert severity="warning" sx={{ mt: 2 }}>
                    Selected provider is only for local development, it will not work on cloud.
                  </Alert>
                )}

                {/* Second row - API Key and Results Limit */}
                <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                  {/* Only show API Key field if provider needs it */}
                  {!apiKeysStatus[provider] && (
                    <Box sx={{ flex: '1 1 250px', minWidth: '250px' }}>
                      <FormControl fullWidth variant="outlined" size="small">
                        <TextField
                          label="API Key for LLM"
                          type="password"
                          value={apiKey}
                          onChange={(e) => setApiKey(e.target.value)}
                          size="small"
                          variant="outlined"
                          InputProps={{
                            startAdornment: (
                              <InputAdornment position="start">
                                <KeyIcon fontSize="small" />
                              </InputAdornment>
                            ),
                          }}
                        />
                      </FormControl>
                    </Box>
                  )}
                  {/* If provider has an API key in .env, show info with option to override */}
                  {apiKeysLoaded && apiKeysStatus[provider] && (
                    <Box sx={{ flex: '1 1 250px', minWidth: '250px' }}>
                      <Paper
                        variant="outlined"
                        sx={{
                          p: 1.5,
                          display: 'flex',
                          flexDirection: 'column',
                          backgroundColor: theme => theme.palette.mode === 'dark' ? alpha(theme.palette.success.main, 0.1) : alpha(theme.palette.success.main, 0.05),
                          border: theme => `1px solid ${alpha(theme.palette.success.main, 0.3)}`
                        }}
                      >
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <CheckCircleIcon color="success" fontSize="small" sx={{ mr: 1 }} />
                            <Typography variant="body2">Using API key from .env file</Typography>
                          </Box>
                          <FormControlLabel
                            control={
                              <Checkbox
                                size="small"
                                checked={apiKey !== 'env'}
                                onChange={(e) => {
                                  setApiKey(e.target.checked ? '' : 'env');
                                }}
                                sx={{ p: 0.5 }}
                              />
                            }
                            label={<Typography variant="caption">Use custom</Typography>}
                            sx={{ m: 0, '& .MuiTypography-root': { fontSize: '0.7rem', opacity: 0.7 } }}
                          />
                        </Box>

                        {/* Show API key input if user wants to use custom key */}
                        {apiKey !== 'env' && (
                          <TextField
                            placeholder="Enter your API key"
                            type="password"
                            value={apiKey}
                            onChange={(e) => setApiKey(e.target.value)}
                            size="small"
                            margin="dense"
                            variant="outlined"
                            InputProps={{
                              startAdornment: (
                                <InputAdornment position="start">
                                  <KeyIcon fontSize="small" />
                                </InputAdornment>
                              ),
                            }}
                            sx={{
                              mt: 1.5,
                              '& .MuiOutlinedInput-root': {
                                backgroundColor: 'background.paper',
                              }
                            }}
                          />
                        )}
                      </Paper>
                    </Box>
                  )}

                  <Box sx={{ flex: '1 1 250px', minWidth: '250px' }}>
                    <FormControl fullWidth variant="outlined" size="small">
                      <InputLabel id="top-k-label">Results Limit</InputLabel>
                      <Select
                        labelId="top-k-label"
                        value={topK}
                        onChange={(e) => setTopK(e.target.value)}
                        label="Results Limit"
                      >
                        {[1, 3, 5, 10, 15, 20, 50, 100].map((k) => (
                          <MenuItem key={k} value={k}>
                            {k}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Box>
                </Box>

                {/* Third row - Debug Mode */}
                <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                  <Box sx={{ flex: '1 1 250px', minWidth: '250px' }}>
                    <FormControl component="fieldset" variant="outlined" fullWidth>
                      <Box
                        onClick={() => setVerbose(!verbose)}
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          p: 1.5,
                          height: '40px',
                          borderRadius: '8px',
                          border: theme => `1px solid ${theme.palette.divider}`,
                          backgroundColor: verbose ?
                            (theme.palette.mode === 'dark' ? alpha(theme.palette.info.main, 0.1) : alpha(theme.palette.info.main, 0.05)) :
                            'transparent',
                          transition: 'all 0.2s ease-in-out',
                          cursor: 'pointer',
                          '&:hover': {
                            backgroundColor: verbose ?
                              (theme.palette.mode === 'dark' ? alpha(theme.palette.info.main, 0.15) : alpha(theme.palette.info.main, 0.08)) :
                              (theme.palette.mode === 'dark' ? alpha(theme.palette.info.main, 0.05) : alpha(theme.palette.info.main, 0.03))
                          }
                        }}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <Tooltip title="Enable to see detailed logs of the vector search process">
                            <InfoOutlinedIcon
                              fontSize="small"
                              sx={{
                                mr: 1.5,
                                color: verbose ? 'info.main' : 'text.secondary',
                                transition: 'color 0.2s ease-in-out',
                              }}
                            />
                          </Tooltip>
                          <Typography variant="body2" sx={{ fontWeight: 500 }}>
                            Debug Mode
                          </Typography>
                        </Box>
                        <Switch
                          checked={verbose}
                          onChange={(e) => {
                            e.stopPropagation(); // Prevent triggering the parent onClick
                            setVerbose(e.target.checked);
                          }}
                          color="info"
                          size="small"
                        />
                      </Box>
                      {verbose && (
                        <Fade in={verbose}>
                          <Typography variant="caption" color="info.main" sx={{ mt: 0.5, display: 'flex', alignItems: 'center' }}>
                            <TerminalIcon fontSize="inherit" sx={{ mr: 0.5 }} />
                            Real-time logs will appear below the results
                          </Typography>
                        </Fade>
                      )}
                    </FormControl>
                  </Box>
                </Box>
              </Box>
            </Paper>
          </Collapse>

          <Box sx={{ mb: 3 }}>
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
          </Box>

          {/* Prominent Settings Button */}
          {!isSettingsValid() && (
            <Box sx={{ mb: 3 }}>
              <Button
                variant="contained"
                color="primary"
                fullWidth
                startIcon={<TuneIcon />}
                onClick={toggleSettings}
                sx={{
                  borderRadius: '12px',
                  py: 1.2,
                  boxShadow: 2,
                  bgcolor: theme => theme.palette.primary.main,
                  '&:hover': {
                    bgcolor: theme => theme.palette.primary.dark,
                  },
                  animation: highlightSettings ? 'pulse 1.5s infinite' : 'none',
                  '@keyframes pulse': {
                    '0%': {
                      boxShadow: '0 0 0 0 rgba(25, 118, 210, 0.7)'
                    },
                    '70%': {
                      boxShadow: '0 0 0 10px rgba(25, 118, 210, 0)'
                    },
                    '100%': {
                      boxShadow: '0 0 0 0 rgba(25, 118, 210, 0)'
                    }
                  }
                }}
              >
                Configure Model Settings
              </Button>
            </Box>
          )}

          {/* Sample Questions - Repositioned for better visibility */}
          <Box sx={{
            display: 'flex',
            justifyContent: 'center',
            mb: 4,
            mt: 1
          }}>
            <SampleQuestions onQuestionClick={handleSampleQuestionClick} isVectorTab={true} />
          </Box>

          <Box sx={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <Tooltip title={isSettingsValid() ? "Generate Cypher Query" : "Configure settings and select vector type first"}>
                <Box
                  onMouseEnter={() => handleActionButtonHover(true)}
                  onMouseLeave={() => handleActionButtonHover(false)}
                >
                  {loading && activeButton === 'generate' ? (
                    <Button
                      variant="outlined"
                      color="error"
                      onClick={handleAbort}
                      startIcon={<StopIcon />}
                      sx={{
                        borderRadius: '12px',
                        px: 3,
                        height: '44px'
                      }}
                    >
                      Abort
                    </Button>
                  ) : (
                    <Button
                      variant="outlined"
                      onClick={handleGenerateQuery}
                      disabled={!question || !isSettingsValid() || loading}
                      startIcon={<SendIcon />}
                      sx={{
                        borderRadius: '12px',
                        px: 3,
                        height: '44px',
                        fontSize: '0.75rem'
                      }}
                    >
                      Only Generate Query
                    </Button>
                  )}
                </Box>
              </Tooltip>

              <Tooltip title={isSettingsValid() ? "Generate and Run Query" : "Configure settings and select vector type first"}>
                <Box
                  onMouseEnter={() => handleActionButtonHover(true)}
                  onMouseLeave={() => handleActionButtonHover(false)}
                >
                  {loading && activeButton === 'generateAndRun' ? (
                    <Button
                      variant="contained"
                      color="error"
                      onClick={handleAbort}
                      startIcon={<StopIcon />}
                      sx={{
                        borderRadius: '12px',
                        px: 3,
                        height: '44px'
                      }}
                    >
                      Abort
                    </Button>
                  ) : (
                    <Button
                      variant="contained"
                      color="primary"
                      onClick={handleGenerateAndRun}
                      disabled={!question || !isSettingsValid() || loading}
                      startIcon={<PlayArrowIcon />}
                      sx={{
                        borderRadius: '12px',
                        px: 3,
                        height: '44px'
                      }}
                    >
                      Generate & Run Query
                    </Button>
                  )}
                </Box>
              </Tooltip>
            </Box>
          </Box>

          {/* Disclaimer */}
          <Box sx={{ mt: 2, display: 'flex', justifyContent: 'center' }}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                textAlign: 'center',
                maxWidth: '600px',
                lineHeight: 1.4,
                fontStyle: 'normal',
                fontSize: '0.85rem'
              }}
            >
              CROssBAR-LLM can make mistakes or miss answers; if something looks wrong, ask again (results can change), or switch to a recommended or alternative model for better reliability.
            </Typography>
          </Box>
        </Box>

        {generatedQuery && !runnedQuery && (
          <>
            <Box sx={{
              p: 3,
              borderTop: theme => `1px solid ${theme.palette.divider}`,
              backgroundColor: theme => theme.palette.mode === 'dark'
                ? alpha(theme.palette.background.subtle, 0.3)
                : alpha(theme.palette.background.subtle, 0.3),
            }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center' }}>
                <CodeIcon fontSize="small" sx={{ mr: 1 }} />
                Generated Query (Editable)
              </Typography>
              <Box
                sx={{
                  position: 'relative',
                  borderRadius: '12px',
                  border: theme => `1px solid ${theme.palette.divider}`,
                  maxHeight: '200px',
                  minHeight: '120px',
                  height: 'auto',
                  overflow: 'hidden',
                }}
              >
                <Box
                  ref={highlighterRef}
                  sx={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    maxHeight: '200px',
                    padding: '16px 14px',
                    overflow: 'auto',
                    overflowX: 'hidden',
                    pointerEvents: 'none',
                    whiteSpace: 'pre-wrap !important',
                    wordBreak: 'break-word',
                    wordWrap: 'break-word',
                  }}
                >
                  <SyntaxHighlighter
                    language="cypher"
                    style={syntaxTheme}
                    wrapLines={true}
                    wrapLongLines={true}
                    customStyle={{
                      margin: 0,
                      padding: 0,
                      background: 'transparent',
                      fontSize: '0.9rem',
                      lineHeight: '1.5',
                      height: 'auto',
                      width: '100%',
                      whiteSpace: 'pre-wrap !important',
                      wordBreak: 'break-word',
                      wordWrap: 'break-word',
                      overflow: 'hidden',
                    }}
                  >
                    {generatedQuery || ' '}
                  </SyntaxHighlighter>
                </Box>
                <textarea
                  ref={textareaRef}
                  value={generatedQuery}
                  onChange={(e) => setGeneratedQuery(e.target.value)}
                  onScroll={(e) => {
                    // Sync scroll position with highlighter
                    if (highlighterRef.current) {
                      highlighterRef.current.scrollTop = e.target.scrollTop;
                      highlighterRef.current.scrollLeft = e.target.scrollLeft;
                    }
                  }}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    maxHeight: '200px',
                    padding: '16px 14px',
                    fontFamily: 'monospace',
                    fontSize: '0.9rem',
                    lineHeight: '1.5',
                    backgroundColor: 'transparent',
                    border: 'none',
                    outline: 'none',
                    color: 'transparent',
                    caretColor: theme.palette.text.primary,
                    resize: 'none',
                    zIndex: 1,
                    whiteSpace: 'pre-wrap !important',
                    wordBreak: 'break-word',
                    wordWrap: 'break-word',
                    overflowWrap: 'break-word',
                    overflowX: 'hidden',
                  }}
                  placeholder="Edit the generated query here..."
                  spellCheck="false"
                  wrap="soft"
                />
              </Box>
            </Box>
            <Box
              onMouseEnter={() => handleActionButtonHover(true)}
              onMouseLeave={() => handleActionButtonHover(false)}
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                p: 2,
                backgroundColor: theme => theme.palette.mode === 'dark'
                  ? alpha(theme.palette.primary.main, 0.1)
                  : alpha(theme.palette.primary.main, 0.05),
                borderTop: theme => `1px solid ${theme.palette.divider}`
              }}
            >
              <Button
                variant="outlined"
                onClick={() => setGeneratedQuery(originalQuery)}
                disabled={false}
                startIcon={<RestoreIcon />}
                sx={{
                  borderRadius: '12px',
                  px: 3
                }}
              >
                Reset to Original
              </Button>
              {loading && activeButton === 'run' ? (
                <Button
                  variant="contained"
                  color="error"
                  onClick={handleAbort}
                  startIcon={<StopIcon />}
                  sx={{
                    borderRadius: '12px',
                    px: 3
                  }}
                >
                  Abort
                </Button>
              ) : (
                <Button
                  variant="contained"
                  color="primary"
                  onClick={handleRunGeneratedQuery}
                  disabled={!isSettingsValid() || !generatedQuery.trim() || loading}
                  startIcon={<PlayArrowIcon />}
                  sx={{
                    borderRadius: '12px',
                    px: 3
                  }}
                >
                  Run Query
                </Button>
              )}
            </Box>
          </>
        )}
      </Paper>

      {error && (
        <Zoom in={!!error}>
          <Alert
            severity="error"
            sx={{
              mb: 3,
              borderRadius: '16px',
              boxShadow: theme => theme.palette.mode === 'dark'
                ? '0 4px 20px rgba(0, 0, 0, 0.3)'
                : '0 4px 20px rgba(0, 0, 0, 0.05)',
            }}
          >
            {typeof error === 'object' && error !== null
              ? (error.msg || JSON.stringify(error))
              : error}

            {/* Countdown timer for rate limiting */}
            {rateLimited && retryCountdown > 0 && (
              <Box sx={{ mt: 1, display: 'flex', alignItems: 'center' }}>
                <CircularProgress size={16} sx={{ mr: 1 }} />
                <Typography variant="body2">
                  {limitType === "minute" && `You can try again in ${retryCountdown} second${retryCountdown !== 1 ? 's' : ''}.`}
                  {limitType === "hour" && `Please wait ${Math.floor(retryCountdown / 60)} minute${Math.floor(retryCountdown / 60) !== 1 ? 's' : ''} and ${retryCountdown % 60} second${retryCountdown % 60 !== 1 ? 's' : ''} before trying again.`}
                  {limitType === "day" && `Daily limit reached. Please try again tomorrow (in ${Math.floor(retryCountdown / 3600)} hour${Math.floor(retryCountdown / 3600) !== 1 ? 's' : ''}).`}
                  {!limitType && `You can try again in ${retryCountdown} second${retryCountdown !== 1 ? 's' : ''}.`}
                </Typography>
              </Box>
            )}
          </Alert>
        </Zoom>
      )}

      {/* Rate limiting warning without other errors */}
      {rateLimited && !error && (
        <Zoom in={rateLimited}>
          <Alert
            severity="warning"
            sx={{
              mb: 3,
              borderRadius: '16px',
              boxShadow: theme => theme.palette.mode === 'dark'
                ? '0 4px 20px rgba(0, 0, 0, 0.3)'
                : '0 4px 20px rgba(0, 0, 0, 0.05)',
            }}
          >
            <Typography variant="body2">
              {limitType === "minute" && "Minute rate limit exceeded (3 requests per minute)."}
              {limitType === "hour" && "Hour rate limit exceeded (10 requests per hour)."}
              {limitType === "day" && "Daily rate limit exceeded (25 requests per day)."}
              {!limitType && "Rate limit exceeded. Please wait before making more requests."}
            </Typography>
            {retryCountdown > 0 && (
              <Box sx={{ mt: 1, display: 'flex', alignItems: 'center' }}>
                <CircularProgress size={16} sx={{ mr: 1 }} />
                <Typography variant="body2">
                  {limitType === "minute" && `You can try again in ${retryCountdown} second${retryCountdown !== 1 ? 's' : ''}.`}
                  {limitType === "hour" && `Please wait ${Math.floor(retryCountdown / 60)} minute${Math.floor(retryCountdown / 60) !== 1 ? 's' : ''} and ${retryCountdown % 60} second${retryCountdown % 60 !== 1 ? 's' : ''} before trying again.`}
                  {limitType === "day" && `Daily limit reached. Please try again tomorrow (in ${Math.floor(retryCountdown / 3600)} hour${Math.floor(retryCountdown / 3600) !== 1 ? 's' : ''}).`}
                  {!limitType && `You can try again in ${retryCountdown} second${retryCountdown !== 1 ? 's' : ''}.`}
                </Typography>
              </Box>
            )}
          </Alert>
        </Zoom>
      )}
    </Box>
  );
}

export default VectorSearch;
