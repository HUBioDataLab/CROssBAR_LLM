import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  IconButton,
  Tooltip,
  useTheme,
  alpha,
  Chip,
  Button,
  CircularProgress,
  Collapse,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  InputAdornment,
  Switch,
  FormControlLabel,
  Checkbox,
  Alert,
  Divider,
  Snackbar,
  Zoom,
  List,
  ListItem,
  ListItemText,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import StopIcon from '@mui/icons-material/Stop';
import AddIcon from '@mui/icons-material/Add';
import CodeIcon from '@mui/icons-material/Code';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import EditIcon from '@mui/icons-material/Edit';
import RestoreIcon from '@mui/icons-material/Restore';
import DataObjectIcon from '@mui/icons-material/DataObject';
import BubbleChartIcon from '@mui/icons-material/BubbleChart';
import HistoryIcon from '@mui/icons-material/History';
import TerminalIcon from '@mui/icons-material/Terminal';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import PersonIcon from '@mui/icons-material/Person';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import TuneIcon from '@mui/icons-material/Tune';
import KeyIcon from '@mui/icons-material/Key';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import LaunchIcon from '@mui/icons-material/Launch';
import CloseIcon from '@mui/icons-material/Close';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import NodeVisualization from './NodeVisualization';
import LatestQueries from './LatestQueries';
import api, { getAvailableModels } from '../services/api';
import axios from 'axios';
import Fuse from 'fuse.js';
import { loadSuggestions } from '../utils/loadSuggestions';

const DRAWER_WIDTH = 420;

