import React, { useState, useEffect } from 'react';
import { ThemeProvider, CssBaseline, Box, Container, Tabs, Tab, Grid2, Modal, Typography, Button, IconButton } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import { getTheme } from './theme';
import QueryInput from './components/QueryInput';
import ResultsDisplay from './components/ResultsDisplay';
import About from './components/About';
import VectorSearch from './components/VectorSearch';
import LatestQueries from './components/LatestQueries';
import axios from './services/api';

function App() {
  const [tabValue, setTabValue] = useState('query');
  const [queryResult, setQueryResult] = useState(null);
  const [executionResult, setExecutionResult] = useState(null);
  const [realtimeLogs, setRealtimeLogs] = useState('');
  const [showAboutModal, setShowAboutModal] = useState(false);
  const [latestQueries, setLatestQueries] = useState([]);
  const [selectedQuery, setSelectedQuery] = useState(null);
  const [provider, setProvider] = useState('');
  const [llmType, setLlmType] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [mode, setMode] = useState(() => {
    const savedMode = localStorage.getItem('theme-mode');
    if (savedMode) {
      return savedMode;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  const theme = React.useMemo(() => getTheme(mode), [mode]);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e) => {
      if (!localStorage.getItem('theme-mode')) {
        setMode(e.matches ? 'dark' : 'light');
      }
    };
    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
  }, []);

  useEffect(() => {
    axios.get('/csrf-token/', { withCredentials: true })
      .then((response) => {
        console.log('CSRF token set in cookies.');
        const csrfToken = response.data.csrf_token;
        document.cookie = `fastapi-csrf-token=${csrfToken}`;
        axios.defaults.headers['X-CSRF-Token'] = csrfToken;
      })
      .catch((error) => {
        console.error('Error fetching CSRF token:', error);
      });

    const navigationType = performance.getEntriesByType('navigation')[0].type;

    if ((navigationType === 'navigate' || navigationType === 'reload') && !localStorage.getItem('hasVisited')) {
      setShowAboutModal(true);
      localStorage.setItem('hasVisited', 'true');
    }
  }, []);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
    setQueryResult(null);
    setExecutionResult(null);
    setRealtimeLogs('');
  };

  const handleCloseModal = () => {
    setShowAboutModal(false);
  };

  const addLatestQuery = (queryDetails) => {
    if (latestQueries.length >= 5) {
      setLatestQueries([...latestQueries.slice(1), queryDetails]);
    } else {
      setLatestQueries([...latestQueries, queryDetails]);
    }
  }

  const handleSelectQuery = (query) => {
    setSelectedQuery(query);
  }

  const toggleColorMode = () => {
    const newMode = mode === 'light' ? 'dark' : 'light';
    setMode(newMode);
    localStorage.setItem('theme-mode', newMode);
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', backgroundColor: 'background.default', mt: { xs: 4, sm: 6, md: 10 }, mb: { xs: 4, sm: 6, md: 10 }, position: 'relative' }}>
        <IconButton
          onClick={toggleColorMode}
          sx={{
            position: 'absolute',
            right: 16,
            top: 16,
            color: 'text.primary'
          }}
        >
          {mode === 'dark' ? <Brightness7Icon /> : <Brightness4Icon />}
        </IconButton>
        <Container maxWidth="lg" sx={{ px: { xs: 2, sm: 3, md: 4 } }}>
          <Typography 
            variant="h2" 
            align="center" 
            gutterBottom 
            sx={{ 
              fontWeight: 'bold',
              fontSize: { xs: '1.75rem', sm: '2.5rem', md: '3.75rem' }
            }}
          >
            CROssBAR LLM Query Interface
          </Typography>
          <Tabs value={tabValue} onChange={handleTabChange} centered sx={{ mb: 2, '.MuiTab-root': { fontWeight: 'bold' } }}>
            <Tab label="LLM Query" value="query" />
            <Tab label="Vector Search" value="vectorSearch" />
            <Tab label="About" value="about" />
          </Tabs>
          {tabValue === 'query' && (
            <Grid2 
              container 
              spacing={2} 
              alignItems="flex-start"
              sx={{ 
                flexDirection: { xs: 'column', md: 'row' },
                justifyContent: 'center'
              }}
            >
              <Grid2 
                item 
                xs={12} 
                sx={{ 
                  maxWidth: { 
                    xs: '100%', 
                    sm: '90%', 
                    md: '1000px' 
                  },
                  mx: 'auto',
                  px: { xs: 1, sm: 2 }
                }}
              >
                <QueryInput
                  setQueryResult={setQueryResult}
                  setExecutionResult={setExecutionResult}
                  setRealtimeLogs={setRealtimeLogs}
                  addLatestQuery={addLatestQuery}
                  provider={provider}
                  setProvider={setProvider}
                  llmType={llmType}
                  setLlmType={setLlmType}
                  apiKey={apiKey}
                  setApiKey={setApiKey}
                />
                <ResultsDisplay
                  queryResult={queryResult}
                  executionResult={executionResult}
                  realtimeLogs={realtimeLogs}
                />
                <LatestQueries 
                  queries={latestQueries} 
                  onSelectQuery={handleSelectQuery}
                />
              </Grid2>
            </Grid2>
          )}
          {tabValue === 'vectorSearch' && 
            <Grid2 
              container 
              spacing={2} 
              alignItems="flex-start"
              sx={{ 
                flexDirection: { xs: 'column', md: 'row' },
                justifyContent: 'center'
              }}
            >
              <Grid2 
                item 
                xs={12} 
                sx={{ 
                  maxWidth: { 
                    xs: '100%', 
                    sm: '90%', 
                    md: '1000px' 
                  },
                  mx: 'auto',
                  px: { xs: 1, sm: 2 }
                }}
              >
                <VectorSearch
                  setQueryResult={setQueryResult}
                  setExecutionResult={setExecutionResult}
                  setRealtimeLogs={setRealtimeLogs}
                  addLatestQuery={addLatestQuery}
                  provider={provider}
                  setProvider={setProvider}
                  llmType={llmType}
                  setLlmType={setLlmType}
                  apiKey={apiKey}
                  setApiKey={setApiKey}
                />
                <ResultsDisplay
                  queryResult={queryResult}
                  executionResult={executionResult}
                  realtimeLogs={realtimeLogs}
                />
                <LatestQueries 
                  queries={latestQueries} 
                  onSelectQuery={handleSelectQuery}
                />
              </Grid2>
            </Grid2>
          }
          {tabValue === 'about' && <About />}
        </Container>
      </Box>
      <Modal
        open={showAboutModal}
        onClose={handleCloseModal}
        aria-describedby="about-modal-description"
      >
        <Box sx={{ 
          position: 'absolute', 
          top: '50%', 
          left: '50%', 
          transform: 'translate(-50%, -50%)', 
          width: '90%', 
          maxWidth: 600, 
          maxHeight: '90%', 
          bgcolor: 'background.paper', 
          boxShadow: 24, 
          p: 4, 
          overflow: 'auto',
          borderRadius: 2,
          position: 'relative'
        }}>
          <IconButton
            onClick={handleCloseModal}
            sx={{
              position: 'absolute',
              right: 8,
              top: 8,
              color: 'grey.500'
            }}
          >
            <CloseIcon />
          </IconButton>
          <About />
        </Box>
      </Modal>
    </ThemeProvider>
  );
}

export default App;