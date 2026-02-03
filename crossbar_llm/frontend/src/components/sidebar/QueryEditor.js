import React from 'react';
import {
  Box,
  Typography,
  Paper,
  TextField,
  Button,
  Collapse,
  CircularProgress,
  alpha,
  useTheme,
} from '@mui/material';
import CodeIcon from '@mui/icons-material/Code';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import RestoreIcon from '@mui/icons-material/Restore';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import LaunchIcon from '@mui/icons-material/Launch';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import SectionHeader from './SectionHeader';
import { NEO4J_BROWSER_URL } from '../../constants';

/**
 * Query editor section for the right panel.
 */
function QueryEditor({
  expanded,
  onToggle,
  queryResult,
  editableQuery,
  originalQuery,
  setEditableQuery,
  queryGenerated,
  isEditingQuery,
  setIsEditingQuery,
  pendingQuestion,
  isLoading,
  onRunQuery,
  onCopy,
  copiedIndex,
}) {
  const theme = useTheme();
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;

  const handleOpenNeo4j = () => {
    onCopy(editableQuery || queryResult, 'query');
    window.open(NEO4J_BROWSER_URL, '_blank');
  };

  const isEditing = isEditingQuery || queryGenerated;

  return (
    <Paper 
      elevation={0} 
      sx={{ 
        mb: 2, 
        borderRadius: '16px', 
        border: `1px solid ${queryGenerated ? theme.palette.info.main : theme.palette.divider}`, 
        overflow: 'hidden' 
      }}
    >
      <SectionHeader 
        title={queryGenerated ? "Generated Query (Editable)" : "Generated Query"} 
        icon={<CodeIcon fontSize="small" color="info" />} 
        expanded={expanded}
        onToggle={onToggle}
        badge={queryGenerated ? "Pending" : null}
      />
      <Collapse in={expanded}>
        <Box sx={{ p: 2, pt: 0 }}>
          {isEditing ? (
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
                    onClick={onRunQuery}
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
                  onClick={() => onCopy(editableQuery, 'query')}
                  sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                >
                  {copiedIndex === 'query' ? 'Copied!' : 'Copy'}
                </Button>
                <Button
                  size="small"
                  startIcon={<LaunchIcon />}
                  onClick={handleOpenNeo4j}
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
                <SyntaxHighlighter 
                  language="cypher" 
                  style={syntaxTheme} 
                  customStyle={{ 
                    margin: 0, 
                    padding: '12px', 
                    fontSize: '0.8rem', 
                    borderRadius: '12px' 
                  }}
                >
                  {queryResult}
                </SyntaxHighlighter>
              </Box>
              <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                <Button
                  size="small"
                  startIcon={<ContentCopyIcon />}
                  onClick={() => onCopy(queryResult, 'query')}
                  sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                >
                  {copiedIndex === 'query' ? 'Copied!' : 'Copy'}
                </Button>
                <Button
                  size="small"
                  startIcon={<LaunchIcon />}
                  onClick={handleOpenNeo4j}
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
  );
}

export default QueryEditor;
