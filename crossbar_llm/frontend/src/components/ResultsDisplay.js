import React, { useState } from 'react';
import { Typography, Card, CardContent, Box, useTheme, IconButton, Dialog, DialogContent, Snackbar } from '@mui/material';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import FullscreenIcon from '@mui/icons-material/Fullscreen';

function ResultsDisplay({ queryResult, executionResult, realtimeLogs }) {
  const theme = useTheme();
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [copySnackbar, setCopySnackbar] = useState(false);

  if (!queryResult && !executionResult) {
    return null;
  }

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text);
    setCopySnackbar(true);
  };

  return (
    <Box sx={{ mt: 4 }}>
      {executionResult && (
        <Card sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="body1" sx={{ fontWeight: 'bold', mb: 2 }}>
              Natural Language Response:
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              {executionResult.response}
            </Typography>
          </CardContent>
        </Card>
      )}

      {(queryResult || executionResult?.result) && (
        <Card sx={{ mb: 2 }}>
          <CardContent>
            {queryResult && (
              <>
                <Typography variant="subtitle1" sx={{ mb: 1 }}>Generated Cypher Query:</Typography>
                <SyntaxHighlighter 
                  language="cypher" 
                  style={syntaxTheme}
                  customStyle={{
                    backgroundColor: theme.palette.mode === 'dark' ? '#1e1e1e' : '#f5f5f5'
                  }}
                >
                  {queryResult}
                </SyntaxHighlighter>
              </>
            )}
            
            {executionResult?.result && (
              <>
                <Box sx={{ position: 'relative', mt: 3 }}>
                  <Typography variant="subtitle1">
                    Raw Query Output:
                  </Typography>
                  <Box sx={{ position: 'absolute', top: 0, right: 0 }}>
                    <IconButton 
                      size="small" 
                      onClick={() => handleCopy(JSON.stringify(executionResult.result, null, 2))}
                      title="Copy to clipboard"
                    >
                      <ContentCopyIcon />
                    </IconButton>
                    <IconButton 
                      size="small" 
                      onClick={() => setIsFullscreen(true)}
                      title="View fullscreen"
                    >
                      <FullscreenIcon />
                    </IconButton>
                  </Box>
                </Box>
                <Box sx={{ maxHeight: '400px', overflow: 'auto' }}>
                  <SyntaxHighlighter 
                    language="json" 
                    style={syntaxTheme}
                    customStyle={{
                      backgroundColor: theme.palette.mode === 'dark' ? '#1e1e1e' : '#f5f5f5'
                    }}
                  >
                    {JSON.stringify(executionResult.result, null, 2)}
                  </SyntaxHighlighter>
                </Box>
              </>
            )}
          </CardContent>
        </Card>
      )}

      <Dialog
        fullScreen
        open={isFullscreen}
        onClose={() => setIsFullscreen(false)}
      >
        <DialogContent sx={{ p: 3 }}>
          <Box sx={{ position: 'relative' }}>
            <IconButton 
              size="small" 
              onClick={() => handleCopy(JSON.stringify(executionResult?.result, null, 2))}
              sx={{ position: 'absolute', right: 48, top: 0 }}
              title="Copy to clipboard"
            >
              <ContentCopyIcon />
            </IconButton>
            <IconButton 
              size="small" 
              onClick={() => setIsFullscreen(false)}
              sx={{ position: 'absolute', right: 0, top: 0 }}
              title="Exit fullscreen"
            >
              <FullscreenIcon />
            </IconButton>
            <SyntaxHighlighter 
              language="json" 
              style={syntaxTheme}
              customStyle={{
                backgroundColor: theme.palette.mode === 'dark' ? '#1e1e1e' : '#f5f5f5',
                margin: '32px 0 0 0'
              }}
            >
              {JSON.stringify(executionResult?.result, null, 2)}
            </SyntaxHighlighter>
          </Box>
        </DialogContent>
      </Dialog>

      <Snackbar
        open={copySnackbar}
        autoHideDuration={2000}
        onClose={() => setCopySnackbar(false)}
        message="Copied to clipboard"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        sx={{
          '& .MuiSnackbarContent-root': {
            bgcolor: theme.palette.mode === 'dark' ? '#333' : '#fff',
            color: theme.palette.mode === 'dark' ? '#fff' : '#333',
            boxShadow: theme.shadows[3]
          }
        }}
      />

      {/* Log sections moved below */}
      {realtimeLogs && (
        <Card sx={{ mt: 2 }}>
          <CardContent>
            <Typography variant="h6">Verbose Output:</Typography>
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
    </Box>
  );
}

export default ResultsDisplay;