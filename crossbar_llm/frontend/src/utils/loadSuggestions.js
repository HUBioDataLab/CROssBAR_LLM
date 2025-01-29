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
      words.forEach((word) => {
        if (word.length > 2) {
          suggestionsSet.add(word);
        }
      });
    } catch (error) {
      console.error(`Error loading ${fileName}:`, error);
    }
  }

  const suggestionsArray = Array.from(suggestionsSet);
  return suggestionsArray;
};

const fetchSuggestions = async () => {
  const response = await axios.get(`${process.env.PUBLIC_URL}/suggestions.json`);
  console.log('Fetched suggestions:', response.data);
  return response.data;
};

function chunkArray(array, size) {
  const chunks = [];
  for (let i = 0; i < array.length; i += size) {
    chunks.push(array.slice(i, i + size));
  }
  return chunks;
}

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

  // try reading chunk info
  const chunkCount = parseInt(localStorage.getItem(CACHE_KEY + '_chunkCount') || '0', 10);
  if (chunkCount > 0) {
    const reassembled = [];
    for (let i = 0; i < chunkCount; i++) {
      const part = localStorage.getItem(CACHE_KEY + '_chunk_' + i);
      if (part) reassembled.push(...JSON.parse(part));
    }
    return reassembled;
  }

  // If no cache or expired, fetch new suggestions
  const suggestions = await fetchSuggestions();
  
  // Save to localStorage with timestamp
  try {
    // clear any old chunks
    const oldChunks = parseInt(localStorage.getItem(CACHE_KEY + '_chunkCount') || '0', 10);
    for (let i = 0; i < oldChunks; i++) {
      localStorage.removeItem(CACHE_KEY + '_chunk_' + i);
    }

    // split and store new data
    const chunked = chunkArray(suggestions, 1000);
    localStorage.setItem(CACHE_KEY + '_chunkCount', chunked.length.toString());
    chunked.forEach((c, idx) => {
      localStorage.setItem(CACHE_KEY + '_chunk_' + idx, JSON.stringify(c));
    });
  } catch (error) {
    console.warn('Storage limit reached, skipping chunk caching:', error);
  }

  return suggestions;
};