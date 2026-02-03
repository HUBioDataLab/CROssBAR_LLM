import React, { useState, useEffect, useCallback } from 'react';
import { 
  ThemeProvider, 
  CssBaseline, 
  Box, 
  Drawer,
  Fade,
  Paper,
  Typography,
  useMediaQuery,
} from '@mui/material';
import SecurityOutlinedIcon from '@mui/icons-material/SecurityOutlined';
import { getTheme } from './theme';
import About from './components/About';
import Home from './components/Home';
import { ChatLayout } from './components/chat';
import { AppHeader, AppSidebar } from './components/layout';
import { refreshCsrfToken } from './services/api';

function App() {
  const [tabValue, setTabValue] = useState('home');
  const [queryResult, setQueryResult] = useState(null);
  const [executionResult, setExecutionResult] = useState(null);
  const [realtimeLogs, setRealtimeLogs] = useState('');
  const [showAboutModal, setShowAboutModal] = useState(false);
  const [question, setQuestion] = useState('');
  const [provider, setProvider] = useState('');
  const [llmType, setLlmType] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [clientIP, setClientIP] = useState('');
  
  // Conversation memory state
  const [sessionId, setSessionId] = useState(() => {
    let id = sessionStorage.getItem('conversationSessionId');
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem('conversationSessionId', id);
    }
    return id;
  });
  const [conversationHistory, setConversationHistory] = useState([]);
  const [pendingFollowUp, setPendingFollowUp] = useState(null);
  
  const [mode, setMode] = useState(() => {
    const savedMode = localStorage.getItem('theme-mode');
    if (savedMode) {
      return savedMode;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  const theme = React.useMemo(() => getTheme(mode), [mode]);
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  // Update drawer visibility based on screen size
  useEffect(() => {
    setDrawerVisible(!isMobile);
  }, [isMobile]);

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
    refreshCsrfToken();

    const tokenRefreshInterval = setInterval(() => {
      console.log('Refreshing CSRF token periodically');
      refreshCsrfToken();
    }, 15 * 60 * 1000);

    const navigationType = performance.getEntriesByType('navigation')[0].type;

    if ((navigationType === 'navigate' || navigationType === 'reload') && !localStorage.getItem('hasVisited')) {
      setShowAboutModal(true);
      localStorage.setItem('hasVisited', 'true');
    }
    
    setTabValue('home');
    
    const prefillQuery = localStorage.getItem('prefillQuery');
    if (prefillQuery) {
      setQuestion(prefillQuery);
      localStorage.removeItem('prefillQuery');
    }
    
    return () => {
      clearInterval(tokenRefreshInterval);
    };
  }, []);

  // Fetch client IP on app startup
  useEffect(() => {
    const fetchClientIP = async () => {
      const storedIP = sessionStorage.getItem('client_ip');
      if (storedIP) {
        setClientIP(storedIP);
        return;
      }

      try {
        const response = await fetch('https://api.ipify.org?format=json');
        if (response.ok) {
          const data = await response.json();
          if (data.ip) {
            setClientIP(data.ip);
            sessionStorage.setItem('client_ip', data.ip);
          }
        }
      } catch (error) {
        console.error('Error fetching client IP:', error);
      }
    };

    fetchClientIP();
  }, []);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
    setQueryResult(null);
    setExecutionResult(null);
    setRealtimeLogs('');
    setDrawerOpen(false);
    setQuestion('');
    
    if (newValue === 'query') {
      const prefillQuery = localStorage.getItem('prefillQuery');
      if (prefillQuery) {
        setQuestion(prefillQuery);
        localStorage.removeItem('prefillQuery');
      }
    }
  };

  const handleCloseModal = () => {
    setShowAboutModal(false);
  };

  const toggleColorMode = () => {
    const newMode = mode === 'light' ? 'dark' : 'light';
    setMode(newMode);
    localStorage.setItem('theme-mode', newMode);
  };

  const toggleDrawerVisibility = () => {
    setDrawerVisible(!drawerVisible);
  };

  // Add a new turn to conversation history
  const addConversationTurn = useCallback((turn) => {
    setConversationHistory(prev => {
      const newHistory = [...prev, {
        ...turn,
        timestamp: new Date().toISOString()
      }];
      if (newHistory.length > 10) {
        return newHistory.slice(-10);
      }
      return newHistory;
    });
  }, []);

  // Start a new conversation
  const startNewConversation = useCallback(() => {
    const newSessionId = crypto.randomUUID();
    sessionStorage.setItem('conversationSessionId', newSessionId);
    setSessionId(newSessionId);
    setConversationHistory([]);
    setQueryResult(null);
    setExecutionResult(null);
    setQuestion('');
    console.log('Started new conversation with session:', newSessionId.substring(0, 8) + '...');
  }, []);

  const renderTabContent = () => {
    switch(tabValue) {
      case 'home':
        return (
          <Fade in={true} timeout={500}>
            <Box>
              <Home handleTabChange={handleTabChange} />
            </Box>
          </Fade>
        );
      case 'query':
        return (
          <ChatLayout
            provider={provider}
            setProvider={setProvider}
            llmType={llmType}
            setLlmType={setLlmType}
            apiKey={apiKey}
            setApiKey={setApiKey}
            sessionId={sessionId}
            conversationHistory={conversationHistory}
            addConversationTurn={addConversationTurn}
            startNewConversation={startNewConversation}
            question={question}
            setQuestion={setQuestion}
            queryResult={queryResult}
            setQueryResult={setQueryResult}
            executionResult={executionResult}
            setExecutionResult={setExecutionResult}
            realtimeLogs={realtimeLogs}
            setRealtimeLogs={setRealtimeLogs}
            pendingFollowUp={pendingFollowUp}
            setPendingFollowUp={setPendingFollowUp}
          />
        );
      case 'about':
        return (
          <Fade in={true} timeout={500}>
            <Box>
              <About />
            </Box>
          </Fade>
        );
      default:
        return null;
    }
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ 
        display: 'flex', 
        minHeight: '100vh',
        background: theme => theme.palette.mode === 'dark' 
          ? 'linear-gradient(135deg, #1c1c1e 0%, #2c2c2e 100%)' 
          : 'linear-gradient(135deg, #f5f5f7 0%, #ffffff 100%)'
      }}>
        <AppHeader
          mode={mode}
          onThemeToggle={toggleColorMode}
          drawerVisible={drawerVisible}
          onDrawerToggle={toggleDrawerVisibility}
          onLogoClick={() => handleTabChange(null, 'home')}
        />
        
        {drawerVisible && (
          <Drawer
            variant="permanent"
            open={true}
            sx={{
              width: 280,
              flexShrink: 0,
              [`& .MuiDrawer-paper`]: { 
                width: 280,
                boxSizing: 'border-box',
                border: 'none',
                background: theme => theme.palette.mode === 'dark' 
                  ? 'rgba(28, 28, 30, 0.8)' 
                  : 'rgba(255, 255, 255, 0.8)',
                backdropFilter: 'blur(10px)',
              }
            }}
          >
            <AppSidebar
              mode={mode}
              tabValue={tabValue}
              onTabChange={handleTabChange}
            />
          </Drawer>
        )}
        
        {tabValue === 'query' ? (
          <Box
            component="main"
            sx={{
              flexGrow: 1,
              width: { xs: '100%', md: drawerVisible ? `calc(100% - 280px)` : '100%' },
              display: 'flex',
              flexDirection: 'column',
              transition: 'all 0.3s ease-in-out',
              overflow: 'hidden',
            }}
          >
            {renderTabContent()}
            {showAboutModal && <About onClose={handleCloseModal} />}
          </Box>
        ) : (
          <Box
            component="main"
            sx={{
              flexGrow: 1,
              p: 3,
              width: { xs: '100%', md: drawerVisible ? `calc(100% - 280px)` : '100%' },
              mt: 6,
              mb: 4,
              maxWidth: drawerVisible ? '1200px' : '1480px',
              mx: 'auto',
              display: 'flex',
              flexDirection: 'column',
              transition: 'all 0.3s ease-in-out'
            }}
          >
            <Box sx={{ flexGrow: 1 }}>
              {renderTabContent()}
              
              {showAboutModal && (
                <About onClose={handleCloseModal} />
              )}
            </Box>
            
            {/* Privacy Banner */}
            <Paper 
              elevation={0}
              sx={{ 
                mt: 4,
                p: 2,
                backgroundColor: theme => theme.palette.mode === 'dark' 
                  ? 'rgba(100, 181, 246, 0.08)' 
                  : 'rgba(0, 113, 227, 0.04)',
                borderRadius: '12px',
                border: theme => `1px solid ${theme.palette.mode === 'dark' 
                  ? 'rgba(100, 181, 246, 0.2)' 
                  : 'rgba(0, 113, 227, 0.1)'}`,
                display: 'flex',
                alignItems: 'flex-start',
                gap: 1.5
              }}
            >
              <SecurityOutlinedIcon 
                sx={{ 
                  fontSize: 20, 
                  color: theme => theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3',
                  mt: 0.25,
                  flexShrink: 0
                }} 
              />
              <Typography 
                variant="caption" 
                sx={{ 
                  color: 'text.secondary',
                  lineHeight: 1.6,
                  fontFamily: "'Poppins', 'Roboto', sans-serif"
                }}
              >
                We save user queries and outputs, but remove all identifiable data once the session is finished. 
                Data is never used for model training. Data is stored on the CROssBAR v2 server. 
                We may analyze data globally to improve the user experience.
              </Typography>
            </Paper>

            <Box sx={{ 
              mt: 2,
              pt: 2, 
              borderTop: theme => `1px solid ${theme.palette.divider}`,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                © {new Date().getFullYear()} CROssBAR
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                <a href="https://www.flaticon.com/free-icons/chatbot" title="chatbot icons" style={{ color: 'inherit', textDecoration: 'none' }}>
                  Chatbot icons created by rukanicon - Flaticon
                </a>
              </Typography>
            </Box>
          </Box>
        )}
      </Box>
    </ThemeProvider>
  );
}

export default App;
