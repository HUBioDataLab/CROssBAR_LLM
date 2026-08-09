import React, { useState, useRef, useEffect, useCallback } from 'react';
import { flushSync } from 'react-dom';
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
  Switch,
  FormControlLabel,
  Alert,
  Snackbar,
  Zoom,
  List,
  ListItem,
  ListItemText,
  Dialog,
  DialogContent,
  DialogTitle,
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
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import SearchIcon from '@mui/icons-material/Search';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import LaunchIcon from '@mui/icons-material/Launch';
import CloseIcon from '@mui/icons-material/Close';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import NodeVisualization from './NodeVisualization';
import {
  getModels,
  dbSearch,
  vectorSearch,
  vectorUploadSearch,
  resumeSession,
} from '../services/api';
import axios from 'axios';
import Fuse from 'fuse.js';
import { loadSuggestions } from '../utils/loadSuggestions';
import ReactMarkdown from 'react-markdown';

const DRAWER_WIDTH = 420;

function ChatLayout({
  // State props
  provider,
  setProvider,
  llmType,
  setLlmType,
  sessionId,
  sessionError,
  conversationHistory,
  addConversationTurn,
  startNewConversation,
  question,
  setQuestion,
  queryResult,
  setQueryResult,
  executionResult,
  setExecutionResult,
  pendingFollowUp,
  setPendingFollowUp,
  // Left sidebar visibility (only on query tab)
  drawerVisible,
  onToggleDrawerVisibility,
}) {
  const theme = useTheme();
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);

  // Local state
  const [isLoading, setIsLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState('');
  const [pendingUserQuestion, setPendingUserQuestion] = useState(''); // Question being processed
  const [error, setError] = useState(null);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [topK, setTopK] = useState(10);
  const [reasoningEnabled, setReasoningEnabled] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState('medium');
  const [copySnackbar, setCopySnackbar] = useState(false);

  // Query editing state
  const [editableQuery, setEditableQuery] = useState('');
  const [originalQuery, setOriginalQuery] = useState('');
  const [pendingQuestion, setPendingQuestion] = useState(''); // Question waiting for query to be run
  const [queryGenerated, setQueryGenerated] = useState(false); // True when query is generated but not run
  const [isEditingQuery, setIsEditingQuery] = useState(false);

  // Historical query viewing state
  const [viewingHistoryIndex, setViewingHistoryIndex] = useState(null);

  // Tutorial video modal — auto-open on first visit
  const [tutorialOpen, setTutorialOpen] = useState(() => {
    try {
      return !localStorage.getItem('crossbar_tutorial_seen');
    } catch {
      return true;
    }
  });

  const handleCloseTutorial = () => {
    setTutorialOpen(false);
    try { localStorage.setItem('crossbar_tutorial_seen', '1'); } catch {}
  };

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

  // Models state (provider -> { models, free_models })
  const [modelChoices, setModelChoices] = useState({});
  const [supportedModels, setSupportedModels] = useState([]);
  const [modelsLoaded, setModelsLoaded] = useState(false);

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

  // Semantic search state
  const [semanticSearchEnabled, setSemanticSearchEnabled] = useState(false);
  const [vectorCategory, setVectorCategory] = useState('');
  const [embeddingType, setEmbeddingType] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

  // Last agent run metadata (search mode + usage summary shown after completion)
  const [lastSearchMode, setLastSearchMode] = useState('db_search');
  const [lastUsage, setLastUsage] = useState(null);

  // Node label to vector index names mapping
  const nodeLabelToVectorIndexNames = {
    "SmallMolecule": "Selformer",
    "Drug": "Selformer",
    "Compound": "Selformer",
    "Protein": ["Prott5", "Esm2"],
    "GOTerm": "Anc2vec",
    "CellularComponent": "Anc2vec",
    "BiologicalProcess": "Anc2vec",
    "MolecularFunction": "Anc2vec",
    "Phenotype": "Cada",
    "Disease": "Doc2vec",
    "ProteinDomain": "Dom2vec",
    "EcNumber": "Rxnfp",
    "Pathway": "Biokeen",
  };

  // Example queries (regular)
  const exampleQueries = [
    "Which Gene is related to psoriasis <Disease> ?",
    "For proteins associated with amyotrophic lateral sclerosis <Disease>, which orthologous proteins in Mus musculus (Mouse) <Organism Taxon> have experimentally validated functional annotations, and which conserved biological processes do they support?",
    "What nodes are on the shortest path that connect MDM2 <Gene> with the drug Sorafenib <Drug> ?",
    "Which drugs target proteins associated with Alzheimer disease <Disease> ?",
    "Which pathways are associated with both diabetes mellitus <Disease> and T-cell non-Hodgkin lymphoma <Disease> ? Return only signaling pathways.",
    "What are the common side effects of drugs targeting the protein of EGFR <Gene> ?",
  ];

  // Vector search example queries
  const vectorExampleQueries = [
    {
      question: "Give me distinct Biological Processes that are similar to cell growth <BiologicalProcess> and drugs targeting proteins involved in these similar processes. Return 10 similar Biological Processes.",
      vectorCategory: "BiologicalProcess",
      embeddingType: "Anc2vec"
    },
    {
      question: "Find a protein domain that is similar to Prot_kinase_dom <ProteinDomain>. Then, find proteins that possess this similar domain.",
      vectorCategory: "ProteinDomain",
      embeddingType: "Dom2vec"
    },
    {
      question: "Give me the names of top 10 Proteins that are targeted by Small Molecules similar to the given embedding.",
      vectorCategory: "SmallMolecule",
      embeddingType: "Selformer",
      vectorFilePath: "small_molecule_embedding.npy"
    },
    {
      question: "What are the most similar proteins to the given protein embedding?",
      vectorCategory: "Protein",
      embeddingType: "Esm2",
      vectorFilePath: "protein_embedding.npy"
    },
    {
      question: "Find diseases related to proteins with similar structure to this embedding.",
      vectorCategory: "Protein",
      embeddingType: "Esm2",
      vectorFilePath: "protein_embedding.npy"
    }
  ];

  const neo4jBrowserUrl = 'https://neo4j.crossbarv2.hubiodatalab.com/browser/?preselectAuthMethod=[NO_AUTH]&dbms=bolt://neo4j.crossbarv2.hubiodatalab.com';

  // Clear error when user starts a new conversation (sessionId changes)
  useEffect(() => {
    setError(null);
  }, [sessionId]);

  // Fetch available models + supported search models from the backend on mount
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const data = await getModels();
        setModelChoices(data?.providers || {});
        setSupportedModels(data?.supported_models_for_search || []);
        setModelsLoaded(true);
        const { default_provider, default_model } = data || {};
        if (default_provider && default_model && !provider && !llmType) {
          const providerModels = data.providers?.[default_provider]?.models || [];
          if (providerModels.includes(default_model)) {
            setProvider(default_provider);
            setLlmType(default_model);
          }
        }
      } catch (error) {
        console.error('Error fetching models:', error);
        setModelChoices({});
        setSupportedModels([]);
        setModelsLoaded(true);
      }
    };
    fetchModels();
  }, []);

  // Scroll to bottom when messages update
  useEffect(() => {
    scrollToBottom();
  }, [conversationHistory, isLoading]);


  // Sync editable query with queryResult 
  useEffect(() => {
    if (queryResult && !queryGenerated && !isEditingQuery) {
      setEditableQuery(queryResult);
      setOriginalQuery(queryResult);
    }
  }, [queryResult, queryGenerated, isEditingQuery]);

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
    const displaySuggestion = `${displayTerm} <${suggestion.type}>`;
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

  // Handle viewing historical query details in right panel
  const handleViewDetails = (turn, index) => {
    // Update right panel with historical turn data
    setQueryResult(turn.cypherQuery || '');
    setExecutionResult(turn.result ? { result: turn.result } : null);
    setViewingHistoryIndex(index);

    // Reset editing state
    setEditableQuery(turn.cypherQuery || '');
    setOriginalQuery(turn.cypherQuery || '');
    setQueryGenerated(false);
    setIsEditingQuery(false);

    // Open right panel if closed
    if (!rightPanelOpen) {
      setRightPanelOpen(true);
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

  // Check if settings are valid (API keys are managed server-side now)
  const isSettingsValid = useCallback(() => {
    return !!(provider && llmType);
  }, [provider, llmType]);

  // Check if semantic search settings are valid (only when enabled)
  const isSemanticSearchValid = useCallback(() => {
    if (!semanticSearchEnabled) return true;
    return vectorCategory && embeddingType;
  }, [semanticSearchEnabled, vectorCategory, embeddingType]);

  // Check if query result has valid data (not a "no result" message)
  const hasValidResults = useCallback((result) => {
    if (!result) return false;
    if (!Array.isArray(result)) return false;
    if (result.length === 0) return false;
    // Check if it's a "no result" string wrapped in array
    if (result.length === 1 && typeof result[0] === 'string' &&
        result[0].toLowerCase().includes('did not return any result')) {
      return false;
    }
    return true;
  }, []);

  // ---- Shared helpers for the agentic backend ----
  const isCancelled = (err) => axios.isCancel?.(err) || err?.name === 'CanceledError' || err?.name === 'AbortError';

  const getErrorMessage = (err) => {
    const detail = err?.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) return detail.map(e => e?.msg || JSON.stringify(e)).join(', ');
      if (typeof detail === 'object') return detail.msg || detail.error || JSON.stringify(detail);
    }
    return err?.message || 'An error occurred';
  };

  // Build the common model-config + search fields shared by every request type.
  const buildRequestBody = useCallback((overrides) => ({
    provider,
    model: llmType,
    top_k: topK,
    reasoning_enabled: reasoningEnabled,
    reasoning_effort: reasoningEnabled ? reasoningEffort : null,
    ...overrides,
  }), [provider, llmType, topK, reasoningEnabled, reasoningEffort]);

  // Run the right query endpoint for the current mode + optional uploaded vector file.
  const runQuery = useCallback((sessionIdVal, baseBody, config) => {
    const searchMode = semanticSearchEnabled ? 'vector_search' : 'db_search';
    const body = { ...baseBody, search_mode: searchMode };
    if (semanticSearchEnabled) {
      const vectorBody = { ...body, vector_category: vectorCategory, embedding_type: embeddingType };
      if (selectedFile) return vectorUploadSearch(sessionIdVal, vectorBody, selectedFile, config);
      return vectorSearch(sessionIdVal, vectorBody, config);
    }
    return dbSearch(sessionIdVal, body, config);
  }, [semanticSearchEnabled, vectorCategory, embeddingType, selectedFile]);

  // Apply a completed/failed ChatResponse to local state + conversation history.
  const applyChatResponse = useCallback((data, userQuestion, searchMode) => {
    const status = data?.status;
    const cypher = data?.generated_cypher || '';
    const finalAnswer = data?.final_answer || '';
    const result = data?.execution_result || [];
    const followUps = data?.follow_up_questions || [];
    const usage = data?.usage || null;
    const isSemantic = searchMode === 'vector_search';

    setQueryResult(cypher);
    setEditableQuery(cypher);
    setOriginalQuery(cypher);
    setLastUsage(usage);

    setExecutionResult({ result, response: finalAnswer, followUpQuestions: followUps });

    addConversationTurn({
      question: userQuestion,
      cypherQuery: cypher,
      response: finalAnswer,
      result,
      followUpQuestions: followUps,
      isSemanticSearch: isSemantic,
      vectorConfig: isSemantic ? { vectorCategory, embeddingType } : null,
      usage,
      status,
    });

    if (status === 'failed') {
      setError('The agent could not complete this query. Try rephrasing it or selecting a different model.');
    }

    if (hasValidResults(result)) {
      setExpandedSections(prev => ({ ...prev, visualization: true }));
    }
  }, [vectorCategory, embeddingType, addConversationTurn, hasValidResults, setExecutionResult, setQueryResult]);

  // Render a compact token/usage summary from the agent's usage dict.
  const renderUsageChips = (usage) => {
    if (!usage) return null;
    const totals = usage?.aggregated_usage?.totals || {};
    const perNode = usage?.per_node_usage || {};
    const nodeCount = Object.keys(perNode).length;
    const callCount = Object.values(perNode).reduce((sum, r) => sum + (r?.call_count || 0), 0);
    const modelsByNode = usage?.aggregated_usage?.models_by_node || {};
    const models = Array.from(new Set(Object.values(modelsByNode).flat())).filter(Boolean);

    const fmt = (n) => (typeof n === 'number' ? n.toLocaleString() : '0');
    const chips = [
      { label: 'Total tokens', value: fmt(totals.total_tokens) },
      { label: 'Input', value: fmt(totals.input_tokens) },
      { label: 'Output', value: fmt(totals.output_tokens) },
      { label: 'LLM calls', value: fmt(callCount) },
      { label: 'Agent steps', value: fmt(nodeCount) },
    ];
    if (totals.reasoning) chips.push({ label: 'Reasoning', value: fmt(totals.reasoning) });
    if (models.length) chips.push({ label: 'Models', value: models.join(', ') });

    return chips.map((c) => (
      <Box key={c.label} sx={{
        display: 'flex', flexDirection: 'column', minWidth: 90,
        p: 1, borderRadius: '8px',
        backgroundColor: alpha(theme.palette.primary.main, 0.05),
        border: `1px solid ${alpha(theme.palette.primary.main, 0.15)}`,
      }}>
        <Typography variant="caption" color="text.secondary">{c.label}</Typography>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>{c.value}</Typography>
      </Box>
    ));
  };

  // Generate query only (without running) — execution_mode: "generate" returns a
  // PendingResumeResponse with the generated Cypher, awaiting human review.
  const handleGenerateOnly = async (e) => {
    e?.preventDefault();
    if (!question.trim() || isLoading) return;
    if (!sessionId) {
      setError('Chat session is not ready yet. Please wait a moment and try again.');
      return;
    }

    if (!isSettingsValid()) {
      setExpandedSections(prev => ({ ...prev, settings: true }));
      setError('Please configure model settings first');
      return;
    }

    if (!isSemanticSearchValid()) {
      setExpandedSections(prev => ({ ...prev, vectorConfig: true }));
      setError('Please configure vector search settings (category and embedding type)');
      return;
    }

    // Collapse settings and examples panels when submitting a question
    flushSync(() => {
      setExpandedSections(prev => ({ ...prev, settings: false, examples: false }));
    });

    const userQuestion = question.trim();
    const searchMode = semanticSearchEnabled ? 'vector_search' : 'db_search';
    setPendingQuestion(userQuestion);
    setQuestion('');
    setPendingUserQuestion(userQuestion); // Show user's question immediately
    setError(null);
    setIsLoading(true);
    setCurrentStep('Generating Cypher query...');
    setLastSearchMode(searchMode);
    setLastUsage(null);
    setQueryResult('');
    setEditableQuery('');
    setOriginalQuery('');
    setQueryGenerated(false);
    setViewingHistoryIndex(null);

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      const body = buildRequestBody({ question: userQuestion, execution_mode: 'generate' });
      const data = await runQuery(sessionId, body, { signal });

      const cypherQuery = data.generated_cypher || '';
      setQueryResult(cypherQuery);
      setEditableQuery(cypherQuery);
      setOriginalQuery(cypherQuery);
      setQueryGenerated(true);
      setIsEditingQuery(false);

      // Expand the query section to show the generated query
      setExpandedSections(prev => ({ ...prev, query: true }));
    } catch (err) {
      if (isCancelled(err)) {
        // request cancelled by the user
      } else {
        console.error('Error:', err);
        setError(getErrorMessage(err));
        setPendingQuestion('');
        setPendingUserQuestion('');
      }
    } finally {
      setIsLoading(false);
      setCurrentStep('');
      abortControllerRef.current = null;
    }
  };

  // Run the generated/edited query via the resume endpoint (human-in-the-loop).
  // action = "approve" if the user left the Cypher unchanged, "edit" otherwise.
  const handleRunEditedQuery = async () => {
    if (!editableQuery.trim() || isLoading) return;
    if (!pendingQuestion) {
      setError('No question associated with this query');
      return;
    }
    if (!sessionId) {
      setError('Chat session is not ready yet. Please wait a moment and try again.');
      return;
    }

    // Collapse example queries immediately when running (use flushSync to force immediate update)
    flushSync(() => {
      setExpandedSections(prev => ({ ...prev, examples: false }));
    });

    setError(null);
    setViewingHistoryIndex(null); // Reset history viewing state
    setPendingUserQuestion(pendingQuestion); // Show user's question immediately
    setIsLoading(true);
    setCurrentStep('Executing query...');
    setLastUsage(null);

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    const edited = editableQuery.trim();
    const action = originalQuery && edited === originalQuery.trim() ? 'approve' : 'edit';

    try {
      const body = buildRequestBody({
        search_mode: lastSearchMode,
        execution_mode: 'resume',
        action,
        edited_cypher: edited,
      });
      const data = await resumeSession(sessionId, body, { signal });

      setQueryGenerated(false);
      setPendingQuestion('');
      setIsEditingQuery(false);
      applyChatResponse(data, pendingQuestion, lastSearchMode);
    } catch (err) {
      if (isCancelled(err)) {
        // request cancelled by the user
      } else {
        console.error('Error:', err);
        setError(getErrorMessage(err));
        setPendingUserQuestion('');
      }
    } finally {
      setIsLoading(false);
      setCurrentStep('');
      setPendingUserQuestion('');
      abortControllerRef.current = null;
    }
  };

  // Generate and run query in one shot — execution_mode: "generate_and_run".
  // The agent runs to completion synchronously and returns a ChatResponse.
  const handleSubmit = async (e) => {
    e?.preventDefault();
    if (!question.trim() || isLoading) return;
    if (!sessionId) {
      setError('Chat session is not ready yet. Please wait a moment and try again.');
      return;
    }

    if (!isSettingsValid()) {
      setExpandedSections(prev => ({ ...prev, settings: true }));
      setError('Please configure model settings first');
      return;
    }

    if (!isSemanticSearchValid()) {
      setExpandedSections(prev => ({ ...prev, vectorConfig: true }));
      setError('Please configure vector search settings (category and embedding type)');
      return;
    }

    // Collapse settings and examples panels when submitting a question
    flushSync(() => {
      setExpandedSections(prev => ({ ...prev, settings: false, examples: false }));
    });

    const userQuestion = question.trim();
    const searchMode = semanticSearchEnabled ? 'vector_search' : 'db_search';
    setQuestion('');
    setPendingUserQuestion(userQuestion); // Show user's question immediately
    setError(null);
    setIsLoading(true);
    setCurrentStep('Running agent...');

    // Reset query editing state and history viewing state
    setQueryGenerated(false);
    setViewingHistoryIndex(null);
    setPendingQuestion('');
    setLastSearchMode(searchMode);
    setLastUsage(null);
    setQueryResult('');
    setEditableQuery('');
    setOriginalQuery('');

    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      const body = buildRequestBody({ question: userQuestion, execution_mode: 'generate_and_run' });
      const data = await runQuery(sessionId, body, { signal });
      applyChatResponse(data, userQuestion, searchMode);
    } catch (err) {
      if (isCancelled(err)) {
        // request cancelled by the user
      } else {
        console.error('Error:', err);
        setError(getErrorMessage(err));
        setPendingUserQuestion('');
      }
    } finally {
      setIsLoading(false);
      setCurrentStep('');
      setPendingUserQuestion('');
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
    // Handle both regular string examples and vector examples (objects)
    if (typeof example === 'object' && example.question) {
      setQuestion(example.question);
      if (example.vectorCategory) {
        setSemanticSearchEnabled(true);
        setVectorCategory(example.vectorCategory);
        setEmbeddingType(example.embeddingType || '');
        setExpandedSections(prev => ({ ...prev, vectorConfig: true }));

        // Load vector file from public folder if specified; otherwise clear any staged file
        if (example.vectorFilePath) {
          loadVectorFileFromPath(example.vectorFilePath);
        } else {
          setSelectedFile(null);
        }
      } else {
        // Non-vector example: clear vector-related state
        setSelectedFile(null);
      }
    } else {
      setQuestion(example);
      // Regular (non-vector) example: clear staged vector file
      setSelectedFile(null);
    }
    inputRef.current?.focus();
  };

  // Load a vector file from the public folder and stage it as a File so the
  // upload-query endpoint can send it (file-based vector search).
  const loadVectorFileFromPath = async (filePath) => {
    try {
      const base = (process.env.PUBLIC_URL || process.env.REACT_APP_CROSSBAR_LLM_ROOT_PATH || '').replace(/\/$/, '');
      const url = base ? `${base}/${filePath}` : `/${filePath}`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`File not found: ${filePath} (HTTP ${response.status})`);
      }
      const blob = await response.blob();
      const fileName = filePath.split('/').pop();
      setSelectedFile(new File([blob], fileName, { type: blob.type || 'application/octet-stream' }));
    } catch (error) {
      console.error('Error loading vector file:', error);
      setError(`Failed to load vector file: ${filePath}`);
      setSelectedFile(null);
    }
  };

  // Handle vector file selection — stage the file; it is sent to the backend at
  // query time via the upload-query endpoint (no separate upload step).
  const handleVectorFileChange = (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (ext !== 'npy' && ext !== 'csv') {
      setError('Vector file must be a .npy or .csv file.');
      event.target.value = '';
      return;
    }
    setSelectedFile(file);
    setError(null);
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

      {/* Tutorial Video Section */}
      <Box sx={{ width: '100%', maxWidth: 700, mt: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary', display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <PlayCircleOutlineIcon sx={{ fontSize: 18 }} />
            How to use CROssBAR-LLM
          </Typography>
          <Button
            size="small"
            variant="outlined"
            startIcon={<PlayCircleOutlineIcon />}
            onClick={() => setTutorialOpen(true)}
            sx={{
              borderRadius: '8px',
              textTransform: 'none',
              fontSize: '0.75rem',
              py: 0.4,
            }}
          >
            Open in full view
          </Button>
        </Box>
        <Box
          sx={{
            borderRadius: '12px',
            overflow: 'hidden',
            border: `1px solid ${alpha(theme.palette.divider, 0.6)}`,
            boxShadow: `0 4px 20px ${alpha(theme.palette.common.black, 0.08)}`,
            backgroundColor: '#000',
            aspectRatio: '16/9',
            maxHeight: 340,
          }}
        >
          <iframe
            title="CROssBAR-LLM tutorial"
            src="https://www.youtube.com/embed/RtR1x_Lfx-Q"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            style={{
              width: '100%',
              height: '100%',
              border: 'none',
            }}
          />
        </Box>
      </Box>

      {/* First-visit Tutorial Modal */}
      <Dialog
        open={tutorialOpen}
        onClose={handleCloseTutorial}
        maxWidth="md"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: '16px',
            overflow: 'hidden',
          },
        }}
      >
        <DialogTitle
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            pb: 1,
            pt: 2,
            px: 3,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <PlayCircleOutlineIcon color="primary" />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Welcome to CROssBAR-LLM
            </Typography>
          </Box>
          <IconButton onClick={handleCloseTutorial} size="small" edge="end">
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={{ p: 0 }}>
          <Box sx={{ px: 3, pb: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              Watch this short tutorial to get started with the biomedical knowledge graph chat interface.
            </Typography>
          </Box>
          <Box
            sx={{
              backgroundColor: '#000',
              lineHeight: 0,
              aspectRatio: '16/9',
              maxHeight: '60vh',
            }}
          >
            <iframe
              title="CROssBAR-LLM tutorial (full view)"
              src="https://www.youtube.com/embed/RtR1x_Lfx-Q?autoplay=1"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              style={{
                width: '100%',
                height: '100%',
                border: 'none',
              }}
            />
          </Box>
          <Box sx={{ px: 3, py: 2, display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              variant="contained"
              onClick={handleCloseTutorial}
              sx={{ borderRadius: '8px', textTransform: 'none', fontWeight: 600 }}
            >
              Get started
            </Button>
          </Box>
        </DialogContent>
      </Dialog>
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
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                You
              </Typography>
              {turn.isSemanticSearch && (
                <Chip
                  size="small"
                  label={`Vector: ${turn.vectorConfig?.vectorCategory || 'N/A'}`}
                  color="secondary"
                  variant="outlined"
                  icon={<SearchIcon sx={{ fontSize: '12px !important' }} />}
                  sx={{ height: '20px', fontSize: '0.65rem' }}
                />
              )}
            </Box>
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
              {turn.cypherQuery && (
                <Chip
                  icon={<CodeIcon sx={{ fontSize: 14 }} />}
                  label={viewingHistoryIndex === index ? "Viewing" : "Query Details"}
                  size="small"
                  onClick={() => handleViewDetails(turn, index)}
                  variant={viewingHistoryIndex === index ? "filled" : "outlined"}
                  color={viewingHistoryIndex === index ? "primary" : "default"}
                  sx={{
                    height: 22,
                    fontSize: '0.7rem',
                    fontWeight: 500,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    '& .MuiChip-icon': {
                      marginLeft: '6px',
                    },
                    '&:hover': {
                      backgroundColor: viewingHistoryIndex === index
                        ? theme.palette.primary.main
                        : alpha(theme.palette.primary.main, 0.1),
                      borderColor: theme.palette.primary.main,
                      color: viewingHistoryIndex === index
                        ? 'white'
                        : theme.palette.primary.main,
                    },
                  }}
                />
              )}
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
              <Box
                sx={{
                  '& p': {
                    margin: 0,
                    marginBottom: 1.5,
                    lineHeight: 1.7,
                    '&:last-child': { marginBottom: 0 }
                  },
                  '& strong': { fontWeight: 600 },
                  '& em': { fontStyle: 'italic' },
                  '& ul, & ol': {
                    margin: 0,
                    marginBottom: 1.5,
                    paddingLeft: 2.5,
                    '&:last-child': { marginBottom: 0 }
                  },
                  '& li': {
                    marginBottom: 0.5,
                    lineHeight: 1.6,
                  },
                  '& code': {
                    backgroundColor: alpha(theme.palette.primary.main, 0.1),
                    padding: '2px 6px',
                    borderRadius: '4px',
                    fontSize: '0.875em',
                    fontFamily: 'monospace',
                  },
                  '& pre': {
                    backgroundColor: theme.palette.mode === 'dark' ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.05)',
                    padding: 2,
                    borderRadius: '8px',
                    overflow: 'auto',
                    marginBottom: 1.5,
                    '& code': {
                      backgroundColor: 'transparent',
                      padding: 0,
                    },
                    '&:last-child': { marginBottom: 0 }
                  },
                  '& h1, & h2, & h3, & h4, & h5, & h6': {
                    marginTop: 2,
                    marginBottom: 1,
                    fontWeight: 600,
                    '&:first-of-type': { marginTop: 0 }
                  },
                  '& a': {
                    color: theme.palette.primary.main,
                    textDecoration: 'none',
                    '&:hover': { textDecoration: 'underline' }
                  },
                  '& blockquote': {
                    borderLeft: `3px solid ${theme.palette.primary.main}`,
                    margin: 0,
                    marginBottom: 1.5,
                    paddingLeft: 2,
                    color: 'text.secondary',
                    '&:last-child': { marginBottom: 0 }
                  },
                  '& hr': {
                    border: 'none',
                    borderTop: `1px solid ${theme.palette.divider}`,
                    margin: '16px 0',
                  },
                  '& table': {
                    borderCollapse: 'collapse',
                    width: '100%',
                    marginBottom: 1.5,
                    '&:last-child': { marginBottom: 0 }
                  },
                  '& th, & td': {
                    border: `1px solid ${theme.palette.divider}`,
                    padding: '8px 12px',
                    textAlign: 'left',
                  },
                  '& th': {
                    backgroundColor: alpha(theme.palette.primary.main, 0.05),
                    fontWeight: 600,
                  },
                }}
              >
                <ReactMarkdown>{turn.response}</ReactMarkdown>
              </Box>
            </Paper>

            {/* Follow-up Questions - only for latest */}
            {isLatest && turn.followUpQuestions && turn.followUpQuestions.length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1, fontWeight: 600 }}>
                  <LightbulbOutlinedIcon sx={{ fontSize: 14 }} />
                  Suggested follow-ups:
                  {turn.isSemanticSearch && (
                    <Chip
                      label="Vector Search"
                      size="small"
                      color="secondary"
                      variant="outlined"
                      sx={{ ml: 1, height: '18px', fontSize: '0.65rem' }}
                    />
                  )}
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  {turn.followUpQuestions.map((q, qIdx) => (
                    <Chip
                      key={qIdx}
                      label={q}
                      size="small"
                      onClick={() => {
                        // Restore semantic search settings if the turn was from semantic search
                        if (turn.isSemanticSearch && turn.vectorConfig) {
                          setSemanticSearchEnabled(true);
                          setVectorCategory(turn.vectorConfig.vectorCategory || '');
                          setEmbeddingType(turn.vectorConfig.embeddingType || '');
                        }
                        handleFollowUpClick(q);
                      }}
                      icon={turn.isSemanticSearch ? <SearchIcon sx={{ fontSize: '14px !important' }} /> : undefined}
                      sx={{
                        cursor: 'pointer',
                        height: 'auto',
                        py: 0.5,
                        '& .MuiChip-label': { whiteSpace: 'normal' },
                        backgroundColor: alpha(turn.isSemanticSearch ? theme.palette.secondary.main : theme.palette.primary.main, 0.1),
                        '&:hover': { backgroundColor: alpha(turn.isSemanticSearch ? theme.palette.secondary.main : theme.palette.primary.main, 0.2) },
                        border: `1px solid ${alpha(turn.isSemanticSearch ? theme.palette.secondary.main : theme.palette.primary.main, 0.3)}`,
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

  // Loading indicator in chat - shows user question and loading response
  const renderLoading = () => (
    <Box sx={{ mb: 4 }}>
      {/* User Message */}
      {pendingUserQuestion && (
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
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                You
              </Typography>
              {semanticSearchEnabled && (
                <Chip
                  size="small"
                  label={`Vector: ${vectorCategory || 'N/A'}`}
                  color="secondary"
                  variant="outlined"
                  icon={<SearchIcon sx={{ fontSize: '12px !important' }} />}
                  sx={{ height: '20px', fontSize: '0.65rem' }}
                />
              )}
            </Box>
            <Typography variant="body1">{pendingUserQuestion}</Typography>
          </Box>
        </Box>
      )}

      {/* Assistant Loading */}
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
        <Box sx={{ flex: 1, pt: 0.5 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: 'text.secondary' }}>
            CROssBAR
          </Typography>
          <Paper
            elevation={0}
            sx={{
              p: 2.5,
              borderRadius: '16px',
              backgroundColor: alpha(theme.palette.background.default, 0.6),
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            {/* Step Progress Indicator */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Box sx={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CircularProgress
                  size={32}
                  thickness={3}
                  sx={{
                    color: currentStep.includes('Generating')
                      ? theme.palette.info.main
                      : theme.palette.success.main
                  }}
                />
                <Box sx={{
                  position: 'absolute',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}>
                  {currentStep.includes('Generating') ? (
                    <CodeIcon sx={{ fontSize: 14, color: theme.palette.info.main }} />
                  ) : (
                    <PlayArrowIcon sx={{ fontSize: 14, color: theme.palette.success.main }} />
                  )}
                </Box>
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography variant="body1" sx={{ fontWeight: 600, color: 'text.primary' }}>
                  {currentStep}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {currentStep.includes('Generating')
                    ? 'Translating your question to a database query...'
                    : 'The agent is running the query and preparing your answer...'}
                </Typography>
              </Box>
            </Box>
          </Paper>
        </Box>
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
            {onToggleDrawerVisibility != null && (
              <Tooltip title={drawerVisible ? "Hide sidebar" : "Show sidebar"}>
                <IconButton
                  onClick={onToggleDrawerVisibility}
                  size="small"
                  sx={{
                    backgroundColor: theme.palette.mode === 'dark'
                      ? 'rgba(255, 255, 255, 0.05)'
                      : 'rgba(0, 113, 227, 0.08)',
                    border: `1px solid ${theme.palette.mode === 'dark'
                      ? 'rgba(255, 255, 255, 0.1)'
                      : 'rgba(0, 113, 227, 0.15)'}`,
                    '&:hover': {
                      backgroundColor: theme.palette.mode === 'dark'
                        ? 'rgba(255, 255, 255, 0.1)'
                        : 'rgba(0, 113, 227, 0.12)',
                    },
                    color: theme.palette.mode === 'dark'
                      ? 'inherit'
                      : 'rgba(0, 113, 227, 0.8)',
                  }}
                >
                  {drawerVisible ? <ChevronLeftIcon /> : <ChevronRightIcon />}
                </IconButton>
              </Tooltip>
            )}
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
          {queryGenerated && pendingQuestion && !isLoading && (
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

          {/* Semantic Search Toggle */}
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Tooltip title="Use this feature to search the knowledge graph for similar proteins, diseases, pathways, phenotypes, etc. related to your query. For instance, given the query &quot;Find a protein domain similar to interpro:IPR000719, then find proteins that possess this domain,&quot; the system identifies similar domains via vector embeddings and retrieves associated proteins by traversing the knowledge graph.">
                <FormControlLabel
                  control={
                    <Switch
                      checked={semanticSearchEnabled}
                      onChange={(e) => {
                        setSemanticSearchEnabled(e.target.checked);
                        if (e.target.checked) {
                          setExpandedSections(prev => ({ ...prev, vectorConfig: true }));
                        } else {
                          // Clear vector config when disabled
                          setVectorCategory('');
                          setEmbeddingType('');
                          setSelectedFile(null);
                        }
                      }}
                      size="small"
                      color="secondary"
                    />
                  }
                  label={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <SearchIcon fontSize="small" color={semanticSearchEnabled ? 'secondary' : 'action'} />
                      <Typography variant="body2" color={semanticSearchEnabled ? 'secondary' : 'text.secondary'}>
                        Enable vector-based similarity search to explore biologically similar entities
                      </Typography>
                    </Box>
                  }
                  sx={{ ml: 0, mr: 0 }}
                />
              </Tooltip>
              {semanticSearchEnabled && vectorCategory && embeddingType && (
                <Chip
                  size="small"
                  label={`${vectorCategory} (${embeddingType})`}
                  color="secondary"
                  variant="outlined"
                  sx={{ fontSize: '0.7rem', height: '22px' }}
                />
              )}
            </Box>
            {semanticSearchEnabled && (
              <Button
                size="small"
                variant="text"
                startIcon={<TuneIcon fontSize="small" />}
                onClick={() => setExpandedSections(prev =>
                  prev.vectorConfig
                    ? { ...prev, vectorConfig: false, examples: true }
                    : { ...prev, vectorConfig: true, examples: false }
                )}
                sx={{ textTransform: 'none', fontSize: '0.75rem' }}
              >
                Configure
              </Button>
            )}
          </Box>

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
                border: `1px solid ${semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.divider}`,
                backgroundColor: alpha(theme.palette.background.default, 0.6),
                '&:focus-within': {
                  borderColor: semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.primary.main,
                  boxShadow: `0 0 0 2px ${alpha(semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.primary.main, 0.2)}`,
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
          <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.divider}`, overflow: 'hidden' }}>
            <SectionHeader
              title={semanticSearchEnabled ? "Vector Search Examples" : "Example Queries"}
              icon={<LightbulbOutlinedIcon fontSize="small" color={semanticSearchEnabled ? "secondary" : "warning"} />}
              section="examples"
            />
            <Collapse in={expandedSections.examples}>
              <Box sx={{ p: 2, pt: 0 }}>
                {semanticSearchEnabled && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
                    Click an example to set the question and configure vector settings
                  </Typography>
                )}
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {(semanticSearchEnabled ? vectorExampleQueries : exampleQueries).map((example, idx) => (
                    <Chip
                      key={idx}
                      label={semanticSearchEnabled ? example.question : example}
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
                        backgroundColor: alpha(semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.primary.main, 0.08),
                        '&:hover': { backgroundColor: alpha(semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.primary.main, 0.15) },
                        border: `1px solid ${alpha(semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.primary.main, 0.2)}`,
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
                      // Auto-select first model for the provider
                      const firstModel = modelChoices[selectedProvider]?.models?.[0];
                      setLlmType(firstModel || '');
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
                    {provider && modelChoices[provider]?.models?.map((m) => {
                      const isSupported = supportedModels.includes(m);
                      const isFreeModel = (modelChoices[provider]?.free_models || []).includes(m);
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
                          {m}{isFreeModel ? ' (Free)' : ''}
                        </MenuItem>
                      );
                    })}
                  </Select>
                </FormControl>

                {/* Model Usage Note */}
                <Paper
                  variant="outlined"
                  sx={{
                    p: 2,
                    mb: 2,
                    backgroundColor: alpha(theme.palette.info.main, 0.03),
                    border: `1px solid ${alpha(theme.palette.info.main, 0.2)}`,
                    borderRadius: '8px'
                  }}
                >
                  <Typography variant="body2" color="text.secondary">
                    API keys are managed securely on the server — no key entry required. Models marked <strong>★</strong> are recommended for this agent. A single query can consume a large number of tokens due to multi-step reasoning.
                  </Typography>
                </Paper>

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

                {/* Reasoning Mode */}
                <Box
                  onClick={() => setReasoningEnabled(!reasoningEnabled)}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    p: 1.5,
                    mb: reasoningEnabled ? 2 : 0,
                    borderRadius: '8px',
                    border: `1px solid ${theme.palette.divider}`,
                    cursor: 'pointer',
                    backgroundColor: reasoningEnabled ? alpha(theme.palette.info.main, 0.08) : 'transparent',
                    '&:hover': { backgroundColor: alpha(theme.palette.info.main, 0.05) },
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <InfoOutlinedIcon fontSize="small" sx={{ color: reasoningEnabled ? 'info.main' : 'text.secondary' }} />
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>Reasoning</Typography>
                      <Typography variant="caption" color="text.secondary">
                        Let the model think step-by-step before answering.
                      </Typography>
                    </Box>
                  </Box>
                  <Switch
                    checked={reasoningEnabled}
                    onChange={(e) => { e.stopPropagation(); setReasoningEnabled(e.target.checked); }}
                    color="info"
                    size="small"
                  />
                </Box>

                {reasoningEnabled && (
                  <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                    <InputLabel>Reasoning Effort</InputLabel>
                    <Select
                      value={reasoningEffort}
                      onChange={(e) => setReasoningEffort(e.target.value)}
                      label="Reasoning Effort"
                    >
                      <MenuItem value="low">Low</MenuItem>
                      <MenuItem value="medium">Medium</MenuItem>
                      <MenuItem value="high">High</MenuItem>
                    </Select>
                  </FormControl>
                )}
              </Box>
            </Collapse>
          </Paper>

          {/* Vector Search Configuration Section */}
          {semanticSearchEnabled && (
            <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${theme.palette.secondary.main}`, overflow: 'hidden' }}>
              <SectionHeader
                title="Vector Search Config"
                icon={<SearchIcon fontSize="small" color="secondary" />}
                section="vectorConfig"
                badge={vectorCategory && embeddingType ? "Ready" : "Required"}
              />
              <Collapse in={expandedSections.vectorConfig}>
                <Box sx={{ p: 2, pt: 0 }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    Configure vector search to find semantically similar entities in the knowledge graph.
                  </Typography>

                  {/* Vector Category */}
                  <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                    <InputLabel>Vector Category</InputLabel>
                    <Select
                      value={vectorCategory}
                      onChange={(e) => {
                        const category = e.target.value;
                        setVectorCategory(category);
                        setSelectedFile(null);
                        const options = nodeLabelToVectorIndexNames[category];
                        if (Array.isArray(options)) {
                          setEmbeddingType('');
                        } else if (options) {
                          setEmbeddingType(options);
                        } else {
                          setEmbeddingType('');
                        }
                      }}
                      label="Vector Category"
                    >
                      <MenuItem value=""><em>Select a category</em></MenuItem>
                      {Object.keys(nodeLabelToVectorIndexNames).map((category) => (
                        <MenuItem key={category} value={category}>{category}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  {/* Embedding Type */}
                  <FormControl fullWidth size="small" sx={{ mb: 2 }} disabled={!vectorCategory}>
                    <InputLabel>Embedding Type</InputLabel>
                    <Select
                      value={embeddingType}
                      onChange={(e) => setEmbeddingType(e.target.value)}
                      label="Embedding Type"
                    >
                      <MenuItem value=""><em>Select embedding type</em></MenuItem>
                      {vectorCategory && (
                        Array.isArray(nodeLabelToVectorIndexNames[vectorCategory])
                          ? nodeLabelToVectorIndexNames[vectorCategory].map((opt) => (
                              <MenuItem key={opt} value={opt}>{opt}</MenuItem>
                            ))
                          : nodeLabelToVectorIndexNames[vectorCategory] && (
                              <MenuItem value={nodeLabelToVectorIndexNames[vectorCategory]}>
                                {nodeLabelToVectorIndexNames[vectorCategory]}
                              </MenuItem>
                            )
                      )}
                    </Select>
                  </FormControl>

                  {/* Ready Status */}
                  {vectorCategory && embeddingType && !selectedFile && (
                    <Box sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                      p: 1.5,
                      mb: 2,
                      borderRadius: '8px',
                      backgroundColor: alpha(theme.palette.success.main, 0.08),
                      border: `1px solid ${alpha(theme.palette.success.main, 0.3)}`,
                    }}>
                      <CheckCircleIcon fontSize="small" color="success" />
                      <Typography variant="body2" color="success.main">
                        Ready for vector search with {vectorCategory} ({embeddingType})
                      </Typography>
                    </Box>
                  )}

                  {/* File Upload Button */}
                  <Button
                    variant="outlined"
                    component="label"
                    fullWidth
                    startIcon={<UploadFileIcon />}
                    disabled={!vectorCategory || !embeddingType}
                    sx={{
                      borderRadius: '12px',
                      height: '44px',
                      borderColor: theme.palette.secondary.main,
                      color: theme.palette.secondary.main,
                      textTransform: 'none',
                      '&:hover': {
                        backgroundColor: alpha(theme.palette.secondary.main, 0.04),
                      }
                    }}
                  >
                    Upload Custom Vector File (.npy) - Optional
                    <input
                      type="file"
                      hidden
                      onChange={handleVectorFileChange}
                      accept=".npy,.csv"
                    />
                  </Button>

                  {selectedFile && (
                    <Typography variant="body2" sx={{ mt: 1, color: 'success.main', display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <CheckCircleIcon fontSize="small" />
                      Vector file staged: {selectedFile.name}
                    </Typography>
                  )}
                </Box>
              </Collapse>
            </Paper>
          )}

          {/* Historical Query Viewing Indicator */}
          {viewingHistoryIndex !== null && (
            <Alert
              severity="info"
              sx={{ mb: 2, borderRadius: '12px' }}
              action={
                <Button
                  color="inherit"
                  size="small"
                  onClick={() => setViewingHistoryIndex(null)}
                  sx={{ textTransform: 'none' }}
                >
                  Clear
                </Button>
              }
            >
              Viewing query from message #{viewingHistoryIndex + 1}
            </Alert>
          )}

          {/* Generated Query Section */}
          {(queryResult || editableQuery) && (
            <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${queryGenerated && !isLoading ? theme.palette.info.main : theme.palette.divider}`, overflow: 'hidden' }}>
              <SectionHeader
                title={(isEditingQuery || queryGenerated) && !isLoading ? "Generated Query (Editable)" : "Generated Query"}
                icon={<CodeIcon fontSize="small" color="info" />}
                section="query"
                badge={queryGenerated && !isLoading ? "Pending" : null}
              />
              <Collapse in={expandedSections.query}>
                <Box sx={{ p: 2, pt: 0 }}>
                  {(isEditingQuery || queryGenerated) && !isLoading ? (
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
                        {(queryGenerated || isEditingQuery) && (
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
                          {(isLoading && editableQuery) ? editableQuery : queryResult}
                        </SyntaxHighlighter>
                      </Box>
                      {!isLoading && (
                      <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                        <Button
                          size="small"
                          startIcon={<EditIcon />}
                          variant="outlined"
                          onClick={() => {
                            const relevantTurn = viewingHistoryIndex !== null
                              ? conversationHistory[viewingHistoryIndex]
                              : conversationHistory[conversationHistory.length - 1];
                            if (relevantTurn?.question) {
                              setPendingQuestion(relevantTurn.question);
                            }
                            setEditableQuery(queryResult);
                            setOriginalQuery(queryResult);
                            setIsEditingQuery(true);
                          }}
                          sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                        >
                          Edit
                        </Button>
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
                      )}
                    </>
                  )}
                </Box>
              </Collapse>
            </Paper>
          )}

          {/* Node Visualization Section */}
          {hasValidResults(executionResult?.result) && (
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

          {/* Raw Results Section - show when we have an execution result */}
          {executionResult && (
            <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${theme.palette.divider}`, overflow: 'hidden' }}>
              <SectionHeader
                title="Structured Query Results"
                icon={<DataObjectIcon fontSize="small" color="warning" />}
                section="results"
                badge={hasValidResults(executionResult?.result) ? executionResult.result.length : null}
              />
              <Collapse in={expandedSections.results}>
                <Box sx={{ p: 2, pt: 0, maxHeight: 300, overflow: 'auto' }}>
                  {hasValidResults(executionResult?.result) ? (
                    <SyntaxHighlighter language="json" style={syntaxTheme} customStyle={{ margin: 0, padding: '12px', fontSize: '0.75rem', borderRadius: '12px' }}>
                      {JSON.stringify(executionResult.result, null, 2)}
                    </SyntaxHighlighter>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      No result returned from CROssBARv2 KG.
                    </Typography>
                  )}
                </Box>
              </Collapse>
            </Paper>
          )}

          {/* Usage Summary (from the last agent run) */}
          {lastUsage && !isLoading && (
            <Paper elevation={0} sx={{ mb: 2, borderRadius: '16px', border: `1px solid ${theme.palette.divider}`, overflow: 'hidden' }}>
              <SectionHeader title="Run Summary" icon={<TerminalIcon fontSize="small" />} section="logs" />
              <Collapse in={expandedSections.logs}>
                <Box sx={{ p: 2, pt: 0, display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                  {renderUsageChips(lastUsage)}
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
