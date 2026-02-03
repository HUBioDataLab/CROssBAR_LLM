import React, { useRef } from 'react';
import {
  Box,
  Typography,
  Paper,
  TextField,
  IconButton,
  Tooltip,
  Switch,
  FormControlLabel,
  Chip,
  Button,
  alpha,
  useTheme,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import StopIcon from '@mui/icons-material/Stop';
import CodeIcon from '@mui/icons-material/Code';
import EditIcon from '@mui/icons-material/Edit';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import TuneIcon from '@mui/icons-material/Tune';
import SearchIcon from '@mui/icons-material/Search';
import AutocompleteSuggestions from './AutocompleteSuggestions';

/**
 * Chat input component with autocomplete and semantic search toggle.
 */
function ChatInput({
  question,
  onQuestionChange,
  onSubmit,
  onGenerateOnly,
  onCancel,
  isLoading,
  // Semantic search props
  semanticSearchEnabled,
  onSemanticSearchToggle,
  vectorCategory,
  embeddingType,
  onConfigureVectorSearch,
  // Autocomplete props
  showSuggestions,
  displaySuggestions,
  selectedSuggestionIndex,
  onSuggestionClick,
  onAutocompleteKeyDown,
  inputRef,
  suggestionsRef,
  inputContainerRef,
  // Query pending props
  queryGenerated,
  pendingQuestion,
  onRunEditedQuery,
  onEditQuery,
  onDismissQuery,
}) {
  const theme = useTheme();

  const handleKeyDown = (e) => {
    // First check autocomplete navigation
    if (onAutocompleteKeyDown(e)) return;
    // Then check for submit
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  const handleInputChange = (e) => {
    onQuestionChange(e.target.value, e.target.selectionStart);
  };

  return (
    <Box
      sx={{
        px: 3,
        py: 2,
        borderTop: `1px solid ${theme.palette.divider}`,
        backgroundColor: alpha(theme.palette.background.paper, 0.8),
        backdropFilter: 'blur(10px)',
      }}
    >
      {/* Pending Query Banner */}
      {queryGenerated && pendingQuestion && (
        <Paper
          elevation={0}
          sx={{
            p: 2,
            mb: 2,
            borderRadius: '12px',
            backgroundColor: alpha(theme.palette.info.main, 0.08),
            border: `1px solid ${alpha(theme.palette.info.main, 0.3)}`,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 1 }}>
              <CodeIcon fontSize="small" color="info" />
              Query Generated - Ready to Run
            </Typography>
            <Button
              size="small"
              variant="text"
              onClick={onDismissQuery}
              sx={{ textTransform: 'none', color: 'text.secondary' }}
            >
              Dismiss
            </Button>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            Question: "{pendingQuestion}"
          </Typography>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              variant="contained"
              size="small"
              startIcon={<PlayArrowIcon />}
              onClick={onRunEditedQuery}
              disabled={isLoading}
              sx={{ textTransform: 'none', borderRadius: '8px' }}
            >
              Run Query
            </Button>
            <Button
              variant="outlined"
              size="small"
              startIcon={<EditIcon />}
              onClick={onEditQuery}
              sx={{ textTransform: 'none', borderRadius: '8px' }}
            >
              Edit Query
            </Button>
          </Box>
        </Paper>
      )}
      
      {/* Semantic Search Toggle */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Tooltip title="Enable semantic search to find similar entities using vector embeddings">
            <FormControlLabel
              control={
                <Switch
                  checked={semanticSearchEnabled}
                  onChange={(e) => onSemanticSearchToggle(e.target.checked)}
                  size="small"
                  color="secondary"
                />
              }
              label={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <SearchIcon fontSize="small" color={semanticSearchEnabled ? 'secondary' : 'action'} />
                  <Typography variant="body2" color={semanticSearchEnabled ? 'secondary' : 'text.secondary'}>
                    Semantic Search
                  </Typography>
                </Box>
              }
              sx={{ ml: 0, mr: 0 }}
            />
          </Tooltip>
          {semanticSearchEnabled && vectorCategory && embeddingType && (
            <Chip
              size="small"
              label={`${vectorCategory} (${embeddingType})`}
              color="secondary"
              variant="outlined"
              sx={{ fontSize: '0.7rem', height: '22px' }}
            />
          )}
        </Box>
        {semanticSearchEnabled && (
          <Button
            size="small"
            variant="text"
            startIcon={<TuneIcon fontSize="small" />}
            onClick={onConfigureVectorSearch}
            sx={{ textTransform: 'none', fontSize: '0.75rem' }}
          >
            Configure
          </Button>
        )}
      </Box>

      {/* Chat Input with Autocomplete */}
      <Box ref={inputContainerRef} sx={{ position: 'relative' }}>
        <Paper
          component="form"
          onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
          elevation={0}
          sx={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: 1,
            p: 1.5,
            borderRadius: '20px',
            border: `1px solid ${semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.divider}`,
            backgroundColor: alpha(theme.palette.background.default, 0.6),
            '&:focus-within': {
              borderColor: semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.primary.main,
              boxShadow: `0 0 0 2px ${alpha(semanticSearchEnabled ? theme.palette.secondary.main : theme.palette.primary.main, 0.2)}`,
            },
          }}
        >
          <TextField
            inputRef={inputRef}
            fullWidth
            multiline
            maxRows={4}
            value={question}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask about genes, diseases, drugs, proteins... (use @ for autocomplete)"
            variant="standard"
            disabled={isLoading}
            InputProps={{
              disableUnderline: true,
              sx: { px: 1.5, py: 0.5, fontSize: '0.95rem' },
            }}
          />
          {isLoading ? (
            <IconButton 
              onClick={onCancel} 
              sx={{ 
                backgroundColor: theme.palette.error.main, 
                color: 'white', 
                '&:hover': { backgroundColor: theme.palette.error.dark } 
              }}
            >
              <StopIcon />
            </IconButton>
          ) : (
            <Box sx={{ display: 'flex', gap: 0.5 }}>
              <Tooltip title="Generate query only (you can edit before running)">
                <IconButton
                  onClick={onGenerateOnly}
                  disabled={!question.trim()}
                  sx={{
                    backgroundColor: alpha(theme.palette.secondary.main, 0.1),
                    color: theme.palette.secondary.main,
                    '&:hover': { backgroundColor: alpha(theme.palette.secondary.main, 0.2) },
                    '&.Mui-disabled': { 
                      backgroundColor: alpha(theme.palette.secondary.main, 0.05), 
                      color: alpha(theme.palette.secondary.main, 0.3) 
                    },
                  }}
                >
                  <CodeIcon />
                </IconButton>
              </Tooltip>
              <Tooltip title="Generate and run query">
                <IconButton
                  type="submit"
                  disabled={!question.trim()}
                  sx={{
                    backgroundColor: theme.palette.primary.main,
                    color: 'white',
                    '&:hover': { backgroundColor: theme.palette.primary.dark },
                    '&.Mui-disabled': { 
                      backgroundColor: alpha(theme.palette.primary.main, 0.3), 
                      color: alpha('#fff', 0.5) 
                    },
                  }}
                >
                  <SendIcon />
                </IconButton>
              </Tooltip>
            </Box>
          )}
        </Paper>

        {/* Autocomplete Suggestions Popup */}
        {showSuggestions && displaySuggestions.length > 0 && (
          <AutocompleteSuggestions
            suggestions={displaySuggestions}
            selectedIndex={selectedSuggestionIndex}
            onSuggestionClick={onSuggestionClick}
            suggestionsRef={suggestionsRef}
          />
        )}
      </Box>
      
      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block', textAlign: 'center' }}>
        <CodeIcon sx={{ fontSize: 12, verticalAlign: 'middle', mr: 0.5 }} /> Generate only • 
        <SendIcon sx={{ fontSize: 12, verticalAlign: 'middle', mx: 0.5 }} /> Generate & Run • 
        Type @ for autocomplete
      </Typography>
    </Box>
  );
}

export default ChatInput;
