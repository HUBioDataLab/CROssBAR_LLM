import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  Fade,
  useTheme,
  alpha,
  Collapse,
  IconButton,
  Tooltip,
  Button,
  Divider,
} from '@mui/material';
import PersonIcon from '@mui/icons-material/Person';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import CodeIcon from '@mui/icons-material/Code';
import DataObjectIcon from '@mui/icons-material/DataObject';
import HistoryIcon from '@mui/icons-material/History';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';

/**
 * ConversationHistory component displays the chat-like conversation thread
 * with follow-up question suggestions and expandable query/results.
 */
function ConversationHistory({ 
  history = [], 
  onFollowUpClick,
  showFullHistory = false,
  hideFollowUps = false,
  showFollowUpsOnlyForLatest = false
}) {
  const theme = useTheme();
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;
  const [expandedTurns, setExpandedTurns] = React.useState({});
  const [expandedDetails, setExpandedDetails] = React.useState({});
  const [copiedIndex, setCopiedIndex] = React.useState(null);
  const [showAll, setShowAll] = React.useState(showFullHistory);

  // Show last 3 by default unless showAll is true
  const displayHistory = showAll ? history : history.slice(-3);

  const toggleExpand = (index) => {
    setExpandedTurns(prev => ({
      ...prev,
      [index]: prev[index] === undefined ? false : !prev[index]
    }));
  };

  const toggleDetails = (index, type) => {
    const key = `${index}-${type}`;
    setExpandedDetails(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const handleCopyResponse = async (text, index) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  if (!history || history.length === 0) {
    return null;
  }

  return (
    <Fade in={true} timeout={500}>
      <Paper
        elevation={0}
        sx={{
          mb: 4,
          borderRadius: '20px',
          border: `1px solid ${theme.palette.divider}`,
          overflow: 'hidden',
          backgroundColor: theme.palette.mode === 'dark'
            ? alpha(theme.palette.background.paper, 0.8)
            : alpha(theme.palette.background.paper, 0.8),
        }}
      >
        {/* Header */}
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            px: 3,
            py: 2,
            borderBottom: `1px solid ${theme.palette.divider}`,
            backgroundColor: theme.palette.mode === 'dark'
              ? alpha(theme.palette.primary.main, 0.05)
              : alpha(theme.palette.primary.main, 0.02),
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <HistoryIcon sx={{ color: theme.palette.primary.main }} />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Conversation History
            </Typography>
            <Chip 
              label={`${history.length} ${history.length === 1 ? 'turn' : 'turns'}`}
              size="small"
              sx={{ 
                backgroundColor: alpha(theme.palette.primary.main, 0.1),
                color: theme.palette.primary.main,
                fontWeight: 500,
              }}
            />
          </Box>
          {history.length > 3 && (
            <Button
              size="small"
              onClick={() => setShowAll(!showAll)}
              sx={{ textTransform: 'none' }}
            >
              {showAll ? 'Show Less' : `Show All (${history.length})`}
            </Button>
          )}
        </Box>

        {/* Messages */}
        <Box sx={{ p: 2 }}>
          {displayHistory.map((turn, displayIndex) => {
            const globalIndex = showAll ? displayIndex : history.length - displayHistory.length + displayIndex;
            const isExpanded = expandedTurns[globalIndex] !== false;
            const showQuery = expandedDetails[`${globalIndex}-query`];
            const showResults = expandedDetails[`${globalIndex}-results`];
            
            return (
              <Box 
                key={globalIndex}
                sx={{
                  mb: displayIndex < displayHistory.length - 1 ? 3 : 0,
                  pb: displayIndex < displayHistory.length - 1 ? 3 : 0,
                  borderBottom: displayIndex < displayHistory.length - 1 
                    ? `1px solid ${theme.palette.divider}` 
                    : 'none',
                }}
              >
                {/* User Message */}
                <Box sx={{ display: 'flex', gap: 1.5, mb: 2 }}>
                  <Box
                    sx={{
                      width: 32,
                      height: 32,
                      borderRadius: '10px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: theme.palette.primary.main,
                      color: 'white',
                      flexShrink: 0,
                    }}
                  >
                    <PersonIcon sx={{ fontSize: 18 }} />
                  </Box>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography 
                      variant="caption" 
                      color="text.secondary"
                      sx={{ fontWeight: 600, display: 'block', mb: 0.5 }}
                    >
                      You
                    </Typography>
                    <Typography variant="body1" sx={{ wordBreak: 'break-word' }}>
                      {turn.question}
                    </Typography>
                  </Box>
                  <IconButton
                    size="small"
                    onClick={() => toggleExpand(globalIndex)}
                    sx={{ alignSelf: 'flex-start' }}
                  >
                    {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  </IconButton>
                </Box>

                {/* Assistant Response */}
                <Collapse in={isExpanded}>
                  <Box sx={{ display: 'flex', gap: 1.5 }}>
                    <Box
                      sx={{
                        width: 32,
                        height: 32,
                        borderRadius: '10px',
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
                      <SmartToyIcon sx={{ fontSize: 18 }} />
                    </Box>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                        <Typography 
                          variant="caption" 
                          color="text.secondary"
                          sx={{ fontWeight: 600 }}
                        >
                          CROssBAR Assistant
                        </Typography>
                        <Tooltip title={copiedIndex === globalIndex ? "Copied!" : "Copy response"}>
                          <IconButton
                            size="small"
                            onClick={() => handleCopyResponse(turn.response, globalIndex)}
                            sx={{ opacity: 0.6, '&:hover': { opacity: 1 } }}
                          >
                            <ContentCopyIcon sx={{ fontSize: 14 }} />
                          </IconButton>
                        </Tooltip>
                      </Box>
                      
                      {/* Response Text */}
                      <Paper
                        elevation={0}
                        sx={{
                          p: 2,
                          borderRadius: '12px',
                          backgroundColor: theme.palette.mode === 'dark'
                            ? alpha(theme.palette.background.default, 0.5)
                            : alpha(theme.palette.grey[100], 0.8),
                          border: `1px solid ${theme.palette.divider}`,
                          mb: 1.5,
                        }}
                      >
                        <Typography 
                          variant="body1" 
                          sx={{ 
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            lineHeight: 1.7,
                          }}
                        >
                          {turn.response}
                        </Typography>
                      </Paper>

                      {/* Expandable Query/Results Buttons */}
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1.5 }}>
                        {turn.cypherQuery && (
                          <Chip
                            icon={<CodeIcon sx={{ fontSize: 16 }} />}
                            label={showQuery ? "Hide Query" : "Show Query"}
                            size="small"
                            onClick={() => toggleDetails(globalIndex, 'query')}
                            sx={{
                              cursor: 'pointer',
                              backgroundColor: alpha(theme.palette.info.main, 0.1),
                              '&:hover': {
                                backgroundColor: alpha(theme.palette.info.main, 0.2),
                              },
                            }}
                          />
                        )}
                        {turn.result && turn.result.length > 0 && (
                          <Chip
                            icon={<DataObjectIcon sx={{ fontSize: 16 }} />}
                            label={showResults ? "Hide Raw Data" : `Show Raw Data (${turn.result.length})`}
                            size="small"
                            onClick={() => toggleDetails(globalIndex, 'results')}
                            sx={{
                              cursor: 'pointer',
                              backgroundColor: alpha(theme.palette.success.main, 0.1),
                              '&:hover': {
                                backgroundColor: alpha(theme.palette.success.main, 0.2),
                              },
                            }}
                          />
                        )}
                      </Box>

                      {/* Cypher Query */}
                      <Collapse in={showQuery}>
                        <Box sx={{ mb: 1.5 }}>
                          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, mb: 0.5, display: 'block' }}>
                            Generated Cypher Query:
                          </Typography>
                          <Box sx={{ borderRadius: '8px', overflow: 'hidden' }}>
                            <SyntaxHighlighter
                              language="cypher"
                              style={syntaxTheme}
                              customStyle={{
                                margin: 0,
                                padding: '12px',
                                fontSize: '0.8rem',
                                borderRadius: '8px',
                              }}
                            >
                              {turn.cypherQuery}
                            </SyntaxHighlighter>
                          </Box>
                        </Box>
                      </Collapse>

                      {/* Raw Results */}
                      <Collapse in={showResults}>
                        <Box sx={{ mb: 1.5 }}>
                          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, mb: 0.5, display: 'block' }}>
                            Raw Query Results:
                          </Typography>
                          <Box sx={{ borderRadius: '8px', overflow: 'hidden' }}>
                            <SyntaxHighlighter
                              language="json"
                              style={syntaxTheme}
                              customStyle={{
                                margin: 0,
                                padding: '12px',
                                fontSize: '0.75rem',
                                borderRadius: '8px',
                                maxHeight: '300px',
                                overflow: 'auto',
                              }}
                            >
                              {JSON.stringify(turn.result, null, 2)}
                            </SyntaxHighlighter>
                          </Box>
                        </Box>
                      </Collapse>

                      {/* Follow-up Questions - show based on props */}
                      {(() => {
                        const isLatestTurn = globalIndex === history.length - 1;
                        const shouldShowFollowUps = !hideFollowUps && 
                          (!showFollowUpsOnlyForLatest || isLatestTurn);
                        return shouldShowFollowUps;
                      })() && turn.followUpQuestions && turn.followUpQuestions.length > 0 && (
                        <Box>
                          <Typography 
                            variant="caption" 
                            color="text.secondary"
                            sx={{ 
                              display: 'flex', 
                              alignItems: 'center', 
                              gap: 0.5,
                              mb: 1,
                              fontWeight: 600,
                            }}
                          >
                            <LightbulbOutlinedIcon sx={{ fontSize: 14 }} />
                            Suggested follow-ups:
                          </Typography>
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                            {turn.followUpQuestions.map((question, qIndex) => (
                              <Chip
                                key={qIndex}
                                label={question}
                                size="small"
                                onClick={() => onFollowUpClick && onFollowUpClick(question)}
                                sx={{
                                  cursor: 'pointer',
                                  maxWidth: '100%',
                                  height: 'auto',
                                  py: 0.5,
                                  '& .MuiChip-label': {
                                    whiteSpace: 'normal',
                                  },
                                  backgroundColor: theme.palette.mode === 'dark'
                                    ? alpha(theme.palette.primary.main, 0.15)
                                    : alpha(theme.palette.primary.main, 0.08),
                                  '&:hover': {
                                    backgroundColor: theme.palette.mode === 'dark'
                                      ? alpha(theme.palette.primary.main, 0.25)
                                      : alpha(theme.palette.primary.main, 0.15),
                                  },
                                  border: `1px solid ${alpha(theme.palette.primary.main, 0.3)}`,
                                }}
                              />
                            ))}
                          </Box>
                        </Box>
                      )}
                    </Box>
                  </Box>
                </Collapse>
              </Box>
            );
          })}
        </Box>

        {/* Show more indicator */}
        {!showAll && history.length > 3 && (
          <Box 
            sx={{ 
              px: 3, 
              py: 1.5, 
              textAlign: 'center',
              borderTop: `1px solid ${theme.palette.divider}`,
              backgroundColor: alpha(theme.palette.background.default, 0.5),
            }}
          >
            <Typography variant="caption" color="text.secondary">
              Showing last 3 of {history.length} turns • 
              <Button 
                size="small" 
                onClick={() => setShowAll(true)}
                sx={{ textTransform: 'none', ml: 0.5 }}
              >
                Show all
              </Button>
            </Typography>
          </Box>
        )}
      </Paper>
    </Fade>
  );
}

export default ConversationHistory;
