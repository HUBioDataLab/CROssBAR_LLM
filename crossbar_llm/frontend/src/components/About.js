import React from 'react';
import { Typography, Container } from '@mui/material';

function About() {
  return (
    <Container sx={{ mt: 4 }}>
      <Typography variant="h4" align="center">
        About This Site
      </Typography>
      <Typography variant="body1" sx={{ mt: 2 }}>
        Welcome to the CROssBAR LLM Query Interface. This platform allows you to generate and execute Cypher queries on a Neo4j database using various Large Language Models (LLMs). You can input natural language questions, and the system will generate the corresponding Cypher queries, which you can run to get detailed results from the database.
      </Typography>
      <Typography variant="h5" sx={{ mt: 4 }}>
        How to Use
      </Typography>
      <Typography variant="body1" sx={{ mt: 2 }}>
        <ol>
          <li>Select an LLM from the list provided.</li>
          <li>Enter your API key for the selected LLM.</li>
          <li>Type your question into the input field. You can use the sample questions provided for inspiration.</li>
          <li>Choose the limit for query returns if needed.</li>
          <li>Enable verbose mode for detailed logs (optional).</li>
          <li>Click "Generate & Run Query" to execute, or use the individual buttons to generate or run queries separately.</li>
        </ol>
      </Typography>
      <Typography variant="h5" sx={{ mt: 4 }}>
        Features
      </Typography>
      <Typography variant="body1" sx={{ mt: 2 }}>
        <ul>
          <li>Supports multiple LLMs for query generation.</li>
          <li>Limit the number of results returned from queries.</li>
          <li>Verbose mode for detailed execution logs.</li>
          <li>View database statistics including node and relationship counts.</li>
          <li>Upload vector files for advanced vector search queries.</li>
        </ul>
      </Typography>
    </Container>
  );
}

export default About;