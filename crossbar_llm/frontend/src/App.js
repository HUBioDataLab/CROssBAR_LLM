import React, { useState, useEffect } from 'react';
import { ThemeProvider, CssBaseline, Box, Container, Tabs, Tab, Grid2, Modal, Typography, Button } from '@mui/material';
import theme from './theme';
import QueryInput from './components/QueryInput';
import ResultsDisplay from './components/ResultsDisplay';
import About from './components/About';
import DatabaseStats from './components/DatabaseStats';
import VectorUpload from './components/VectorUpload';
import VectorSearch from './components/VectorSearch';
import LatestQueries from './components/LatestQueries';

function App() {
  const [tabValue, setTabValue] = useState('query');
  const [queryResult, setQueryResult] = useState(null);
  const [executionResult, setExecutionResult] = useState(null);
  const [showAboutModal, setShowAboutModal] = useState(false);
  const [latestQueries, setLatestQueries] = useState([]);
  const [selectedQuery, setSelectedQuery] = useState(null);

  useEffect(() => {
    const navigationType = performance.getEntriesByType('navigation')[0].type;

    if ((navigationType === 'navigate' || navigationType === 'reload')) {
      setShowAboutModal(true);
      localStorage.setItem('hasVisited', 'true');
    }
  }, []);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
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

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', backgroundColor: 'background.default', mt: 4 }}>
        <Container maxWidth="lg">
          <Typography variant="h5" align="center" gutterBottom>
            CROssBAR LLM Query Interface
          </Typography>
          <Tabs value={tabValue} onChange={handleTabChange} centered sx={{ mb: 2 }}>
            <Tab label="LLM Query" value="query" />
            <Tab label="Vector Search" value="vectorSearch" />
            <Tab label="About" value="about" />
          </Tabs>
          {tabValue === 'query' && (
            <Grid2 container spacing={2}>
              <Grid2 item xs={12} md={8}>
                <QueryInput
                  setQueryResult={setQueryResult}
                  setExecutionResult={setExecutionResult}
                  addLatestQuery={addLatestQuery}
                />
                <ResultsDisplay
                  queryResult={queryResult}
                  executionResult={executionResult}
                />
                <LatestQueries 
                  queries={latestQueries} 
                  onSelectQuery={handleSelectQuery}
                />
              </Grid2>
              <Grid2 item xs={12} md={4}>
                <DatabaseStats />
              </Grid2>
            </Grid2>
          )}
          {tabValue === 'vectorSearch' && 
            <Grid2 container spacing={2}>
              <Grid2 item xs={12} md={8}>
                <VectorSearch
                  setQueryResult={setQueryResult}
                  setExecutionResult={setExecutionResult}
                  addLatestQuery={addLatestQuery}
                />
                <ResultsDisplay
                  queryResult={queryResult}
                  executionResult={executionResult}
                />
              </Grid2>
              <Grid2 item xs={12} md={4}>
                <DatabaseStats />
              </Grid2>
            </Grid2>
          }
          {tabValue === 'about' && <About />}
        </Container>
      </Box>
      <Modal
        open={showAboutModal}
        onClose={handleCloseModal}
        aria-labelledby="about-modal-title"
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
          overflow: 'auto' 
        }}>
          <Typography id="about-modal-title" variant="h6" component="h2">
            About This Site
          </Typography>
          <About />
          <Button onClick={handleCloseModal} sx={{ mt: 2 }}>Close</Button>
        </Box>
      </Modal>
    </ThemeProvider>
  );
}

export default App;