function ChatLayout({
  // State props
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
  addLatestQuery,
  question,
  setQuestion,
  queryResult,
  setQueryResult,
  executionResult,
  setExecutionResult,
  realtimeLogs,
  setRealtimeLogs,
  latestQueries,
  handleSelectQuery,
  pendingFollowUp,
  setPendingFollowUp,
}) {
  const theme = useTheme();
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);

  // Local state
  const [isLoading, setIsLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState('');
  const [error, setError] = useState(null);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [topK, setTopK] = useState(10);
  const [verbose, setVerbose] = useState(false);
  const [copySnackbar, setCopySnackbar] = useState(false);
  
  // Query editing state
  const [editableQuery, setEditableQuery] = useState('');
  const [originalQuery, setOriginalQuery] = useState('');
  const [pendingQuestion, setPendingQuestion] = useState(''); // Question waiting for query to be run
  const [queryGenerated, setQueryGenerated] = useState(false); // True when query is generated but not run
  const [isEditingQuery, setIsEditingQuery] = useState(false);
  
  // Autocomplete hint visibility
  const [showAutocompleteHint, setShowAutocompleteHint] = useState(true);
  
  // Autocomplete state
  const [suggestions, setSuggestions] = useState([]);
  const [displaySuggestions, setDisplaySuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedSuggestionIndex, setSelectedSuggestionIndex] = useState(0);
  const [cursorPosition, setCursorPosition] = useState(0);
  const inputContainerRef = useRef(null);
  const suggestionsRef = useRef(null);
  const debounceTimeoutRef = useRef(null);
  
  // Node type color mapping for autocomplete
  const nodeTypeColors = {
    "Gene": { bg: '#287271', text: '#FFFFFF' },
    "Protein": { bg: '#3aa6a4', text: '#FFFFFF' },
    "Drug": { bg: '#815ac0', text: '#FFFFFF' },
    "Disease": { bg: '#079dbb', text: '#FFFFFF' },
    "Compound": { bg: '#d2b7e5', text: '#FFFFFF' },
    "Pathway": { bg: '#720026', text: '#FFFFFF' },
    "Phenotype": { bg: '#58d0e8', text: '#FFFFFF' },
    "default": { bg: '#A5ABB6', text: '#FFFFFF' }
  };
  
  // API keys and models state
  const [apiKeysStatus, setApiKeysStatus] = useState({});
  const [apiKeysLoaded, setApiKeysLoaded] = useState(false);
  const [modelChoices, setModelChoices] = useState({});
  const [modelsLoaded, setModelsLoaded] = useState(false);
  
  // Expanded sections in right panel
  const [expandedSections, setExpandedSections] = useState({
    examples: true,
    settings: false,
    query: true,
    results: false,
    visualization: true,
    logs: false,
    history: false,
  });

  // Example queries
  const exampleQueries = [
    "Which Gene is related to the Disease named psoriasis?",
    "What proteins does the drug named Caffeine target?",
    "Which drugs target proteins associated with Alzheimer disease?",
    "Which pathways are associated with both diabetes mellitus and T-cell non-Hodgkin lymphoma? Return only signaling pathways.",
    "What are the common side effects of drugs targeting the EGFR gene's protein?",
  ];

  const neo4jBrowserUrl = 'https://neo4j.crossbarv2.hubiodatalab.com/browser/?preselectAuthMethod=[NO_AUTH]&dbms=bolt://neo4j.crossbarv2.hubiodatalab.com';

  // Supported/recommended models (highlighted in model selection)
  const supportedModels = [
    'gpt-5.1', 'gpt-4o', 'o4-mini', 'claude-sonnet-4-5', 'claude-opus-4-1', 
    'llama3.2-405b', 'deepseek/deepseek-r1', 'gemini-2.5-pro', 'gemini-2.5-flash'
  ];

  // Fetch available models on mount
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

  // Scroll to bottom when messages update
  useEffect(() => {
    scrollToBottom();
  }, [conversationHistory, isLoading]);

  // Auto-collapse example queries after first question
  useEffect(() => {
    if (conversationHistory.length > 0 || queryGenerated) {
      setExpandedSections(prev => ({ ...prev, examples: false }));
    }
  }, [conversationHistory.length, queryGenerated]);

  // Sync editable query with queryResult
  useEffect(() => {
    if (queryResult && !queryGenerated) {
      setEditableQuery(queryResult);
      setOriginalQuery(queryResult);
    }
  }, [queryResult, queryGenerated]);

  // Ref to hold handleSubmit for use in useEffect
  const handleSubmitRef = useRef(null);

  // Handle pending follow-up
  useEffect(() => {
    if (pendingFollowUp && question === pendingFollowUp && !isLoading) {
      setPendingFollowUp(null);
      if (handleSubmitRef.current) {
        handleSubmitRef.current();
      }
    }
  }, [pendingFollowUp, question, isLoading, setPendingFollowUp]);

  // Load autocomplete suggestions when @ is typed
  useEffect(() => {
    const hasAtSymbol = question.includes('@');
    if (hasAtSymbol && suggestions.length === 0) {
      const fetchSuggestions = async () => {
        const loadedSuggestions = await loadSuggestions();
        setSuggestions(loadedSuggestions);
      };
      fetchSuggestions();
    }
  }, [question, suggestions.length]);

  // Fuse.js instance for fuzzy search
  const fuse = React.useMemo(() => new Fuse(suggestions, {
    includeScore: true,
    threshold: 0.5,
    ignoreLocation: true,
    minMatchCharLength: 2,
    keys: ['term'],
  }), [suggestions]);

  // Handle autocomplete input changes
  const handleAutocompleteChange = useCallback((newValue, cursorPos) => {
    setQuestion(newValue);
    setCursorPosition(cursorPos);
    setSelectedSuggestionIndex(0);

    // Clear existing timeout
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    // Only process if @ symbol is present
    if (!newValue.includes('@')) {
      setShowSuggestions(false);
      setDisplaySuggestions([]);
      return;
    }

    // Debounce search
    debounceTimeoutRef.current = setTimeout(() => {
      const lastAtSymbol = newValue.lastIndexOf('@', cursorPos - 1);

      if (lastAtSymbol !== -1) {
        const query = newValue.slice(lastAtSymbol + 1, cursorPos);
        const formattedQuery = query.replace(/\s+/g, '_');

        if (query.length > 2) {
          let matchedSuggestions;

          // First try direct inclusion for exact matches
          matchedSuggestions = suggestions.filter(s =>
            s.term.toLowerCase().includes(formattedQuery.toLowerCase())
          )
            .sort((a, b) => a.term.length - b.term.length)
            .slice(0, 10);

          // Use fuzzy search if no direct matches
          if (matchedSuggestions.length === 0) {
            const results = fuse.search(formattedQuery);
            matchedSuggestions = results.map((result) => result.item)
              .sort((a, b) => a.term.length - b.term.length)
              .slice(0, 10);
          }

          setDisplaySuggestions(matchedSuggestions);
          setShowSuggestions(matchedSuggestions.length > 0);
        } else {
          setShowSuggestions(false);
        }
      } else {
        setShowSuggestions(false);
      }
    }, 200);
  }, [suggestions, fuse]);

  // Handle suggestion selection
  const handleSuggestionClick = useCallback((suggestion) => {
    const displayTerm = suggestion.term.replaceAll('_', ' ');
    const displaySuggestion = `${displayTerm} (${suggestion.type})`;
    const textBeforeCursor = question.slice(0, cursorPosition);
    const textAfterCursor = question.slice(cursorPosition);
    const lastAtSymbol = textBeforeCursor.lastIndexOf('@');

    const newTextBeforeCursor = textBeforeCursor.slice(0, lastAtSymbol) + displaySuggestion + ' ';
    const newValue = newTextBeforeCursor + textAfterCursor;

    setQuestion(newValue);
    setShowSuggestions(false);
    inputRef.current?.focus();
  }, [question, cursorPosition]);

  // Handle autocomplete keyboard navigation
  const handleAutocompleteKeyDown = useCallback((e) => {
    if (!showSuggestions) return false;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedSuggestionIndex((prev) =>
          prev < displaySuggestions.length - 1 ? prev + 1 : prev
        );
        return true;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedSuggestionIndex((prev) => (prev > 0 ? prev - 1 : prev));
        return true;
      case 'Tab':
      case 'Enter':
        if (displaySuggestions[selectedSuggestionIndex]) {
          e.preventDefault();
          handleSuggestionClick(displaySuggestions[selectedSuggestionIndex]);
          return true;
        }
        return false;
      case 'Escape':
        setShowSuggestions(false);
        return true;
      default:
        return false;
    }
  }, [showSuggestions, displaySuggestions, selectedSuggestionIndex, handleSuggestionClick]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const handleCopy = async (text, index) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIndex(index);
      setCopySnackbar(true);
      setTimeout(() => {
        setCopiedIndex(null);
        setCopySnackbar(false);
      }, 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
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

  // Generate query only (without running)
  const handleGenerateOnly = async (e) => {
    e?.preventDefault();
    if (!question.trim() || isLoading) return;

    if (!isSettingsValid()) {
      setExpandedSections(prev => ({ ...prev, settings: true }));
      setError('Please configure model settings first');
      return;
    }

    // Collapse settings panel when submitting a question (like example questions)
    setExpandedSections(prev => ({ ...prev, settings: false }));

    const userQuestion = question.trim();
    setPendingQuestion(userQuestion);
    setQuestion('');
    setError(null);
    setIsLoading(true);
    setCurrentStep('Generating Cypher query...');

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    const effectiveApiKey = (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;

    try {
      const generateResponse = await api.post('/generate_query/', {
        question: userQuestion,
        llm_type: llmType,
        provider,
        api_key: effectiveApiKey,
        verbose,
        top_k: topK,
        session_id: sessionId,
      }, { signal });

      const cypherQuery = generateResponse.data.query;
      setQueryResult(cypherQuery);
      setEditableQuery(cypherQuery);
      setOriginalQuery(cypherQuery);
      setQueryGenerated(true);
      setIsEditingQuery(false);
      
      // Expand the query section to show the generated query
      setExpandedSections(prev => ({ ...prev, query: true }));

      // Add to latest queries as generated
      addLatestQuery({
        question: userQuestion,
        query: cypherQuery,
        queryType: 'generated',
        timestamp: new Date().toISOString(),
      });

    } catch (err) {
      if (axios.isCancel(err) || err.name === 'CanceledError' || err.name === 'AbortError') {
        console.log('Request cancelled');
      } else {
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
        setPendingQuestion('');
      }
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

    setError(null);
    setIsLoading(true);
    setCurrentStep('Executing query...');

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    const effectiveApiKey = (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;

    try {
      const runResponse = await api.post('/run_query/', {
        query: editableQuery,
        question: pendingQuestion,
        llm_type: llmType,
        provider,
        api_key: effectiveApiKey,
        verbose,
        top_k: topK,
        session_id: sessionId,
      }, { signal });

      setExecutionResult({
        result: runResponse.data.result,
        response: runResponse.data.response,
        followUpQuestions: runResponse.data.follow_up_questions || [],
      });

      // Update queryResult with the edited query
      setQueryResult(editableQuery);

      // Add to conversation history
      addConversationTurn({
        question: pendingQuestion,
        cypherQuery: editableQuery,
        response: runResponse.data.response,
        result: runResponse.data.result,
        followUpQuestions: runResponse.data.follow_up_questions || [],
      });

      // Add to latest queries
      addLatestQuery({
        question: pendingQuestion,
        query: editableQuery,
        response: runResponse.data.response,
        queryType: 'run',
        timestamp: new Date().toISOString(),
      });

      // Reset query editing state
      setQueryGenerated(false);
      setPendingQuestion('');
      setIsEditingQuery(false);

      // Auto-expand visualization if we have results
      if (runResponse.data.result && runResponse.data.result.length > 0) {
        setExpandedSections(prev => ({ ...prev, visualization: true }));
      }

    } catch (err) {
      if (axios.isCancel(err) || err.name === 'CanceledError' || err.name === 'AbortError') {
        console.log('Request cancelled');
      } else {
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
      }
    } finally {
      setIsLoading(false);
      setCurrentStep('');
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

    // Collapse settings panel when submitting a question (like example questions)
    setExpandedSections(prev => ({ ...prev, settings: false }));

    const userQuestion = question.trim();
    setQuestion('');
    setError(null);
    setIsLoading(true);
    setCurrentStep('Generating Cypher query...');
    
    // Reset query editing state
    setQueryGenerated(false);
    setPendingQuestion('');

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    const effectiveApiKey = (apiKeysStatus[provider] && apiKey === 'env') ? 'env' : apiKey;

    try {
      // Step 1: Generate Cypher query
      const generateResponse = await api.post('/generate_query/', {
        question: userQuestion,
        llm_type: llmType,
        provider,
        api_key: effectiveApiKey,
        verbose,
        top_k: topK,
        session_id: sessionId,
      }, { signal });

      const cypherQuery = generateResponse.data.query;
      setQueryResult(cypherQuery);
      setEditableQuery(cypherQuery);
      setOriginalQuery(cypherQuery);
      setCurrentStep('Executing query...');

      // Step 2: Run the query
      const runResponse = await api.post('/run_query/', {
        query: cypherQuery,
        question: userQuestion,
        llm_type: llmType,
        provider,
        api_key: effectiveApiKey,
        verbose,
        top_k: topK,
        session_id: sessionId,
      }, { signal });

      setExecutionResult({
        result: runResponse.data.result,
        response: runResponse.data.response,
        followUpQuestions: runResponse.data.follow_up_questions || [],
      });

      // Add to conversation history
      addConversationTurn({
        question: userQuestion,
        cypherQuery: cypherQuery,
        response: runResponse.data.response,
        result: runResponse.data.result,
        followUpQuestions: runResponse.data.follow_up_questions || [],
      });

      // Add to latest queries
      addLatestQuery({
        question: userQuestion,
        query: cypherQuery,
        response: runResponse.data.response,
        queryType: 'run',
        timestamp: new Date().toISOString(),
      });

      // Auto-expand visualization if we have results
      if (runResponse.data.result && runResponse.data.result.length > 0) {
        setExpandedSections(prev => ({ ...prev, visualization: true }));
      }

    } catch (err) {
      if (axios.isCancel(err) || err.name === 'CanceledError' || err.name === 'AbortError') {
        console.log('Request cancelled');
      } else {
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
      }
    } finally {
      setIsLoading(false);
      setCurrentStep('');
      abortControllerRef.current = null;
    }
  };

  // Assign to ref for use in useEffect
  handleSubmitRef.current = handleSubmit;

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFollowUpClick = (followUpQuestion) => {
    setQuestion(followUpQuestion);
    setPendingFollowUp(followUpQuestion);
  };

  const handleExampleClick = (example) => {
    setQuestion(example);
    inputRef.current?.focus();
  };

  // Welcome screen when no messages
  const renderWelcome = () => (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        flex: 1,
        py: 4,
        px: 3,
        textAlign: 'center',
      }}
    >
      {/* Logo and Title */}
      <Box
        sx={{
          width: 72,
          height: 72,
          borderRadius: '20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: theme.palette.mode === 'dark'
            ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
            : 'linear-gradient(135deg, #0071e3 0%, #5e5ce6 100%)',
          mb: 2.5,
          boxShadow: `0 8px 32px ${alpha(theme.palette.primary.main, 0.3)}`,
        }}
      >
        <AutoAwesomeIcon sx={{ fontSize: 36, color: 'white' }} />
      </Box>
      <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
        CROssBAR-LLM
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 4, maxWidth: 550 }}>
        Ask questions about the biomedical knowledge graph. I'll generate Cypher queries and provide natural language answers.
      </Typography>
      
      {/* Features Grid */}
      <Box sx={{ 
        display: 'grid', 
        gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' }, 
        gap: 2, 
        width: '100%', 
        maxWidth: 700,
        mt: 2,
      }}>
        <Paper
          elevation={0}
          sx={{
            p: 2,
            borderRadius: '12px',
            backgroundColor: alpha(theme.palette.success.main, 0.06),
            border: `1px solid ${alpha(theme.palette.success.main, 0.15)}`,
            textAlign: 'center',
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 600, color: theme.palette.success.main, mb: 0.5 }}>
            Natural Language
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Ask questions in plain English
          </Typography>
        </Paper>
        <Paper
          elevation={0}
          sx={{
            p: 2,
            borderRadius: '12px',
            backgroundColor: alpha(theme.palette.info.main, 0.06),
            border: `1px solid ${alpha(theme.palette.info.main, 0.15)}`,
            textAlign: 'center',
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 600, color: theme.palette.info.main, mb: 0.5 }}>
            Auto-generated Queries
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Cypher queries created for you
          </Typography>
        </Paper>
        <Paper
          elevation={0}
          sx={{
            p: 2,
            borderRadius: '12px',
            backgroundColor: alpha(theme.palette.warning.main, 0.06),
            border: `1px solid ${alpha(theme.palette.warning.main, 0.15)}`,
            textAlign: 'center',
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 600, color: theme.palette.warning.main, mb: 0.5 }}>
            Entity Autocomplete
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Type @ for suggestions
          </Typography>
        </Paper>
      </Box>
    </Box>
  );

  // Render a single message
  const renderMessage = (turn, index) => {
    const isLatest = index === conversationHistory.length - 1;

    return (
      <Box key={index} sx={{ mb: 4 }}>
        {/* User Message */}
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <Box
            sx={{
              width: 36,
              height: 36,
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: theme.palette.primary.main,
              color: 'white',
              flexShrink: 0,
            }}
          >
            <PersonIcon sx={{ fontSize: 20 }} />
          </Box>
          <Box sx={{ flex: 1, pt: 0.5 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5, color: 'text.secondary' }}>
              You
            </Typography>
            <Typography variant="body1">{turn.question}</Typography>
          </Box>
        </Box>

        {/* Assistant Message */}
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Box
            sx={{
              width: 36,
              height: 36,
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: theme.palette.mode === 'dark'
                ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
                : 'linear-gradient(135deg, #0071e3 0%, #5e5ce6 100%)',
              color: 'white',
              flexShrink: 0,
            }}
          >
            <SmartToyIcon sx={{ fontSize: 20 }} />
          </Box>
          <Box sx={{ flex: 1, pt: 0.5, minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                CROssBAR
              </Typography>
              <Tooltip title={copiedIndex === index ? "Copied!" : "Copy"}>
                <IconButton size="small" onClick={() => handleCopy(turn.response, index)} sx={{ opacity: 0.6 }}>
                  <ContentCopyIcon sx={{ fontSize: 14 }} />
                </IconButton>
              </Tooltip>
            </Box>

            <Paper
              elevation={0}
              sx={{
                p: 2.5,
                borderRadius: '16px',
                backgroundColor: alpha(theme.palette.background.default, 0.6),
                border: `1px solid ${theme.palette.divider}`,
              }}
            >
              <Typography variant="body1" sx={{ lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                {turn.response}
              </Typography>
            </Paper>

            {/* Follow-up Questions - only for latest */}
            {isLatest && turn.followUpQuestions && turn.followUpQuestions.length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1, fontWeight: 600 }}>
                  <LightbulbOutlinedIcon sx={{ fontSize: 14 }} />
                  Suggested follow-ups:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  {turn.followUpQuestions.map((q, qIdx) => (
                    <Chip
                      key={qIdx}
                      label={q}
                      size="small"
                      onClick={() => handleFollowUpClick(q)}
                      sx={{
                        cursor: 'pointer',
                        height: 'auto',
                        py: 0.5,
                        '& .MuiChip-label': { whiteSpace: 'normal' },
                        backgroundColor: alpha(theme.palette.primary.main, 0.1),
                        '&:hover': { backgroundColor: alpha(theme.palette.primary.main, 0.2) },
                        border: `1px solid ${alpha(theme.palette.primary.main, 0.3)}`,
                      }}
                    />
                  ))}
                </Box>
              </Box>
            )}
          </Box>
        </Box>
      </Box>
    );
  };

  // Loading indicator in chat
  const renderLoading = () => (
    <Box sx={{ display: 'flex', gap: 2, mb: 4 }}>
      <Box
        sx={{
          width: 36,
          height: 36,
          borderRadius: '12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: theme.palette.mode === 'dark'
            ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
            : 'linear-gradient(135deg, #0071e3 0%, #5e5ce6 100%)',
          color: 'white',
          flexShrink: 0,
        }}
      >
        <SmartToyIcon sx={{ fontSize: 20 }} />
      </Box>
      <Box sx={{ flex: 1, pt: 0.5 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: 'text.secondary' }}>
          CROssBAR
        </Typography>
        <Paper
          elevation={0}
          sx={{
            p: 2,
            borderRadius: '16px',
            backgroundColor: alpha(theme.palette.background.default, 0.6),
            border: `1px solid ${theme.palette.divider}`,
            display: 'flex',
            alignItems: 'center',
            gap: 2,
          }}
        >
          <CircularProgress size={20} />
          <Typography variant="body2" color="text.secondary">{currentStep}</Typography>
        </Paper>
      </Box>
    </Box>
  );

  // Right panel section header
  const SectionHeader = ({ title, icon, section, badge }) => (
    <Box
      onClick={() => toggleSection(section)}
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        p: 1.5,
        cursor: 'pointer',
        borderRadius: '12px',
        '&:hover': { backgroundColor: alpha(theme.palette.primary.main, 0.05) },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
        {icon}
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>{title}</Typography>
        {badge && <Chip label={badge} size="small" sx={{ height: 20, fontSize: '0.7rem' }} />}
      </Box>
      {expandedSections[section] ? <ExpandLessIcon /> : <ExpandMoreIcon />}
    </Box>
  );

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
        {/* Chat Header */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            px: 3,
            py: 2,
            borderBottom: `1px solid ${theme.palette.divider}`,
            backgroundColor: alpha(theme.palette.background.paper, 0.8),
            backdropFilter: 'blur(10px)',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              CROssBAR Chat
            </Typography>
            {conversationHistory.length > 0 && (
              <Chip
                label={`${conversationHistory.length} message${conversationHistory.length !== 1 ? 's' : ''}`}
                size="small"
                sx={{ fontSize: '0.75rem' }}
              />
            )}
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {conversationHistory.length > 0 && (
              <Tooltip title="New conversation">
                <IconButton onClick={startNewConversation} size="small">
                  <AddIcon />
                </IconButton>
              </Tooltip>
            )}
            <Tooltip title={rightPanelOpen ? "Hide panel" : "Show panel"}>
              <IconButton onClick={() => setRightPanelOpen(!rightPanelOpen)} size="small">
                {rightPanelOpen ? <ChevronRightIcon /> : <ChevronLeftIcon />}
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        {/* Messages Area */}
        <Box
          sx={{
            flex: 1,
            overflow: 'auto',
            px: 3,
            py: 3,
          }}
        >
          {conversationHistory.length === 0 && !isLoading ? (
            renderWelcome()
          ) : (
            <>
              {conversationHistory.map((turn, index) => renderMessage(turn, index))}
              {isLoading && renderLoading()}
              <div ref={messagesEndRef} />
            </>
          )}
        </Box>

        {/* Error Display */}
        {error && (
          <Box sx={{ px: 3, pb: 1 }}>
            <Paper
              elevation={0}
              sx={{
                p: 2,
                borderRadius: '12px',
                backgroundColor: alpha(theme.palette.error.main, 0.1),
                border: `1px solid ${alpha(theme.palette.error.main, 0.3)}`,
              }}
            >
              <Typography variant="body2" color="error">{error}</Typography>
            </Paper>
          </Box>
        )}

        {/* Input Area */}
        <Box
          sx={{
            px: 3,
            py: 2,
            borderTop: `1px solid ${theme.palette.divider}`,
            backgroundColor: alpha(theme.palette.background.paper, 0.8),
            backdropFilter: 'blur(10px)',
          }}
        >
          {/* Pending Query Banner */}
          {queryGenerated && pendingQuestion && (
            <Paper
              elevation={0}
              sx={{
                p: 2,
                mb: 2,
                borderRadius: '12px',
                backgroundColor: alpha(theme.palette.info.main, 0.08),
                border: `1px solid ${alpha(theme.palette.info.main, 0.3)}`,
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <CodeIcon fontSize="small" color="info" />
                  Query Generated - Ready to Run
                </Typography>
                <Button
                  size="small"
                  variant="text"
                  onClick={() => {
                    setQueryGenerated(false);
                    setPendingQuestion('');
                    setEditableQuery('');
                    setOriginalQuery('');
                  }}
                  sx={{ textTransform: 'none', color: 'text.secondary' }}
                >
                  Dismiss
                </Button>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Question: "{pendingQuestion}"
              </Typography>
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<PlayArrowIcon />}
                  onClick={handleRunEditedQuery}
                  disabled={isLoading}
                  sx={{ textTransform: 'none', borderRadius: '8px' }}
                >
                  Run Query
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<EditIcon />}
                  onClick={() => {
                    setExpandedSections(prev => ({ ...prev, query: true }));
                    setIsEditingQuery(true);
                  }}
                  sx={{ textTransform: 'none', borderRadius: '8px' }}
                >
                  Edit Query
                </Button>
              </Box>
            </Paper>
          )}
          
          {/* Chat Input with Autocomplete */}
          <Box ref={inputContainerRef} sx={{ position: 'relative' }}>
            <Paper
              component="form"
              onSubmit={handleSubmit}
              elevation={0}
              sx={{
                display: 'flex',
                alignItems: 'flex-end',
                gap: 1,
                p: 1.5,
                borderRadius: '20px',
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: alpha(theme.palette.background.default, 0.6),
                '&:focus-within': {
                  borderColor: theme.palette.primary.main,
                  boxShadow: `0 0 0 2px ${alpha(theme.palette.primary.main, 0.2)}`,
                },
              }}
            >
              <TextField
                inputRef={inputRef}
                fullWidth
                multiline
                maxRows={4}
                value={question}
                onChange={(e) => handleAutocompleteChange(e.target.value, e.target.selectionStart)}
                onKeyDown={(e) => {
                  // First check autocomplete navigation
                  if (handleAutocompleteKeyDown(e)) return;
                  // Then check for submit
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit();
                  }
                }}
                placeholder="Ask about genes, diseases, drugs, proteins... (use @ for autocomplete)"
                variant="standard"
                disabled={isLoading}
                InputProps={{
                  disableUnderline: true,
                  sx: { px: 1.5, py: 0.5, fontSize: '0.95rem' },
                }}
              />
              {isLoading ? (
                <IconButton onClick={handleCancel} sx={{ backgroundColor: theme.palette.error.main, color: 'white', '&:hover': { backgroundColor: theme.palette.error.dark } }}>
                  <StopIcon />
                </IconButton>
              ) : (
                <Box sx={{ display: 'flex', gap: 0.5 }}>
                  <Tooltip title="Generate query only (you can edit before running)">
                    <IconButton
                      onClick={handleGenerateOnly}
                      disabled={!question.trim()}
                      sx={{
                        backgroundColor: alpha(theme.palette.secondary.main, 0.1),
                        color: theme.palette.secondary.main,
                        '&:hover': { backgroundColor: alpha(theme.palette.secondary.main, 0.2) },
                        '&.Mui-disabled': { backgroundColor: alpha(theme.palette.secondary.main, 0.05), color: alpha(theme.palette.secondary.main, 0.3) },
                      }}
                    >
                      <CodeIcon />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Generate and run query">
                    <IconButton
                      type="submit"
                      disabled={!question.trim()}
                      sx={{
                        backgroundColor: theme.palette.primary.main,
                        color: 'white',
                        '&:hover': { backgroundColor: theme.palette.primary.dark },
                        '&.Mui-disabled': { backgroundColor: alpha(theme.palette.primary.main, 0.3), color: alpha('#fff', 0.5) },
                      }}
                    >
                      <SendIcon />
                    </IconButton>
                  </Tooltip>
                </Box>
              )}
            </Paper>

            {/* Autocomplete Suggestions Popup */}
            {showSuggestions && displaySuggestions.length > 0 && (
              <Paper
                ref={suggestionsRef}
                elevation={6}
                sx={{
                  position: 'absolute',
                  bottom: '100%',
                  left: 0,
                  right: 0,
                  mb: 1,
                  maxHeight: 250,
                  overflowY: 'auto',
                  borderRadius: '12px',
                  zIndex: 1000,
                  boxShadow: theme.shadows[8],
                }}
              >
                <List sx={{ py: 0.5 }}>
                  {displaySuggestions.map((suggestion, index) => (
                    <ListItem
                      key={index}
                      button
                      onClick={() => handleSuggestionClick(suggestion)}
                      selected={index === selectedSuggestionIndex}
                      sx={{
                        py: 1,
                        px: 2,
                        borderLeft: index === selectedSuggestionIndex
                          ? `3px solid ${theme.palette.primary.main}`
                          : '3px solid transparent',
                        backgroundColor: index === selectedSuggestionIndex
                          ? alpha(theme.palette.primary.main, 0.08)
                          : 'transparent',
                        '&:hover': {
                          backgroundColor: alpha(theme.palette.primary.main, 0.05),
                        }
                      }}
                    >
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Typography
                              variant="body2"
                              sx={{
                                fontWeight: index === selectedSuggestionIndex ? 600 : 400,
                                color: index === selectedSuggestionIndex
                                  ? theme.palette.primary.main
                                  : theme.palette.text.primary
                              }}
                            >
                              {suggestion.term.replace(/_/g, ' ')}
                            </Typography>
                            <Chip
                              label={suggestion.type}
                              size="small"
                              sx={{
                                height: 20,
                                fontSize: '0.65rem',
                                fontWeight: 500,
                                color: (nodeTypeColors[suggestion.type] || nodeTypeColors.default).text,
                                backgroundColor: (nodeTypeColors[suggestion.type] || nodeTypeColors.default).bg,
                              }}
                            />
                          </Box>
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              </Paper>
            )}
          </Box>
          
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block', textAlign: 'center' }}>
            <CodeIcon sx={{ fontSize: 12, verticalAlign: 'middle', mr: 0.5 }} /> Generate only • 
            <SendIcon sx={{ fontSize: 12, verticalAlign: 'middle', mx: 0.5 }} /> Generate & Run • 
            Type @ for autocomplete
          </Typography>
        </Box>
      </Box>

      {/* Right Panel - Details Sidebar */}
      <Box
        sx={{
          width: rightPanelOpen ? DRAWER_WIDTH : 0,
          flexShrink: 0,
          height: '100%',
          borderLeft: rightPanelOpen ? `1px solid ${theme.palette.divider}` : 'none',
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
          <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${theme.palette.divider}`, overflow: 'hidden' }}>
            <SectionHeader title="Example Queries" icon={<LightbulbOutlinedIcon fontSize="small" color="warning" />} section="examples" />
            <Collapse in={expandedSections.examples}>
              <Box sx={{ p: 2, pt: 0 }}>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {exampleQueries.map((example, idx) => (
                    <Chip
                      key={idx}
                      label={example}
                      onClick={() => handleExampleClick(example)}
                      sx={{
                        cursor: 'pointer',
                        justifyContent: 'flex-start',
                        height: 'auto',
                        py: 1,
                        px: 0.5,
                        '& .MuiChip-label': { 
                          whiteSpace: 'normal',
                          textAlign: 'left',
                        },
                        backgroundColor: alpha(theme.palette.primary.main, 0.08),
                        '&:hover': { backgroundColor: alpha(theme.palette.primary.main, 0.15) },
                        border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
                      }}
                    />
                  ))}
                </Box>
              </Box>
            </Collapse>
          </Paper>

          {/* Settings Section */}
          <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${theme.palette.divider}`, overflow: 'hidden' }}>
            <SectionHeader 
              title="Model Settings" 
              icon={<TuneIcon fontSize="small" color="primary" />} 
              section="settings" 
              badge={!isSettingsValid() ? "Required" : null}
            />
            <Collapse in={expandedSections.settings}>
              <Box sx={{ p: 2, pt: 0 }}>
                <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                  <InputLabel>Provider</InputLabel>
                  <Select 
                    value={provider} 
                    onChange={(e) => {
                      const selectedProvider = e.target.value;
                      setProvider(selectedProvider);
                      // Auto-select first model
                      if (selectedProvider && modelChoices[selectedProvider]) {
                        const firstModel = modelChoices[selectedProvider].find(m => typeof m === 'string');
                        if (firstModel) setLlmType(firstModel);
                        else setLlmType('');
                      } else {
                        setLlmType('');
                      }
                    }} 
                    label="Provider"
                  >
                    <MenuItem value=""><em>Select a provider</em></MenuItem>
                    {Object.keys(modelChoices).map((p) => (
                      <MenuItem key={p} value={p}>{p}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                  <InputLabel>Model</InputLabel>
                  <Select value={llmType} onChange={(e) => setLlmType(e.target.value)} label="Model" disabled={!provider}>
                    <MenuItem value=""><em>Select a model</em></MenuItem>
                    {provider && modelChoices[provider]?.map((m, idx) => {
                      if (typeof m === 'object' && m.value === 'separator') {
                        return <Divider key={`sep-${idx}`} sx={{ my: 1 }} />;
                      }
                      if (typeof m === 'object' && m.value === 'label') {
                        return <MenuItem key={`label-${idx}`} disabled sx={{ opacity: 0.7, fontWeight: 'bold', fontSize: '0.85rem' }}>{m.label}</MenuItem>;
                      }
                      const isSupported = supportedModels.includes(m);
                      return (
                        <MenuItem 
                          key={m} 
                          value={m}
                          sx={isSupported ? {
                            backgroundColor: alpha(theme.palette.success.main, 0.08),
                            fontWeight: 600,
                            '&:hover': {
                              backgroundColor: alpha(theme.palette.success.main, 0.15),
                            },
                            '&.Mui-selected': {
                              backgroundColor: alpha(theme.palette.success.main, 0.2),
                              '&:hover': {
                                backgroundColor: alpha(theme.palette.success.main, 0.25),
                              },
                            },
                          } : {}}
                        >
                          {isSupported && (
                            <Box component="span" sx={{ 
                              color: theme.palette.success.main, 
                              mr: 1, 
                              fontSize: '0.75rem',
                              fontWeight: 700,
                            }}>★</Box>
                          )}
                          {m}
                        </MenuItem>
                      );
                    })}
                  </Select>
                </FormControl>
                
                {/* API Key Section */}
                {apiKeysLoaded && apiKeysStatus[provider] ? (
                  <Paper
                    variant="outlined"
                    sx={{
                      p: 1.5,
                      mb: 2,
                      backgroundColor: alpha('#4caf50', 0.05),
                      border: '1px solid rgba(76, 175, 80, 0.3)'
                    }}
                  >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{ color: '#4caf50' }}>✓</Box>
                        Using API key from server
                      </Typography>
                      <FormControlLabel
                        control={
                          <Checkbox
                            size="small"
                            checked={apiKey !== 'env'}
                            onChange={(e) => setApiKey(e.target.checked ? '' : 'env')}
                            sx={{ p: 0.5 }}
                          />
                        }
                        label={<Typography variant="caption">Use custom</Typography>}
                        sx={{ m: 0 }}
                      />
                    </Box>
                    {apiKey !== 'env' && (
                      <TextField
                        fullWidth
                        size="small"
                        type="password"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder="Enter your API key"
                        sx={{ mt: 1.5 }}
                        InputProps={{
                          startAdornment: <InputAdornment position="start"><KeyIcon fontSize="small" /></InputAdornment>,
                        }}
                      />
                    )}
                  </Paper>
                ) : (
                  <TextField
                    fullWidth
                    size="small"
                    label="API Key"
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    sx={{ mb: 2 }}
                    InputProps={{
                      startAdornment: <InputAdornment position="start"><KeyIcon fontSize="small" /></InputAdornment>,
                    }}
                  />
                )}
                
                <TextField
                  fullWidth
                  size="small"
                  label="Top K Results"
                  type="number"
                  value={topK}
                  onChange={(e) => setTopK(Math.max(1, Math.min(100, parseInt(e.target.value) || 10)))}
                  inputProps={{ min: 1, max: 100 }}
                  helperText="Number of results to return (1-100)"
                  sx={{ mb: 2 }}
                />
                
                {/* Debug Mode */}
                <Box
                  onClick={() => setVerbose(!verbose)}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    p: 1.5,
                    borderRadius: '8px',
                    border: `1px solid ${theme.palette.divider}`,
                    cursor: 'pointer',
                    backgroundColor: verbose ? alpha(theme.palette.info.main, 0.08) : 'transparent',
                    '&:hover': { backgroundColor: alpha(theme.palette.info.main, 0.05) },
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <InfoOutlinedIcon fontSize="small" sx={{ color: verbose ? 'info.main' : 'text.secondary' }} />
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>Debug Mode</Typography>
                  </Box>
                  <Switch
                    checked={verbose}
                    onChange={(e) => { e.stopPropagation(); setVerbose(e.target.checked); }}
                    color="info"
                    size="small"
                  />
                </Box>
              </Box>
            </Collapse>
          </Paper>

          {/* Generated Query Section */}
          {(queryResult || editableQuery) && (
            <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${queryGenerated ? theme.palette.info.main : theme.palette.divider}`, overflow: 'hidden' }}>
              <SectionHeader 
                title={queryGenerated ? "Generated Query (Editable)" : "Generated Query"} 
                icon={<CodeIcon fontSize="small" color="info" />} 
                section="query" 
                badge={queryGenerated ? "Pending" : null}
              />
              <Collapse in={expandedSections.query}>
                <Box sx={{ p: 2, pt: 0 }}>
                  {isEditingQuery || queryGenerated ? (
                    // Editable mode
                    <>
                      <TextField
                        fullWidth
                        multiline
                        minRows={4}
                        maxRows={12}
                        value={editableQuery}
                        onChange={(e) => setEditableQuery(e.target.value)}
                        variant="outlined"
                        placeholder="Edit the Cypher query..."
                        sx={{
                          mb: 1.5,
                          '& .MuiOutlinedInput-root': {
                            fontFamily: 'monospace',
                            fontSize: '0.85rem',
                            backgroundColor: alpha(theme.palette.background.default, 0.5),
                          },
                        }}
                      />
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                        {queryGenerated && (
                          <Button
                            size="small"
                            variant="contained"
                            startIcon={isLoading ? <CircularProgress size={16} /> : <PlayArrowIcon />}
                            onClick={handleRunEditedQuery}
                            disabled={isLoading || !editableQuery.trim()}
                            sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                          >
                            Run Query
                          </Button>
                        )}
                        {editableQuery !== originalQuery && (
                          <Button
                            size="small"
                            variant="outlined"
                            startIcon={<RestoreIcon />}
                            onClick={() => setEditableQuery(originalQuery)}
                            sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                          >
                            Reset
                          </Button>
                        )}
                        <Button
                          size="small"
                          startIcon={<ContentCopyIcon />}
                          onClick={() => handleCopy(editableQuery, 'query')}
                          sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                        >
                          {copiedIndex === 'query' ? 'Copied!' : 'Copy'}
                        </Button>
                        <Button
                          size="small"
                          startIcon={<LaunchIcon />}
                          onClick={() => {
                            handleCopy(editableQuery, 'query');
                            window.open(neo4jBrowserUrl, '_blank');
                          }}
                          sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                        >
                          Neo4j Browser
                        </Button>
                      </Box>
                      {pendingQuestion && (
                        <Typography variant="caption" color="text.secondary" sx={{ mt: 1.5, display: 'block' }}>
                          For question: "{pendingQuestion}"
                        </Typography>
                      )}
                    </>
                  ) : (
                    // Read-only mode
                    <>
                      <Box sx={{ borderRadius: '12px', overflow: 'hidden' }}>
                        <SyntaxHighlighter language="cypher" style={syntaxTheme} customStyle={{ margin: 0, padding: '12px', fontSize: '0.8rem', borderRadius: '12px' }}>
                          {queryResult}
                        </SyntaxHighlighter>
                      </Box>
                      <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                        <Button
                          size="small"
                          startIcon={<ContentCopyIcon />}
                          onClick={() => handleCopy(queryResult, 'query')}
                          sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                        >
                          {copiedIndex === 'query' ? 'Copied!' : 'Copy'}
                        </Button>
                        <Button
                          size="small"
                          startIcon={<LaunchIcon />}
                          onClick={() => {
                            handleCopy(queryResult, 'query');
                            window.open(neo4jBrowserUrl, '_blank');
                          }}
                          sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                        >
                          Neo4j Browser
                        </Button>
                      </Box>
                    </>
                  )}
                </Box>
              </Collapse>
            </Paper>
          )}

          {/* Node Visualization Section */}
          {executionResult?.result && executionResult.result.length > 0 && (
            <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${theme.palette.divider}`, overflow: 'hidden' }}>
              <SectionHeader 
                title="Node Information" 
                icon={<BubbleChartIcon fontSize="small" color="success" />} 
                section="visualization"
                badge={executionResult.result.length}
              />
              <Collapse in={expandedSections.visualization}>
                <Box sx={{ p: 2, pt: 0 }}>
                  <NodeVisualization executionResult={executionResult} />
                </Box>
              </Collapse>
            </Paper>
          )}

          {/* Raw Results Section */}
          {executionResult?.result && (
            <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${theme.palette.divider}`, overflow: 'hidden' }}>
              <SectionHeader 
                title="Structured Query Results" 
                icon={<DataObjectIcon fontSize="small" color="warning" />} 
                section="results"
                badge={executionResult.result.length}
              />
              <Collapse in={expandedSections.results}>
                <Box sx={{ p: 2, pt: 0, maxHeight: 300, overflow: 'auto' }}>
                  <SyntaxHighlighter language="json" style={syntaxTheme} customStyle={{ margin: 0, padding: '12px', fontSize: '0.75rem', borderRadius: '12px' }}>
                    {JSON.stringify(executionResult.result, null, 2)}
                  </SyntaxHighlighter>
                </Box>
              </Collapse>
            </Paper>
          )}

          {/* Debug Logs Section */}
          {realtimeLogs && (
            <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${theme.palette.divider}`, overflow: 'hidden' }}>
              <SectionHeader title="Debug Logs" icon={<TerminalIcon fontSize="small" />} section="logs" />
              <Collapse in={expandedSections.logs}>
                <Box sx={{ p: 2, pt: 0, maxHeight: 200, overflow: 'auto', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                  {realtimeLogs}
                </Box>
              </Collapse>
            </Paper>
          )}

          {/* Recent Queries Section */}
          {latestQueries && latestQueries.length > 0 && (
            <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${theme.palette.divider}`, overflow: 'hidden' }}>
              <SectionHeader 
                title="Recent Queries" 
                icon={<HistoryIcon fontSize="small" />} 
                section="history"
                badge={latestQueries.length}
              />
              <Collapse in={expandedSections.history}>
                <Box sx={{ maxHeight: 300, overflow: 'auto' }}>
                  <LatestQueries queries={latestQueries} onSelectQuery={handleSelectQuery} />
                </Box>
              </Collapse>
            </Paper>
          )}
        </Box>
      </Box>

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
