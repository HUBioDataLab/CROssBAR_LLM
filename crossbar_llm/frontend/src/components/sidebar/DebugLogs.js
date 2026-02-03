import React from 'react';
import {
  Box,
  Paper,
  Collapse,
  useTheme,
} from '@mui/material';
import TerminalIcon from '@mui/icons-material/Terminal';
import SectionHeader from './SectionHeader';

/**
 * Debug logs section for the right panel.
 */
function DebugLogs({
  expanded,
  onToggle,
  logs,
}) {
  const theme = useTheme();

  if (!logs) return null;

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
        title="Debug Logs" 
        icon={<TerminalIcon fontSize="small" />} 
        expanded={expanded}
        onToggle={onToggle}
      />
      <Collapse in={expanded}>
        <Box 
          sx={{ 
            p: 2, 
            pt: 0, 
            maxHeight: 200, 
            overflow: 'auto', 
            fontFamily: 'monospace', 
            fontSize: '0.75rem' 
          }}
        >
          {logs}
        </Box>
      </Collapse>
    </Paper>
  );
}

export default DebugLogs;
