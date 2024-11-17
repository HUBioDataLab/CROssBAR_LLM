import React from 'react';
import { Typography, Card, CardContent, Box } from '@mui/material';

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
            <Typography
              variant="body1"
              component="pre"
              sx={{
                whiteSpace: 'pre-wrap',
                wordWrap: 'break-word',
                fontFamily: 'monospace',
                mt: 1,
              }}
            >
              {queryResult}
            </Typography>
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
                <Typography
                  variant="body2"
                  component="pre"
                  sx={{
                    whiteSpace: 'pre-wrap',
                    wordWrap: 'break-word',
                    fontFamily: 'monospace',
                    mt: 1,
                  }}
                >
                  {executionResult.verbose}
                </Typography>
              </>
            )}
            <Typography variant="subtitle1" sx={{ mt: 2 }}>
              Natural Language Response:
            </Typography>
            <Typography variant="body1" sx={{ mt: 1 }}>
              {executionResult.response}
            </Typography>
            <Typography variant="subtitle1" sx={{ mt: 2 }}>
              Raw Query Output:
            </Typography>
            <Typography
              variant="body1"
              component="pre"
              sx={{
                whiteSpace: 'pre-wrap',
                wordWrap: 'break-word',
                fontFamily: 'monospace',
                mt: 1,
              }}
            >
              {JSON.stringify(executionResult.result, null, 2)}
            </Typography>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

export default ResultsDisplay;