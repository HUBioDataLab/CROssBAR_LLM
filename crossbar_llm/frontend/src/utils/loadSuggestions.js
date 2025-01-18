import axios from 'axios';

const CACHE_KEY = 'crossbar_suggestions_cache';
const CACHE_EXPIRY = 24 * 60 * 60 * 1000;

const computeSuggestions = async () => {
  const fileNames = [];
  const context = require.context('../../public', false, /\.txt$/);
  context.keys().forEach((key) => {
    fileNames.push(key.replace('./', ''));
  });

  const suggestionsSet = new Set();

  for (const fileName of fileNames) {
    try {
      const response = await axios.get(`${process.env.PUBLIC_URL}/${fileName}`);
      const fileContent = response.data;
      const words = fileContent.split(/\s+/).filter(Boolean);
      words.forEach((word) => suggestionsSet.add(word));
    } catch (error) {
      console.error(`Error loading ${fileName}:`, error);
    }
  }

  return Array.from(suggestionsSet);
};

export const loadSuggestions = async () => {
  // Check localStorage for cached suggestions
  const cached = localStorage.getItem(CACHE_KEY);
  if (cached) {
    const { data, timestamp } = JSON.parse(cached);
    // Check if cache is still valid
    if (Date.now() - timestamp < CACHE_EXPIRY) {
      return data;
    }
  }

  // If no cache or expired, compute new suggestions
  const suggestions = await computeSuggestions();
  
  // Save to localStorage with timestamp
  localStorage.setItem(CACHE_KEY, JSON.stringify({
    data: suggestions,
    timestamp: Date.now()
  }));

  return suggestions;
};