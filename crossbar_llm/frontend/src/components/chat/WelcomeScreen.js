import React from 'react';
import {
  Box,
  Typography,
  Paper,
  alpha,
  useTheme,
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';

/**
 * Welcome screen shown when there are no messages.
 */
function WelcomeScreen() {
  const theme = useTheme();

  return (
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
}

export default WelcomeScreen;
