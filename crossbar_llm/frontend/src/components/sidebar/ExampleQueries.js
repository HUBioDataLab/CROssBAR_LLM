import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  Collapse,
  alpha,
  useTheme,
} from '@mui/material';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import SectionHeader from './SectionHeader';
import { exampleQueries, vectorExampleQueries } from '../../constants';

/**
 * Example queries section for the right panel.
 */
function ExampleQueries({
  expanded,
  onToggle,
  semanticSearchEnabled,
  onExampleClick,
}) {
  const theme = useTheme();
  const examples = semanticSearchEnabled ? vectorExampleQueries : exampleQueries;

  return (
    <Paper 
      elevation={0} 
      sx={{ 
        mb: 2, 
        borderRadius: '16px', 
        border: `1px solid ${semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.divider}`, 
        overflow: 'hidden' 
      }}
    >
      <SectionHeader 
        title={semanticSearchEnabled ? "Vector Search Examples" : "Example Queries"} 
        icon={<LightbulbOutlinedIcon fontSize="small" color={semanticSearchEnabled ? "secondary" : "warning"} />} 
        expanded={expanded}
        onToggle={onToggle}
      />
      <Collapse in={expanded}>
        <Box sx={{ p: 2, pt: 0 }}>
          {semanticSearchEnabled && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
              Click an example to set the question and configure vector settings
            </Typography>
          )}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {examples.map((example, idx) => (
              <Chip
                key={idx}
                label={semanticSearchEnabled ? example.question : example}
                onClick={() => onExampleClick(example)}
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
                  '&:hover': { 
                    backgroundColor: alpha(semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.primary.main, 0.15) 
                  },
                  border: `1px solid ${alpha(semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.primary.main, 0.2)}`,
                }}
              />
            ))}
          </Box>
        </Box>
      </Collapse>
    </Paper>
  );
}

export default ExampleQueries;
