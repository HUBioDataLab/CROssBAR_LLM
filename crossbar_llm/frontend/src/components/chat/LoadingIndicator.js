import React from 'react';
import {
  Box,
  Typography,
  Paper,
  CircularProgress,
  Chip,
  alpha,
  useTheme,
} from '@mui/material';
import PersonIcon from '@mui/icons-material/Person';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import CodeIcon from '@mui/icons-material/Code';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SearchIcon from '@mui/icons-material/Search';

/**
 * Loading indicator component shown while query is being processed.
 */
function LoadingIndicator({
  pendingUserQuestion,
  currentStep,
  queryResult,
  semanticSearchEnabled,
  vectorCategory,
}) {
  const theme = useTheme();

  return (
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
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: queryResult ? 2 : 0 }}>
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
              <Box>
                <Typography variant="body1" sx={{ fontWeight: 600, color: 'text.primary' }}>
                  {currentStep}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {currentStep.includes('Generating') 
                    ? 'Translating your question to a database query...'
                    : 'Running the query and preparing your answer...'}
                </Typography>
              </Box>
            </Box>

            {/* Show generated query preview when available */}
            {queryResult && currentStep.includes('Executing') && (
              <Box sx={{ 
                mt: 1,
                p: 1.5, 
                borderRadius: '8px', 
                backgroundColor: alpha(theme.palette.info.main, 0.05),
                border: `1px solid ${alpha(theme.palette.info.main, 0.2)}`,
              }}>
                <Typography variant="caption" sx={{ 
                  fontWeight: 600, 
                  color: theme.palette.info.main,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.5,
                  mb: 0.5,
                }}>
                  <CodeIcon sx={{ fontSize: 12 }} />
                  Generated Cypher Query
                </Typography>
                <Typography 
                  variant="body2" 
                  sx={{ 
                    fontFamily: 'monospace', 
                    fontSize: '0.75rem',
                    color: 'text.secondary',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    maxHeight: 80,
                    overflow: 'hidden',
                  }}
                >
                  {queryResult.length > 200 ? queryResult.substring(0, 200) + '...' : queryResult}
                </Typography>
              </Box>
            )}
          </Paper>
        </Box>
      </Box>
    </Box>
  );
}

export default LoadingIndicator;
