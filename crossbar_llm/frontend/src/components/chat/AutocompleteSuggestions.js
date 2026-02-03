import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  List,
  ListItem,
  ListItemText,
  alpha,
  useTheme,
} from '@mui/material';
import { nodeTypeColors } from '../../constants';

/**
 * Autocomplete suggestions popup component.
 */
function AutocompleteSuggestions({
  suggestions,
  selectedIndex,
  onSuggestionClick,
  suggestionsRef,
}) {
  const theme = useTheme();

  if (!suggestions || suggestions.length === 0) {
    return null;
  }

  return (
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
        {suggestions.map((suggestion, index) => (
          <ListItem
            key={index}
            button
            onClick={() => onSuggestionClick(suggestion)}
            selected={index === selectedIndex}
            sx={{
              py: 1,
              px: 2,
              borderLeft: index === selectedIndex
                ? `3px solid ${theme.palette.primary.main}`
                : '3px solid transparent',
              backgroundColor: index === selectedIndex
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
                      fontWeight: index === selectedIndex ? 600 : 400,
                      color: index === selectedIndex
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
  );
}

export default AutocompleteSuggestions;
