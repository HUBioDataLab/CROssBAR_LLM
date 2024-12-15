import React from 'react';
import { Typography, Card, CardContent, Box } from '@mui/material';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';

function ResultsDisplay({ queryResult, executionResult }) {
  if (!queryResult && !executionResult) {
    return null;
  }

  return (
    <Box sx={{ mt: 4 }}>
      {queryResult && executionResult && (
        <Card sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="h6">Generated Cypher Query:</Typography>
            <SyntaxHighlighter language="cypher" style={dracula}>
              {queryResult}
            </SyntaxHighlighter>
          </CardContent>
        </Card>
      )}
      {executionResult && (
        <Card>
          <CardContent>
            <Typography variant="h6">Results:</Typography>
            {executionResult.verbose && (
              <>
                <Typography variant="subtitle1" sx={{ mt: 2 }}>
                  Verbose Output:
                </Typography>
                <SyntaxHighlighter language="plaintext" style={dracula}>
                  {executionResult.verbose}
                </SyntaxHighlighter>
              </>
            )}
            <Typography variant="body1" sx={{ mt: 2, fontWeight: 'bold' }}>
              Natural Language Response:
            </Typography>
            <Typography variant="body1" sx={{ mt: 1, mb: 2 }}>
              {executionResult.response}
            </Typography>
            <Box sx={{ height: 16 }} />
            <Typography variant="subtitle1" sx={{ mt: 2 }}>
              Raw Query Output:
            </Typography>
            <SyntaxHighlighter language="json" style={dracula}>
              {JSON.stringify(executionResult.result, null, 2)}
            </SyntaxHighlighter>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

export default ResultsDisplay;