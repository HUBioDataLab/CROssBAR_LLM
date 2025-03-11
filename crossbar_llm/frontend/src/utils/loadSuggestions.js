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
  console.log('Fetched suggestions count:', response.data.length);
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
    try {
      const { data, timestamp } = JSON.parse(cached);
      // Check if cache is still valid
      if (Date.now() - timestamp < CACHE_EXPIRY) {
        return data;
      }
    } catch (error) {
      console.error('Error parsing cached suggestions:', error);
      localStorage.removeItem(CACHE_KEY);
    }
  }

  // try reading chunk info
  const chunkCount = parseInt(localStorage.getItem(CACHE_KEY + '_chunkCount') || '0', 10);
  if (chunkCount > 0) {
    try {
      const reassembled = [];
      let allChunksValid = true;
      
      for (let i = 0; i < chunkCount; i++) {
        const part = localStorage.getItem(CACHE_KEY + '_chunk_' + i);
        if (part) {
          try {
            const parsedPart = JSON.parse(part);
            reassembled.push(...parsedPart);
          } catch (error) {
            console.error(`Error parsing chunk ${i}:`, error);
            allChunksValid = false;
            break;
          }
        } else {
          console.warn(`Chunk ${i} not found in localStorage`);
          allChunksValid = false;
          break;
        }
      }
      
      if (allChunksValid) {
        return reassembled;
      }
    } catch (error) {
      console.error('Error reassembling chunks:', error);
    }
  }

  // If no cache or expired, fetch new suggestions
  const suggestions = await fetchSuggestions();
  
  // Save to localStorage with timestamp
  try {
    // Try to save the whole array first
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify({
        data: suggestions,
        timestamp: Date.now()
      }));
      return suggestions;
    } catch (error) {
      console.warn('Error saving to localStorage, will try chunking:', error);
    }
    
    // clear any old chunks
    const oldChunks = parseInt(localStorage.getItem(CACHE_KEY + '_chunkCount') || '0', 10);
    for (let i = 0; i < oldChunks; i++) {
      localStorage.removeItem(CACHE_KEY + '_chunk_' + i);
    }

    // split and store new data
    const chunked = chunkArray(suggestions, 1000);
    localStorage.setItem(CACHE_KEY + '_chunkCount', chunked.length.toString());
    
    let allChunksSaved = true;
    for (let i = 0; i < chunked.length; i++) {
      try {
        localStorage.setItem(CACHE_KEY + '_chunk_' + i, JSON.stringify(chunked[i]));
      } catch (error) {
        console.error(`Failed to save chunk ${i}:`, error);
        allChunksSaved = false;
        break;
      }
    }
    
    if (!allChunksSaved) {
      // If we couldn't save all chunks, try with smaller chunk size
      console.warn('Not all chunks saved, trying smaller chunk size');
      // Clear previous failed chunks
      for (let i = 0; i < chunked.length; i++) {
        localStorage.removeItem(CACHE_KEY + '_chunk_' + i);
      }
      
      const smallerChunked = chunkArray(suggestions, 500);
      localStorage.setItem(CACHE_KEY + '_chunkCount', smallerChunked.length.toString());
      
      for (let i = 0; i < smallerChunked.length; i++) {
        try {
          localStorage.setItem(CACHE_KEY + '_chunk_' + i, JSON.stringify(smallerChunked[i]));
        } catch (error) {
          console.error(`Failed to save smaller chunk ${i}:`, error);
          // At this point, we just give up on chunking
          localStorage.setItem(CACHE_KEY + '_chunkCount', '0');
          break;
        }
      }
    }
  } catch (error) {
    console.error('Storage error during chunking:', error);
  }

  return suggestions;
};