import React from 'react';
import {
  Box,
  Paper,
  Collapse,
  useTheme,
} from '@mui/material';
import DataObjectIcon from '@mui/icons-material/DataObject';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import SectionHeader from './SectionHeader';

/**
 * Raw results section for the right panel.
 */
function ResultsSection({
  expanded,
  onToggle,
  results,
}) {
  const theme = useTheme();
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;

  return (
    <Paper 
      elevation={0} 
      sx={{ 
        mb: 2, 
        borderRadius: '16px', 
        border: `1px solid ${theme.palette.divider}`, 
        overflow: 'hidden' 
      }}
    >
      <SectionHeader 
        title="Structured Query Results" 
        icon={<DataObjectIcon fontSize="small" color="warning" />} 
        expanded={expanded}
        onToggle={onToggle}
        badge={results?.length}
      />
      <Collapse in={expanded}>
        <Box sx={{ p: 2, pt: 0, maxHeight: 300, overflow: 'auto' }}>
          <SyntaxHighlighter 
            language="json" 
            style={syntaxTheme} 
            customStyle={{ 
              margin: 0, 
              padding: '12px', 
              fontSize: '0.75rem', 
              borderRadius: '12px' 
            }}
          >
            {JSON.stringify(results, null, 2)}
          </SyntaxHighlighter>
        </Box>
      </Collapse>
    </Paper>
  );
}

export default ResultsSection;
