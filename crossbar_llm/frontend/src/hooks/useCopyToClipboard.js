import { useState, useCallback } from 'react';

/**
 * Hook for copying text to clipboard with feedback.
 * 
 * @param {number} feedbackDuration - Duration to show copied feedback in ms
 * @returns {Object} Copy state and handler
 */
export function useCopyToClipboard(feedbackDuration = 2000) {
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [copySnackbar, setCopySnackbar] = useState(false);

  const handleCopy = useCallback(async (text, index) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIndex(index);
      setCopySnackbar(true);
      setTimeout(() => {
        setCopiedIndex(null);
        setCopySnackbar(false);
      }, feedbackDuration);
      return true;
    } catch (err) {
      console.error('Failed to copy:', err);
      return false;
    }
  }, [feedbackDuration]);

  return {
    copiedIndex,
    copySnackbar,
    handleCopy,
    setCopySnackbar,
  };
}

export default useCopyToClipboard;
