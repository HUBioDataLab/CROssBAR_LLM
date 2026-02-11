import React, { useState, useEffect, useRef } from 'react';
import { 
  TextField, 
  List, 
  ListItem, 
  ListItemText, 
  Paper, 
  Typography,
  Box,
  useTheme,
  alpha,
  Fade,
  Portal,
  Tooltip,
  Zoom,
  Slide,
  Button,
  Collapse,
  Divider,
  IconButton
} from '@mui/material';
import Fuse from 'fuse.js';
import { loadSuggestions } from '../utils/loadSuggestions';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import CloseIcon from '@mui/icons-material/Close';

// Node type color mapping based on Neo4j style
const nodeTypeColors = {
  // Handle both formats: with and without spaces
  "BiologicalProcess": { bg: '#ff8800', text: '#FFFFFF' },
  "Biological Process": { bg: '#ff8800', text: '#FFFFFF' },
  "CellularComponent": { bg: '#ffc300', text: '#FFFFFF' },
  "Cellular Component": { bg: '#ffc300', text: '#FFFFFF' },
  "MolecularFunction": { bg: '#ffaa00', text: '#FFFFFF' },
  "Molecular Function": { bg: '#ffaa00', text: '#FFFFFF' },
  "Compound": { bg: '#d2b7e5', text: '#FFFFFF' },
  "Protein": { bg: '#3aa6a4', text: '#FFFFFF' },
  "ProteinDomain": { bg: '#6bbf59', text: '#FFFFFF' },
  "Protein Domain": { bg: '#6bbf59', text: '#FFFFFF' },
  "Gene": { bg: '#287271', text: '#FFFFFF' },
  "Drug": { bg: '#815ac0', text: '#000000' },
  "SideEffect": { bg: '#9ae9f8', text: '#FFFFFF' },
  "Side Effect": { bg: '#9ae9f8', text: '#FFFFFF' },
  "Phenotype": { bg: '#58d0e8', text: '#FFFFFF' },
  "Disease": { bg: '#079dbb', text: '#FFFFFF' },
  "Pathway": { bg: '#720026', text: '#FFFFFF' },
  "OrganismTaxon": { bg: '#a6a6a6', text: '#FFFFFF' },
  "Organism Taxon": { bg: '#a6a6a6', text: '#FFFFFF' },
  "Reaction": { bg: '#ce4257', text: '#FFFFFF' },
  // Default for any type not listed
  "default": { bg: '#A5ABB6', text: '#FFFFFF' }
};

