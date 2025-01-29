import React, { useState, useEffect, useRef } from 'react';
import { TextField, List, ListItem, ListItemText, Paper } from '@mui/material';
import Fuse from 'fuse.js';
import { loadSuggestions } from '../utils/loadSuggestions';

function AutocompleteTextField({ value, setValue, label, placeholder }) {
  const [suggestions, setSuggestions] = useState([]);
  const [displaySuggestions, setDisplaySuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [cursorPosition, setCursorPosition] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const textFieldRef = useRef(null);
  const suggestionsRef = useRef(null);
  const ITEM_HEIGHT = 48;
  const [mentions, setMentions] = useState([]); // [{start, end, state}] where state is 'typing', 'selecting', or 'completed'

  useEffect(() => {
    const fetchSuggestions = async () => {
      const loadedSuggestions = await loadSuggestions();
      setSuggestions(loadedSuggestions);
    };
    fetchSuggestions();
  }, []);

  const fuse = new Fuse(suggestions, {
    includeScore: true,
    threshold: 0.3,
  });

  const debounceTimeoutRef = useRef(null);

  const renderStyledText = () => {
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
        mention.state === 'typing' ? '#ff6b6b' : 
        mention.state === 'selecting' ? '#51cf66' : 
        '#000000';

      parts.push(
        <span key={`mention-${mention.start}`} style={{ color }}>
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

  const handleInputChange = (event) => {
    const newValue = event.target.value;
    const cursorPos = event.target.selectionStart;
    setValue(newValue);
    setCursorPosition(cursorPos);
    setSelectedIndex(0);

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

    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    debounceTimeoutRef.current = setTimeout(() => {
      const lastAtSymbol = newValue.lastIndexOf('@', cursorPosition - 1);

      if (lastAtSymbol !== -1) {
        const query = newValue.slice(lastAtSymbol + 1, cursorPosition+1);
        if (query.length > 2) {
          const results = fuse.search(query);
          const matchedSuggestions = results.map((result) => result.item);
          setDisplaySuggestions(matchedSuggestions);
          setShowSuggestions(true);
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
    suggestion = suggestion.replaceAll('_', ' ');
    const textBeforeCursor = value.slice(0, cursorPosition);
    const textAfterCursor = value.slice(cursorPosition);
    const lastAtSymbol = textBeforeCursor.lastIndexOf('@');

    const newTextBeforeCursor =
      textBeforeCursor.slice(0, lastAtSymbol) + suggestion + ' ';
    const newCursorPosition = newTextBeforeCursor.length;

    const newValue = newTextBeforeCursor + textAfterCursor;

    // Update mention state with completed suggestion
    setMentions(prevMentions => 
      prevMentions.map(mention => {
        if (mention.start === lastAtSymbol) {
          return {
            start: lastAtSymbol,
            end: lastAtSymbol + suggestion.length,
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
    <div style={{ position: 'relative' }}>
      <div style={{ position: 'relative' }}>
        <TextField
          inputRef={textFieldRef}
          label={label}
          placeholder={placeholder}
          value={value}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          fullWidth
          multiline
          rows={4}
          margin="normal"
          sx={{
            '& .MuiInputBase-input': {
              color: 'transparent',
              caretColor: 'black',
            },
          }}
        />
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
            fontFamily: 'inherit',
            fontSize: 'inherit',
            lineHeight: '1.5',
            whiteSpace: 'pre-wrap',
          }}
        >
          {renderStyledText()}
        </div>
      </div>
      {showSuggestions && displaySuggestions.length > 0 && (
        <Paper
          ref={suggestionsRef}
          style={{
            position: 'absolute',
            zIndex: 9999,
            maxHeight: 200,
            overflowY: 'auto',
            width: '100%',
          }}
        >
          <List>
            {displaySuggestions.map((suggestion, index) => (
              <ListItem
                button
                key={index}
                onClick={() => handleSuggestionClick(suggestion)}
                selected={index === selectedIndex}
                style={{
                  backgroundColor: index === selectedIndex ? '#e3f2fd' : 'transparent'
                }}
              >
                <ListItemText primary={suggestion} />
              </ListItem>
            ))}
          </List>
        </Paper>
      )}
    </div>
  );
}

export default AutocompleteTextField;