import React, { useState, useEffect, useRef } from 'react';
import { TextField, List, ListItem, ListItemText, Paper } from '@mui/material';
import Fuse from 'fuse.js';
import { loadSuggestions } from '../utils/loadSuggestions';

function AutocompleteTextField({ value, setValue, label, placeholder }) {
  const [suggestions, setSuggestions] = useState([]);
  const [displaySuggestions, setDisplaySuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [cursorPosition, setCursorPosition] = useState(0);
  const textFieldRef = useRef(null);

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
  
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    debounceTimeoutRef.current = setTimeout(() => {
      const lastAtSymbol = newValue.lastIndexOf('@', cursorPosition - 1);

      if (lastAtSymbol !== -1) {
        const query = newValue.slice(lastAtSymbol + 1, cursorPosition);
        if (query.length > 0) {
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

    // Set cursor position
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
        fullWidth
        multiline
        rows={4}
        margin="normal"
      />
      {showSuggestions && displaySuggestions.length > 0 && (
        <Paper
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