function AutocompleteTextField({ 
  value, 
  setValue, 
  label, 
  placeholder,
  onKeyPress,
  customStyles = {},
  rows = 4,
  hideHint = false,
  disabled = false,
}) {
  const theme = useTheme();
  const [suggestions, setSuggestions] = useState([]);
  const [displaySuggestions, setDisplaySuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [cursorPosition, setCursorPosition] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const textFieldRef = useRef(null);
  const suggestionsRef = useRef(null);
  const containerRef = useRef(null);
  const [suggestionsPosition, setSuggestionsPosition] = useState({ top: 0, left: 0, width: 0 });
  const ITEM_HEIGHT = 48;
  const [mentions, setMentions] = useState([]); // [{start, end, state}] where state is 'typing', 'selecting', or 'completed'
  const [showHint, setShowHint] = useState(true);
  const [expandedHint, setExpandedHint] = useState(false);
  
  // Performance optimization: only activate complex rendering when @ is present
  const hasAtSymbol = value.includes('@');
  const debounceTimeoutRef = useRef(null);

  useEffect(() => {
    // Only load suggestions if @ symbol is present
    if (hasAtSymbol) {
      const fetchSuggestions = async () => {
        if (suggestions.length === 0) {
          const loadedSuggestions = await loadSuggestions();
          setSuggestions(loadedSuggestions);
        }
      };
      fetchSuggestions();
    }
  }, [hasAtSymbol, suggestions.length]);

  // Update suggestions position when they are shown
  useEffect(() => {
    if (showSuggestions && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setSuggestionsPosition({
        top: rect.bottom + window.scrollY,
        left: rect.left + window.scrollX,
        width: rect.width
      });
    }
  }, [showSuggestions]);

  const fuse = new Fuse(suggestions, {
    includeScore: true,
    threshold: 0.5,
    ignoreLocation: true,
    minMatchCharLength: 2,
    keys: ['term'],
  });

  const renderStyledText = () => {
    // Only render styled text if @ symbol is present
    if (!hasAtSymbol) {
      return value;
    }

    const parts = [];
    let lastIndex = 0;

    mentions.sort((a, b) => a.start - b.start).forEach((mention) => {
      // Text before mention
      if (mention.start > lastIndex) {
        parts.push(
          <span key={`text-${lastIndex}`}>
            {value.slice(lastIndex, mention.start)}
          </span>
        );
      }

      // Mentioned text
      const mentionText = value.slice(mention.start, mention.end);
      const color = 
        mention.state === 'typing' ? theme.palette.error.main : 
        mention.state === 'selecting' ? theme.palette.success.main : 
        theme.palette.text.primary;

      parts.push(
        <span key={`mention-${mention.start}`} style={{ color, fontWeight: 500 }}>
          {mentionText}
        </span>
      );

      lastIndex = mention.end;
    });

    // Remaining text
    if (lastIndex < value.length) {
      parts.push(
        <span key={`text-${lastIndex}`}>
          {value.slice(lastIndex)}
        </span>
      );
    }

    return parts;
  };

  // Initial setup - only show hint if field is empty and hideHint is false
  useEffect(() => {
    // Only show hint initially if the field is empty and hideHint is false
    if (!value && !hideHint) {
      setShowHint(true);
    } else {
      setShowHint(false);
    }
  }, [hideHint]);

  // Additional effect to monitor value changes - show hint when field becomes empty
  useEffect(() => {
    // If value becomes empty, show the hint
    if (value === '') {
      setShowHint(true);
    }
  }, [value]);

  const handleInputChange = (event) => {
    const newValue = event.target.value;
    const cursorPos = event.target.selectionStart;
    setValue(newValue);
    setCursorPosition(cursorPos);
    setSelectedIndex(0);
    
    // Clear existing timeout
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    // Only do complex processing if @ symbol is present
    if (!newValue.includes('@')) {
      // Reset all mention-related state when no @ symbol
      setMentions([]);
      setShowSuggestions(false);
      setDisplaySuggestions([]);
      return;
    }

    // Clean up mentions when text is deleted
    setMentions(prevMentions => 
      prevMentions.filter(mention => 
        mention.start < newValue.length && 
        newValue.slice(mention.start, mention.end) === value.slice(mention.start, mention.end)
      )
    );

    // Add new mention when @ is typed
    if (newValue[cursorPos - 1] === '@') {
      setMentions(prevMentions => [...prevMentions, {
        start: cursorPos - 1,
        end: cursorPos,
        state: 'typing'
      }]);
    }

    // Update mentions state when typing
    const lastAtSymbol = newValue.lastIndexOf('@', cursorPos - 1);
    if (lastAtSymbol !== -1) {
      setMentions(prevMentions => 
        prevMentions.map(mention => {
          if (mention.start === lastAtSymbol) {
            return {
              ...mention,
              end: cursorPos,
              state: 'typing'
            };
          }
          return mention;
        })
      );
    }

    // Only set up debounce if @ symbol is present
    debounceTimeoutRef.current = setTimeout(() => {
      const lastAtSymbol = newValue.lastIndexOf('@', cursorPosition - 1);

      if (lastAtSymbol !== -1) {
        const query = newValue.slice(lastAtSymbol + 1, cursorPosition+1);
        // Convert spaces to underscores in query to match the format of suggestions
        const formattedQuery = query.replace(/\s+/g, '_');
        
        if (query.length > 1) { 
          let matchedSuggestions;
          
          // First try direct inclusion for exact matches
          if (query.length > 3) {
            matchedSuggestions = suggestions.filter(s => 
              s.term.toLowerCase().includes(formattedQuery.toLowerCase())
            )
            // Sort by length to prioritize shorter suggestions
            .sort((a, b) => a.term.length - b.term.length)
            .slice(0, 15); // Limit to 15 results
          }
          
          // Only use fuzzy search if query is more than 3 characters
          if ((!matchedSuggestions || matchedSuggestions.length === 0) && query.length > 3) {
            const results = fuse.search(formattedQuery);
            matchedSuggestions = results.map((result) => result.item)
              // Sort by length to prioritize shorter suggestions
              .sort((a, b) => a.term.length - b.term.length)
              .slice(0, 15);
          }
          
          setDisplaySuggestions(matchedSuggestions || []);
          setShowSuggestions(matchedSuggestions && matchedSuggestions.length > 0);
        } else {
          setShowSuggestions(false);
        }
      } else {
        setShowSuggestions(false);
      }
    }, 300);
  };

  useEffect(() => {
    if (showSuggestions && displaySuggestions.length > 0) {
      // Update mention state to 'selecting' when suggestions are shown
      const lastAtSymbol = value.lastIndexOf('@', cursorPosition - 1);
      if (lastAtSymbol !== -1) {
        setMentions(prevMentions => 
          prevMentions.map(mention => {
            if (mention.start === lastAtSymbol) {
              return {
                ...mention,
                state: 'selecting'
              };
            }
            return mention;
          })
        );
      }
    }
  }, [showSuggestions, displaySuggestions, cursorPosition, value]);

  const handleKeyDown = (event) => {
    if (!showSuggestions) return;

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setSelectedIndex((prev) => {
          const newIndex = prev < displaySuggestions.length - 1 ? prev + 1 : prev;
          scrollSelectedIntoView(newIndex);
          return newIndex;
        });
        break;
      case 'ArrowUp':
        event.preventDefault();
        setSelectedIndex((prev) => {
          const newIndex = prev > 0 ? prev - 1 : prev;
          scrollSelectedIntoView(newIndex);
          return newIndex;
        });
        break;
      case 'Tab':
      case 'Enter':
        event.preventDefault();
        if (displaySuggestions[selectedIndex]) {
          handleSuggestionClick(displaySuggestions[selectedIndex]);
        }
        break;
      case 'Escape':
        setShowSuggestions(false);
        break;
    }
  };

  const scrollSelectedIntoView = (index) => {
    if (!suggestionsRef.current) return;

    const container = suggestionsRef.current;
    const selectedElement = container.children[0].children[index];
    
    if (!selectedElement) return;

    const containerHeight = container.clientHeight;
    const scrollTop = container.scrollTop;
    const elementTop = selectedElement.offsetTop;
    const elementBottom = elementTop + ITEM_HEIGHT;

    if (elementBottom > scrollTop + containerHeight) {
      // Scroll down
      container.scrollTo({
        top: elementBottom - containerHeight,
        behavior: 'smooth'
      });
    } else if (elementTop < scrollTop) {
      // Scroll up
      container.scrollTo({
        top: elementTop,
        behavior: 'smooth'
      });
    }
  };

  const handleSuggestionClick = (suggestion) => {
    // Replace underscores with spaces when using the suggestion in the text field
    const displayTerm = suggestion.term.replaceAll('_', ' ');
    // Format as "Term <Type>"
    const displaySuggestion = `${displayTerm} <<${suggestion.type}>>`;
    const textBeforeCursor = value.slice(0, cursorPosition);
    const textAfterCursor = value.slice(cursorPosition);
    const lastAtSymbol = textBeforeCursor.lastIndexOf('@');

    const newTextBeforeCursor =
      textBeforeCursor.slice(0, lastAtSymbol) + displaySuggestion + ' ';
    const newCursorPosition = newTextBeforeCursor.length;

    const newValue = newTextBeforeCursor + textAfterCursor;

    // Update mention state with completed suggestion
    setMentions(prevMentions => 
      prevMentions.map(mention => {
        if (mention.start === lastAtSymbol) {
          return {
            start: lastAtSymbol,
            end: lastAtSymbol + displaySuggestion.length,
            state: 'completed'
          };
        }
        return mention;
      }).filter(mention => mention.start !== mention.end) // Remove empty mentions
    );

    setValue(newValue);
    setShowSuggestions(false);

    setTimeout(() => {
      if (textFieldRef.current) {
        textFieldRef.current.setSelectionRange(newCursorPosition, newCursorPosition);
      }
    }, 0);
  };

  return (
    <div ref={containerRef} style={{ position: 'relative', ...(customStyles.container || {}) }}>
      <div style={{ position: 'relative' }}>
        <TextField
          inputRef={textFieldRef}
          label={label}
          placeholder={placeholder}
          value={value}
          onChange={handleInputChange}
          onKeyDown={(e) => {
            handleKeyDown(e);
            // Also call the custom onKeyPress handler if provided
            if (onKeyPress && !showSuggestions) {
              onKeyPress(e);
            }
          }}
          onFocus={() => {
            // Only show hint on focus if the field is empty and hint is not already shown
            if (!value && !showHint && !hideHint) {
              setShowHint(true);
            }
          }}
          fullWidth
          multiline
          rows={rows}
          margin="normal"
          disabled={disabled}
          sx={{
            '& .MuiInputBase-input': {
              // Only make text transparent if @ symbol is present
              color: hasAtSymbol ? 'transparent' : theme.palette.text.primary,
              caretColor: theme.palette.primary.main,
              fontFamily: theme.typography.fontFamily,
              fontSize: '1rem',
            },
            '& .MuiOutlinedInput-root': {
              borderRadius: '12px',
              transition: 'all 0.2s ease-in-out',
              '&:hover': {
                boxShadow: `0 0 0 2px ${alpha(theme.palette.primary.main, 0.1)}`,
              },
              '&.Mui-focused': {
                boxShadow: `0 0 0 3px ${alpha(theme.palette.primary.main, 0.2)}`,
              }
            },
            ...(customStyles.container || {}),
          }}
        />
        {/* Only render overlay when @ symbol is present */}
        {hasAtSymbol && (
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              pointerEvents: 'none',
              padding: '16.5px 14px',
              marginTop: '16px',
              fontFamily: theme.typography.fontFamily,
              fontSize: '1rem',
              lineHeight: '1.5',
              whiteSpace: 'pre-wrap',
            }}
          >
            {value ? renderStyledText() : (
              <span style={{ color: theme.palette.text.disabled }}>
                {placeholder}
              </span>
            )}
          </div>
        )}
      </div>
      
      {/* Enhanced Autocomplete hint with slide animation */}
      {showHint && !hideHint && (
        <Slide 
          direction="up" 
          in={showHint} 
          timeout={400} 
          unmountOnExit
          mountOnEnter
        >
          <Paper
            elevation={1}
            sx={{
              mt: 1,
              mb: 2,
              p: 1,
              borderRadius: '8px',
              border: `1px solid ${alpha(theme.palette.info.main, 0.3)}`,
              backgroundColor: alpha(theme.palette.info.main, 0.05),
              position: 'relative',
              transformOrigin: 'bottom',
            }}
          >
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <InfoOutlinedIcon 
                  fontSize="small" 
                  sx={{ 
                    fontSize: '18px', 
                    mr: 1,
                    mt: 0.2, 
                    color: theme.palette.info.main 
                  }} 
                />
                <Box>
                  <Typography 
                    variant="subtitle2" 
                    sx={{ 
                      color: theme.palette.info.main,
                      fontWeight: 500,
                    }}
                  >
                    Entity Autocomplete Available
                  </Typography>
                  <Typography 
                    variant="body2" 
                    sx={{ 
                      color: theme.palette.text.secondary,
                      fontWeight: 400,
                    }}
                  >
                    Type @ followed by at least 3 characters to search for biomedical entities
                  </Typography>
                </Box>
              </Box>
              
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Button
                  size="small"
                  color="info"
                  sx={{ minWidth: '30px', mr: 1 }}
                  onClick={() => {
                    setExpandedHint(!expandedHint);
                  }}
                  endIcon={expandedHint ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                >
                  {expandedHint ? "Less" : "More"}
                </Button>
                <IconButton 
                  size="small" 
                  onClick={() => setShowHint(false)}
                  sx={{ color: theme.palette.text.secondary }}
                  aria-label="Close hint"
                >
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Box>
            </Box>
            
            <Collapse in={expandedHint} timeout="auto">
              <Divider sx={{ my: 1.5 }} />
              <Box sx={{ py: 0.5 }}>
                <Typography variant="body2" paragraph sx={{ mb: 1 }}>
                  <strong>How to use autocomplete:</strong>
                </Typography>
                <Box component="ol" sx={{ pl: 2, mt: 0, mb: 1.5 }}>
                  <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
                    Type <code style={{ backgroundColor: alpha(theme.palette.primary.main, 0.1), padding: '2px 4px', borderRadius: '3px' }}>@</code> symbol followed by the entity name you're looking for.
                  </Typography>
                  <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
                    After typing at least 3 characters, a dropdown menu will appear with matching entities.
                  </Typography>
                  <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
                    Use <strong>arrow keys</strong> to navigate the suggestions, <strong>Enter</strong> or <strong>Tab</strong> to select.
                  </Typography>
                  <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
                    You can also click on a suggestion to select it.
                  </Typography>
                </Box>
                <Typography variant="body2" paragraph sx={{ mb: 1 }}>
                  <strong>Available entity types include:</strong> genes, proteins, diseases, drugs, pathways and more.
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic', mt: 1 }}>
                  This feature helps ensure accurate entity names in your queries and improves search results.
                </Typography>
              </Box>
            </Collapse>
          </Paper>
        </Slide>
      )}
      
      {showSuggestions && displaySuggestions.length > 0 && (
        <Portal>
          <Fade in={showSuggestions} timeout={200}>
            <Paper
              ref={suggestionsRef}
              elevation={6}
              sx={{
                position: 'absolute',
                zIndex: 9999,
                maxHeight: 350,
                overflowY: 'auto',
                width: suggestionsPosition.width,
                top: suggestionsPosition.top,
                left: suggestionsPosition.left,
                borderRadius: '12px',
                boxShadow: theme.shadows[8],
                '&::-webkit-scrollbar': {
                  width: '8px',
                },
                '&::-webkit-scrollbar-thumb': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.2),
                  borderRadius: '4px',
                },
                '&::-webkit-scrollbar-track': {
                  backgroundColor: alpha(theme.palette.background.paper, 0.5),
                }
              }}
            >
              <List sx={{ py: 1 }}>
                {displaySuggestions.map((suggestion, index) => (
                  <ListItem
                    button
                    key={index}
                    onClick={() => handleSuggestionClick(suggestion)}
                    selected={index === selectedIndex}
                    sx={{
                      py: 1,
                      px: 2,
                      transition: 'all 0.15s ease-in-out',
                      borderLeft: index === selectedIndex 
                        ? `4px solid ${theme.palette.primary.main}` 
                        : '4px solid transparent',
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
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <Typography 
                            variant="body1" 
                            sx={{ 
                              fontWeight: index === selectedIndex ? 500 : 400,
                              color: index === selectedIndex 
                                ? theme.palette.primary.main 
                                : theme.palette.text.primary
                            }}
                          >
                            {suggestion.term.replace(/_/g, ' ')}
                          </Typography>
                          <Typography 
                            variant="caption"
                            sx={{ 
                              color: nodeTypeColors[suggestion.type]?.text || nodeTypeColors.default.text,
                              backgroundColor: nodeTypeColors[suggestion.type]?.bg || nodeTypeColors.default.bg,
                              borderRadius: '4px',
                              px: 1,
                              py: 0.5,
                              ml: 1,
                              fontWeight: 500
                            }}
                          >
                            {suggestion.type}
                          </Typography>
                        </Box>
                      } 
                    />
                  </ListItem>
                ))}
              </List>
            </Paper>
          </Fade>
        </Portal>
      )}
    </div>
  );
}

export default AutocompleteTextField;
