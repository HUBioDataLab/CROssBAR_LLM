import React, { useState, useRef, useEffect } from 'react';
import { 
  Typography, 
  Box, 
  useTheme, 
  IconButton, 
  Dialog, 
  DialogContent, 
  Snackbar,
  Alert,
  Paper,
  Divider,
  Chip,
  Fade,
  Tooltip,
  Collapse,
  Button,
  alpha,
  DialogTitle,
  DialogActions,
  Zoom,
  CircularProgress
} from '@mui/material';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import CloseIcon from '@mui/icons-material/Close';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import CodeIcon from '@mui/icons-material/Code';
import DataObjectIcon from '@mui/icons-material/DataObject';
import ChatBubbleOutlineIcon from '@mui/icons-material/ChatBubbleOutline';
import TerminalIcon from '@mui/icons-material/Terminal';
import ClearAllIcon from '@mui/icons-material/ClearAll';
import LaunchIcon from '@mui/icons-material/Launch';
import EditIcon from '@mui/icons-material/Edit';
import NodeVisualization from './NodeVisualization';

function ResultsDisplay({ queryResult, executionResult, realtimeLogs }) {
  const theme = useTheme();
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [copySnackbar, setCopySnackbar] = useState(false);
  const [clearLogsSnackbar, setClearLogsSnackbar] = useState(false);
  const [neo4jBrowserSnackbar, setNeo4jBrowserSnackbar] = useState(false);
  const [showNeo4jDialog, setShowNeo4jDialog] = useState(false);
  const [expandedSections, setExpandedSections] = useState({
    response: true,
    query: true,
    result: true,
    logs: true
  });
  
  const logContainerRef = useRef(null);
  const resultsContainerRef = useRef(null);
  
  const neo4jBrowserUrl = 'https://neo4j.crossbarv2.hubiodatalab.com/browser/?preselectAuthMethod=[NO_AUTH]&dbms=bolt://neo4j.crossbarv2.hubiodatalab.com';
  
  // Auto-scroll logs to bottom when they update
  useEffect(() => {
    if (logContainerRef.current && expandedSections.logs) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [realtimeLogs, expandedSections.logs]);

  useEffect(() => {
    if (executionResult && resultsContainerRef.current) {
      setTimeout(() => {
        const element = resultsContainerRef.current;
        const headerOffset = 100; // Adjust for fixed AppBar (approx 64px) + padding
        const elementPosition = element.getBoundingClientRect().top;
        const offsetPosition = elementPosition + window.scrollY - headerOffset;

        window.scrollTo({
          top: offsetPosition,
          behavior: 'smooth'
        });
      }, 100);
    }
  }, [executionResult]);

  // Process queryResult to handle objects
  const processedQueryResult = React.useMemo(() => {
    if (!queryResult) return null;
    
    // Check if queryResult is an object with the error structure
    if (typeof queryResult === 'object' && queryResult !== null) {
      // If it has the error structure (type, loc, msg, input), convert to string representation
      if ('type' in queryResult && 'loc' in queryResult && 'msg' in queryResult && 'input' in queryResult) {
        return JSON.stringify(queryResult, null, 2);
      }
      // For other objects, also stringify them
      return JSON.stringify(queryResult, null, 2);
    }
    
    // If it's already a string, return as is
    return queryResult;
  }, [queryResult]);

  if (!processedQueryResult && !executionResult && !realtimeLogs) {
    return null;
  }

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text);
    setCopySnackbar(true);
    setTimeout(() => {
      setCopySnackbar(false);
    }, 1500);
  };

  const handleClearLogs = () => {
    // Dispatch a custom event that parent components can listen for
    const clearLogsEvent = new CustomEvent('clearDebugLogs');
    window.dispatchEvent(clearLogsEvent);
    
    // Show a confirmation message that auto-closes after 1.5 seconds
    setClearLogsSnackbar(true);
    setTimeout(() => {
      setClearLogsSnackbar(false);
    }, 1500);
  };

  const handleNeo4jBrowserOpen = () => {
    // Show dialog first instead of immediately opening the browser
    setShowNeo4jDialog(true);
    
    // Copy the query to clipboard
    if (processedQueryResult) {
      navigator.clipboard.writeText(processedQueryResult);
      setCopySnackbar(true);
      setTimeout(() => {
        setCopySnackbar(false);
      }, 1500);
    }
  };
  
  const openNeo4jBrowser = () => {
    // Close the dialog
    setShowNeo4jDialog(false);
    
    // Open Neo4j Browser in a new tab
    window.open(neo4jBrowserUrl, '_blank');
  };

  const toggleSection = (section) => {
    setExpandedSections({
      ...expandedSections,
      [section]: !expandedSections[section]
    });
  };
  
  // Format log lines with colors based on log level
  const formatLogLine = (line) => {
    if (line.includes('ERROR') || line.includes('Error:')) {
      return <Typography component="span" sx={{ color: 'error.main', fontFamily: 'monospace', fontSize: '0.9rem', display: 'block' }}>{line}</Typography>;
    } else if (line.includes('WARNING') || line.includes('Warning:')) {
      return <Typography component="span" sx={{ color: 'warning.main', fontFamily: 'monospace', fontSize: '0.9rem', display: 'block' }}>{line}</Typography>;
    } else if (line.includes('INFO') || line.includes('Successfully')) {
      return <Typography component="span" sx={{ color: 'success.main', fontFamily: 'monospace', fontSize: '0.9rem', display: 'block' }}>{line}</Typography>;
    } else if (line.includes('DEBUG')) {
      return <Typography component="span" sx={{ color: 'info.main', fontFamily: 'monospace', fontSize: '0.9rem', display: 'block' }}>{line}</Typography>;
    } else {
      return <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.9rem', display: 'block' }}>{line}</Typography>;
    }
  };

  return (
    <Box sx={{ mb: 4 }}>
      <Fade in={true} timeout={800}>
        <Box>
          {executionResult && (
            <Paper 
              ref={resultsContainerRef}
              elevation={0} 
              sx={{ 
                mb: 4, 
                borderRadius: '20px',
                border: theme => `1px solid ${theme.palette.divider}`,
                overflow: 'hidden',
                backdropFilter: 'blur(10px)',
                backgroundColor: theme => theme.palette.mode === 'dark' 
                  ? alpha(theme.palette.background.paper, 0.8)
                  : alpha(theme.palette.background.paper, 0.8),
              }}
            >
              <Box 
                onClick={() => toggleSection('response')}
                sx={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center',
                  px: 3,
                  py: 2.5,
                  borderBottom: expandedSections.response ? theme => `1px solid ${theme.palette.divider}` : 'none',
                  cursor: 'pointer',
                  '&:hover': {
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? alpha(theme.palette.primary.main, 0.05)
                      : alpha(theme.palette.primary.main, 0.03),
                  }
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <ChatBubbleOutlineIcon sx={{ 
                    mr: 1.5, 
                    color: theme => theme.palette.mode === 'dark' ? theme.palette.secondary.light : theme.palette.secondary.main 
                  }} />
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    Natural Language Response
                  </Typography>
                </Box>
                <IconButton 
                  size="small" 
                  onClick={(e) => {
                    e.stopPropagation(); // Prevent triggering the parent onClick
                    toggleSection('response');
                  }}
                  sx={{ borderRadius: '10px' }}
                >
                  {expandedSections.response ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
              
              <Collapse in={expandedSections.response}>
                <Box sx={{ p: 3 }}>
                  <Typography variant="body1" sx={{ lineHeight: 1.7 }}>
                    {typeof executionResult.response === 'object' && executionResult.response !== null
                      ? JSON.stringify(executionResult.response, null, 2)
                      : executionResult.response}
                  </Typography>
                </Box>
              </Collapse>
            </Paper>
          )}

          {/* Node Visualization Component */}
          {executionResult?.result && <NodeVisualization executionResult={executionResult} />}

          {processedQueryResult && (
            <Paper 
              elevation={0} 
              sx={{ 
                mb: 4, 
                borderRadius: '20px',
                border: theme => `1px solid ${theme.palette.divider}`,
                overflow: 'hidden',
                backdropFilter: 'blur(10px)',
                backgroundColor: theme => theme.palette.mode === 'dark' 
                  ? alpha(theme.palette.background.paper, 0.8)
                  : alpha(theme.palette.background.paper, 0.8),
              }}
            >
              <Box 
                onClick={() => toggleSection('query')}
                sx={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center',
                  px: 3,
                  py: 2.5,
                  borderBottom: expandedSections.query ? theme => `1px solid ${theme.palette.divider}` : 'none',
                  cursor: 'pointer',
                  '&:hover': {
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? alpha(theme.palette.primary.main, 0.05)
                      : alpha(theme.palette.primary.main, 0.03),
                  }
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <CodeIcon sx={{ 
                    mr: 1.5, 
                    color: theme => theme.palette.mode === 'dark' ? theme.palette.primary.light : theme.palette.primary.main 
                  }} />
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    Generated Cypher Query
                  </Typography>
                </Box>
                <Box>
                  <Tooltip title="View in Neo4j Browser">
                    <Button
                      variant="outlined"
                      color="primary"
                      size="small"
                      startIcon={<LaunchIcon fontSize="small" />}
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent triggering the parent onClick
                        handleNeo4jBrowserOpen();
                      }}
                      sx={{ 
                        mr: 1, 
                        borderRadius: '10px',
                        textTransform: 'none'
                      }}
                    >
                      Neo4j Browser
                    </Button>
                  </Tooltip>
                  <Tooltip title="Copy to clipboard">
                    <IconButton 
                      size="small" 
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent triggering the parent onClick
                        handleCopy(processedQueryResult);
                      }}
                      sx={{ mr: 1, borderRadius: '10px' }}
                    >
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Edit Query">
                    <IconButton 
                      size="small" 
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent triggering the parent onClick
                        // Dispatch event for parent component to handle query editing
                        const editQueryEvent = new CustomEvent('editQuery');
                        window.dispatchEvent(editQueryEvent);
                      }}
                      sx={{ mr: 1, borderRadius: '10px' }}
                    >
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <IconButton 
                    size="small" 
                    onClick={(e) => {
                      e.stopPropagation(); // Prevent triggering the parent onClick
                      toggleSection('query');
                    }}
                    sx={{ borderRadius: '10px' }}
                  >
                    {expandedSections.query ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  </IconButton>
                </Box>
              </Box>
              
              <Collapse in={expandedSections.query}>
                <Box sx={{ maxHeight: '250px', overflow: 'auto', p: 0 }}>
                  <SyntaxHighlighter 
                    language="cypher" 
                    style={syntaxTheme}
                    customStyle={{
                      backgroundColor: 'transparent',
                      margin: 0,
                      padding: '20px 24px',
                      borderRadius: 0,
                      fontSize: '0.9rem',
                      lineHeight: 1.6
                    }}
                    wrapLines={true}
                    wrapLongLines={true}
                  >
                    {processedQueryResult}
                  </SyntaxHighlighter>
                </Box>
              </Collapse>
            </Paper>
          )}
          
          {executionResult?.result && (
            <Paper 
              elevation={0} 
              sx={{ 
                mb: 4, 
                borderRadius: '20px',
                border: theme => `1px solid ${theme.palette.divider}`,
                overflow: 'hidden',
                backdropFilter: 'blur(10px)',
                backgroundColor: theme => theme.palette.mode === 'dark' 
                  ? alpha(theme.palette.background.paper, 0.8)
                  : alpha(theme.palette.background.paper, 0.8),
              }}
            >
              <Box 
                onClick={() => toggleSection('result')}
                sx={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center',
                  px: 3,
                  py: 2.5,
                  borderBottom: expandedSections.result ? theme => `1px solid ${theme.palette.divider}` : 'none',
                  cursor: 'pointer',
                  '&:hover': {
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? alpha(theme.palette.primary.main, 0.05)
                      : alpha(theme.palette.primary.main, 0.03),
                  }
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <DataObjectIcon sx={{ 
                    mr: 1.5, 
                    color: theme => theme.palette.mode === 'dark' ? theme.palette.secondary.light : theme.palette.secondary.main 
                  }} />
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    Query Results
                  </Typography>
                </Box>
                <Box>
                  <Tooltip title="Copy to clipboard">
                    <IconButton 
                      size="small" 
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent triggering the parent onClick
                        handleCopy(JSON.stringify(executionResult.result, null, 2));
                      }}
                      sx={{ mr: 1, borderRadius: '10px' }}
                    >
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="View fullscreen">
                    <IconButton 
                      size="small" 
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent triggering the parent onClick
                        setIsFullscreen(true);
                      }}
                      sx={{ mr: 1, borderRadius: '10px' }}
                    >
                      <FullscreenIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <IconButton 
                    size="small" 
                    onClick={(e) => {
                      e.stopPropagation(); // Prevent triggering the parent onClick
                      toggleSection('result');
                    }}
                    sx={{ borderRadius: '10px' }}
                  >
                    {expandedSections.result ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  </IconButton>
                </Box>
              </Box>
              
              <Collapse in={expandedSections.result}>
                <Box sx={{ maxHeight: '400px', overflow: 'auto' }}>
                  <SyntaxHighlighter 
                    language="json" 
                    style={syntaxTheme}
                    customStyle={{
                      backgroundColor: 'transparent',
                      margin: 0,
                      padding: '20px 24px',
                      borderRadius: 0,
                      fontSize: '0.9rem',
                      lineHeight: 1.6
                    }}
                    wrapLines={true}
                    wrapLongLines={true}
                  >
                    {JSON.stringify(executionResult.result, null, 2)}
                  </SyntaxHighlighter>
                </Box>
              </Collapse>
            </Paper>
          )}
          
          {/* Verbose Mode Logs Section - Moved to the bottom */}
          {realtimeLogs && (
            <Paper 
              elevation={0} 
              sx={{ 
                mb: 4, 
                borderRadius: '20px',
                border: theme => `1px solid ${theme.palette.divider}`,
                overflow: 'hidden',
                backdropFilter: 'blur(10px)',
                backgroundColor: theme => theme.palette.mode === 'dark' 
                  ? alpha(theme.palette.background.paper, 0.8)
                  : alpha(theme.palette.background.paper, 0.8),
              }}
            >
              <Box 
                onClick={() => toggleSection('logs')}
                sx={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center',
                  px: 3,
                  py: 2.5,
                  borderBottom: expandedSections.logs ? theme => `1px solid ${theme.palette.divider}` : 'none',
                  cursor: 'pointer',
                  '&:hover': {
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? alpha(theme.palette.primary.main, 0.05)
                      : alpha(theme.palette.primary.main, 0.03),
                  }
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <TerminalIcon sx={{ 
                    mr: 1.5, 
                    color: theme => theme.palette.mode === 'dark' ? theme.palette.info.light : theme.palette.info.main 
                  }} />
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    Debug Logs
                  </Typography>
                  {realtimeLogs.includes('Connecting') && (
                    <Box sx={{ display: 'flex', alignItems: 'center', ml: 2 }}>
                      <CircularProgress size={16} thickness={5} sx={{ mr: 1 }} />
                      <Typography variant="caption" color="text.secondary">
                        Live
                      </Typography>
                    </Box>
                  )}
                </Box>
                <Box>
                  <Tooltip title="Copy to clipboard">
                    <IconButton 
                      size="small" 
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent triggering the parent onClick
                        handleCopy(realtimeLogs);
                      }}
                      sx={{ mr: 1, borderRadius: '10px' }}
                    >
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Clear logs">
                    <IconButton 
                      size="small" 
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent triggering the parent onClick
                        handleClearLogs();
                      }}
                      sx={{ mr: 1, borderRadius: '10px' }}
                    >
                      <ClearAllIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <IconButton 
                    size="small" 
                    onClick={(e) => {
                      e.stopPropagation(); // Prevent triggering the parent onClick
                      toggleSection('logs');
                    }}
                    sx={{ borderRadius: '10px' }}
                  >
                    {expandedSections.logs ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  </IconButton>
                </Box>
              </Box>
              
              <Collapse in={expandedSections.logs}>
                <Box 
                  ref={logContainerRef}
                  sx={{ 
                    p: 3, 
                    maxHeight: '300px', 
                    overflow: 'auto',
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? alpha(theme.palette.background.default, 0.5)
                      : alpha(theme.palette.background.default, 0.5),
                  }}
                >
                  {realtimeLogs.split('\n').map((line, index) => (
                    <React.Fragment key={index}>
                      {formatLogLine(line)}
                    </React.Fragment>
                  ))}
                </Box>
              </Collapse>
            </Paper>
          )}
        </Box>
      </Fade>

      <Dialog
        fullScreen
        open={isFullscreen}
        onClose={() => setIsFullscreen(false)}
        sx={{
          '& .MuiDialog-paper': {
            backdropFilter: 'blur(10px)',
            backgroundColor: theme => theme.palette.mode === 'dark' 
              ? alpha(theme.palette.background.paper, 0.9)
              : alpha(theme.palette.background.paper, 0.9),
          }
        }}
      >
        <DialogTitle sx={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          borderBottom: theme => `1px solid ${theme.palette.divider}`,
          py: 2
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <DataObjectIcon sx={{ mr: 1.5, color: 'secondary.main' }} />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Query Results
            </Typography>
          </Box>
          <Box>
            <Tooltip title="Copy to clipboard">
              <IconButton 
                onClick={() => handleCopy(JSON.stringify(executionResult?.result, null, 2))}
                sx={{ mr: 1, borderRadius: '10px' }}
              >
                <ContentCopyIcon />
              </IconButton>
            </Tooltip>
            <IconButton 
              onClick={() => setIsFullscreen(false)}
              sx={{ borderRadius: '10px' }}
            >
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent sx={{ p: 0 }}>
          <SyntaxHighlighter 
            language="json" 
            style={syntaxTheme}
            customStyle={{
              backgroundColor: 'transparent',
              margin: 0,
              padding: '24px',
              height: '100%',
              fontSize: '0.95rem',
              lineHeight: 1.6
            }}
            wrapLines={true}
            wrapLongLines={true}
          >
            {JSON.stringify(executionResult?.result, null, 2)}
          </SyntaxHighlighter>
        </DialogContent>
        <DialogActions sx={{ 
          borderTop: theme => `1px solid ${theme.palette.divider}`,
          p: 2
        }}>
          <Button 
            onClick={() => setIsFullscreen(false)} 
            variant="outlined"
            sx={{ borderRadius: '12px' }}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={copySnackbar}
        autoHideDuration={1500}
        onClose={() => setCopySnackbar(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Zoom in={copySnackbar}>
          <Alert 
            severity="success" 
            variant="filled"
            onClose={() => setCopySnackbar(false)}
            sx={{ 
              borderRadius: '12px',
              boxShadow: theme => theme.palette.mode === 'dark' 
                ? '0 4px 20px rgba(0, 0, 0, 0.3)' 
                : '0 4px 20px rgba(0, 0, 0, 0.1)',
            }}
          >
            Copied to clipboard
          </Alert>
        </Zoom>
      </Snackbar>

      <Snackbar
        open={clearLogsSnackbar}
        autoHideDuration={1500}
        onClose={() => setClearLogsSnackbar(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Zoom in={clearLogsSnackbar}>
          <Alert 
            severity="info" 
            variant="filled"
            onClose={() => setClearLogsSnackbar(false)}
            sx={{ 
              borderRadius: '12px',
              boxShadow: theme => theme.palette.mode === 'dark' 
                ? '0 4px 20px rgba(0, 0, 0, 0.3)' 
                : '0 4px 20px rgba(0, 0, 0, 0.1)',
            }}
          >
            Debug logs cleared successfully
          </Alert>
        </Zoom>
      </Snackbar>

      <Snackbar
        open={neo4jBrowserSnackbar}
        autoHideDuration={3000}
        onClose={() => setNeo4jBrowserSnackbar(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Zoom in={neo4jBrowserSnackbar}>
          <Alert 
            severity="info" 
            variant="filled"
            onClose={() => setNeo4jBrowserSnackbar(false)}
            sx={{ 
              borderRadius: '12px',
              boxShadow: theme => theme.palette.mode === 'dark' 
                ? '0 4px 20px rgba(0, 0, 0, 0.3)' 
                : '0 4px 20px rgba(0, 0, 0, 0.1)',
            }}
          >
            <Typography variant="body2">
              Query copied! Paste it in the Neo4j Browser command line (using Ctrl+V or ⌘+V)
            </Typography>
          </Alert>
        </Zoom>
      </Snackbar>
      
      {/* Neo4j Browser Instructions Dialog */}
      <Dialog 
        open={showNeo4jDialog} 
        onClose={() => setShowNeo4jDialog(false)}
        sx={{
          '& .MuiDialog-paper': {
            borderRadius: '20px',
            backdropFilter: 'blur(10px)',
            backgroundColor: theme => theme.palette.mode === 'dark' 
              ? alpha(theme.palette.background.paper, 0.9)
              : alpha(theme.palette.background.paper, 0.9),
            maxWidth: '500px'
          }
        }}
      >
        <DialogTitle sx={{ 
          borderBottom: theme => `1px solid ${theme.palette.divider}`,
          pb: 2
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <LaunchIcon sx={{ mr: 1.5, color: 'primary.main' }} />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Open in Neo4j Browser
            </Typography>
          </Box>
        </DialogTitle>
        <DialogContent sx={{ mt: 2, p: 3 }}>
          <Typography variant="body1" sx={{ mb: 2 }}>
            The query has been copied to your clipboard. When Neo4j Browser opens:
          </Typography>
          <Box sx={{ 
            backgroundColor: theme => theme.palette.mode === 'dark' 
              ? alpha(theme.palette.background.default, 0.5)
              : alpha(theme.palette.background.default, 0.5),
            p: 2,
            borderRadius: '10px',
            mb: 2
          }}>
            <Typography component="ol" sx={{ pl: 2 }}>
              <li>Click the "Open Neo4j browser" button below,</li>
              <li>On the Neo4j browser page, Connect to the database by clicking the respective button,</li>
              <li>Click in the command input bar at the top of the Neo4j Browser,</li>
              <li>Paste the copied cypher query using Ctrl+V (Windows/Linux) or ⌘+V (Mac),</li>
              <li>Click the play button to run the query.</li>
            </Typography>
          </Box>
          <Typography variant="body2" color="text.secondary">
            The Neo4j Browser provides a visual representation of your graph database query results.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ 
          borderTop: theme => `1px solid ${theme.palette.divider}`,
          p: 2
        }}>
          <Button 
            onClick={() => setShowNeo4jDialog(false)} 
            variant="outlined"
            sx={{ borderRadius: '12px', textTransform: 'none' }}
          >
            Cancel
          </Button>
          <Button 
            onClick={openNeo4jBrowser} 
            variant="contained"
            sx={{ borderRadius: '12px', textTransform: 'none' }}
            autoFocus
          >
            Open Neo4j Browser
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default ResultsDisplay;