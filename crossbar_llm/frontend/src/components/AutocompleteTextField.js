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

  const handleInputChange = (event) => {
    const newValue = event.target.value;
    setValue(newValue);
    setCursorPosition(event.target.selectionStart);
    setSelectedIndex(0);
  
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    debounceTimeoutRef.current = setTimeout(() => {
      const lastAtSymbol = newValue.lastIndexOf('@', cursorPosition - 1);

      if (lastAtSymbol !== -1) {
        const query = newValue.slice(lastAtSymbol + 1, cursorPosition);
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
    const textBeforeCursor = value.slice(0, cursorPosition);
    const textAfterCursor = value.slice(cursorPosition);
    const lastAtSymbol = textBeforeCursor.lastIndexOf('@');

    const newTextBeforeCursor =
      textBeforeCursor.slice(0, lastAtSymbol) + suggestion + ' ';
    const newCursorPosition = newTextBeforeCursor.length;

    const newValue = newTextBeforeCursor + textAfterCursor;
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
      />
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