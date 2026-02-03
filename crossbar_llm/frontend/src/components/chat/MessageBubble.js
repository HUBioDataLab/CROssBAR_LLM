import React from 'react';
import {
  Box,
  Typography,
  Paper,
  IconButton,
  Tooltip,
  Chip,
  alpha,
  useTheme,
} from '@mui/material';
import PersonIcon from '@mui/icons-material/Person';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import SearchIcon from '@mui/icons-material/Search';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import ReactMarkdown from 'react-markdown';

/**
 * Single message bubble component for user/assistant messages.
 */
function MessageBubble({
  turn,
  index,
  isLatest,
  onCopy,
  copiedIndex,
  onFollowUpClick,
}) {
  const theme = useTheme();

  return (
    <Box sx={{ mb: 4 }}>
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
              <IconButton size="small" onClick={() => onCopy(turn.response, index)} sx={{ opacity: 0.6 }}>
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
                    onClick={() => onFollowUpClick(q, turn)}
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
}

export default MessageBubble;
