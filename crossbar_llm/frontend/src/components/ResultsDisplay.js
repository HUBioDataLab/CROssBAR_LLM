import React from 'react';
import { Typography, Card, CardContent, Box, useTheme } from '@mui/material';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';

function ResultsDisplay({ queryResult, executionResult, realtimeLogs }) {
  const theme = useTheme();
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;

  if (!queryResult && !executionResult) {
    return null;
  }

  return (
    <Box sx={{ mt: 4 }}>
      {queryResult && executionResult && (
        <Card sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="h6">Generated Cypher Query:</Typography>
            <SyntaxHighlighter 
              language="cypher" 
              style={syntaxTheme}
              customStyle={{
                backgroundColor: theme.palette.mode === 'dark' ? '#1e1e1e' : '#f5f5f5'
              }}
            >
              {queryResult}
            </SyntaxHighlighter>
          </CardContent>
        </Card>
      )}
      {executionResult && (
        <Card>
          <CardContent>
            <Typography variant="h6">Results:</Typography>
            {realtimeLogs && (
              <Card sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="h6">Real-time Logs:</Typography>
                  <SyntaxHighlighter 
                    language="plaintext" 
                    style={syntaxTheme}
                    customStyle={{
                      backgroundColor: theme.palette.mode === 'dark' ? '#1e1e1e' : '#f5f5f5'
                    }}
                  >
                    {realtimeLogs}
                  </SyntaxHighlighter>
                </CardContent>
              </Card>
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
            <SyntaxHighlighter 
              language="json" 
              style={syntaxTheme}
              customStyle={{
                backgroundColor: theme.palette.mode === 'dark' ? '#1e1e1e' : '#f5f5f5'
              }}
            >
              {JSON.stringify(executionResult.result, null, 2)}
            </SyntaxHighlighter>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

export default ResultsDisplay;