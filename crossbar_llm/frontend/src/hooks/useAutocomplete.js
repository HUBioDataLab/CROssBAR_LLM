import { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import Fuse from 'fuse.js';
import { loadSuggestions } from '../utils/loadSuggestions';

/**
 * Hook for managing autocomplete functionality with Fuse.js fuzzy search.
 * 
 * @param {string} question - Current input value
 * @param {function} setQuestion - Function to update input value
 * @returns {Object} Autocomplete state and handlers
 */
export function useAutocomplete(question, setQuestion) {
  const [suggestions, setSuggestions] = useState([]);
  const [displaySuggestions, setDisplaySuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedSuggestionIndex, setSelectedSuggestionIndex] = useState(0);
  const [cursorPosition, setCursorPosition] = useState(0);
  
  const debounceTimeoutRef = useRef(null);

  // Load suggestions when @ is typed
  useEffect(() => {
    const hasAtSymbol = question.includes('@');
    if (hasAtSymbol && suggestions.length === 0) {
      const fetchSuggestions = async () => {
        const loadedSuggestions = await loadSuggestions();
        setSuggestions(loadedSuggestions);
      };
      fetchSuggestions();
    }
  }, [question, suggestions.length]);

  // Fuse.js instance for fuzzy search
  const fuse = useMemo(() => new Fuse(suggestions, {
    includeScore: true,
    threshold: 0.5,
    ignoreLocation: true,
    minMatchCharLength: 2,
    keys: ['term'],
  }), [suggestions]);

  // Handle input changes with autocomplete
  const handleAutocompleteChange = useCallback((newValue, cursorPos) => {
    setQuestion(newValue);
    setCursorPosition(cursorPos);
    setSelectedSuggestionIndex(0);

    // Clear existing timeout
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    // Only process if @ symbol is present
    if (!newValue.includes('@')) {
      setShowSuggestions(false);
      setDisplaySuggestions([]);
      return;
    }

    // Debounce search
    debounceTimeoutRef.current = setTimeout(() => {
      const lastAtSymbol = newValue.lastIndexOf('@', cursorPos - 1);

      if (lastAtSymbol !== -1) {
        const query = newValue.slice(lastAtSymbol + 1, cursorPos);
        const formattedQuery = query.replace(/\s+/g, '_');

        if (query.length > 2) {
          let matchedSuggestions;

          // First try direct inclusion for exact matches
          matchedSuggestions = suggestions.filter(s =>
            s.term.toLowerCase().includes(formattedQuery.toLowerCase())
          )
            .sort((a, b) => a.term.length - b.term.length)
            .slice(0, 10);

          // Use fuzzy search if no direct matches
          if (matchedSuggestions.length === 0) {
            const results = fuse.search(formattedQuery);
            matchedSuggestions = results.map((result) => result.item)
              .sort((a, b) => a.term.length - b.term.length)
              .slice(0, 10);
          }

          setDisplaySuggestions(matchedSuggestions);
          setShowSuggestions(matchedSuggestions.length > 0);
        } else {
          setShowSuggestions(false);
        }
      } else {
        setShowSuggestions(false);
      }
    }, 200);
  }, [suggestions, fuse, setQuestion]);

  // Handle suggestion selection
  const handleSuggestionClick = useCallback((suggestion) => {
    const displayTerm = suggestion.term.replaceAll('_', ' ');
    const displaySuggestion = `${displayTerm} (${suggestion.type})`;
    const textBeforeCursor = question.slice(0, cursorPosition);
    const textAfterCursor = question.slice(cursorPosition);
    const lastAtSymbol = textBeforeCursor.lastIndexOf('@');

    const newTextBeforeCursor = textBeforeCursor.slice(0, lastAtSymbol) + displaySuggestion + ' ';
    const newValue = newTextBeforeCursor + textAfterCursor;

    setQuestion(newValue);
    setShowSuggestions(false);
  }, [question, cursorPosition, setQuestion]);

  // Handle keyboard navigation
  const handleAutocompleteKeyDown = useCallback((e) => {
    if (!showSuggestions) return false;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedSuggestionIndex((prev) =>
          prev < displaySuggestions.length - 1 ? prev + 1 : prev
        );
        return true;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedSuggestionIndex((prev) => (prev > 0 ? prev - 1 : prev));
        return true;
      case 'Tab':
      case 'Enter':
        if (displaySuggestions[selectedSuggestionIndex]) {
          e.preventDefault();
          handleSuggestionClick(displaySuggestions[selectedSuggestionIndex]);
          return true;
        }
        return false;
      case 'Escape':
        setShowSuggestions(false);
        return true;
      default:
        return false;
    }
  }, [showSuggestions, displaySuggestions, selectedSuggestionIndex, handleSuggestionClick]);

  // Close suggestions
  const closeSuggestions = useCallback(() => {
    setShowSuggestions(false);
  }, []);

  return {
    // State
    suggestions,
    displaySuggestions,
    showSuggestions,
    selectedSuggestionIndex,
    cursorPosition,
    // Handlers
    handleAutocompleteChange,
    handleSuggestionClick,
    handleAutocompleteKeyDown,
    closeSuggestions,
  };
}

export default useAutocomplete;
