import React, { useEffect, useState, useRef, useCallback } from 'react';
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
  Divider,
  IconButton,
  Tooltip,
  Fade,
  Chip,
  InputAdornment,
  Grid,
  Alert,
  Collapse,
  Card,
  CardContent,
  Stack,
  Autocomplete,
  Zoom,
  alpha,
  Switch,
  Dialog,
  DialogContent,
  DialogTitle,
  CheckCircleIcon
} from '@mui/material';
import AutocompleteTextField from './AutocompleteTextField';
import api from '../services/api';
import axios from 'axios';
import SampleQuestions from './SampleQuestions';
import SendIcon from '@mui/icons-material/Send';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SettingsIcon from '@mui/icons-material/Settings';
import KeyIcon from '@mui/icons-material/Key';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import TuneIcon from '@mui/icons-material/Tune';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import TerminalIcon from '@mui/icons-material/Terminal';
import CodeIcon from '@mui/icons-material/Code';
import RestoreIcon from '@mui/icons-material/Restore';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import StopIcon from '@mui/icons-material/Stop';
import EditIcon from '@mui/icons-material/Edit';

function QueryInput({
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
  const [runnedQuery, setRunnedQuery] = useState(false);
  const [generatedQuery, setGeneratedQuery] = useState('');
  const [editableQuery, setEditableQuery] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeButton, setActiveButton] = useState(null);
  const [logs, setLogs] = useState('');
  const [showWarning, setShowWarning] = useState(false);
  const [localRealtimeLogs, setLocalRealtimeLogs] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [highlightSettings, setHighlightSettings] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [apiKeysStatus, setApiKeysStatus] = useState({});
  const [apiKeysLoaded, setApiKeysLoaded] = useState(false);
  // Rate limiting states
  const [rateLimited, setRateLimited] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);
  const [retryCountdown, setRetryCountdown] = useState(0);
  const [limitType, setLimitType] = useState("");
  const eventSourceRef = useRef(null);
  const logContainerRef = useRef(null);
  const abortControllerRef = useRef(null);
  const countdownTimerRef = useRef(null);
  const theme = useTheme();

  // Refs for scroll sync between textarea and syntax highlighter
  const textareaRef = useRef(null);
  const highlighterRef = useRef(null);

  // Create a custom syntax highlighting theme based on current theme
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;

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
      return typeof error.response.data.detail === 'object'
        ? (error.response.data.detail.error || error.response.data.detail.msg || JSON.stringify(error.response.data.detail))
        : error.response.data.detail;
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

  const modelChoices = {
    OpenAI: [
      'gpt-4o',
      'gpt-4.1',
      'gpt-4.1-2025-04-14',
      'o4-mini-2025-04-16',
      'o3-mini-2025-01-31',
      'o1-mini-2024-09-12',
      { value: 'separator', label: '──────────' },
      { value: 'label', label: 'Other models:' },
      'o3-pro-2025-06-10',
      'gpt-4o-mini',
      'o3-2025-04-16',
      'o1-2024-12-17',
      'o1-pro-2025-03-19',
      'gpt-4-turbo',
      'gpt-4-turbo-preview',
    ],
    Anthropic: [
      'claude-3-5-sonnet-latest',
      'claude-3-5-haiku-latest',
      'claude-3-7-sonnet-latest',
      'claude-3-5-sonnet-20240620',
      'claude-3-opus-20240229',
      'claude-3-sonnet-20240229',
      'claude-3-haiku-20240307',
      "claude-opus-4-20250514",
      "claude-sonnet-4-20250514",
    ],
    OpenRouter: [
      "deepseek/deepseek-r1-distill-llama-70b",
      "deepseek/deepseek-r1:free",
      "deepseek/deepseek-r1",
      "deepseek/deepseek-chat",
      "qwen/qwen3-235b-a22b-2507",
      "moonshotai/kimi-k2",
      "x-ai/grok-4",
      "x-ai/grok-3",
      "tencent/hunyuan-a13b-instruct",
    ],
    Google: [
      "gemini-2.0-flash-thinking-exp-01-21",
      "gemini-2.0-pro-exp-02-05",
      "gemini-2.0-flash",
      "gemini-2.0-flash-lite",
      "gemini-2.5-flash",
      "gemini-2.5-flash-preview-05-20",
      "gemini-2.5-pro",
      "gemini-2.5-pro-preview-03-25",
    ],
    Groq: [
      "llama-3.3-70b-versatile",
      "deepseek-r1-distill-llama-70b",
      "meta-llama/llama-4-maverick-17b-128e-instruct",
      "meta-llama/llama-4-scout-17b-16e-instruct",
      "moonshotai/kimi-k2-instruct",
      "compound-beta",
      "compound-beta-mini",
    ],
    Nvidia: [
      "meta/llama-3.1-405b-instruct",
      "meta/llama-3.1-70b-instruct",
      "meta/llama-3.1-8b-instruct",
      "meta/llama-4-maverick-17b-128e-instruct",
      "meta/llama-4-scout-17b-16e-instruct",
      "mistralai/mixtral-8x22b-instruct-v0.1",
      "qwen/qwen3-235b-a22b",
      "moonshotai/kimi-k2-instruct",
      "deepseek-ai/deepseek-r1",
    ],
  };

  const supportedModels = ['gpt-4o', 'claude-3-7-sonnet-latest', 'claude-3-5-sonnet-latest', 'llama3.2-405b', 'deepseek/deepseek-r1', 'gemini-2.0-flash'];

  // Fetch API keys status on component mount
  useEffect(() => {
    const fetchApiKeysStatus = async () => {
      try {
        const response = await api.get('/api_keys_status/');
        if (response.data) {
          console.log('API keys status:', response.data);
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

    return true;
  };

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

  // Reset highlight when settings become valid
  useEffect(() => {
    if (isSettingsValid()) {
      setHighlightSettings(false);
    }
  }, [provider, llmType, apiKey]);

  // Enhanced log streaming setup with better error handling and reconnection
  const setupLogStream = () => {
    if (verbose) {
      console.log('Setting up log stream for verbose mode');

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

  // Listen for edit query event from ResultsDisplay
  useEffect(() => {
    const handleEditQuery = () => {
      if (generatedQuery && runnedQuery) {
        setRunnedQuery(false);
      }
    };

    window.addEventListener('editQuery', handleEditQuery);

    return () => {
      window.removeEventListener('editQuery', handleEditQuery);
    };
  }, [generatedQuery, runnedQuery]);

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
      alert("Please configure the LLM settings first");
      setSettingsOpen(true);
      setHighlightSettings(true);
      return;
    }

    // Prevent submitting if rate limited
    if (rateLimited) {
      return;
    }

    // Clear any previous errors at the start of the operation
    setError(null);

    // Create a new AbortController
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    setLoading(true);
    setActiveButton('generate');
    updateRealtimeLogs(verbose ? 'Generating Cypher query...\n' : '');
    setLogs('');
    try {
      if (verbose) {
        updateRealtimeLogs(prev => prev + `Sending request with parameters:\n- Question: ${question}\n- Model: ${llmType}\n- Top K: ${topK}\n- Verbose: ${verbose}\n`);
      }

      // Update API key to use from environment if available
      const effectiveApiKey = (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;

      const response = await api.post('/generate_query/', {
        question,
        llm_type: llmType,
        top_k: topK,
        api_key: effectiveApiKey,
        verbose,
      }, { signal });

      // Process the query result before setting it
      const queryData = response.data.query;

      // Set the generated query regardless of type
      setGeneratedQuery(queryData);
      setEditableQuery(queryData);

      // Set the query result to null to hide it from ResultsDisplay
      setQueryResult(null);
      setExecutionResult(null);
      setRunnedQuery(false);

      // Collapse settings panel to show results
      if (showSettings) {
        setShowSettings(false);
      }

      if (verbose) {
        if (response.data.logs) {
          setLogs(response.data.logs);
          updateRealtimeLogs(prev => prev + 'Query generation completed successfully!\n');
        } else {
          updateRealtimeLogs(prev => prev + 'Warning: No logs returned from server despite verbose mode enabled\n');
        }
      }

      addLatestQuery({
        question: question,
        query: queryData,
        timestamp: new Date().toISOString(),
        queryType: 'generated'
      });
    } catch (error) {
      if (axios.isCancel(error)) {
        console.log('Request canceled:', error.message);
      } else {
        console.error('Error generating query:', error);
        // Use the rate limit handler to process errors
        const errorMessage = handleRateLimitError(error);
        setError(errorMessage);

        if (verbose) {
          updateRealtimeLogs(prev => prev + `Error: ${errorMessage}\n`);
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
    if (!editableQuery) return;

    if (!isSettingsValid()) {
      alert("Please configure the LLM settings first");
      setSettingsOpen(true);
      setHighlightSettings(true);
      return;
    }

    // Prevent submitting if rate limited
    if (rateLimited) {
      return;
    }

    // Clear any previous errors at the start of the operation
    setError(null);

    // Create a new AbortController
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    setLoading(true);
    setActiveButton('run');
    try {
      if (verbose) {
        updateRealtimeLogs(prev => prev + 'Executing generated Cypher query...\n');
      }

      // Update API key to use from environment if available
      const effectiveApiKey = (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;

      const response = await api.post('/run_query/', {
        query: editableQuery,
        question: question,
        llm_type: llmType,
        api_key: effectiveApiKey,
        verbose,
      }, { signal });

      // Now show the query in the results display
      setQueryResult(editableQuery);
      setExecutionResult({
        result: response.data.result,
        response: response.data.response
      });
      setRunnedQuery(true);

      // Collapse settings panel to show results
      if (showSettings) {
        setShowSettings(false);
      }

      if (verbose) {
        if (response.data.logs) {
          setLogs(prev => prev + '\n\n' + response.data.logs);
          updateRealtimeLogs(prev => prev + 'Query execution completed successfully!\n');
        } else {
          updateRealtimeLogs(prev => prev + 'Warning: No logs returned from server despite verbose mode enabled\n');
        }
      }

      // Update the latest query with the run information
      addLatestQuery({
        question: question,
        query: editableQuery,
        timestamp: new Date().toISOString(),
        queryType: 'run',
        response: response.data.response
      });
    } catch (error) {
      if (axios.isCancel(error)) {
        console.log('Request canceled:', error.message);
      } else {
        console.error('Error running query:', error);
        // Use the rate limit handler to process errors
        const errorMessage = handleRateLimitError(error);
        setError(errorMessage);

        if (verbose) {
          updateRealtimeLogs(prev => prev + `Error: ${errorMessage}\n`);
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
      alert("Please configure the LLM settings first");
      setSettingsOpen(true);
      setHighlightSettings(true);
      return;
    }

    // Prevent submitting if rate limited
    if (rateLimited) {
      return;
    }

    // Clear any previous errors at the start of the operation
    setError(null);

    // Create a new AbortController
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    setLoading(true);
    setActiveButton('generateAndRun');
    updateRealtimeLogs(verbose ? 'Generating and running Cypher query...\n' : '');
    setLogs('');
    try {
      if (verbose) {
        updateRealtimeLogs(prev => prev + `Sending request with parameters:\n- Question: ${question}\n- Model: ${llmType}\n- Top K: ${topK}\n- Verbose: ${verbose}\n`);
      }

      // Update API key to use from environment if available
      const effectiveApiKey = (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;

      // First generate the query
      const generateResponse = await api.post('/generate_query/', {
        question,
        llm_type: llmType,
        top_k: topK,
        api_key: effectiveApiKey,
        verbose,
      }, { signal });

      // Process the query result
      const processedQuery = generateResponse.data.query;

      // Set the generated query
      setGeneratedQuery(processedQuery);
      setEditableQuery(processedQuery);

      // Initially set queryResult to null to hide it
      setQueryResult(null);

      if (verbose) {
        if (generateResponse.data.logs) {
          setLogs(generateResponse.data.logs);
          updateRealtimeLogs(prev => prev + 'Query generation completed successfully!\n');
        } else {
          updateRealtimeLogs(prev => prev + 'Warning: No logs returned from server despite verbose mode enabled\n');
        }
      }

      // Check if the request was aborted during generation
      if (signal.aborted) {
        throw new axios.Cancel('Operation canceled by the user');
      }

      // Then run the query
      if (verbose) {
        updateRealtimeLogs(prev => prev + 'Executing generated Cypher query...\n');
      }

      const runResponse = await api.post('/run_query/', {
        query: processedQuery,
        question: question,
        llm_type: llmType,
        api_key: effectiveApiKey,
        verbose,
      }, { signal });

      // Now show the query in the results display
      setQueryResult(processedQuery);
      setExecutionResult({
        result: runResponse.data.result,
        response: runResponse.data.response
      });
      setRunnedQuery(true);

      // Collapse settings panel to show results
      if (showSettings) {
        setShowSettings(false);
      }

      if (verbose) {
        if (runResponse.data.logs) {
          setLogs(prev => prev + '\n\n' + runResponse.data.logs);
          updateRealtimeLogs(prev => prev + 'Query execution completed successfully!\n');
        } else {
          updateRealtimeLogs(prev => prev + 'Warning: No logs returned from server despite verbose mode enabled\n');
        }
      }

      // Update the latest queries with both generate and run information
      addLatestQuery({
        question: question,
        query: processedQuery,
        timestamp: new Date().toISOString(),
        queryType: 'generated'
      });

      // After running the query, update with the run information
      addLatestQuery({
        question: question,
        query: processedQuery,
        timestamp: new Date().toISOString(),
        queryType: 'run',
        response: runResponse.data.response
      });
    } catch (error) {
      if (axios.isCancel(error)) {
        console.log('Request canceled:', error.message);
      } else {
        console.error('Error generating and running query:', error);
        // Use the rate limit handler to process errors
        const errorMessage = handleRateLimitError(error);
        setError(errorMessage);

        if (verbose) {
          updateRealtimeLogs(prev => prev + `Error: ${errorMessage}\n`);
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

  const handleSampleQuestionClick = (sampleQuestion) => {
    setQuestion(typeof sampleQuestion === 'string' ? sampleQuestion : sampleQuestion.question);
  };

  const toggleSettings = () => {
    setShowSettings(!showSettings);
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
        }}
      >
        <Box sx={{ p: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h5" sx={{ fontWeight: 600, letterSpacing: '-0.01em' }}>
              Graph Explorer
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
              Ask any biomedical question to query the CROssBAR knowledge graph. For example, "Which drugs target proteins associated with Alzheimer disease?"
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
              placeholder="E.g., Which drugs target proteins associated with Alzheimer disease?"
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

          {/* Settings panel moved below the query input and Configure Settings button */}
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
                        {Object.keys(modelChoices).map((provider) => (
                          <MenuItem key={provider} value={provider}>
                            {provider}
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
                        onChange={(e) => setLlmType(e.target.value)}
                        label="Model"
                      >
                        <MenuItem value="">
                          <em>Select a model</em>
                        </MenuItem>
                        {provider && modelChoices[provider].map((model) => {
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

                {/* Second row - API Key and Top K */}
                <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                  {/* Show API Key field based on conditions */}
                  {!apiKeysStatus[provider] && (
                    <Box sx={{ flex: '1 1 250px', minWidth: '250px' }}>
                      <FormControl fullWidth variant="outlined" size="small">
                        <TextField
                          label="API Key"
                          type="password"
                          value={apiKey}
                          onChange={(e) => setApiKey(e.target.value)}
                          size="small"
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
                          backgroundColor: theme => theme.palette.mode === 'dark' ? alpha('#4caf50', 0.1) : alpha('#4caf50', 0.05),
                          border: '1px solid rgba(76, 175, 80, 0.3)'
                        }}
                      >
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <Box sx={{ color: '#4caf50', mr: 1, display: 'flex', alignItems: 'center' }}>
                              <svg width="20" height="20" viewBox="0 0 24 24">
                                <path fill="currentColor" d="M9,16.17L4.83,12l-1.42,1.41L9,19L21,7l-1.41-1.41L9,16.17z"/>
                              </svg>
                            </Box>
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
                      <TextField
                        label="Top K Results"
                        type="number"
                        value={topK}
                        onChange={(e) => setTopK(parseInt(e.target.value))}
                        size="small"
                        inputProps={{ min: 1, max: 100 }}
                      />
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
                          <Tooltip title="Enable to see detailed logs of the query generation and execution process">
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

          {/* Sample Questions - Moved to top position for better visibility */}
          <Box sx={{
            display: 'flex',
            justifyContent: 'center',
            mb: 3,
            mt: !showSettings && !showWarning ? 1 : 0
          }}>
            <SampleQuestions onQuestionClick={handleSampleQuestionClick} />
          </Box>

          <Box sx={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <Tooltip title={isSettingsValid() ? "Generate Cypher Query" : "Configure settings first"}>
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
                      startIcon={activeButton === 'generate' ? <CircularProgress size={20} /> : <SendIcon />}
                      sx={{
                        borderRadius: '12px',
                        px: 3,
                        height: '44px',
                        fontSize: '0.75rem',
                      }}
                    >
                      Only Generate Query
                    </Button>
                  )}
                </Box>
              </Tooltip>

              <Tooltip title={isSettingsValid() ? "Generate and Run Query" : "Configure settings first"}>
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
                      startIcon={activeButton === 'generateAndRun' ? <CircularProgress size={20} /> : <PlayArrowIcon />}
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
                  height: '150px',
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
                    height: '100%',
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
                    {editableQuery || ' '}
                  </SyntaxHighlighter>
                </Box>
                <textarea
                  ref={textareaRef}
                  value={editableQuery}
                  onChange={(e) => setEditableQuery(e.target.value)}
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
                    height: '100%',
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
                onClick={() => setEditableQuery(generatedQuery)}
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
                  disabled={!isSettingsValid() || !editableQuery.trim() || loading}
                  startIcon={activeButton === 'run' ? <CircularProgress size={20} /> : <PlayArrowIcon />}
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
                  {limitType === "hour" && `Please wait ${Math.floor(retryCountdown/60)} minute${Math.floor(retryCountdown/60) !== 1 ? 's' : ''} and ${retryCountdown % 60} second${retryCountdown % 60 !== 1 ? 's' : ''} before trying again.`}
                  {limitType === "day" && `Daily limit reached. Please try again tomorrow (in ${Math.floor(retryCountdown/3600)} hour${Math.floor(retryCountdown/3600) !== 1 ? 's' : ''}).`}
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
                  {limitType === "hour" && `Please wait ${Math.floor(retryCountdown/60)} minute${Math.floor(retryCountdown/60) !== 1 ? 's' : ''} and ${retryCountdown % 60} second${retryCountdown % 60 !== 1 ? 's' : ''} before trying again.`}
                  {limitType === "day" && `Daily limit reached. Please try again tomorrow (in ${Math.floor(retryCountdown/3600)} hour${Math.floor(retryCountdown/3600) !== 1 ? 's' : ''}).`}
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

export default QueryInput;
