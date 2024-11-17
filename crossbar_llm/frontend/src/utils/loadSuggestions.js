import axios from 'axios';

export const loadSuggestions = async () => {
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

  const suggestions = Array.from(suggestionsSet);

  return suggestions;
};